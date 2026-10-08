"""Planning workspace API for the four operations tabs."""

from datetime import date, datetime, timedelta, timezone
import json
import os
import secrets
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pymysql

from .db import check_database, connection
from .integration import queue_event, queue_manual_slot, router as integration_router
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
    ManualPreviewInput,
    ManualPreviewResponse,
    ManualTaskSummary,
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


LIFECYCLE_STAGES = ('冷启动验证期', '流量增长期', '转化探索期', '转化放大期', '稳定经营期')


def infer_lifecycle_stage(account_id: str) -> str:
    """Provide a stable demo stage until the account lifecycle snapshot is integrated."""
    score = sum(ord(char) for char in account_id)
    return LIFECYCLE_STAGES[score % len(LIFECYCLE_STAGES)]


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
            "营销" if row.get("slot_type") == "marketing_priority" or source.get("is_marketing") else "普通"
        )
    row["lifecycle_stage"] = row.get("lifecycle_stage") or infer_lifecycle_stage(row.get("account_id", ""))
    row["content_role"] = row.get("content_role") or infer_content_role(row, source if source_payload else {})
    published_at = row.get("published_at")
    known = bool(row.get("slot_id"))
    publish_status = ("待确定选题" if not row.get("topic_id") else
                      "已发布" if published_at else "未发布" if known else "状态未知")
    allow = bool(plan_type == "auto" and known and row.get("topic_id") and not published_at)
    row["publish_status"] = publish_status
    row["allow_replace"] = allow
    row["replace_block_reason"] = "" if allow else (
        "仅支持 AI 自动策划结果" if plan_type != "auto" else
        "发布状态已确认不可替换" if published_at else
        "热点空槽待确定选题" if not row.get("topic_id") else
        "状态暂无法确认，不允许替换"
    )
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
def put_config(config: StrategyConfig, expected_version: int | None = None) -> ConfigResponse:
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
                    "update_by='system', del_flag='N' WHERE config_key='operations'",
                    (config.model_dump_json(), version),
                )
            else:
                cursor.execute(
                    "INSERT INTO godp_strategy_config "
                    "(config_key, config_json, version, create_by, update_by) "
                    "VALUES ('operations', %s, 1, 'system', 'system')",
                    (config.model_dump_json(),),
                )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, create_by, update_by) "
                "VALUES ('operations', %s, %s, '保存', 'system', 'system')",
                (version, config.model_dump_json()),
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
def restore_config(version: int, expected_version: int | None = None) -> ConfigResponse:
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
                "update_by='system' WHERE config_key='operations'",
                (source["config_json"], next_version),
            )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, source_version, create_by, update_by) "
                "VALUES ('operations', %s, %s, '恢复', %s, 'system', 'system')",
                (next_version, source["config_json"], version),
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
                  source_version: int | None = None) -> ConfigResponse:
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
                    "update_by='system', del_flag='N' WHERE config_key='operations'",
                    (snapshot, aggregate_version + 1),
                )
            else:
                cursor.execute(
                    "INSERT INTO godp_strategy_config "
                    "(config_key, config_json, version, create_by, update_by) "
                    "VALUES ('operations', %s, 1, 'system', 'system')", (snapshot,),
                )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, source_version, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, 'system', 'system')",
                (module, module_version, snapshot,
                 '恢复' if source_version is not None else '保存', source_version),
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
    return change_module(module, expected_version, incoming=config)


@app.post("/api/config/modules/{module}/versions/{version}/restore",
          response_model=ConfigResponse)
def restore_config_module(module: str, version: int,
                          expected_version: int | None = None) -> ConfigResponse:
    return change_module(module, expected_version, source_version=version)


