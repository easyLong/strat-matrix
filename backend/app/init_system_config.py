"""Create the config table, import legacy .env values, then optionally prune files."""

import argparse
from pathlib import Path
import re
import tempfile

from dotenv import dotenv_values, set_key
import pymysql

from .db import ROOT, connection
from .system_config_catalog import CATALOG, MYSQL_KEYS, Setting, validate_value


def schema_statement() -> str:
    source = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
    found = re.search(r"CREATE TABLE IF NOT EXISTS godp_system_config \([\s\S]+?\) ENGINE=[^;]+;", source)
    if not found:
        raise RuntimeError("系统配置建表语句不存在")
    return found.group(0)


def imported_values(paths: list[Path]) -> dict[str, str]:
    result = {}
    for path in paths:
        for key, value in dotenv_values(path).items():
            if key not in MYSQL_KEYS and value is not None:
                if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,99}", key):
                    raise ValueError("存在不合法的历史配置键，请先检查文件")
                result[key] = value
    return result


def seed_config(cursor, imported: dict[str, str] | None = None) -> int:
    values = {key: spec.default for key, spec in CATALOG.items()}
    values.update(imported or {})
    for key, value in values.items():
        validate_value(key, value)
    inserted = 0
    for key, value in values.items():
        spec = CATALOG.get(key) or Setting("custom", "历史迁移配置项", secret=bool(
            re.search(r"KEY|TOKEN|SECRET|PASSWORD", key)))
        cursor.execute(
            "INSERT INTO godp_system_config "
            "(config_key,config_group,config_name,config_value,value_type,is_secret,create_by,update_by) "
            "VALUES (%s,%s,%s,%s,%s,%s,'config-migration','config-migration') "
            "ON DUPLICATE KEY UPDATE config_key=VALUES(config_key)",
            (key, spec.group, spec.name, value, spec.kind, int(spec.secret)),
        )
        inserted += int(cursor.rowcount == 1)
    return inserted


def clean_env_file(path: Path):
    """Atomically rewrite only MySQL entries, preserving quoting and password characters."""
    if not path.exists():
        return
    values = dotenv_values(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", prefix=".tmp-db-env-", dir=path.parent,
                                         delete=False, encoding="utf-8") as stream:
            temporary = Path(stream.name)
            stream.write("# MySQL connection only; application settings are in godp_system_config.\n")
        for key in MYSQL_KEYS:
            if key in values and values[key] is not None:
                set_key(temporary, key, values[key], quote_mode="always")
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def initialize(*, migrate_env=False, clean_env=False) -> dict:
    if clean_env and not migrate_env:
        raise ValueError("清理配置文件必须同时迁移原配置")
    paths = [ROOT / "docs" / ".env", ROOT / ".env"]
    imported = imported_values(paths) if migrate_env else {}
    with connection() as db, db.cursor() as cursor:
        cursor.execute(schema_statement())
        inserted = seed_config(cursor, imported)
        if clean_env:
            cursor.execute("SELECT config_key,config_value FROM godp_system_config WHERE del_flag='N'")
            saved = {row["config_key"]: row["config_value"] for row in cursor.fetchall()}
            if any(saved.get(key) != value for key, value in imported.items()):
                raise ValueError("数据库配置与文件存在差异，已保留原文件；请先核对配置键")
        db.commit()
    # Prune only after the real DB commit and successful value-by-value verification.
    if clean_env:
        for path in paths:
            clean_env_file(path)
    return {"inserted": inserted, "imported_keys": len(imported), "env_cleaned": clean_env}


def main():
    parser = argparse.ArgumentParser(description="创建 MySQL 系统配置表并安全迁移历史配置")
    parser.add_argument("--migrate-env", action="store_true")
    parser.add_argument("--clean-env", action="store_true")
    args = parser.parse_args()
    try:
        result = initialize(migrate_env=args.migrate_env, clean_env=args.clean_env)
        print(f"系统配置已初始化：新增 {result['inserted']} 项，导入 {result['imported_keys']} 项，"
              f"配置文件已清理：{result['env_cleaned']}")
        return 0
    except (ValueError, RuntimeError):
        print("系统配置迁移失败，原文件已保留；请检查配置键、类型及数据库现有值")
        return 2
    except pymysql.MySQLError:
        print("系统配置迁移失败，请检查 MySQL 权限及表结构；原文件已保留")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
