"""Planning workspace API for the four operations tabs."""

from datetime import date, datetime, timedelta, timezone
import json
import os
import secrets
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pymysql

from .db import check_database, connection
from .account_metrics import account_metrics, months_ago
from .account_profile import interaction_snapshot
from .integration import queue_event, queue_manual_slot, router as integration_router
from .topic_vector_api import router as topic_vector_router
from .account_vector_api import router as account_vector_router
from .matching_readiness_api import router as matching_readiness_router
from .ai_preparation_api import router as ai_preparation_router
from .matching_execution_api import router as matching_execution_router
from .ordinary_planning import PlanningError, lifecycle_stage, load_accounts
from .manual_availability import ensure_manual_accounts_available, planned_manual_accounts
from .planning_progress import COMPLETED_ACCOUNT_COUNT_SQL, PRODUCTION_STATUS_SQL, planning_status_label, production_status
from .models import (
    AccountOption,
    AccountPlanRecord,
    AutoCycleSummary,
    AutoFailure,
    BatchDetail,
    BatchSummary,
    ConfigResponse,
    ConfigVersionSummary,
    ManualPlanCreate,
    ManualItem,
    ManualAccountAvailability,
    ManualPreviewInput,
    ManualPreviewResponse,
    ManualTaskSummary,
    PlanningAccountSummary,
    PlanningCycleSummary,
    ReplaceTopicInput,
    ReplaceTopicResponse,
    AdjustmentRecord,
    StrategyConfig,
    TopicOption,
)


app = FastAPI(title="多账号智能策划 API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{os.getenv('FRONTEND_PORT', '930')}",
        f"http://127.0.0.1:{os.getenv('FRONTEND_PORT', '930')}",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)
app.include_router(integration_router)
app.include_router(topic_vector_router)
app.include_router(account_vector_router)
app.include_router(matching_readiness_router)
app.include_router(ai_preparation_router)
app.include_router(matching_execution_router)


@app.middleware("http")
async def integration_auth_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)
    # Integration and worker APIs use their separate machine-to-machine token.
    if path.startswith("/api/integrations/") or path.startswith("/api/internal/"):
        expected = os.getenv("INTEGRATION_TOKEN", "")
        supplied = request.headers.get("x-integration-token", "")
        if not expected:
            return JSONResponse(status_code=503, content={"detail": "系统接口令牌尚未配置"})
        if not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
            return JSONResponse(status_code=401, content={"detail": "系统接口认证失败"})
        return await call_next(request)

    return await call_next(request)


def infer_content_role(row: dict, topic: dict) -> str:
    """Use the topic/slot business role for local demo data."""
    if topic.get('business_role'):
        return str(topic['business_role'])
    if row.get('slot_type') == 'marketing_priority' or topic.get('is_marketing'):
        return '转化'
    return '流量'


def database_error() -> HTTPException:
    # Do not include host, account, SQL, or password details in API responses.
    return HTTPException(status_code=503, detail="数据库暂不可用，请检查连接、库权限和建表状态")


def replacement_block_reason(row: dict, plan_type: str | None = None) -> str:
    if plan_type not in ("auto", "manual"):
        return "当前策划类型不支持替换"
    if not row.get("topic_id"):
        return "热点空槽待确定选题"
    if not row.get("slot_id") or row.get("version") is None:
        return "状态暂无法确认，不允许替换"
    if "slot_topic_id" in row and row["slot_topic_id"] != row["topic_id"]:
        return "当前结果与槽位状态不一致，请刷新后重试"
    if (row.get("published_at") is not None or row.get("status") == "已发布"
            or row.get("production_status") in ("published", "已发布")):
        return "内容已发布，当前结果不可替换"
    return ""


def enrich_plan_item(row: dict, plan_type: str | None = None) -> dict:
    source_payload = row.pop("topic_payload", None)
    source = {}
    if source_payload and row.get("topic_type") not in ("营销", "热点"):
        try:
            source = json.loads(source_payload)
            if not isinstance(source, dict):
                source = {}
        except (TypeError, json.JSONDecodeError):
            source = {}
    row["content_type"] = row.get("content_type") or source.get("content_type", "")
    row["outline"] = row.get("outline") or source.get("outline", "") or source.get("summary", "")
    if not row.get("topic_type") and row.get("topic_id"):
        row["topic_type"] = (
            "热点" if row.get("slot_type") == "hotspot" else
            "营销" if row.get("slot_type") == "marketing_priority" or
            source.get("is_marketing") or row.get("source_is_marketing") else "普通"
        )
    row["content_role"] = row.get("content_role") or infer_content_role(row, source if source_payload else {})
    row["production_status"] = production_status(row)
    published_at = row.get("published_at")
    block_reason = replacement_block_reason(row, plan_type)
    allow = not block_reason
    publish_status = ("待确定选题" if not row.get("topic_id") else
                      "已发布" if (published_at or row.get("status") == "已发布"
                                   or row.get("production_status") in ("published", "已发布"))
                      else "未发布")
    row["publish_status"] = publish_status
    row["allow_replace"] = allow
    row["replace_block_reason"] = block_reason
    row["result_version"] = row.get("version")
    row.pop("published_at", None)
    row.pop("version", None)
    return row


@app.get("/api/health")
def health() -> dict:
    return {"service": "ok", "database": "ok" if check_database() else "unavailable"}


@app.get("/api/config", response_model=ConfigResponse)
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


@app.put("/api/config", response_model=ConfigResponse)
def put_config(config: StrategyConfig,
               expected_version: int | None = None) -> ConfigResponse:
    operator = "运营人员"
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT version FROM godp_strategy_config WHERE config_key='operations' FOR UPDATE"
            )
            previous = cursor.fetchone()
            current_version = previous["version"] if previous else 0
            if expected_version is not None and expected_version != current_version:
                raise HTTPException(status_code=409, detail="配置已被其他操作更新，请刷新后重试")
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


@app.get("/api/config/versions", response_model=list[ConfigVersionSummary])
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


@app.post("/api/config/versions/{version}/restore", response_model=ConfigResponse)
def restore_config(version: int,
                   expected_version: int | None = None) -> ConfigResponse:
    operator = "运营人员"
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT config_json FROM godp_strategy_config_version "
                "WHERE config_key='operations' AND version=%s AND del_flag='N'",
                (version,),
            )
            source = cursor.fetchone()
            if not source:
                raise HTTPException(status_code=404, detail="配置快照不存在")
            cursor.execute(
                "SELECT version FROM godp_strategy_config WHERE config_key='operations' FOR UPDATE"
            )
            current = cursor.fetchone()
            if not current:
                raise HTTPException(status_code=409, detail="当前配置不存在")
            if expected_version is not None and expected_version != current["version"]:
                raise HTTPException(status_code=409, detail="配置已被其他操作更新，请刷新后重试")
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


CONFIG_MODULE_FIELDS = {
    "marketing": ("marketing_max", "planning_days", "schedule_day", "schedule_time", "hotspot_ratio"),
    "strategy": ("rolling_posts", "stage_targets", "lifecycle_rules"),
}


def config_module_fields(module: str) -> tuple[str, ...]:
    fields = CONFIG_MODULE_FIELDS.get(module)
    if fields is None:
        raise HTTPException(status_code=404, detail="配置模块不存在")
    return fields


@app.get("/api/config/modules/{module}/versions", response_model=list[ConfigVersionSummary])
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
                raise HTTPException(status_code=409, detail="配置已被其他操作更新，请刷新后重试")
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
                    raise HTTPException(status_code=404, detail="模块配置快照不存在")
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


@app.put("/api/config/modules/{module}", response_model=ConfigResponse)
def put_config_module(module: str, config: StrategyConfig,
                      expected_version: int | None = None) -> ConfigResponse:
    return change_module(module, expected_version, incoming=config,
                         operator="运营人员")


@app.post("/api/config/modules/{module}/versions/{version}/restore",
          response_model=ConfigResponse)
def restore_config_module(module: str, version: int,
                          expected_version: int | None = None) -> ConfigResponse:
    return change_module(module, expected_version, source_version=version,
                         operator="运营人员")


