"""Customer-system boundary and the project's local integration state."""

from datetime import datetime, timezone
from hmac import compare_digest
import json
import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator
import pymysql

from .db import connection
from .integration_models import (
    AccountSync,
    ContentReadyInput,
    ContentStatusCallback,
    HistorySync,
    SyncResult,
    TopicSync,
)


router = APIRouter()


def require_integration_token(x_integration_token: str = Header(default="")) -> None:
    expected = os.getenv("INTEGRATION_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="尚未配置系统对接令牌")
    if not compare_digest(x_integration_token, expected):
        raise HTTPException(status_code=401, detail="系统对接令牌无效")


def utc_naive(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def queue_event(cursor, destination: str, event_type: str, payload: dict) -> str:
    event_id = "EVT-" + uuid4().hex.upper()
    envelope = {
        "event_id": event_id,
        "schema_version": "1.0",
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    cursor.execute(
        "INSERT INTO godp_integration_outbox "
        "(event_id, destination, event_type, payload_json) VALUES (%s, %s, %s, %s)",
        (event_id, destination, event_type, as_json(envelope)),
    )
    return event_id


def source_state(cursor, table: str, id_column: str, record_id: str, updated_at: datetime, payload: str) -> str:
    # Table and column names are fixed by callers, never supplied by an HTTP request.
    cursor.execute(
        f"SELECT source_updated_at, payload_json FROM {table} WHERE {id_column}=%s FOR UPDATE",
        (record_id,),
    )
    row = cursor.fetchone()
    if not row:
        return "inserted"
    if updated_at < row["source_updated_at"]:
        return "stale"
    if updated_at == row["source_updated_at"]:
        if payload == row["payload_json"]:
            return "unchanged"
        raise HTTPException(status_code=409, detail=f"{record_id} 的更新时间相同但内容不同")
    return "updated"


def duplicate_ids(records: list, field: str) -> None:
    ids = [getattr(record, field) for record in records]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail=f"同一批次中 {field} 不能重复")
    if any(value.startswith("DEMO-") for value in ids):
        raise HTTPException(status_code=422, detail="DEMO- 前缀保留给本地演示数据")


def summary(batch_id: str, received: int, counters: dict[str, int]) -> SyncResult:
    return SyncResult(source_batch_id=batch_id, received=received, **counters)


def db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="数据库暂不可用")


@router.post("/api/integrations/accounts/sync", response_model=SyncResult, dependencies=[Depends(require_integration_token)])
def sync_accounts(payload: AccountSync) -> SyncResult:
    duplicate_ids(payload.records, "account_id")
    counters = {"inserted": 0, "updated": 0, "unchanged": 0, "stale": 0}
    try:
        with connection() as db, db.cursor() as cursor:
            for record in payload.records:
                raw = as_json(record.model_dump(mode="json"))
                timestamp = utc_naive(record.updated_at)
                state = source_state(cursor, "godp_account_source", "account_id", record.account_id, timestamp, raw)
                counters[state] += 1
                if state in ("stale", "unchanged"):
                    continue
                cursor.execute(
                    "INSERT INTO godp_account_source (account_id, source_updated_at, payload_json) "
                    "VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE "
                    "source_updated_at=VALUES(source_updated_at), payload_json=VALUES(payload_json), "
                    "update_by='integration', del_flag='N'",
                    (record.account_id, timestamp, raw),
                )
                cursor.execute(
                    "INSERT INTO godp_account "
                    "(account_code, account_name, city, persona, marketing_eligible, status, create_by, update_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, 'integration', 'integration') "
                    "ON DUPLICATE KEY UPDATE account_name=VALUES(account_name), city=VALUES(city), "
                    "persona=VALUES(persona), marketing_eligible=VALUES(marketing_eligible), "
                    "status=VALUES(status), update_by='integration', del_flag='N'",
                    (record.account_id, record.account_name, record.city, record.persona,
                     record.marketing_eligible, "启用" if record.enabled else "停用"),
                )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return summary(payload.source_batch_id, len(payload.records), counters)


@router.post("/api/integrations/topics/sync", response_model=SyncResult, dependencies=[Depends(require_integration_token)])
def sync_topics(payload: TopicSync) -> SyncResult:
    duplicate_ids(payload.records, "topic_id")
    counters = {"inserted": 0, "updated": 0, "unchanged": 0, "stale": 0}
    try:
        with connection() as db, db.cursor() as cursor:
            for record in payload.records:
                raw = as_json(record.model_dump(mode="json"))
                timestamp = utc_naive(record.updated_at)
                state = source_state(cursor, "godp_topic_source", "topic_id", record.topic_id, timestamp, raw)
                counters[state] += 1
                if state in ("stale", "unchanged"):
                    continue
                cursor.execute(
                    "INSERT INTO godp_topic_source "
                    "(topic_id, source_updated_at, approval_status, valid_from, valid_to, payload_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                    "source_updated_at=VALUES(source_updated_at), approval_status=VALUES(approval_status), "
                    "valid_from=VALUES(valid_from), valid_to=VALUES(valid_to), "
                    "payload_json=VALUES(payload_json), update_by='integration', del_flag='N'",
                    (record.topic_id, timestamp, record.approval_status,
                     utc_naive(record.valid_from), utc_naive(record.valid_to), raw),
                )
                cursor.execute(
                    "INSERT INTO godp_topic "
                    "(topic_code, title, category, is_marketing, status, create_by, update_by) "
                    "VALUES (%s, %s, %s, %s, %s, 'integration', 'integration') "
                    "ON DUPLICATE KEY UPDATE title=VALUES(title), category=VALUES(category), "
                    "is_marketing=VALUES(is_marketing), status=VALUES(status), "
                    "update_by='integration', del_flag='N'",
                    (record.topic_id, record.title, record.category, record.is_marketing,
                     "可用" if record.enabled else "停用"),
                )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return summary(payload.source_batch_id, len(payload.records), counters)


@router.post("/api/integrations/content-history/sync", response_model=SyncResult, dependencies=[Depends(require_integration_token)])
def sync_content_history(payload: HistorySync) -> SyncResult:
    duplicate_ids(payload.records, "content_id")
    counters = {"inserted": 0, "updated": 0, "unchanged": 0, "stale": 0}
    try:
        with connection() as db, db.cursor() as cursor:
            for record in payload.records:
                raw = as_json(record.model_dump(mode="json"))
                timestamp = utc_naive(record.updated_at)
                state = source_state(cursor, "godp_content_history", "content_id", record.content_id, timestamp, raw)
                counters[state] += 1
                if state in ("stale", "unchanged"):
                    continue
                cursor.execute(
                    "INSERT INTO godp_content_history "
                    "(content_id, account_id, topic_id, published_at, source_updated_at, payload_json) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                    "account_id=VALUES(account_id), topic_id=VALUES(topic_id), "
                    "published_at=VALUES(published_at), source_updated_at=VALUES(source_updated_at), "
                    "payload_json=VALUES(payload_json), update_by='integration', del_flag='N'",
                    (record.content_id, record.account_id, record.topic_id,
                     utc_naive(record.published_at), timestamp, raw),
                )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return summary(payload.source_batch_id, len(payload.records), counters)


def queue_manual_slot(cursor, item_id: int, batch_id: int, batch_code: str, account_id: str,
                      topic_id: str, publish_date: str) -> bool:
    """Create local slot state; output only for synced customer facts."""
    slot_id = f"SLOT-{item_id}"
    if batch_code.startswith("DEMO-"):
        return False
    cursor.execute(
        "SELECT a.account_id FROM godp_account_source a JOIN godp_account p "
        "ON p.account_code=a.account_id WHERE a.account_id=%s AND p.status='启用' AND p.del_flag='N'",
        (account_id,),
    )
    account_ready = cursor.fetchone() is not None
    cursor.execute(
        "SELECT s.topic_id FROM godp_topic_source s JOIN godp_topic t "
        "ON t.topic_code=s.topic_id WHERE s.topic_id=%s AND t.status='可用' AND t.del_flag='N' "
        "AND (t.is_marketing=0 OR s.approval_status='approved') "
        "AND (s.valid_from IS NULL OR s.valid_from<=UTC_TIMESTAMP(6)) "
        "AND (s.valid_to IS NULL OR s.valid_to>=UTC_TIMESTAMP(6))",
        (topic_id,),
    )
    if not account_ready or cursor.fetchone() is None:
        return False
    cursor.execute(
        "INSERT INTO godp_slot_state (item_id, slot_id, version, topic_id) VALUES (%s, %s, 1, %s)",
        (item_id, slot_id, topic_id),
    )
    queue_event(cursor, "planning", "SLOT_PLAN_CREATED", {
        "planning_cycle_id": publish_date,
        "planning_batch_id": batch_id,
        "batch_code": batch_code,
        "account_id": account_id,
        "slot_id": slot_id,
        "version": 1,
        "publish_date": publish_date,
        "slot_type": "manual_extra",
        "slot_status": "planned",
        "allocation_score_source": "manual",
    })
    return True


@router.post("/api/internal/slots/{slot_id}/content-ready", dependencies=[Depends(require_integration_token)])
def content_ready(slot_id: str, payload: ContentReadyInput) -> dict:
    """Called by this project's planning worker after it has the complete Agent input."""
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT s.item_id, s.version, s.topic_id, s.production_status, "
                "i.account_id, i.publish_date, i.slot_type, i.batch_id "
                "FROM godp_slot_state s JOIN godp_planning_item i ON i.id=s.item_id "
                "WHERE s.slot_id=%s AND s.del_flag='N' FOR UPDATE",
                (slot_id,),
            )
            slot = cursor.fetchone()
            if not slot:
                raise HTTPException(status_code=404, detail="槽位不存在")
            if not slot["topic_id"]:
                raise HTTPException(status_code=409, detail="占位槽尚未绑定真实选题")
            if slot["production_status"] in ("generated", "published", "failed"):
                raise HTTPException(status_code=409, detail="当前版本已结束生产；再次生产需要新版本")
            if slot["production_status"] == "ready":
                cursor.execute(
                    "SELECT event_id FROM godp_integration_outbox WHERE event_type='CONTENT_READY' "
                    "AND JSON_UNQUOTE(JSON_EXTRACT(payload_json, '$.slot_id'))=%s "
                    "ORDER BY id DESC LIMIT 1",
                    (slot_id,),
                )
                previous = cursor.fetchone()
                return {"slot_id": slot_id, "version": slot["version"],
                        "event_id": previous["event_id"] if previous else None, "queued": False}
            event_id = queue_event(cursor, "planning", "CONTENT_READY", {
                "planning_cycle_id": slot["publish_date"].isoformat(),
                "planning_batch_id": slot["batch_id"],
                "account_id": slot["account_id"],
                "slot_id": slot_id,
                "version": slot["version"],
                "production_task_id": f"{slot_id}-v{slot['version']}",
                "publish_date": slot["publish_date"].isoformat(),
                "slot_type": slot["slot_type"],
                "topic_id": slot["topic_id"],
                "fit_score": payload.fit_score,
                "tags": payload.tags,
                "agent_type": payload.agent_type,
                "content_agent_input": payload.content_agent_input,
            })
            cursor.execute(
                "UPDATE godp_slot_state SET production_status='ready' WHERE slot_id=%s", (slot_id,),
            )
            db.commit()
            return {"slot_id": slot_id, "version": slot["version"], "event_id": event_id, "queued": True}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/integrations/content-status", dependencies=[Depends(require_integration_token)])