@app.get("/api/accounts", response_model=list[AccountOption])
def list_accounts(limit: int = 200) -> list[dict]:
    limit = max(1, min(limit, 1000))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT a.account_code AS account_id, a.account_name, a.city, a.persona, "
                "a.marketing_eligible, a.status, s.payload_json "
                "FROM godp_account a LEFT JOIN godp_account_source s "
                "ON s.account_id=a.account_code AND s.del_flag='N' "
                "WHERE a.del_flag='N' AND a.status='启用' ORDER BY a.id LIMIT %s",
                (limit,),
            )
            rows = cursor.fetchall()
            for row in rows:
                source = json.loads(row.pop("payload_json")) if row["payload_json"] else {}
                row["certified"] = bool(source["certified"]) if "certified" in source else None
                row["followers"] = int(source["followers"]) if "followers" in source else None
                row["traffic_trend"] = source.get("traffic_trend") or "数据不足"
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
                "t.is_marketing, t.status, s.payload_json FROM godp_topic t "
                "LEFT JOIN godp_topic_source s ON s.topic_id=t.topic_code "
                "WHERE t.del_flag='N' AND t.status='可用' "
                "AND (s.id IS NULL OR ((t.is_marketing=0 OR s.approval_status='approved') "
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
            return rows
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.get("/api/batches", response_model=list[BatchSummary])
def list_batches(plan_type: str | None = None, limit: int = 50) -> list[dict]:
    if plan_type not in (None, "manual", "auto"):
        raise HTTPException(status_code=422, detail="无效的策划类型")
    limit = max(1, min(limit, 200))
    try:
        with connection() as db, db.cursor() as cursor:
            if plan_type:
                cursor.execute(
                    "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                    "account_count, content_count, note, create_time AS created_at "
                    "FROM godp_planning_batch WHERE del_flag='N' AND plan_type=%s "
                    "ORDER BY id DESC LIMIT %s",
                    (plan_type, limit),
                )
            else:
                cursor.execute(
                    "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                    "account_count, content_count, note, create_time AS created_at "
                    "FROM godp_planning_batch WHERE del_flag='N' ORDER BY id DESC LIMIT %s",
                    (limit,),
                )
            rows = cursor.fetchall()
            if rows:
                ids = [row["id"] for row in rows]
                cursor.execute(
                    "SELECT batch_id, COUNT(*) AS item_count FROM godp_planning_item "
                    "WHERE del_flag='N' AND batch_id IN (" + ",".join(["%s"] * len(ids)) + ") "
                    "GROUP BY batch_id", ids,
                )
                counts = {row["batch_id"]: row["item_count"] for row in cursor.fetchall()}
                for row in rows:
                    row["result_count"] = counts.get(row["id"], 0)
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
                "s.published_at, s.version, ts.payload_json AS topic_payload "
                "FROM godp_planning_item i LEFT JOIN godp_slot_state s ON s.item_id=i.id "
                "LEFT JOIN godp_topic_source ts ON ts.topic_id=i.topic_id "
                "WHERE i.batch_id=%s AND i.del_flag='N' ORDER BY i.id",
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
                "s.published_at, s.version, ts.payload_json AS topic_payload, "
                "b.batch_code, b.plan_type, "
                "b.cycle_start, b.cycle_end FROM godp_planning_item i "
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id "
                "LEFT JOIN godp_topic_source ts ON ts.topic_id=i.topic_id "
                "JOIN godp_planning_batch b ON b.id=i.batch_id "
                "WHERE i.del_flag='N' AND b.del_flag='N' "
                "AND (i.account_id LIKE %s OR i.account_name LIKE %s) "
                "ORDER BY i.publish_date DESC, i.id DESC LIMIT %s",
                (f"%{account}%", f"%{account}%", limit),
            )
            rows = cursor.fetchall()
            return [enrich_plan_item(row, row["plan_type"]) for row in rows]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