@app.get("/api/accounts", response_model=list[AccountOption])
def list_accounts(limit: int = 200, include_disabled: bool = False) -> list[dict]:
    limit = max(1, min(limit, 1000))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT config_json FROM godp_strategy_config "
                "WHERE config_key='operations' AND del_flag='N'"
            )
            config_row = cursor.fetchone()
            config = StrategyConfig.model_validate_json(config_row["config_json"]) if config_row else StrategyConfig()
            account_scope = "" if include_disabled else "AND a.status=%s AND (s.id IS NULL OR s.active_in_snapshot=1) "
            account_params = (limit,) if include_disabled else ("\u542f\u7528", limit)
            cursor.execute(
                "SELECT a.account_code AS account_id, a.account_name, a.city, a.persona, "
                "a.marketing_eligible, a.status, s.payload_json "
                "FROM godp_account a LEFT JOIN godp_account_source s "
                "ON s.account_id=a.account_code AND s.del_flag='N' "
                "WHERE a.del_flag='N' " + account_scope + "ORDER BY a.id LIMIT %s",
                account_params,
            )
            rows = cursor.fetchall()
            metrics_at = datetime.now(timezone.utc)
            sources: dict[str, dict] = {}
            legacy_ids: list[str] = []
            for row in rows:
                source = json.loads(row["payload_json"]) if row["payload_json"] else {}
                if not isinstance(source, dict):
                    source = {}
                sources[row["account_id"]] = source
                if source.get("interaction_data") is None:
                    legacy_ids.append(row["account_id"])
            legacy_posts: dict[str, list[dict]] = {}
            if legacy_ids:
                cursor.execute(
                    "SELECT account_id, published_at, payload_json FROM godp_content_history "
                    "WHERE del_flag='N' AND published_at IS NOT NULL AND published_at>=%s AND published_at<=%s "
                    "AND account_id IN (" + ",".join(["%s"] * len(legacy_ids)) + ") "
                    "ORDER BY account_id, published_at DESC, id DESC",
                    (months_ago(metrics_at, 3).replace(tzinfo=None),
                     metrics_at.replace(tzinfo=None), *legacy_ids),
                )
                for history in cursor.fetchall():
                    post = json.loads(history["payload_json"]) if history["payload_json"] else {}
                    if not isinstance(post, dict):
                        post = {}
                    post["published_at"] = history["published_at"].isoformat()
                    legacy_posts.setdefault(history["account_id"], []).append(post)
            for row in rows:
                source = sources[row["account_id"]]
                row.pop("payload_json", None)
                row["account_alias"] = source.get("account_alias") or ""
                row["um_no"] = source.get("um_no") or ""
                row["organization"] = source.get("organization") or ""
                row["platform"] = source.get("platform") or ""
                row["business_line"] = source.get("business_line") or ""
                certified = source.get("certification_status")
                row["certified"] = bool(certified if certified is not None else source["certified"]) \
                    if certified is not None or "certified" in source else None
                row["account_type"] = source.get("account_type") or (
                    "认证" if row["certified"] is True else "非认证" if row["certified"] is False else ""
                )
                followers = source.get("follower_count")
                row["followers"] = int(followers if followers is not None else source["followers"]) \
                    if followers is not None or "followers" in source else None
                interaction_data = source.get("interaction_data")
                if interaction_data is None:
                    interaction_data = legacy_posts.get(row["account_id"], [])
                snapshot = interaction_snapshot(interaction_data, metrics_at)
                metrics = account_metrics(snapshot, config.rolling_posts, metrics_at)
                row["traffic_trend"] = metrics["traffic_trend"]
                row["lifecycle_stage"] = lifecycle_stage(config, {
                    **metrics,
                    "followers_count": row["followers"] or 0,
                })
            return rows
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/topics", response_model=list[TopicOption])
def list_topics(limit: int = 200) -> list[dict]:
    limit = max(1, min(limit, 1000))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT t.topic_code AS topic_id, t.title AS topic_title, t.category, "
                "t.is_marketing, t.status, s.valid_from, s.valid_to, s.payload_json FROM godp_topic t "
                "LEFT JOIN godp_topic_source s ON s.topic_id=t.topic_code "
                "WHERE t.del_flag='N' AND t.status='可用' "
                "AND (s.id IS NULL OR (s.active_in_snapshot=1 "
                "AND (t.is_marketing=0 OR s.approval_status='approved') "
                "AND (s.valid_from IS NULL OR s.valid_from<=UTC_TIMESTAMP(6)) "
                "AND (s.valid_to IS NULL OR s.valid_to>=UTC_TIMESTAMP(6)))) "
                "ORDER BY t.id LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
            for row in rows:
                source = json.loads(row.pop("payload_json")) if row["payload_json"] else {}
                row["content_type"] = source.get("content_type", "")
                row["outline"] = source.get("outline", "")
                def dimension_text(*keys: str) -> str:
                    for key in keys:
                        value = source.get(key)
                        if isinstance(value, list):
                            value = "、".join(str(part).strip() for part in value if str(part).strip())
                        if value is not None and str(value).strip():
                            return str(value).strip()
                    return ""

                row["account_type"] = dimension_text("account_type", "applicable_account_type", "account_types")
                row["related_product"] = dimension_text("related_product", "product_name", "product_or_activity")
                row["related_activity"] = dimension_text("related_activity", "activity_name")
                row["related_hotspot"] = dimension_text(
                    "related_hotspot", "applicable_hotspot", "local_hotspot", "hotspot_title",
                )
                valid_from = row.get("valid_from") or source.get("valid_from")
                valid_to = row.get("valid_to") or source.get("valid_to")
                row["valid_from"] = str(valid_from)[:16] if valid_from else None
                row["valid_to"] = str(valid_to)[:16] if valid_to else None
                row["topic_type"] = {"hotspot": "热点", "marketing": "营销", "normal": "普通", "ordinary": "普通", "非营销": "普通", "普通": "普通", "营销": "营销", "热点": "热点"}.get(
                    source.get("topic_type"), "营销" if row["is_marketing"] else "普通")
                row["_catalog_topic"] = True
                row["topic_payload"] = source
            attach_topic_labels(cursor, rows)
            for row in rows:
                row.pop("topic_payload", None)
                row.pop("_catalog_topic", None)
            return rows
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


def attach_topic_labels(cursor, rows: list[dict]) -> None:
    """Expose saved label facts without classifying legacy topics or mixing source namespaces."""
    ordinary = [row["topic_id"] for row in rows if row.get("topic_type") == "普通" or row.get("_catalog_topic")]
    saved = {}
    if ordinary:
        placeholders = ",".join(["%s"] * len(ordinary))
        cursor.execute(
            "SELECT topic_id, tags_json, label_status, version, taxonomy_version "
            f"FROM godp_topic_tag WHERE topic_id IN ({placeholders}) AND del_flag='N'", ordinary,
        )
        saved = {row["topic_id"]: row for row in cursor.fetchall()}
    for row in rows:
        payload = row.get("topic_payload") or {}
        record = saved.get(row["topic_id"]) if row.get("topic_type") == "普通" or row.get("_catalog_topic") else None
        try:
            labels = json.loads(record["tags_json"]) if record and record.get("tags_json") else payload.get("labels", payload.get("tags", {}))
        except (TypeError, json.JSONDecodeError):
            labels = {}
        row["labels"] = labels if isinstance(labels, dict) else {}
        row["label_status"] = record["label_status"] if record else payload.get("label_status")
        row["label_version"] = record["version"] if record else payload.get("label_version")
        row["taxonomy_version"] = record["taxonomy_version"] if record else payload.get("taxonomy_version")
        row["applicable_cities"] = payload.get("applicable_cities") if isinstance(payload.get("applicable_cities"), list) else []