def receive_content_status(payload: ContentStatusCallback) -> dict:
    receipt_json = as_json(payload.model_dump(mode="json"))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT payload_json FROM godp_content_receipt WHERE event_id=%s", (payload.event_id,))
            previous = cursor.fetchone()
            if previous:
                if previous["payload_json"] != receipt_json:
                    raise HTTPException(status_code=409, detail="相同事件 ID 的回传内容不同")
                return {"accepted": True, "applied": False, "reason": "duplicate_event"}
            cursor.execute(
                "SELECT s.item_id, s.version, s.production_status, s.content_id, i.batch_id "
                "FROM godp_slot_state s JOIN godp_planning_item i ON i.id=s.item_id "
                "WHERE s.slot_id=%s AND s.del_flag='N' FOR UPDATE", (payload.slot_id,),
            )
            slot = cursor.fetchone()
            if not slot:
                raise HTTPException(status_code=404, detail="槽位不存在")
            if payload.version > slot["version"]:
                raise HTTPException(status_code=409, detail="回传版本超过当前槽位版本")
            if payload.production_task_id != f"{payload.slot_id}-v{payload.version}":
                raise HTTPException(status_code=422, detail="生产任务 ID 与槽位版本不匹配")
            if payload.version == slot["version"] and slot["content_id"] and payload.content_id \
                    and slot["content_id"] != payload.content_id:
                raise HTTPException(status_code=409, detail="回传的内容 ID 与当前版本不一致")
            cursor.execute("SELECT payload_json FROM godp_content_receipt WHERE event_id=%s", (payload.event_id,))
            previous = cursor.fetchone()
            if previous:
                if previous["payload_json"] != receipt_json:
                    raise HTTPException(status_code=409, detail="相同事件 ID 的回传内容不同")
                return {"accepted": True, "applied": False, "reason": "duplicate_event"}
            cursor.execute(
                "INSERT INTO godp_content_receipt "
                "(event_id, slot_id, version, production_status, content_id, payload_json) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (payload.event_id, payload.slot_id, payload.version, payload.status,
                 payload.content_id, receipt_json),
            )
            old = slot["production_status"]
            reason = "applied"
            new = payload.status
            if payload.version < slot["version"]:
                reason = "old_version"
            elif old == "published" or (old == "generated" and new == "failed"):
                reason = "state_already_advanced"
            elif old == "planned":
                reason = "content_not_ready"
            else:
                cursor.execute(
                    "UPDATE godp_slot_state SET production_status=%s, "
                    "content_id=COALESCE(%s, content_id), "
                    "generated_at=CASE WHEN %s IN ('generated','published') "
                    "THEN COALESCE(generated_at, %s) ELSE generated_at END, "
                    "published_at=CASE WHEN %s='published' THEN %s ELSE published_at END, "
                    "update_by='integration' WHERE slot_id=%s",
                    (new, payload.content_id, new, utc_naive(payload.occurred_at),
                     new, utc_naive(payload.occurred_at), payload.slot_id),
                )
                translated = {"generated": "已生成", "failed": "生成失败", "published": "已发布"}[new]
                cursor.execute(
                    "UPDATE godp_planning_item SET status=%s, update_by='integration' WHERE id=%s",
                    (translated, slot["item_id"]),
                )
                if new in ("generated", "published") and old not in ("generated", "published"):
                    cursor.execute(
                        "UPDATE godp_planning_batch SET content_count=content_count+1, "
                        "update_by='integration' WHERE id=%s", (slot["batch_id"],),
                    )
                cursor.execute(
                    "SELECT COUNT(*) AS total, "
                    "SUM(status IN ('已生成','已发布')) AS completed, "
                    "SUM(status='已发布') AS published, "
                    "SUM(status='生成失败') AS failed "
                    "FROM godp_planning_item WHERE batch_id=%s AND del_flag='N'",
                    (slot["batch_id"],),
                )
                counts = cursor.fetchone()
                if counts["completed"] == counts["total"]:
                    batch_status = "已发布" if counts["published"] == counts["total"] else "已生成"
                elif counts["failed"]:
                    batch_status = "未完成"
                elif counts["completed"]:
                    batch_status = "生成中"
                else:
                    batch_status = "待生成"
                cursor.execute(
                    "UPDATE godp_planning_batch SET status=%s, update_by='integration' WHERE id=%s",
                    (batch_status, slot["batch_id"]),
                )
            db.commit()
            return {"accepted": True, "applied": reason == "applied", "reason": reason}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.get("/api/topics/{topic_id}/usage")