@app.post("/api/items/{item_id}/replace-topic", response_model=ReplaceTopicResponse)
def replace_topic(item_id: int, payload: ReplaceTopicInput) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT i.id, i.account_id, i.account_name, i.publish_date, i.slot_type, "
                "i.topic_id, i.topic_title, i.topic_type, i.status, i.lifecycle_stage, i.content_role, "
                "b.id AS batch_id, b.plan_type, b.batch_code, b.cycle_start, b.cycle_end, "
                "s.slot_id, s.version, s.production_status, s.published_at "
                "FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id "
                "WHERE i.id=%s AND i.del_flag='N' AND b.del_flag='N' FOR UPDATE", (item_id,),
            )
            item = cursor.fetchone()
            if not item:
                raise HTTPException(status_code=404, detail="策划结果不存在")
            if item["plan_type"] != "auto":
                raise HTTPException(status_code=409, detail="当前基线只允许替换 AI 自动策划结果")
            if not item["slot_id"] or item["version"] != payload.expected_version:
                raise HTTPException(status_code=409, detail="结果版本已变化或状态无法确认，请刷新后重试")
            if item["published_at"] is not None:
                raise HTTPException(status_code=409, detail="内容已发布，当前结果不可替换")
            if not item["topic_id"]:
                raise HTTPException(status_code=409, detail="热点空槽尚未确定选题，当前不可替换")
            topics = available_topics(cursor, [payload.new_topic_id])
            topic = topics.get(payload.new_topic_id)
            if topic is None:
                raise HTTPException(status_code=409, detail="新选题不可用、未审核或已过期，请重新选择")
            if item["slot_type"] == "regular" and topic["is_marketing"]:
                raise HTTPException(status_code=409, detail="普通槽位只能替换为普通选题")
            next_version = item["version"] + 1
            topic_payload = {}
            if topic.get("topic_payload"):
                try:
                    topic_payload = json.loads(topic["topic_payload"])
                except (TypeError, json.JSONDecodeError):
                    topic_payload = {}
            cursor.execute(
                "SELECT tags_json FROM godp_topic_tag WHERE topic_id=%s AND del_flag='N'",
                (topic["topic_id"],),
            )
            tag_row = cursor.fetchone()
            tag_values = json.loads(tag_row["tags_json"]) if tag_row else {}
            role_value = tag_values.get("T2", [])
            next_role = role_value[0] if isinstance(role_value, list) and role_value else role_value
            if next_role not in ("流量", "转化"):
                next_role = infer_content_role(item, topic_payload)
            cursor.execute(
                "UPDATE godp_planning_item SET topic_id=%s, topic_title=%s, topic_type=%s, "
                "outline=%s, content_type=%s, content_role=%s, "
                "status='已规划', update_by='system' WHERE id=%s",
                (topic["topic_id"], topic["topic_title"],
                 "营销" if topic["is_marketing"] else "普通",
                 topic_payload.get("outline") or topic_payload.get("summary") or "",
                 topic_payload.get("content_type") or "", next_role, item_id),
            )
            cursor.execute(
                "UPDATE godp_slot_state SET version=%s, topic_id=%s, "
                "production_status='planned', content_id=NULL, generated_at=NULL, "
                "update_by='system' WHERE item_id=%s",
                (next_version, topic["topic_id"], item_id),
            )
            cursor.execute(
                "INSERT INTO godp_planning_adjustment "
                "(item_id, result_version, adjustment_source, old_topic_id, old_topic_title, "
                "new_topic_id, new_topic_title, reason, create_by, update_by) "
                "VALUES (%s, %s, '人工替换', %s, %s, %s, %s, %s, 'system', 'system')",
                (item_id, next_version, item["topic_id"], item["topic_title"],
                 topic["topic_id"], topic["topic_title"], payload.reason),
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
        "batch_code": item["batch_code"], "plan_type": item["plan_type"],
        "cycle_start": item["cycle_start"], "cycle_end": item["cycle_end"],
        "publish_status": "未发布", "allow_replace": True,
        "replace_block_reason": "", "result_version": next_version,
        "content_type": topic_payload.get("content_type", ""),
        "outline": topic_payload.get("outline", "") or topic_payload.get("summary", ""),
        "topic_type": "营销" if topic["is_marketing"] else "普通",
        "lifecycle_stage": item.get("lifecycle_stage") or infer_lifecycle_stage(item["account_id"]),
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
    try:
        with connection() as db, db.cursor() as cursor:
            batch_id = insert_manual_batch(cursor, payload)
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return get_batch(batch_id)


def insert_manual_batch(cursor, payload: ManualPlanCreate) -> int:
    is_demo = any(
        item.account_id.startswith("DEMO-") or item.topic_id.startswith("DEMO-")
        for item in payload.items
    )
    batch_code = ("DEMO-MAN-" if is_demo else "MAN-") + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:6].upper()
    note = (("演示数据｜" if is_demo else "") + payload.note)[:500]
    cursor.execute(
        "INSERT INTO godp_planning_batch "
        "(batch_code, plan_type, status, cycle_start, cycle_end, account_count, "
        "content_count, note, create_by, update_by) "
        "VALUES (%s, 'manual', '待生成', %s, %s, %s, 0, %s, 'system', 'system')",
        (batch_code, payload.publish_date, payload.publish_date, len(payload.items), note),
    )
    batch_id = cursor.lastrowid
    for item in payload.items:
        cursor.execute(
            "INSERT INTO godp_planning_item "
            "(batch_id, account_id, account_name, publish_date, slot_type, "
            "topic_id, topic_title, status, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, 'manual_extra', %s, %s, '待生成', 'system', 'system')",
            (batch_id, item.account_id, item.account_name, payload.publish_date,
             item.topic_id, item.topic_title),
        )
        queue_manual_slot(
            cursor, cursor.lastrowid, batch_id, batch_code,
            item.account_id, item.topic_id, payload.publish_date.isoformat(),
        )
    return batch_id