@app.get("/api/topics/{topic_id}/detail", response_model=TopicOption)
def topic_detail(topic_id: str, topic_type: str | None = None) -> dict:
    if not topic_id.strip() or len(topic_id) > 64 or topic_type not in (None, "普通", "营销", "热点"):
        raise HTTPException(status_code=422, detail="选题ID或类型无效")
    try:
        with connection() as db, db.cursor() as cursor:
            matches = []
            if topic_type in (None, "普通", "营销", "热点"):
                cursor.execute(
                    "SELECT t.topic_code AS topic_id, t.title AS topic_title, t.category, t.is_marketing, "
                    "t.status, s.payload_json FROM godp_topic t LEFT JOIN godp_topic_source s "
                    "ON s.topic_id=t.topic_code AND s.del_flag='N' WHERE t.topic_code=%s AND t.del_flag='N'", (topic_id,),
                )
                row = cursor.fetchone()
                if row:
                    raw = json.loads(row["payload_json"]) if row.get("payload_json") else {}
                    raw = raw if isinstance(raw, dict) else {}
                    kind = {"hotspot": "热点", "marketing": "营销", "normal": "普通", "ordinary": "普通", "非营销": "普通", "普通": "普通", "营销": "营销", "热点": "热点"}.get(raw.get("topic_type"), "营销" if row["is_marketing"] else "普通")
                    if topic_type is None or topic_type == kind:
                        row.update(topic_type=kind, _catalog_topic=True)
                        matches.append(row)
            for kind, table in (("营销", "godp_marketing_topic_source"), ("热点", "godp_hotspot_topic_source")):
                if topic_type not in (None, kind):
                    continue
                cursor.execute(f"SELECT topic_id, payload_json, enabled FROM {table} WHERE topic_id=%s AND del_flag='N'", (topic_id,))
                row = cursor.fetchone()
                if row:
                    row.update(topic_type=kind, is_marketing=kind == "营销", status="可用" if row["enabled"] else "停用")
                    matches.append(row)
            if not matches:
                raise HTTPException(status_code=404, detail="选题不存在")
            if len(matches) > 1:
                raise HTTPException(status_code=409, detail="选题ID存在多个来源，请明确选题类型")
            row = matches[0]
            source = json.loads(row.pop("payload_json")) if row.get("payload_json") else {}
            if not isinstance(source, dict):
                source = {}
            row.update(
                topic_title=row.get("topic_title") or source.get("title") or "",
                content_type=source.get("content_type") or "", outline=source.get("outline") or source.get("summary") or "",
                topic_payload=source,
            )
            for key in ("valid_from", "valid_to", "related_product", "related_activity", "related_hotspot", "account_type", "account_id"):
                if key in source:
                    value = source[key]
                    if key in ("valid_from", "valid_to", "account_id"):
                        row[key] = str(value) if value is not None else None
                    else:
                        row[key] = "、".join(str(part) for part in value) if isinstance(value, list) else str(value or "")
            attach_topic_labels(cursor, [row])
            row.pop("topic_payload", None)
            row.pop("_catalog_topic", None)
            return row
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/batches", response_model=list[BatchSummary])
def list_batches(plan_type: str | None = None, limit: int = 200) -> list[dict]:
    if plan_type not in (None, "manual", "auto"):
        raise HTTPException(status_code=422, detail="\u65e0\u6548\u7684\u7b56\u5212\u7c7b\u578b")
    limit = max(1, min(limit, 5000))
    try:
        with connection() as db, db.cursor() as cursor:
            query = (
                "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                "account_count, content_count, note, create_time AS created_at, "
                "update_time AS updated_at "
                "FROM godp_planning_batch WHERE del_flag='N' "
            )
            params: tuple = ()
            if plan_type:
                query += "AND plan_type=%s "
                params = (plan_type,)
            query += "ORDER BY create_time DESC, id DESC LIMIT %s"
            cursor.execute(query, (*params, limit))
            rows = cursor.fetchall()
            if not rows:
                return []

            ids = [row["id"] for row in rows]
            placeholders = ",".join(["%s"] * len(ids))
            cursor.execute(
                "SELECT batch_id, MAX(task_name) AS task_name, "
                "SUBSTRING_INDEX(GROUP_CONCAT(status ORDER BY id DESC), ',', 1) AS task_status, "
                "SUM(result_count) AS task_completed_count, SUM(failure_count) AS task_failed_count, "
                "SUM(topic_count) AS task_topic_count, MAX(update_time) AS task_updated_at "
                "FROM godp_manual_task WHERE del_flag='N' AND batch_id IN (" + placeholders + ") "
                "GROUP BY batch_id",
                ids,
            )
            tasks = {row["batch_id"]: row for row in cursor.fetchall()}
            cursor.execute(
                "SELECT i.batch_id, COUNT(*) AS item_count, "
                "COUNT(DISTINCT i.account_id) AS account_item_count, "
                "COUNT(DISTINCT CASE WHEN (i.status LIKE '%%失败%%' OR i.status LIKE '%%异常%%' "
                "OR i.status LIKE '%%错误%%') AND COALESCE(s.production_status, '') <> 'failed' "
                "AND i.status NOT IN ('生成失败','生产失败','生产异常') THEN i.account_id END) AS planning_failed_count, "
                "COUNT(DISTINCT NULLIF(i.topic_id,'')) AS selected_topic_count, "
                f"{COMPLETED_ACCOUNT_COUNT_SQL} AS completed_account_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL} IN ('generated','published') THEN 1 ELSE 0 END) AS production_completed_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='ready' THEN 1 ELSE 0 END) AS ready_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='failed' THEN 1 ELSE 0 END) AS failed_count "
                "FROM godp_planning_item i LEFT JOIN godp_slot_state s "
                "ON s.item_id=i.id AND s.del_flag='N' "
                "WHERE i.del_flag='N' AND i.batch_id IN (" + placeholders + ") "
                "GROUP BY i.batch_id",
                ids,
            )
            counts = {row["batch_id"]: row for row in cursor.fetchall()}
            for row in rows:
                task = tasks.get(row["id"], {})
                counts_for_batch = counts.get(row["id"], {})
                slot_count = counts_for_batch.get("item_count", 0)
                production_completed_count = counts_for_batch.get("production_completed_count", 0)
                ready_count = counts_for_batch.get("ready_count", 0)
                production_failed_count = counts_for_batch.get("failed_count", 0)
                planning_failed_count = counts_for_batch.get("planning_failed_count", 0)
                row["task_name"] = task.get("task_name") or (
                    f"{'Auto-' if row['plan_type'] == 'auto' else 'Manual-'}{row['cycle_start'].strftime('%Y%m%d')}"
                )
                row["updated_at"] = task.get("task_updated_at") or row["updated_at"]
                row["planning_status"] = task.get("task_status") or (
                    "\u5df2\u5b8c\u6210" if row["plan_type"] == "manual" else row["status"]
                )
                row["content_status"] = (
                    "\u751f\u6210\u5931\u8d25" if production_failed_count else
                    "\u5df2\u5b8c\u6210" if slot_count and production_completed_count == slot_count else
                    "\u751f\u6210\u4e2d" if ready_count or production_completed_count else
                    "\u5f85\u751f\u4ea7"
                )
                row["result_count"] = slot_count
                row["content_failed_count"] = production_failed_count
                row["content_completed_count"] = production_completed_count
                row["content_total_count"] = slot_count
                row["content_completed_account_count"] = counts_for_batch.get("completed_account_count", 0)
                if row["plan_type"] == "manual" and task:
                    row["completed_count"] = task.get("task_completed_count") or 0
                    row["failed_count"] = task.get("task_failed_count") or 0
                    row["topic_count"] = task.get("task_topic_count") or 0
                else:
                    failed_accounts = planning_failed_count
                    if not counts_for_batch and is_execution_error(row["status"]):
                        failed_accounts = row["account_count"]
                    row["failed_count"] = failed_accounts
                    row["completed_count"] = max(
                        0, min(row["account_count"], counts_for_batch.get("account_item_count", 0) - failed_accounts)
                    )
                    row["topic_count"] = counts_for_batch.get("selected_topic_count", 0)
                # Content callbacks can mark a batch as unfinished without a planning failure.
                if (row["planning_status"] in ("未完成", "生成失败", "生产失败", "生产异常")
                        and production_failed_count and not row["failed_count"]):
                    row["planning_status"] = "已完成"
                row["planning_status"] = planning_status_label(row["planning_status"], row["failed_count"])
            return rows
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/batches/{batch_id}", response_model=BatchDetail)
def get_batch(batch_id: int) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                "account_count, content_count, note, create_time AS created_at "
                "FROM godp_planning_batch WHERE id=%s AND del_flag='N'",
                (batch_id,),
            )
            batch = cursor.fetchone()
            if not batch:
                raise HTTPException(status_code=404, detail="策划批次不存在")
            cursor.execute(
                "SELECT i.id, i.account_id, i.account_name, i.publish_date, i.slot_type, "
                "i.topic_id, i.topic_title, i.topic_type, i.outline, i.content_type, "
                "i.status, i.lifecycle_stage, i.content_role, s.slot_id, s.production_status, "
                "s.topic_id AS slot_topic_id, s.published_at, s.version, ts.payload_json AS topic_payload, "
                "t.is_marketing AS source_is_marketing "
                "FROM godp_planning_item i LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
                "LEFT JOIN godp_topic t ON t.topic_code=i.topic_id AND t.del_flag='N' "
                "LEFT JOIN godp_topic_source ts ON ts.topic_id=i.topic_id "
                "WHERE i.batch_id=%s AND i.del_flag='N' "
                "ORDER BY i.account_name, i.publish_date, i.id",
                (batch_id,),
            )
            items = [enrich_plan_item(item, batch["plan_type"]) for item in cursor.fetchall()]
            return {**batch, "result_count": len(items), "items": items}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/items", response_model=list[AccountPlanRecord])