def topic_usage(topic_id: str) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS generated_count FROM godp_slot_state "
                "WHERE topic_id=%s AND production_status IN ('generated','published') "
                "AND del_flag='N'", (topic_id,),
            )
            row = cursor.fetchone()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "generated_count": row["generated_count"]}


class TagTaxonomyInput(BaseModel):
    tags: dict[str, list[str]]

    @model_validator(mode="after")
    def check_tags(self):
        if set(self.tags) != {f"T{index}" for index in range(1, 6)}:
            raise ValueError("固定标签必须包含 T1–T5")
        for values in self.tags.values():
            if not values or len(values) > 100 or len(set(values)) != len(values):
                raise ValueError("每个标签维度需有 1–100 个不重复的值")
            if any(not value.strip() or len(value) > 80 for value in values):
                raise ValueError("标签值不能为空且不能超过 80 字")
        return self


class TopicTagsInput(BaseModel):
    tags: dict[str, Any] = Field(min_length=1)


@router.get("/api/tag-taxonomy")
def get_tag_taxonomy() -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT version, config_json FROM godp_strategy_config "
                "WHERE config_key='tag_taxonomy' AND del_flag='N'",
            )
            row = cursor.fetchone()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"version": row["version"], "tags": json.loads(row["config_json"])} if row else {"version": 0, "tags": {}}