def available_topics(cursor, topic_ids: list[str]) -> dict[str, dict]:
    placeholders = ",".join(["%s"] * len(topic_ids))
    cursor.execute(
        "SELECT t.topic_code AS topic_id, t.title AS topic_title, t.is_marketing, "
        "s.payload_json AS topic_payload "
        "FROM godp_topic t LEFT JOIN godp_topic_source s ON s.topic_id=t.topic_code "
        f"WHERE t.topic_code IN ({placeholders}) AND t.del_flag='N' AND t.status='可用' "
        "AND (s.id IS NULL OR ((t.is_marketing=0 OR s.approval_status='approved') "
        "AND (s.valid_from IS NULL OR s.valid_from<=UTC_TIMESTAMP(6)) "
        "AND (s.valid_to IS NULL OR s.valid_to>=UTC_TIMESTAMP(6))))",
        topic_ids,
    )
    return {row["topic_id"]: row for row in cursor.fetchall()}


@app.post("/api/manual-plans/previews", response_model=ManualPreviewResponse, status_code=201)
def preview_manual_plan(payload: ManualPreviewInput) -> dict:
    if payload.followers_min is not None and payload.followers_max is not None \
            and payload.followers_min > payload.followers_max:
        raise HTTPException(status_code=422, detail="粉丝量下限不能大于上限")
    catalog = list_accounts(limit=1000)
    filtered = [account for account in catalog if
                  (not payload.keyword or payload.keyword.lower() in
                   f"{account['account_id']} {account['account_name']}".lower()) and
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
    target = payload.target_count or len(candidates)
    if not target or target > len(candidates):
        raise HTTPException(status_code=422, detail="符合条件的账号不足，无法完成本次抽取")
    if payload.target_count is not None:
        candidates = secrets.SystemRandom().sample(candidates, target)
    try:
        with connection() as db, db.cursor() as cursor:
            topics = available_topics(cursor, payload.topic_ids)
            if len(topics) != len(payload.topic_ids):
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
                "(preview_code, publish_date, allocations_json, note, expires_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (preview_id, payload.publish_date,
                 json.dumps([item.model_dump() for item in items], ensure_ascii=False),
                 payload.note, expires_at.replace(tzinfo=None)),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return {"preview_id": preview_id, "publish_date": payload.publish_date,
            "expires_at": expires_at, "items": items, "note": payload.note}