def search_items(account: str, limit: int = 1000) -> list[dict]:
    account = account.strip()
    if not account:
        return []
    limit = max(1, min(limit, 5000))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT i.id, i.account_id, i.account_name, i.publish_date, i.slot_type, "
                "i.topic_id, i.topic_title, i.topic_type, i.outline, i.content_type, "
                "i.status, i.lifecycle_stage, i.content_role, s.slot_id, s.production_status, "
                "s.topic_id AS slot_topic_id, s.published_at, s.version, ts.payload_json AS topic_payload, "
                "t.is_marketing AS source_is_marketing, "
                "b.id AS batch_id, b.batch_code, b.plan_type, b.create_time AS batch_created_at, "
                "b.cycle_start, b.cycle_end FROM godp_planning_item i "
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
                "LEFT JOIN godp_topic t ON t.topic_code=i.topic_id AND t.del_flag='N' "
                "LEFT JOIN godp_topic_source ts ON ts.topic_id=i.topic_id "
                "LEFT JOIN godp_account_source account_source "
                "ON account_source.account_id=i.account_id AND account_source.del_flag='N' "
                "JOIN godp_planning_batch b ON b.id=i.batch_id "
                "WHERE i.del_flag='N' AND b.del_flag='N' "
                "AND (i.account_id LIKE %s OR i.account_name LIKE %s OR "
                "JSON_UNQUOTE(JSON_EXTRACT(account_source.payload_json, '$.account_alias')) LIKE %s) "
                "ORDER BY b.cycle_start DESC, b.create_time DESC, i.publish_date, i.id LIMIT %s",
                (f"%{account}%", f"%{account}%", f"%{account}%", limit),
            )
            rows = cursor.fetchall()
            return [enrich_plan_item(row, row["plan_type"]) for row in rows]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/planning-accounts", response_model=list[PlanningAccountSummary])
def list_planning_accounts(limit: int = 5000) -> list[dict]:
    limit = max(1, min(limit, 10000))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT i.account_id, MAX(i.account_name) AS account_name, "
                "COALESCE(MAX(JSON_UNQUOTE(JSON_EXTRACT(account_source.payload_json, '$.organization'))), '') AS account_owner, "
                "COUNT(DISTINCT b.cycle_start) AS cycle_count, COUNT(*) AS slot_count, "
                "MAX(b.cycle_start) AS latest_cycle_start, "
                "MAX(b.create_time) AS latest_cycle_updated_at, "
                "SUBSTRING_INDEX(GROUP_CONCAT(b.status ORDER BY b.create_time DESC, b.id DESC), ',', 1) AS latest_status, "
                "CAST(SUBSTRING_INDEX(GROUP_CONCAT(b.id ORDER BY b.create_time DESC, b.id DESC), ',', 1) AS UNSIGNED) AS latest_batch_id "
                "FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
                "LEFT JOIN godp_account_source account_source "
                "ON account_source.account_id=i.account_id AND account_source.del_flag='N' "
                "WHERE i.del_flag='N' AND b.del_flag='N' "
                "GROUP BY i.account_id "
                "ORDER BY latest_cycle_updated_at DESC, account_name, i.account_id LIMIT %s",
                (limit,),
            )
            return cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.post("/api/items/{item_id}/replace-topic", response_model=ReplaceTopicResponse)
def replace_topic(item_id: int, payload: ReplaceTopicInput) -> dict:
    operator = "运营人员"
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT i.id, i.account_id, i.account_name, i.publish_date, i.slot_type, "
                "i.topic_id, i.topic_title, i.topic_type, i.status, i.lifecycle_stage, i.content_role, "
                "b.id AS batch_id, b.plan_type, b.batch_code, b.create_time AS batch_created_at, "
                "b.cycle_start, b.cycle_end, "
                "s.slot_id, s.version, s.topic_id AS slot_topic_id, s.production_status, s.published_at "
                "FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
                "WHERE i.id=%s AND i.del_flag='N' AND b.del_flag='N' FOR UPDATE", (item_id,),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="策划结果不存在")
            block_reason = replacement_block_reason(item, item["plan_type"])
            if block_reason:
                raise HTTPException(status_code=409, detail=block_reason)
            if item["version"] != payload.expected_version:
                raise HTTPException(status_code=409, detail="结果版本已变化或状态无法确认，请刷新后重试")
            if payload.new_topic_id == item["topic_id"]:
                raise HTTPException(status_code=409, detail="新选题与当前选题相同")
            topics = available_replacement_topics(cursor, item["account_id"], payload.new_topic_id)
            topic = topics[0] if topics else None
            if topic is None:
                raise HTTPException(status_code=409, detail="新选题不可用、未审核或已过期，请重新选择")
            next_version = item["version"] + 1
            topic_payload = topic["topic_payload"]
            cursor.execute(
                "SELECT tags_json FROM godp_topic_tag WHERE topic_id=%s AND del_flag='N'",
                (topic["topic_id"],),
            )
            tag_row = cursor.fetchone()
            tag_values = json.loads(tag_row["tags_json"]) if tag_row else {}
            role_value = tag_values.get("T2", [])
            next_role = role_value[0] if isinstance(role_value, list) and role_value else role_value
            if next_role not in ("流量", "转化"):
                role_slot_type = (
                    "marketing_priority" if topic["topic_type"] == "营销" else
                    "hotspot" if topic["topic_type"] == "热点" else "regular"
                )
                next_role = infer_content_role({**item, "slot_type": role_slot_type}, topic_payload)
            cursor.execute(
                "UPDATE godp_planning_item SET topic_id=%s, topic_title=%s, topic_type=%s, "
                "outline=%s, content_type=%s, content_role=%s, "
                "status='已规划', update_by=%s WHERE id=%s",
                (topic["topic_id"], topic["topic_title"],
                 topic["topic_type"],
                 topic_payload.get("outline") or topic_payload.get("summary") or "",
                 topic_payload.get("content_type") or "", next_role, operator, item_id),
            )
            cursor.execute(
                "UPDATE godp_slot_state SET version=%s, topic_id=%s, "
                "production_status='planned', content_id=NULL, generated_at=NULL, "
                "update_by=%s WHERE item_id=%s",
                (next_version, topic["topic_id"], operator, item_id),
            )
            cursor.execute(
                "INSERT INTO godp_planning_adjustment "
                "(item_id, result_version, adjustment_source, old_topic_id, old_topic_title, "
                "new_topic_id, new_topic_title, reason, create_by, update_by) "
                "VALUES (%s, %s, '人工替换', %s, %s, %s, %s, %s, %s, %s)",
                (item_id, next_version, item["topic_id"], item["topic_title"],
                 topic["topic_id"], topic["topic_title"], payload.reason, operator, operator),
            )
            adjustment_id = cursor.lastrowid
            queue_event(cursor, "planning", "CONTENT_VERSION_CHANGED", {
                "planning_batch_id": item["batch_id"],
                "account_id": item["account_id"],
                "slot_id": item["slot_id"],
                "item_id": item_id,
                "version": next_version,
                "old_topic_id": item["topic_id"],
                "new_topic_id": topic["topic_id"],
                "adjustment_source": "manual",
                "reason": payload.reason,
                "operator": operator,
            })
            cursor.execute(
                "SELECT id, create_time AS created_at, create_by AS created_by, item_id, result_version, "
                "adjustment_source, old_topic_id, old_topic_title, new_topic_id, new_topic_title, reason "
                "FROM godp_planning_adjustment WHERE id=%s", (adjustment_id,),
            )
            adjustment = cursor.fetchone()
            db.commit()
    except HTTPException:
        raise
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    updated = {
        "id": item_id, "account_id": item["account_id"], "account_name": item["account_name"],
        "publish_date": item["publish_date"], "slot_type": item["slot_type"],
        "topic_id": topic["topic_id"], "topic_title": topic["topic_title"], "status": "已规划",
        "slot_id": item["slot_id"], "production_status": "planned",
        "batch_id": item["batch_id"], "batch_code": item["batch_code"],
        "batch_created_at": item["batch_created_at"], "plan_type": item["plan_type"],
        "cycle_start": item["cycle_start"], "cycle_end": item["cycle_end"],
        "publish_status": "未发布", "allow_replace": True,
        "replace_block_reason": "", "result_version": next_version,
        "content_type": topic_payload.get("content_type", ""),
        "outline": topic_payload.get("outline", "") or topic_payload.get("summary", ""),
        "topic_type": topic["topic_type"],
        "lifecycle_stage": item.get("lifecycle_stage"),
        "content_role": next_role,
    }
    return {"item": updated, "adjustment": adjustment}


