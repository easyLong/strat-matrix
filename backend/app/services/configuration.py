"""Shared configuration use cases; no HTTP routing."""
import pymysql
from ..core.actor import current_actor
from ..db import connection
from ..models import ConfigResponse, StrategyConfig
from .errors import ApplicationError, database_error


def get_config() -> ConfigResponse:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT config_json, version, update_time, create_by, update_by FROM godp_strategy_config "
                "WHERE config_key=%s AND del_flag='N' LIMIT 1",
                ("operations",),
            )
            row = cursor.fetchone()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    if row is None:
        return ConfigResponse(version=0, updated_at=None, config=StrategyConfig(), is_demo=False)
    return ConfigResponse(
        version=row["version"],
        updated_at=row["update_time"],
        config=StrategyConfig.model_validate_json(row["config_json"]),
        is_demo=row["create_by"] == "demo-seed" and row["update_by"] == "demo-seed",
    )

def put_config(config: StrategyConfig,
               expected_version: int | None = None) -> ConfigResponse:
    operator = current_actor()
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT version FROM godp_strategy_config WHERE config_key='operations' FOR UPDATE"
            )
            previous = cursor.fetchone()
            current_version = previous["version"] if previous else 0
            if expected_version is not None and expected_version != current_version:
                raise ApplicationError(status_code=409, detail="配置已被其他操作更新，请刷新后重试")
            version = current_version + 1
            if previous:
                cursor.execute(
                    "UPDATE godp_strategy_config SET config_json=%s, version=%s, "
                    "update_by=%s, del_flag='N' WHERE config_key='operations'",
                    (config.model_dump_json(), version, operator),
                )
            else:
                cursor.execute(
                    "INSERT INTO godp_strategy_config "
                    "(config_key, config_json, version, create_by, update_by) "
                    "VALUES ('operations', %s, 1, %s, %s)",
                    (config.model_dump_json(), operator, operator),
                )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, create_by, update_by) "
                "VALUES ('operations', %s, %s, '保存', %s, %s)",
                (version, config.model_dump_json(), operator, operator),
            )
            cursor.execute(
                "SELECT version, update_time FROM godp_strategy_config WHERE config_key=%s",
                ("operations",),
            )
            row = cursor.fetchone()
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return ConfigResponse(version=row["version"], updated_at=row["update_time"], config=config, is_demo=False)

def list_config_versions(limit: int = 30) -> list[dict]:
    limit = max(1, min(limit, 100))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT version, action, source_version, create_time AS created_at, "
                "create_by AS created_by, config_json FROM godp_strategy_config_version "
                "WHERE config_key='operations' AND del_flag='N' ORDER BY version DESC LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    for row in rows:
        row["config"] = StrategyConfig.model_validate_json(row.pop("config_json"))
    return rows

def restore_config(version: int,
                   expected_version: int | None = None) -> ConfigResponse:
    operator = current_actor()
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT config_json FROM godp_strategy_config_version "
                "WHERE config_key='operations' AND version=%s AND del_flag='N'",
                (version,),
            )
            source = cursor.fetchone()
            if not source:
                raise ApplicationError(status_code=404, detail="配置快照不存在")
            cursor.execute(
                "SELECT version FROM godp_strategy_config WHERE config_key='operations' FOR UPDATE"
            )
            current = cursor.fetchone()
            if not current:
                raise ApplicationError(status_code=409, detail="当前配置不存在")
            if expected_version is not None and expected_version != current["version"]:
                raise ApplicationError(status_code=409, detail="配置已被其他操作更新，请刷新后重试")
            next_version = current["version"] + 1
            config = StrategyConfig.model_validate_json(source["config_json"])
            cursor.execute(
                "UPDATE godp_strategy_config SET config_json=%s, version=%s, "
                "update_by=%s WHERE config_key='operations'",
                (source["config_json"], next_version, operator),
            )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, source_version, create_by, update_by) "
                "VALUES ('operations', %s, %s, '恢复', %s, %s, %s)",
                (next_version, source["config_json"], version, operator, operator),
            )
            cursor.execute(
                "SELECT update_time FROM godp_strategy_config WHERE config_key='operations'"
            )
            updated_at = cursor.fetchone()["update_time"]
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return ConfigResponse(version=next_version, updated_at=updated_at, config=config, is_demo=False)