@router.put("/api/tag-taxonomy")
def put_tag_taxonomy(payload: TagTaxonomyInput) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO godp_strategy_config "
                "(config_key, config_json, version, create_by, update_by) "
                "VALUES ('tag_taxonomy', %s, 1, 'system', 'system') "
                "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), "
                "version=version+1, update_by='system', del_flag='N'",
                (as_json(payload.tags),),
            )
            cursor.execute("SELECT version FROM godp_strategy_config WHERE config_key='tag_taxonomy'")
            version = cursor.fetchone()["version"]
            queue_event(cursor, "topics", "TOPIC_TAXONOMY_CHANGED", {
                "taxonomy_version": version, "tags": payload.tags,
            })
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"version": version, "tags": payload.tags}


@router.put("/api/internal/topic-tags/{topic_id}", dependencies=[Depends(require_integration_token)])
def put_topic_tags(topic_id: str, payload: TopicTagsInput) -> dict:
    if not topic_id or topic_id.startswith("DEMO-"):
        raise HTTPException(status_code=422, detail="无效的选题 ID")
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT id FROM godp_topic WHERE topic_code=%s AND del_flag='N'", (topic_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="选题不存在")
            cursor.execute(
                "INSERT INTO godp_topic_tag (topic_id, version, tags_json) VALUES (%s, 1, %s) "
                "ON DUPLICATE KEY UPDATE version=version+1, tags_json=VALUES(tags_json), update_by='system'",
                (topic_id, as_json(payload.tags)),
            )
            cursor.execute("SELECT version FROM godp_topic_tag WHERE topic_id=%s", (topic_id,))
            version = cursor.fetchone()["version"]
            queue_event(cursor, "topics", "TOPIC_TAGS_CHANGED", {
                "topic_id": topic_id, "version": version, "tags": payload.tags,
            })
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "version": version}


@router.get("/api/internal/outbox", dependencies=[Depends(require_integration_token)])
def list_outbox(destination: str | None = None, limit: int = 50) -> list[dict]:
    if destination not in (None, "planning", "topics"):
        raise HTTPException(status_code=422, detail="无效的事件目标")
    limit = max(1, min(limit, 200))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT event_id, destination, event_type, payload_json, delivery_status, "
                "attempts, last_error, create_time FROM godp_integration_outbox "
                "WHERE del_flag='N' AND (%s IS NULL OR destination=%s) "
                "ORDER BY id DESC LIMIT %s", (destination, destination, limit),
            )
            rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    for row in rows:
        row["payload"] = json.loads(row.pop("payload_json"))
    return rows