@app.get("/api/items/{item_id}/adjustments", response_model=list[AdjustmentRecord])
def list_adjustments(item_id: int, limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 100))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, item_id, result_version, adjustment_source, old_topic_id, old_topic_title, "
                "new_topic_id, new_topic_title, reason, create_time AS created_at, create_by AS created_by "
                "FROM godp_planning_adjustment WHERE item_id=%s AND del_flag='N' "
                "ORDER BY id DESC LIMIT %s", (item_id, limit),
            )
            return cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.post("/api/batches/manual", response_model=BatchDetail, status_code=201)
def create_manual_batch(payload: ManualPlanCreate) -> dict:
    operator = "运营人员"
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            batch_id = insert_manual_batch(cursor, payload, operator=operator)
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return get_batch(batch_id)


def insert_manual_batch(cursor, payload: ManualPlanCreate, operator: str = "system",
                        exclude_task_id: int | None = None) -> int:
    ensure_manual_accounts_available(cursor, payload.publish_date,
                                     [item.account_id for item in payload.items], exclude_task_id)
    is_demo = any(
        item.account_id.startswith("DEMO-") or item.topic_id.startswith("DEMO-")
        for item in payload.items
    )
    batch_code = ("DEMO-MAN-" if is_demo else "MAN-") + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:6].upper()
    note = (("演示数据｜" if is_demo else "") + payload.note)[:500]
    lifecycle_by_account: dict[str, str] = {}
    cursor.execute(
        "SELECT config_json FROM godp_strategy_config WHERE config_key='operations' AND del_flag='N'"
    )
    config_row = cursor.fetchone()
    config = StrategyConfig.model_validate_json(config_row["config_json"]) if config_row else StrategyConfig()
    for scope in ("production", "demo"):
        try:
            lifecycle_by_account.update({
                account["account_id"]: account["lifecycle_stage"]
                for account in load_accounts(cursor, scope, config)
            })
        except PlanningError:
            continue
    cursor.execute(
        "INSERT INTO godp_planning_batch "
        "(batch_code, plan_type, status, cycle_start, cycle_end, account_count, "
        "content_count, note, create_by, update_by) "
        "VALUES (%s, 'manual', '待生成', %s, %s, %s, 0, %s, %s, %s)",
        (batch_code, payload.publish_date, payload.publish_date, len(payload.items), note,
         operator, operator),
    )
    batch_id = cursor.lastrowid
    for item in payload.items:
        cursor.execute(
            "INSERT INTO godp_planning_item "
            "(batch_id, account_id, account_name, publish_date, slot_type, "
            "topic_id, topic_title, status, lifecycle_stage, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, 'manual_extra', %s, %s, '待生成', %s, %s, %s)",
            (batch_id, item.account_id, item.account_name, payload.publish_date,
             item.topic_id, item.topic_title, lifecycle_by_account.get(item.account_id),
             operator, operator),
        )
        queue_manual_slot(
            cursor, cursor.lastrowid, batch_id, batch_code,
            item.account_id, item.topic_id, payload.publish_date.isoformat(), operator=operator,
        )
    return batch_id


def available_topics(cursor, topic_ids: list[str]) -> dict[str, dict]:
    placeholders = ",".join(["%s"] * len(topic_ids))
    cursor.execute(
        "SELECT t.topic_code AS topic_id, t.title AS topic_title, t.is_marketing, "
        "s.payload_json AS topic_payload "
        "FROM godp_topic t LEFT JOIN godp_topic_source s ON s.topic_id=t.topic_code "
        f"WHERE t.topic_code IN ({placeholders}) AND t.del_flag='N' AND t.status='可用' "
        "AND (s.id IS NULL OR (s.active_in_snapshot=1 "
        "AND (t.is_marketing=0 OR s.approval_status='approved') "
        "AND (s.valid_from IS NULL OR s.valid_from<=UTC_TIMESTAMP(6)) "
        "AND (s.valid_to IS NULL OR s.valid_to>=UTC_TIMESTAMP(6))))",
        topic_ids,
    )
    return {row["topic_id"]: row for row in cursor.fetchall()}