def config_module_fields(module: str) -> tuple[str, ...]:
    fields = CONFIG_MODULE_FIELDS.get(module)
    if fields is None:
        raise ApplicationError(status_code=404, detail="配置模块不存在")
    return fields

def list_module_versions(module: str, limit: int = 30) -> list[dict]:
    config_module_fields(module)
    limit = max(1, min(limit, 100))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT version, action, source_version, create_time AS created_at, "
                "create_by AS created_by, config_json FROM godp_strategy_config_version "
                "WHERE config_key=%s AND del_flag='N' ORDER BY version DESC LIMIT %s",
                (module, limit),
            )
            rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    for row in rows:
        row["config"] = StrategyConfig.model_validate_json(row.pop("config_json"))
    return rows

def change_module(module: str, expected_version: int | None,
                  incoming: StrategyConfig | None = None,
                  source_version: int | None = None,
                  operator: str = "system") -> ConfigResponse:
    fields = config_module_fields(module)
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT config_json, version FROM godp_strategy_config "
                "WHERE config_key='operations' FOR UPDATE"
            )
            current = cursor.fetchone()
            aggregate_version = current["version"] if current else 0
            if expected_version is not None and expected_version != aggregate_version:
                raise ApplicationError(status_code=409, detail="配置已被其他操作更新，请刷新后重试")
            base = StrategyConfig.model_validate_json(current["config_json"]) if current else StrategyConfig()
            cursor.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM godp_strategy_config_version "
                "WHERE config_key=%s", (module,),
            )
            module_version = cursor.fetchone()["version"] + 1
            if source_version is not None:
                cursor.execute(
                    "SELECT config_json FROM godp_strategy_config_version "
                    "WHERE config_key=%s AND version=%s AND del_flag='N'",
                    (module, source_version),
                )
                source = cursor.fetchone()
                if source is None:
                    raise ApplicationError(status_code=404, detail="模块配置快照不存在")
                incoming = StrategyConfig.model_validate_json(source["config_json"])
            assert incoming is not None
            values = base.model_dump()
            for field in fields:
                values[field] = getattr(incoming, field)
            merged = StrategyConfig.model_validate(values)
            snapshot = merged.model_dump_json()
            if current:
                cursor.execute(
                    "UPDATE godp_strategy_config SET config_json=%s, version=%s, "
                    "update_by=%s, del_flag='N' WHERE config_key='operations'",
                    (snapshot, aggregate_version + 1, operator),
                )
            else:
                cursor.execute(
                    "INSERT INTO godp_strategy_config "
                    "(config_key, config_json, version, create_by, update_by) "
                    "VALUES ('operations', %s, 1, %s, %s)", (snapshot, operator, operator),
                )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, source_version, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (module, module_version, snapshot,
                 '恢复' if source_version is not None else '保存', source_version,
                 operator, operator),
            )
            cursor.execute(
                "SELECT update_time FROM godp_strategy_config WHERE config_key='operations'"
            )
            updated_at = cursor.fetchone()["update_time"]
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return ConfigResponse(version=aggregate_version + 1, updated_at=updated_at,
                          config=merged, is_demo=False)

def put_config_module(module: str, config: StrategyConfig,
                      expected_version: int | None = None) -> ConfigResponse:
    return change_module(module, expected_version, incoming=config,
                         operator=current_actor())

def restore_config_module(module: str, version: int,
                          expected_version: int | None = None) -> ConfigResponse:
    return change_module(module, expected_version, source_version=version,
                         operator=current_actor())