@app.post("/api/manual-plans/previews/{preview_id}/submit", response_model=BatchDetail)
def submit_manual_preview(preview_id: str) -> dict:
    task_code = "MAN-TASK-" + uuid4().hex.upper()
    task_id: int | None = None
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT publish_date, allocations_json, note, status, expires_at, batch_id "
                "FROM godp_manual_preview WHERE preview_code=%s AND del_flag='N' FOR UPDATE",
                (preview_id,),
            )
            preview = cursor.fetchone()
            if not preview:
                raise HTTPException(status_code=404, detail="策划预览不存在")
            if preview["status"] == "submitted" and preview["batch_id"]:
                return get_batch(preview["batch_id"])
            items = [ManualItem.model_validate(item) for item in json.loads(preview["allocations_json"])]
            topic_ids = list({item.topic_id for item in items})
            cursor.execute(
                "INSERT INTO godp_manual_task "
                "(task_code, preview_code, publish_date, planned_account_count, topic_count, status, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, '执行中', 'system', 'system')",
                (task_code, preview_id, preview["publish_date"], len(items), len(topic_ids)),
            )
            task_id = cursor.lastrowid
            db.commit()
            if preview["expires_at"] < datetime.now(timezone.utc).replace(tzinfo=None):
                raise HTTPException(status_code=409, detail="策划预览已过期，请重新预览")
            cursor.execute(
                "SELECT account_code FROM godp_account WHERE account_code IN (" +
                ",".join(["%s"] * len(items)) + ") AND status='启用' AND del_flag='N'",
                [item.account_id for item in items],
            )
            if len(cursor.fetchall()) != len(items):
                raise HTTPException(status_code=409, detail="账号状态已变化，请重新预览")
            topics = available_topics(cursor, topic_ids)
            if len(topics) != len(topic_ids):
                raise HTTPException(status_code=409, detail="选题状态已变化，请重新预览")
            cursor.execute(
                "SELECT account_code, marketing_eligible FROM godp_account WHERE account_code IN (" +
                ",".join(["%s"] * len(items)) + ")",
                [item.account_id for item in items],
            )
            eligible = {row["account_code"]: row["marketing_eligible"] for row in cursor.fetchall()}
            if any(topics[item.topic_id]["is_marketing"] and not eligible.get(item.account_id)
                   for item in items):
                raise HTTPException(status_code=409, detail="账号营销资格已变化，请重新预览")
            batch_id = insert_manual_batch(cursor, ManualPlanCreate(
                publish_date=preview["publish_date"], items=items, note=preview["note"],
            ))
            cursor.execute(
                "UPDATE godp_manual_preview SET status='submitted', batch_id=%s "
                "WHERE preview_code=%s", (batch_id, preview_id),
            )
            cursor.execute(
                "UPDATE godp_manual_task SET status='已完成', result_count=%s, batch_id=%s, "
                "update_by='system' WHERE id=%s", (len(items), batch_id, task_id),
            )
            db.commit()
    except HTTPException as exc:
        if task_id is not None:
            try:
                with connection() as db, db.cursor() as cursor:
                    cursor.execute(
                        "UPDATE godp_manual_task SET status='执行失败', failure_count=planned_account_count, "
                        "failure_reason=%s, last_error=%s, update_by='system' WHERE id=%s",
                        (exc.detail, exc.detail, task_id),
                    )
                    db.commit()
            except (pymysql.MySQLError, RuntimeError, ValueError):
                pass
        raise
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        if task_id is not None:
            try:
                with connection() as db, db.cursor() as cursor:
                    cursor.execute(
                        "UPDATE godp_manual_task SET status='执行失败', failure_count=planned_account_count, "
                        "failure_reason=%s, last_error=%s, update_by='system' WHERE id=%s",
                        ("系统异常，请查看服务日志", str(exc)[:500], task_id),
                    )
                    db.commit()
            except (pymysql.MySQLError, RuntimeError, ValueError):
                pass
        raise database_error() from exc
    return get_batch(batch_id)


@app.get("/api/manual-plans/tasks", response_model=list[ManualTaskSummary])
def list_manual_tasks(limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, task_code, preview_code, publish_date, planned_account_count, "
                "result_count, failure_count, topic_count, status, failure_reason, batch_id, "
                "last_error, create_time AS created_at, update_time AS updated_at "
                "FROM godp_manual_task WHERE del_flag='N' ORDER BY id DESC LIMIT %s", (limit,),
            )
            return cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