def available_replacement_topics(cursor, account_id: str, topic_id: str | None = None) -> list[dict]:
    """Read current, account-eligible ordinary, marketing, and hotspot candidates."""
    candidates: list[dict] = []
    id_clause = " AND t.topic_code=%s" if topic_id is not None else ""
    params: list[object] = [topic_id] if topic_id is not None else []
    cursor.execute(
        "SELECT t.topic_code AS topic_id, t.title AS topic_title, t.category, "
        "s.payload_json AS topic_payload FROM godp_topic t "
        "LEFT JOIN godp_topic_source s ON s.topic_id=t.topic_code AND s.del_flag='N' "
        "WHERE t.del_flag='N' AND t.status='可用' AND t.is_marketing=0 "
        "AND (s.id IS NULL OR (s.active_in_snapshot=1 "
        "AND (s.valid_from IS NULL OR s.valid_from<=UTC_TIMESTAMP(6)) "
        "AND (s.valid_to IS NULL OR s.valid_to>=UTC_TIMESTAMP(6))))" + id_clause,
        params,
    )
    for row in cursor.fetchall():
        try:
            payload = json.loads(row["topic_payload"]) if row.get("topic_payload") else {}
            if not isinstance(payload, dict):
                payload = {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        candidates.append({
            "topic_id": row["topic_id"], "topic_title": row["topic_title"],
            "category": row.get("category") or "", "content_type": payload.get("content_type") or "",
            "outline": payload.get("outline") or payload.get("summary") or "",
            "is_marketing": False, "topic_type": "普通", "account_id": None, "status": "可用",
            "topic_payload": payload,
        })

    id_clause = " AND m.topic_id=%s" if topic_id is not None else ""
    params = [account_id] + ([topic_id] if topic_id is not None else [])
    cursor.execute(
        "SELECT m.topic_id, m.account_id, m.payload_json FROM godp_marketing_topic_source m "
        "WHERE m.account_id=%s AND m.del_flag='N' AND m.active_in_snapshot=1 AND m.enabled=1 "
        "AND m.approval_status='approved' AND m.approved_at IS NOT NULL "
        "AND (m.valid_from IS NULL OR m.valid_from<=UTC_TIMESTAMP(6)) "
        "AND (m.valid_to IS NULL OR m.valid_to>=UTC_TIMESTAMP(6))" + id_clause,
        params,
    )
    for row in cursor.fetchall():
        try:
            payload = json.loads(row["payload_json"]) if row.get("payload_json") else {}
            if not isinstance(payload, dict):
                payload = {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        payload["is_marketing"] = True
        candidates.append({
            "topic_id": row["topic_id"], "topic_title": payload.get("title") or "",
            "category": payload.get("category") or "", "content_type": payload.get("content_type") or "",
            "outline": payload.get("outline") or "", "is_marketing": True,
            "topic_type": "营销", "account_id": row.get("account_id") or account_id,
            "status": "可用", "topic_payload": payload,
        })

    id_clause = " AND h.topic_id=%s" if topic_id is not None else ""
    params = [topic_id] if topic_id is not None else []
    cursor.execute(
        "SELECT h.topic_id, h.payload_json FROM godp_hotspot_topic_source h "
        "WHERE h.del_flag='N' AND h.active_in_snapshot=1 AND h.enabled=1 "
        "AND (h.valid_from IS NULL OR h.valid_from<=UTC_TIMESTAMP(6)) "
        "AND (h.valid_to IS NULL OR h.valid_to>=UTC_TIMESTAMP(6))" + id_clause,
        params,
    )
    for row in cursor.fetchall():
        try:
            payload = json.loads(row["payload_json"]) if row.get("payload_json") else {}
            if not isinstance(payload, dict):
                payload = {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        candidates.append({
            "topic_id": row["topic_id"], "topic_title": payload.get("title") or "",
            "category": payload.get("category") or "", "content_type": payload.get("content_type") or "",
            "outline": payload.get("outline") or "", "is_marketing": False,
            "topic_type": "热点", "account_id": None, "status": "可用", "topic_payload": payload,
        })
    # A topic ID collision across source types cannot be selected safely.
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate["topic_id"]] = counts.get(candidate["topic_id"], 0) + 1
    return sorted((row for row in candidates if row["topic_title"] and counts[row["topic_id"]] == 1),
                  key=lambda row: ({"普通": 0, "营销": 1, "热点": 2}[row["topic_type"]], row["topic_title"]))


@app.get("/api/items/{item_id}/replacement-candidates", response_model=list[TopicOption])
def list_replacement_candidates(item_id: int) -> list[dict]:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT i.account_id, i.topic_id, i.status, b.plan_type, s.slot_id, s.version, s.topic_id AS slot_topic_id, "
                "s.production_status, s.published_at FROM godp_planning_item i "
                "JOIN godp_planning_batch b ON b.id=i.batch_id "
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
                "WHERE i.id=%s AND i.del_flag='N' AND b.del_flag='N'", (item_id,),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="策划结果不存在")
            reason = replacement_block_reason(item, item["plan_type"])
            if reason:
                raise HTTPException(status_code=409, detail=reason)
            candidates = [candidate for candidate in available_replacement_topics(
                cursor, item["account_id"]
            ) if candidate["topic_id"] != item["topic_id"]]
            attach_topic_labels(cursor, candidates)
            for candidate in candidates:
                payload = candidate.get("topic_payload") or {}
                for key in ("related_product", "related_activity", "related_hotspot", "valid_from", "valid_to"):
                    candidate[key] = payload.get(key) if key.startswith("valid_") else payload.get(key) or ""
                candidate.pop("topic_payload", None)
            return candidates
    except HTTPException:
        raise
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/manual-plans/account-availability", response_model=ManualAccountAvailability)
def manual_account_availability(publish_date: date) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            planned = planned_manual_accounts(cursor, publish_date)
        return {"publish_date": publish_date, "planned_account_ids": sorted(planned)}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.post("/api/manual-plans/previews", response_model=ManualPreviewResponse, status_code=201)
def preview_manual_plan(payload: ManualPreviewInput) -> dict:
    operator = "运营人员"
    if payload.followers_min is not None and payload.followers_max is not None \
            and payload.followers_min > payload.followers_max:
        raise HTTPException(status_code=422, detail="粉丝量下限不能大于上限")
    catalog = list_accounts(limit=1000)
    filtered = [account for account in catalog if
                  (not payload.keyword or payload.keyword.lower() in
                   f"{account['account_id']} {account['account_name']} {account['account_alias']}".lower()) and
                  (not payload.city or account["city"] == payload.city) and
                  (not payload.persona or account["persona"] == payload.persona) and
                  (not payload.traffic_trend or account["traffic_trend"] == payload.traffic_trend) and
                  (payload.certified is None or account["certified"] == payload.certified) and
                  (payload.followers_min is None or (account["followers"] is not None and
                   account["followers"] >= payload.followers_min)) and
                  (payload.followers_max is None or (account["followers"] is not None and
                   account["followers"] <= payload.followers_max))]
    if payload.account_ids:
        wanted = set(payload.account_ids)
        candidates = [account for account in filtered if account["account_id"] in wanted]
        if len(candidates) != len(wanted):
            raise HTTPException(status_code=409, detail="抽中账号状态或筛选条件已变化，请重新查询并抽取")
    else:
        candidates = filtered
    blocked = set(manual_account_availability(payload.publish_date)["planned_account_ids"])
    if payload.account_ids and blocked.intersection(payload.account_ids):
        raise HTTPException(status_code=409, detail="所选账号包含当日已手动策划的账号，请重新选择")
    candidates = [account for account in candidates if account["account_id"] not in blocked]
    target = payload.target_count or len(candidates)
    if not target or target > len(candidates):
        raise HTTPException(status_code=422, detail="符合条件的账号不足，无法完成本次抽取")
    if payload.target_count is not None:
        candidates = secrets.SystemRandom().sample(candidates, target)
    try:
        with connection() as db, db.cursor() as cursor:
            unique_topic_ids = list(dict.fromkeys(payload.topic_ids))
            topics = available_topics(cursor, unique_topic_ids)
            if len(topics) != len(unique_topic_ids):
                raise HTTPException(status_code=422, detail="所选选题包含不可用、未审核或已过期的选题")
            items = []
            for account in candidates:
                compatible = [topics[topic_id] for topic_id in payload.topic_ids
                              if not topics[topic_id]["is_marketing"] or account["marketing_eligible"]]
                if not compatible:
                    raise HTTPException(status_code=422, detail=f"账号 {account['account_name']} 不具备所选营销选题资格")
                topic = secrets.choice(compatible)
                items.append(ManualItem(
                    account_id=account["account_id"], account_name=account["account_name"],
                    topic_id=topic["topic_id"], topic_title=topic["topic_title"],
                ))
            preview_id = "PREV-" + uuid4().hex.upper()
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
            cursor.execute(
                "INSERT INTO godp_manual_preview "
                "(preview_code, task_name, publish_date, allocations_json, note, expires_at, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (preview_id, payload.task_name, payload.publish_date,
                 json.dumps([item.model_dump() for item in items], ensure_ascii=False),
                 payload.note, expires_at.replace(tzinfo=None), operator, operator),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return {"preview_id": preview_id, "task_name": payload.task_name, "publish_date": payload.publish_date,
            "expires_at": expires_at, "items": items, "note": payload.note}


def mark_manual_task_failed(task_id: int, reason: str, last_error: str, operator: str) -> None:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "UPDATE godp_manual_task SET status='执行失败', "
                "failure_count=planned_account_count, failure_reason=%s, last_error=%s, "
                "update_by=%s WHERE id=%s AND status='执行中'",
                (reason, last_error[:500], operator, task_id),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError):
        pass


def execute_manual_preview(preview_id: str, task_id: int, operator: str) -> None:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute(
                "SELECT publish_date, allocations_json, note, status, expires_at, batch_id "
                "FROM godp_manual_preview WHERE preview_code=%s AND del_flag='N' FOR UPDATE",
                (preview_id,),
            )
            preview = cursor.fetchone()
            if not preview:
                raise HTTPException(status_code=404, detail="策划预览不存在")
            if preview["status"] == "submitted" and preview["batch_id"]:
                cursor.execute(
                    "UPDATE godp_manual_task SET status='已完成', batch_id=%s, update_by=%s "
                    "WHERE id=%s AND status='执行中'",
                    (preview["batch_id"], operator, task_id),
                )
                db.commit()
                return
            items = [ManualItem.model_validate(item) for item in json.loads(preview["allocations_json"])]
            topic_ids = list({item.topic_id for item in items})
            if preview["expires_at"] < datetime.now(timezone.utc).replace(tzinfo=None):
                raise HTTPException(status_code=409, detail="策划预览已过期，请重新提交")
            cursor.execute(
                "SELECT account_code FROM godp_account WHERE account_code IN (" +
                ",".join(["%s"] * len(items)) + ") AND status='启用' AND del_flag='N'",
                [item.account_id for item in items],
            )
            if len(cursor.fetchall()) != len(items):
                raise HTTPException(status_code=409, detail="账号状态已变化，请重新提交")
            topics = available_topics(cursor, topic_ids)
            if len(topics) != len(topic_ids):
                raise HTTPException(status_code=409, detail="选题状态已变化，请重新提交")
            cursor.execute(
                "SELECT account_code, marketing_eligible FROM godp_account WHERE account_code IN (" +
                ",".join(["%s"] * len(items)) + ")",
                [item.account_id for item in items],
            )
            eligible = {row["account_code"]: row["marketing_eligible"] for row in cursor.fetchall()}
            if any(topics[item.topic_id]["is_marketing"] and not eligible.get(item.account_id)
                   for item in items):
                raise HTTPException(status_code=409, detail="账号营销资格已变化，请重新提交")
            batch_id = insert_manual_batch(cursor, ManualPlanCreate(
                publish_date=preview["publish_date"], items=items, note=preview["note"],
            ), operator=operator, exclude_task_id=task_id)
            cursor.execute(
                "UPDATE godp_manual_preview SET status='submitted', batch_id=%s, update_by=%s "
                "WHERE preview_code=%s", (batch_id, operator, preview_id),
            )
            cursor.execute(
                "UPDATE godp_manual_task SET status='已完成', result_count=%s, batch_id=%s, "
                "update_by=%s WHERE id=%s", (len(items), batch_id, operator, task_id),
            )
            db.commit()
    except HTTPException as exc:
        mark_manual_task_failed(task_id, exc.detail, exc.detail, operator)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        mark_manual_task_failed(task_id, "系统异常，请查看服务日志", str(exc), operator)
    except Exception as exc:
        mark_manual_task_failed(task_id, "系统异常，请查看服务日志", str(exc), operator)