def cycle_records() -> tuple[list[dict], list[dict]]:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                "account_count, content_count, note, update_time "
                "FROM godp_planning_batch WHERE del_flag='N' ORDER BY id DESC LIMIT 200"
            )
            batches = cursor.fetchall()
            if not batches:
                return [], []
            placeholders = ",".join(["%s"] * len(batches))
            cursor.execute(
                "SELECT i.batch_id, i.account_id, i.account_name, i.slot_type, i.topic_id, i.status, "
                "s.production_status "
                "FROM godp_planning_item i LEFT JOIN godp_slot_state s ON s.item_id=i.id "
                f"WHERE i.del_flag='N' AND i.batch_id IN ({placeholders})",
                [batch["id"] for batch in batches],
            )
            items = cursor.fetchall()
            return batches, items
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


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
                "s.published_at, s.version, ts.payload_json AS topic_payload, "
                "b.batch_code, b.plan_type, b.cycle_start, b.cycle_end "
                "FROM godp_planning_item i "
                "JOIN godp_planning_batch b ON b.id=i.batch_id "
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id "
                "LEFT JOIN godp_topic_source ts ON ts.topic_id=i.topic_id "
                "WHERE i.del_flag='N' AND b.del_flag='N' "
                "AND b.cycle_start >= %s AND b.cycle_start < %s "
                "ORDER BY i.publish_date, i.account_name, i.id LIMIT %s",
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
        auto_accounts = {item["account_id"] for item in auto_rows}
        failed_ids = {item["account_id"] for item in auto_rows if "失败" in item["status"]}
        pending_hotspot_accounts = {
            item["account_id"] for item in auto_rows
            if hotspot_is_pending(item)
        }
        missing_failed = sum(batch["account_count"] for batch in group
                             if batch["plan_type"] == "auto" and "失败" in batch["status"]
                             and not by_batch.get(batch["id"]))
        assigned = [item for item in rows if item["topic_id"] and "失败" not in item["status"]]
        result.append({
            "cycle_id": start.isoformat(), "cycle_start": start,
            "cycle_end": start + timedelta(days=6), "batch_count": len(group),
            "account_count": len(auto_accounts) + missing_failed,
            "auto_item_count": sum(len(by_batch.get(batch["id"], [])) for batch in group
                                   if batch["plan_type"] == "auto"),
            "manual_item_count": sum(len(by_batch.get(batch["id"], [])) for batch in group
                                     if batch["plan_type"] == "manual"),
            "content_count": len(rows),
            "regular_slots": sum(item["slot_type"] == "regular" for item in auto_rows),
            "marketing_slots": sum(item["slot_type"] == "marketing_priority" for item in auto_rows),
            "hotspot_slots": sum(item["slot_type"] == "hotspot" for item in auto_rows),
            "topic_uses": len(assigned),
            "unique_topics": len({item["topic_id"] for item in assigned}),
            "success_accounts": len(auto_accounts - failed_ids - pending_hotspot_accounts),
            "failed_accounts": len(failed_ids) + missing_failed,
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
        failed_ids = {item["account_id"] for item in rows if "失败" in item["status"]}
        missing_failed = sum(batch["account_count"] for batch in group
                             if "失败" in batch["status"] and not by_batch.get(batch["id"]))
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
        execution_started = start <= datetime.now(timezone(timedelta(hours=8))).date()
        if not execution_started:
            cycle_status = "已规划"
        elif hotspot_pending > 0 or failed:
            cycle_status = "热点空槽待填充"
        else:
            cycle_status = "已完成"
        result.append({
            "cycle_id": start.isoformat(), "cycle_start": start,
            "cycle_end": start + timedelta(days=6), "batch_count": len(group),
            "account_count": len(accounts) + missing_failed,
            "success_accounts": len(accounts - failed_ids - pending_hotspot_accounts),
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
        for item in rows:
            if "失败" in item["status"]:
                failures.append({"batch_code": batch["batch_code"],
                                 "account_id": item["account_id"],
                                 "account_name": item["account_name"],
                                 "reason": item["status"]})
        if "失败" in batch["status"] and not rows:
            failures.append({"batch_code": batch["batch_code"], "account_id": None,
                             "account_name": "未记录账号", "reason": batch["note"] or "批次失败，缺少账号级明细"})
    return failures