@app.post("/api/manual-plans/previews/{preview_id}/submit", response_model=ManualTaskSummary, status_code=202)
def submit_manual_preview(preview_id: str, background_tasks: BackgroundTasks) -> dict:
    operator = "运营人员"
    task_code = "MAN-TASK-" + uuid4().hex.upper()
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute(
                "SELECT task_name, publish_date, allocations_json, status, batch_id, expires_at "
                "FROM godp_manual_preview WHERE preview_code=%s AND del_flag='N' FOR UPDATE",
                (preview_id,),
            )
            preview = cursor.fetchone()
            if not preview:
                raise HTTPException(status_code=404, detail="策划预览不存在")
            cursor.execute(
                "SELECT id, task_code, preview_code, task_name, publish_date, planned_account_count, "
                "result_count, failure_count, topic_count, status, failure_reason, batch_id, "
                "last_error, create_time AS created_at, create_by AS created_by, "
                "update_time AS updated_at FROM godp_manual_task "
                "WHERE preview_code=%s AND del_flag='N' AND status IN ('执行中','进行中','已完成') "
                "ORDER BY id DESC LIMIT 1",
                (preview_id,),
            )
            existing_task = cursor.fetchone()
            if existing_task:
                return existing_task
            if preview["status"] == "submitted" and preview["batch_id"]:
                raise HTTPException(status_code=409, detail="该策划已提交")
            if preview["expires_at"] < datetime.now(timezone.utc).replace(tzinfo=None):
                raise HTTPException(status_code=409, detail="策划预览已过期，请重新提交")
            items = [ManualItem.model_validate(item) for item in json.loads(preview["allocations_json"])]
            ensure_manual_accounts_available(cursor, preview["publish_date"],
                                             [item.account_id for item in items])
            topic_count = len({item.topic_id for item in items})
            cursor.execute(
                "INSERT INTO godp_manual_task "
                "(task_code, preview_code, task_name, publish_date, planned_account_count, topic_count, status, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, '执行中', %s, %s)",
                (task_code, preview_id, preview["task_name"], preview["publish_date"], len(items), topic_count,
                 operator, operator),
            )
            task_id = cursor.lastrowid
            db.commit()
            cursor.execute(
                "SELECT id, task_code, preview_code, task_name, publish_date, planned_account_count, "
                "result_count, failure_count, topic_count, status, failure_reason, batch_id, "
                "last_error, create_time AS created_at, create_by AS created_by, "
                "update_time AS updated_at FROM godp_manual_task WHERE id=%s",
                (task_id,),
            )
            task = cursor.fetchone()
        background_tasks.add_task(execute_manual_preview, preview_id, task_id, operator)
        return task
    except HTTPException:
        raise
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/manual-plans/tasks", response_model=list[ManualTaskSummary])
def list_manual_tasks(limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, task_code, preview_code, task_name, publish_date, planned_account_count, "
                "result_count, failure_count, topic_count, status, failure_reason, t.batch_id, "
                "CASE WHEN status IN ('执行中','进行中') THEN '待生产' "
                "WHEN status <> '已完成' THEN '待生产' "
                "WHEN t.batch_id IS NULL OR COALESCE(cs.slot_count, 0)=0 THEN '待生产' "
                "WHEN cs.failed_count > 0 THEN '生成失败' "
                "WHEN cs.completed_count=cs.slot_count THEN '已完成' "
                "WHEN cs.ready_count > 0 OR cs.completed_count > 0 THEN '生成中' "
                "ELSE '待生产' END AS content_status, "
                "COALESCE(cs.failed_count, 0) AS content_failed_count, "
                "COALESCE(cs.completed_count, 0) AS content_completed_count, "
                "COALESCE(cs.slot_count, 0) AS content_total_count, "
                "COALESCE(cs.completed_account_count, 0) AS content_completed_account_count, "
                "COALESCE((SELECT batch_code FROM godp_planning_batch WHERE id=t.batch_id AND del_flag='N'), '') AS batch_code, "
                "last_error, create_time AS created_at, create_by AS created_by, "
                "update_time AS updated_at "
                "FROM godp_manual_task t "
                "LEFT JOIN (SELECT i.batch_id, COUNT(*) AS slot_count, "
                f"{COMPLETED_ACCOUNT_COUNT_SQL} AS completed_account_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL} IN ('generated','published') THEN 1 ELSE 0 END) AS completed_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='ready' THEN 1 ELSE 0 END) AS ready_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='failed' THEN 1 ELSE 0 END) AS failed_count "
                "FROM godp_planning_item i LEFT JOIN godp_slot_state s "
                "ON s.item_id=i.id AND s.del_flag='N' "
                "WHERE i.del_flag='N' GROUP BY i.batch_id) cs ON cs.batch_id=t.batch_id "
                "WHERE t.del_flag='N' ORDER BY t.id DESC LIMIT %s", (limit,),
            )
            rows = cursor.fetchall()
            for row in rows:
                row["planning_status"] = planning_status_label(row["status"], row["failure_count"])
            return rows
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


def cycle_records() -> tuple[list[dict], list[dict]]:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                "account_count, content_count, note, update_time, create_time "
                "FROM godp_planning_batch WHERE del_flag='N' "
                "ORDER BY create_time DESC, id DESC LIMIT 5000"
            )
            batches = cursor.fetchall()
            if not batches:
                return [], []
            placeholders = ",".join(["%s"] * len(batches))
            cursor.execute(
                "SELECT i.batch_id, i.account_id, i.account_name, i.slot_type, i.topic_id, "
                "i.topic_type, i.status, t.is_marketing AS source_is_marketing, s.production_status "
                "FROM godp_planning_item i LEFT JOIN godp_slot_state s ON s.item_id=i.id "
                "LEFT JOIN godp_topic t ON t.topic_code=i.topic_id AND t.del_flag='N' "
                f"WHERE i.del_flag='N' AND i.batch_id IN ({placeholders})",
                [batch["id"] for batch in batches],
            )
            items = cursor.fetchall()
            return batches, items
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def is_execution_error(status: str | None) -> bool:
    return bool(status and any(marker in status for marker in ("失败", "异常", "错误")))


def planning_topic_type(item: dict) -> str:
    value = item.get("topic_type")
    aliases = {
        "normal": "普通", "regular": "普通", "普通": "普通",
        "marketing": "营销", "marketing_priority": "营销", "营销": "营销",
        "hotspot": "热点", "热点": "热点",
    }
    if value in aliases:
        return aliases[value]
    if item.get("slot_type") == "hotspot":
        return "热点"
    if item.get("slot_type") == "marketing_priority" or item.get("source_is_marketing"):
        return "营销"
    return "普通"


def hotspot_is_pending(item: dict) -> bool:
    return item["slot_type"] == "hotspot" and (
        not item["topic_id"] or
        (item["account_id"].startswith("DEMO-") and item.get("production_status") in (None, "planned"))
    )


@app.get("/api/planning-cycles/{cycle_id}/items", response_model=list[AccountPlanRecord])
def list_cycle_items(cycle_id: date, limit: int = 1000) -> list[dict]:
    if cycle_id.weekday() != 0:
        raise HTTPException(status_code=422, detail="策划周期应使用周一日期")
    limit = max(1, min(limit, 5000))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT i.id, i.account_id, i.account_name, i.publish_date, i.slot_type, "
                "i.topic_id, i.topic_title, i.topic_type, i.outline, i.content_type, "
                "i.status, i.lifecycle_stage, i.content_role, s.slot_id, s.production_status, "
                "s.topic_id AS slot_topic_id, s.published_at, s.version, ts.payload_json AS topic_payload, "
                "t.is_marketing AS source_is_marketing, "
                "b.id AS batch_id, b.batch_code, b.plan_type, b.create_time AS batch_created_at, "
                "b.cycle_start, b.cycle_end "
                "FROM godp_planning_item i "
                "JOIN godp_planning_batch b ON b.id=i.batch_id "
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
                "LEFT JOIN godp_topic t ON t.topic_code=i.topic_id AND t.del_flag='N' "
                "LEFT JOIN godp_topic_source ts ON ts.topic_id=i.topic_id "
                "WHERE i.del_flag='N' AND b.del_flag='N' "
                "AND b.cycle_start >= %s AND b.cycle_start < %s "
                "ORDER BY i.account_name, b.create_time DESC, i.publish_date, i.id LIMIT %s",
                (cycle_id, cycle_id + timedelta(days=7), limit),
            )
            rows = cursor.fetchall()
            return [enrich_plan_item(row, row["plan_type"]) for row in rows]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/planning-cycles", response_model=list[PlanningCycleSummary])
def list_planning_cycles() -> list[dict]:
    batches, items = cycle_records()
    by_batch: dict[int, list[dict]] = {}
    for item in items:
        by_batch.setdefault(item["batch_id"], []).append(item)
    grouped: dict[date, list[dict]] = {}
    for batch in batches:
        grouped.setdefault(monday(batch["cycle_start"]), []).append(batch)
    result = []
    for start, group in sorted(grouped.items(), reverse=True):
        rows = [item for batch in group for item in by_batch.get(batch["id"], [])]
        auto_rows = [item for batch in group if batch["plan_type"] == "auto"
                     for item in by_batch.get(batch["id"], [])]
        all_accounts = {item["account_id"] for item in rows}
        failed_batches = [batch for batch in group if is_execution_error(batch["status"])]
        failed_ids = {item["account_id"] for item in rows if is_execution_error(item["status"])}
        for batch in failed_batches:
            failed_ids.update(item["account_id"] for item in by_batch.get(batch["id"], []))
        pending_hotspot_accounts = {
            item["account_id"] for item in auto_rows if hotspot_is_pending(item)
        }
        missing_failed = sum(batch["account_count"] for batch in failed_batches
                             if not by_batch.get(batch["id"]))
        assigned = [item for item in rows
                    if item["topic_id"] and not is_execution_error(item["status"])]
        planning_failed_accounts = len(failed_ids) + missing_failed
        completed_accounts = len(all_accounts - failed_ids - pending_hotspot_accounts)
        execution_started = start <= datetime.now(timezone(timedelta(hours=8))).date()
        if planning_failed_accounts:
            planning_status = "\u6267\u884c\u5f02\u5e38"
        elif not execution_started:
            planning_status = "\u5df2\u89c4\u5212"
        elif pending_hotspot_accounts:
            planning_status = "\u70ed\u70b9\u7a7a\u69fd\u5f85\u586b\u5145"
        else:
            planning_status = "\u5df2\u5b8c\u6210"
        production_states = [item.get("production_status") for item in rows]
        production_failed = sum(state == "failed" for state in production_states)
        production_completed = sum(state in ("generated", "published") for state in production_states)
        production_ready = sum(state == "ready" for state in production_states)
        if production_failed:
            content_status = "\u751f\u4ea7\u5f02\u5e38"
        elif production_states and production_completed == len(production_states):
            content_status = "\u5df2\u5b8c\u6210"
        elif production_ready or production_completed:
            content_status = "\u751f\u4ea7\u4e2d"
        else:
            content_status = "\u5f85\u751f\u4ea7"
        result.append({
            "cycle_id": start.isoformat(), "cycle_start": start,
            "cycle_end": start + timedelta(days=6), "batch_count": len(group),
            "account_count": len(all_accounts) + missing_failed,
            "auto_item_count": sum(len(by_batch.get(batch["id"], [])) for batch in group
                                    if batch["plan_type"] == "auto"),
            "manual_item_count": sum(len(by_batch.get(batch["id"], [])) for batch in group
                                      if batch["plan_type"] == "manual"),
            "content_count": len(rows),
            "regular_slots": sum(item["slot_type"] == "regular" for item in auto_rows),
            "marketing_slots": sum(item["slot_type"] == "marketing_priority" for item in auto_rows),
            "hotspot_slots": sum(item["slot_type"] == "hotspot" for item in auto_rows),
            "topic_uses": len(assigned),
            "unique_topics": len({(planning_topic_type(item), item["topic_id"])
                                   for item in assigned}),
            "success_accounts": completed_accounts,
            "failed_accounts": planning_failed_accounts,
            "planning_status": planning_status,
            "content_status": content_status,
            "updated_at": max(batch["update_time"] for batch in group),
        })
    return result


@app.get("/api/auto-planning/cycles", response_model=list[AutoCycleSummary])
def list_auto_cycles() -> list[dict]:
    batches, items = cycle_records()
    auto_ids = [batch["id"] for batch in batches if batch["plan_type"] == "auto"]
    run_by_batch: dict[int, dict] = {}
    if auto_ids:
        try:
            with connection() as db, db.cursor() as cursor:
                cursor.execute(
                    "SELECT batch_id, config_version, config_json, plan_mode "
                    "FROM godp_auto_plan_run WHERE del_flag='N' AND batch_id IN (" +
                    ",".join(["%s"] * len(auto_ids)) + ")", auto_ids,
                )
                run_by_batch = {row["batch_id"]: row for row in cursor.fetchall()}
        except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
            raise database_error() from exc
    by_batch: dict[int, list[dict]] = {}
    for item in items:
        by_batch.setdefault(item["batch_id"], []).append(item)
    grouped: dict[date, list[dict]] = {}
    for batch in batches:
        if batch["plan_type"] == "auto":
            grouped.setdefault(monday(batch["cycle_start"]), []).append(batch)
    result = []
    for start, group in sorted(grouped.items(), reverse=True):
        run = next((run_by_batch[batch["id"]] for batch in group if batch["id"] in run_by_batch), None)
        run_config = StrategyConfig.model_validate_json(run["config_json"]) if run else None
        rows = [item for batch in group for item in by_batch.get(batch["id"], [])]
        accounts = {item["account_id"] for item in rows}
        failed_ids = {item["account_id"] for item in rows if is_execution_error(item["status"])}
        failed_batches = [batch for batch in group if is_execution_error(batch["status"])]
        missing_failed = sum(batch["account_count"] for batch in group
                             if is_execution_error(batch["status"]) and not by_batch.get(batch["id"]))
        failed = len(failed_ids) + missing_failed
        regular_slots = sum(1 for item in rows if item["slot_type"] == "regular")
        marketing_slots = sum(1 for item in rows if item["slot_type"] == "marketing_priority")
        hotspot_rows = [item for item in rows if item["slot_type"] == "hotspot"]
        hotspot_slots = len(hotspot_rows)
        hotspot_pending = sum(1 for item in hotspot_rows if hotspot_is_pending(item))
        hotspot_submitted = hotspot_slots - hotspot_pending
        pending_hotspot_accounts = {
            item["account_id"] for item in hotspot_rows
            if hotspot_is_pending(item)
        }
        has_execution_exception = bool(failed_ids or failed_batches)
        execution_started = start <= datetime.now(timezone(timedelta(hours=8))).date()
        if has_execution_exception:
            cycle_status = None
        elif not execution_started:
            cycle_status = "已规划"
        elif hotspot_pending > 0:
            cycle_status = "热点空槽待填充"
        else:
            cycle_status = "已完成"
        base_planning_complete_accounts = len(accounts - failed_ids)
        all_topics_determined_accounts = len(
            accounts - failed_ids - pending_hotspot_accounts
        )
        result.append({
            "cycle_id": start.isoformat(), "cycle_start": start,
            "cycle_end": start + timedelta(days=6), "batch_count": len(group),
            "account_count": len(accounts) + missing_failed,
            "base_planning_complete_accounts": base_planning_complete_accounts,
            "all_topics_determined_accounts": all_topics_determined_accounts,
            "planning_failed_accounts": failed,
            "has_execution_exception": has_execution_exception,
            # Keep the previous response fields for existing consumers. Their precise
            # meanings are exposed above under explicit names.
            "success_accounts": all_topics_determined_accounts,
            "failed_accounts": failed,
            "regular_slots": regular_slots,
            "marketing_slots": marketing_slots,
            "hotspot_slots": hotspot_slots,
            "hotspot_submitted": hotspot_submitted,
            "hotspot_pending": hotspot_pending,
            "status": cycle_status,
            "updated_at": max(batch["update_time"] for batch in group),
            "config_version": run["config_version"] if run else None,
            "planning_days": run_config.planning_days if run_config else None,
            "schedule_day": run_config.schedule_day if run_config else None,
            "schedule_time": run_config.schedule_time if run_config else None,
            "allocation_method": run["plan_mode"] if run else None,
        })
    return result


@app.get("/api/auto-planning/cycles/{cycle_id}/failures", response_model=list[AutoFailure])
def list_auto_failures(cycle_id: date) -> list[dict]:
    batches, items = cycle_records()
    relevant = [batch for batch in batches if batch["plan_type"] == "auto"
                and monday(batch["cycle_start"]) == cycle_id]
    if not relevant:
        raise HTTPException(status_code=404, detail="自动策划周期不存在")
    by_batch: dict[int, list[dict]] = {}
    for item in items:
        by_batch.setdefault(item["batch_id"], []).append(item)
    failures = []
    for batch in relevant:
        rows = by_batch.get(batch["id"], [])
        item_failures = [item for item in rows if is_execution_error(item["status"])]
        for item in item_failures:
            failures.append({"batch_code": batch["batch_code"],
                             "account_id": item["account_id"],
                             "account_name": item["account_name"],
                             "reason": item["status"]})
        if is_execution_error(batch["status"]) and not item_failures:
            reason = f"批次状态：{batch['status']}"
            if batch["note"]:
                reason += f"；批次备注：{batch['note']}"
            failures.append({"batch_code": batch["batch_code"], "account_id": None,
                             "account_name": "批次级异常",
                             "reason": reason})
    return failures

