"""Customer-system boundary and the project's local integration state."""

from datetime import datetime, timedelta, timezone
from hmac import compare_digest
import json
import os
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
import pymysql

from .db import connection
from .integration_models import (
    AccountSync,
    ContentReadyInput,
    ContentStatusCallback,
    PublicationStatusCallback,
    OfficialUsageQuery,
    OfficialUsageUpdate,
    HistorySync,
    HotspotTopicSync,
    MarketingTopicSync,
    SyncResult,
    TopicSync,
)
from .taxonomy import DIMENSIONS, active_tag_names, normalize_taxonomy


router = APIRouter()


def effective_topic_type(slot_type: str, is_marketing: bool, frozen: str | None = None) -> str:
    if frozen in ("普通", "营销", "热点"):
        return frozen
    if slot_type == "hotspot":
        return "热点"
    return "营销" if is_marketing else "普通"


def single_choice_labels(tags: dict) -> dict[str, str] | None:
    if not isinstance(tags, dict):
        return None
    labels: dict[str, str] = {}
    for index in range(1, 7):
        value = tags.get(f"T{index}", tags.get(f"t{index}"))
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, str) or not value.strip() or len(value) > 80:
            return None
        labels[f"t{index}"] = value.strip()
    return labels


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


def source_record_json(record: BaseModel, added_fields: set[str]) -> str:
    """Keep retries from older clients byte-identical after optional fields are added."""
    absent = added_fields - record.model_fields_set
    return as_json(record.model_dump(mode="json", exclude=absent))


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


def full_snapshot_start(cursor, payload: AccountSync | TopicSync,
                        source_type: str) -> tuple[datetime, str] | SyncResult:
    request_json = as_json(payload.model_dump(mode="json", exclude_unset=True))
    cursor.execute(
        "SELECT payload_json, result_json FROM godp_source_sync_run "
        "WHERE source_type=%s AND source_batch_id=%s",
        (source_type, payload.source_batch_id),
    )
    previous = cursor.fetchone()
    if previous:
        if previous["payload_json"] != request_json:
            raise HTTPException(status_code=409, detail="相同批次 ID 的全量快照内容不同")
        return SyncResult.model_validate_json(previous["result_json"])
    cursor.execute(
        "SELECT MAX(source_snapshot_at) AS latest_at FROM godp_source_sync_run "
        "WHERE source_type=%s AND del_flag='N'", (source_type,),
    )
    latest_at = cursor.fetchone()["latest_at"]
    snapshot_at = utc_naive(payload.snapshot_at) or datetime.now(timezone.utc).replace(tzinfo=None)
    if latest_at and snapshot_at <= latest_at:
        raise HTTPException(status_code=409, detail="全量快照时间未晚于已接收快照")
    return snapshot_at, request_json


def full_snapshot_finish(cursor, payload: AccountSync | TopicSync, source_type: str,
                         snapshot_at: datetime, request_json: str,
                         counters: dict[str, int]) -> SyncResult:
    if source_type == "account":
        cursor.execute(
            "SELECT s.account_id FROM godp_account_source s "
            "JOIN godp_account a ON a.account_code=s.account_id "
            "WHERE s.del_flag='N' AND s.active_in_snapshot=1 "
            "AND s.account_id NOT LIKE 'DEMO-%%' FOR UPDATE"
        )
        active = {row["account_id"] for row in cursor.fetchall()}
        incoming = {record.account_id for record in payload.records}
        missing = active - incoming
        for account_id in missing:
            cursor.execute(
                "UPDATE godp_account_source SET active_in_snapshot=0, "
                "update_by='integration' WHERE account_id=%s", (account_id,),
            )
            cursor.execute(
                "UPDATE godp_account SET status='停用', update_by='integration' "
                "WHERE account_code=%s", (account_id,),
            )
    else:
        cursor.execute(
            "SELECT s.topic_id FROM godp_topic_source s "
            "JOIN godp_topic t ON t.topic_code=s.topic_id "
            "WHERE s.del_flag='N' AND s.active_in_snapshot=1 AND t.is_marketing=0 "
            "AND s.topic_id NOT LIKE 'DEMO-%%' FOR UPDATE"
        )
        active = {row["topic_id"] for row in cursor.fetchall()}
        incoming = {record.topic_id for record in payload.records}
        missing = active - incoming
        for topic_id in missing:
            cursor.execute(
                "UPDATE godp_topic_source SET active_in_snapshot=0, "
                "update_by='integration' WHERE topic_id=%s", (topic_id,),
            )
            cursor.execute(
                "UPDATE godp_topic SET status='停用', update_by='integration' "
                "WHERE topic_code=%s", (topic_id,),
            )
    result = summary(payload.source_batch_id, len(payload.records),
                     {**counters, "deactivated": len(missing)})
    cursor.execute(
        "INSERT INTO godp_source_sync_run "
        "(source_type, source_batch_id, source_snapshot_at, payload_json, result_json) "
        "VALUES (%s, %s, %s, %s, %s)",
        (source_type, payload.source_batch_id, snapshot_at, request_json,
         as_json(result.model_dump(mode="json"))),
    )
    return result


def db_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail="数据库暂不可用")


@router.post("/api/integrations/accounts/sync", response_model=SyncResult, dependencies=[Depends(require_integration_token)])
def sync_accounts(payload: AccountSync) -> SyncResult:
    duplicate_ids(payload.records, "account_id")
    counters = {"inserted": 0, "updated": 0, "unchanged": 0, "stale": 0}
    try:
        with connection() as db, db.cursor() as cursor:
            lock_name = "godp:account-source-sync"
            cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (lock_name,))
            if cursor.fetchone()["acquired"] != 1:
                raise HTTPException(status_code=409, detail="账号同步正在执行，请稍后重试")
            try:
                full = full_snapshot_start(cursor, payload, "account") if payload.mode == "full" else None
                if isinstance(full, SyncResult):
                    return full
                for record in payload.records:
                    raw = source_record_json(record, {
                        "account_alias", "account_status", "certification_status",
                        "account_persona", "account_tags", "follower_count", "interaction_data",
                    })
                    timestamp = utc_naive(record.updated_at)
                    state = source_state(cursor, "godp_account_source", "account_id", record.account_id, timestamp, raw)
                    counters[state] += 1
                    if state == "stale":
                        if payload.mode == "full":
                            raise HTTPException(status_code=409, detail=f"账号 {record.account_id} 的记录版本早于本地")
                        continue
                    if state == "unchanged" and payload.mode == "incremental":
                        continue
                    cursor.execute(
                        "INSERT INTO godp_account_source "
                        "(account_id, source_updated_at, active_in_snapshot, payload_json) "
                        "VALUES (%s, %s, 1, %s) ON DUPLICATE KEY UPDATE "
                        "source_updated_at=VALUES(source_updated_at), active_in_snapshot=1, "
                        "payload_json=VALUES(payload_json), update_by='integration', del_flag='N'",
                        (record.account_id, timestamp, raw),
                    )
                    cursor.execute(
                        "INSERT INTO godp_account "
                        "(account_code, account_name, city, persona, marketing_eligible, status, create_by, update_by) "
                        "VALUES (%s, %s, %s, %s, %s, %s, 'integration', 'integration') "
                        "ON DUPLICATE KEY UPDATE account_name=VALUES(account_name), city=VALUES(city), "
                        "persona=VALUES(persona), marketing_eligible=VALUES(marketing_eligible), "
                        "status=VALUES(status), update_by='integration', del_flag='N'",
                        (record.account_id, record.account_name, record.city,
                         record.account_persona if record.account_persona is not None else record.persona,
                         record.is_marketing_account if record.is_marketing_account is not None
                         else record.marketing_eligible,
                         "启用" if (record.account_status if record.account_status is not None else record.enabled)
                         else "停用"),
                    )
                result = (full_snapshot_finish(cursor, payload, "account", full[0], full[1], counters)
                          if full else summary(payload.source_batch_id, len(payload.records), counters))
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/integrations/topics/sync", response_model=SyncResult, dependencies=[Depends(require_integration_token)])
def sync_topics(payload: TopicSync) -> SyncResult:
    duplicate_ids(payload.records, "topic_id")
    counters = {"inserted": 0, "updated": 0, "unchanged": 0, "stale": 0}
    try:
        with connection() as db, db.cursor() as cursor:
            lock_name = "godp:ordinary-topic-source-sync"
            cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (lock_name,))
            if cursor.fetchone()["acquired"] != 1:
                raise HTTPException(status_code=409, detail="普通选题同步正在执行，请稍后重试")
            try:
                full = full_snapshot_start(cursor, payload, "topic") if payload.mode == "full" else None
                if isinstance(full, SyncResult):
                    return full
                for record in payload.records:
                    raw = source_record_json(record, {"status"})
                    timestamp = utc_naive(record.updated_at)
                    state = source_state(cursor, "godp_topic_source", "topic_id", record.topic_id, timestamp, raw)
                    counters[state] += 1
                    if state == "stale":
                        if payload.mode == "full":
                            raise HTTPException(status_code=409, detail=f"选题 {record.topic_id} 的记录版本早于本地")
                        continue
                    if state == "unchanged" and payload.mode == "incremental":
                        continue
                    cursor.execute(
                        "INSERT INTO godp_topic_source "
                        "(topic_id, source_updated_at, active_in_snapshot, approval_status, "
                        "valid_from, valid_to, payload_json) "
                        "VALUES (%s, %s, 1, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE "
                        "source_updated_at=VALUES(source_updated_at), active_in_snapshot=1, "
                        "approval_status=VALUES(approval_status), valid_from=VALUES(valid_from), "
                        "valid_to=VALUES(valid_to), payload_json=VALUES(payload_json), "
                        "update_by='integration', del_flag='N'",
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
                         "可用" if (record.status if record.status is not None else record.enabled)
                         else "停用"),
                    )
                result = (full_snapshot_finish(cursor, payload, "topic", full[0], full[1], counters)
                          if full else summary(payload.source_batch_id, len(payload.records), counters))
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.get("/api/internal/source-sync-status/{source_type}", dependencies=[Depends(require_integration_token)])
def source_sync_status(source_type: str) -> dict:
    if source_type not in ("account", "topic"):
        raise HTTPException(status_code=422, detail="来源类型只能为 account 或 topic")
    count_sql = (
        "SELECT COUNT(*) AS active_count FROM godp_account_source s "
        "JOIN godp_account a ON a.account_code=s.account_id "
        "WHERE s.del_flag='N' AND s.active_in_snapshot=1 AND a.status='启用' "
        "AND s.account_id NOT LIKE 'DEMO-%%'"
        if source_type == "account" else
        "SELECT COUNT(*) AS active_count FROM godp_topic_source s "
        "JOIN godp_topic t ON t.topic_code=s.topic_id "
        "WHERE s.del_flag='N' AND s.active_in_snapshot=1 AND t.status='可用' "
        "AND t.is_marketing=0 AND s.topic_id NOT LIKE 'DEMO-%%'"
    )
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT source_batch_id, source_snapshot_at, result_json "
                "FROM godp_source_sync_run WHERE source_type=%s AND del_flag='N' "
                "ORDER BY source_snapshot_at DESC, id DESC LIMIT 1", (source_type,),
            )
            latest = cursor.fetchone()
            if not latest:
                return {"synced": False, "source_batch_id": None,
                        "snapshot_at": None, "received": None,
                        "deactivated": None, "active_count": None}
            cursor.execute(count_sql)
            active_count = cursor.fetchone()["active_count"]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    result = json.loads(latest["result_json"])
    return {"synced": True, "source_batch_id": latest["source_batch_id"],
            "snapshot_at": latest["source_snapshot_at"].isoformat() + "Z",
            "received": result["received"], "deactivated": result["deactivated"],
            "active_count": active_count}


@router.post("/api/integrations/marketing-topics/sync", dependencies=[Depends(require_integration_token)])
def sync_marketing_topics(payload: MarketingTopicSync) -> dict:
    """IF-03 local contract: an atomic full snapshot of account-bound marketing topics."""
    request_json = as_json(payload.model_dump(mode="json"))
    snapshot_at = utc_naive(payload.snapshot_at)
    lock_name = "godp:marketing-topic-sync"
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (lock_name,))
            if cursor.fetchone()["acquired"] != 1:
                raise HTTPException(status_code=409, detail="营销选题同步正在执行，请稍后重试")
            try:
                cursor.execute(
                    "SELECT payload_json, result_json FROM godp_marketing_sync_run "
                    "WHERE source_batch_id=%s", (payload.source_batch_id,),
                )
                previous_run = cursor.fetchone()
                if previous_run:
                    if previous_run["payload_json"] != request_json:
                        raise HTTPException(status_code=409, detail="相同批次 ID 的营销选题快照内容不同")
                    return json.loads(previous_run["result_json"])
                cursor.execute(
                    "SELECT MAX(source_snapshot_at) AS latest_at FROM godp_marketing_sync_run "
                    "WHERE del_flag='N'"
                )
                latest_at = cursor.fetchone()["latest_at"]
                if latest_at and snapshot_at <= latest_at:
                    raise HTTPException(status_code=409, detail="营销选题快照时间未晚于已接收快照")
                cursor.execute(
                    "SELECT topic_id, payload_json, active_in_snapshot FROM godp_marketing_topic_source "
                    "WHERE del_flag='N' FOR UPDATE"
                )
                existing = {row["topic_id"]: row for row in cursor.fetchall()}
                incoming = {record.topic_id for record in payload.records}
                counters = {"inserted": 0, "updated": 0, "unchanged": 0, "deactivated": 0}
                for record in payload.records:
                    raw = as_json(record.model_dump(mode="json"))
                    old = existing.get(record.topic_id)
                    if old is None:
                        counters["inserted"] += 1
                    elif old["payload_json"] == raw and old["active_in_snapshot"]:
                        counters["unchanged"] += 1
                    else:
                        counters["updated"] += 1
                    cursor.execute(
                        "INSERT INTO godp_marketing_topic_source "
                        "(topic_id, account_id, source_batch_id, source_snapshot_at, "
                        "approval_status, approved_at, valid_from, valid_to, enabled, "
                        "active_in_snapshot, payload_json) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s) "
                        "ON DUPLICATE KEY UPDATE account_id=VALUES(account_id), "
                        "source_batch_id=VALUES(source_batch_id), "
                        "source_snapshot_at=VALUES(source_snapshot_at), "
                        "approval_status=VALUES(approval_status), "
                        "approved_at=VALUES(approved_at), valid_from=VALUES(valid_from), "
                        "valid_to=VALUES(valid_to), enabled=VALUES(enabled), "
                        "active_in_snapshot=1, payload_json=VALUES(payload_json), "
                        "update_by='integration', del_flag='N'",
                        (record.topic_id, record.account_id, payload.source_batch_id,
                         snapshot_at, record.approval_status, utc_naive(record.approved_at),
                         utc_naive(record.valid_from), utc_naive(record.valid_to),
                         record.enabled, raw),
                    )
                for topic_id, old in existing.items():
                    if topic_id not in incoming and old["active_in_snapshot"]:
                        cursor.execute(
                            "UPDATE godp_marketing_topic_source SET active_in_snapshot=0, "
                            "update_by='integration' WHERE topic_id=%s", (topic_id,),
                        )
                        counters["deactivated"] += 1
                result = {"source_batch_id": payload.source_batch_id,
                          "snapshot_at": payload.snapshot_at.isoformat(),
                          "received": len(payload.records), **counters}
                cursor.execute(
                    "INSERT INTO godp_marketing_sync_run "
                    "(source_batch_id, source_snapshot_at, payload_json, result_json) "
                    "VALUES (%s, %s, %s, %s)",
                    (payload.source_batch_id, snapshot_at, request_json, as_json(result)),
                )
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/integrations/hotspot-topics/sync", dependencies=[Depends(require_integration_token)])
def sync_hotspot_topics(payload: HotspotTopicSync) -> dict:
    """IF-04 local contract: an atomic full snapshot of hotspot topics."""
    request_json = as_json(payload.model_dump(mode="json"))
    snapshot_at = utc_naive(payload.snapshot_at)
    lock_name = "godp:hotspot-topic-sync"
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (lock_name,))
            if cursor.fetchone()["acquired"] != 1:
                raise HTTPException(status_code=409, detail="热点选题同步正在执行，请稍后重试")
            try:
                cursor.execute(
                    "SELECT payload_json, result_json FROM godp_hotspot_sync_run "
                    "WHERE source_batch_id=%s", (payload.source_batch_id,),
                )
                previous_run = cursor.fetchone()
                if previous_run:
                    if previous_run["payload_json"] != request_json:
                        raise HTTPException(status_code=409, detail="相同批次 ID 的热点选题快照内容不同")
                    return json.loads(previous_run["result_json"])
                cursor.execute(
                    "SELECT MAX(source_snapshot_at) AS latest_at FROM godp_hotspot_sync_run "
                    "WHERE del_flag='N'"
                )
                latest_at = cursor.fetchone()["latest_at"]
                if latest_at and snapshot_at <= latest_at:
                    raise HTTPException(status_code=409, detail="热点选题快照时间未晚于已接收快照")
                cursor.execute(
                    "SELECT topic_id, payload_json, active_in_snapshot FROM godp_hotspot_topic_source "
                    "WHERE del_flag='N' FOR UPDATE"
                )
                existing = {row["topic_id"]: row for row in cursor.fetchall()}
                incoming = {record.topic_id for record in payload.records}
                counters = {"inserted": 0, "updated": 0, "unchanged": 0, "deactivated": 0}
                for record in payload.records:
                    raw = as_json(record.model_dump(mode="json"))
                    old = existing.get(record.topic_id)
                    if old is None:
                        counters["inserted"] += 1
                    elif old["payload_json"] == raw and old["active_in_snapshot"]:
                        counters["unchanged"] += 1
                    else:
                        counters["updated"] += 1
                    cursor.execute(
                        "INSERT INTO godp_hotspot_topic_source "
                        "(topic_id, source_batch_id, source_snapshot_at, valid_from, valid_to, "
                        "enabled, active_in_snapshot, payload_json) "
                        "VALUES (%s, %s, %s, %s, %s, %s, 1, %s) "
                        "ON DUPLICATE KEY UPDATE source_batch_id=VALUES(source_batch_id), "
                        "source_snapshot_at=VALUES(source_snapshot_at), "
                        "valid_from=VALUES(valid_from), valid_to=VALUES(valid_to), "
                        "enabled=VALUES(enabled), active_in_snapshot=1, "
                        "payload_json=VALUES(payload_json), update_by='integration', del_flag='N'",
                        (record.topic_id, payload.source_batch_id, snapshot_at,
                         utc_naive(record.valid_from), utc_naive(record.valid_to),
                         record.enabled, raw),
                    )
                for topic_id, old in existing.items():
                    if topic_id not in incoming and old["active_in_snapshot"]:
                        cursor.execute(
                            "UPDATE godp_hotspot_topic_source SET active_in_snapshot=0, "
                            "update_by='integration' WHERE topic_id=%s", (topic_id,),
                        )
                        counters["deactivated"] += 1
                result = {"source_batch_id": payload.source_batch_id,
                          "snapshot_at": payload.snapshot_at.isoformat(),
                          "received": len(payload.records), **counters}
                cursor.execute(
                    "INSERT INTO godp_hotspot_sync_run "
                    "(source_batch_id, source_snapshot_at, payload_json, result_json) "
                    "VALUES (%s, %s, %s, %s)",
                    (payload.source_batch_id, snapshot_at, request_json, as_json(result)),
                )
                db.commit()
                return result
            except Exception:
                db.rollback()
                raise
            finally:
                cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


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


@router.get("/api/internal/marketing-topics/sync-status", dependencies=[Depends(require_integration_token)])
def marketing_sync_status() -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT source_batch_id, source_snapshot_at, result_json "
                "FROM godp_marketing_sync_run WHERE del_flag='N' "
                "ORDER BY source_snapshot_at DESC, id DESC LIMIT 1"
            )
            latest = cursor.fetchone()
            if not latest:
                return {"synced": False, "source_batch_id": None,
                        "snapshot_at": None, "received": None, "active_count": None}
            cursor.execute(
                "SELECT COUNT(*) AS active_count FROM godp_marketing_topic_source "
                "WHERE del_flag='N' AND active_in_snapshot=1 AND enabled=1"
            )
            active_count = cursor.fetchone()["active_count"]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"synced": True, "source_batch_id": latest["source_batch_id"],
            "snapshot_at": latest["source_snapshot_at"].isoformat() + "Z",
            "received": json.loads(latest["result_json"])["received"],
            "active_count": active_count}


@router.get("/api/internal/hotspot-topics/sync-status", dependencies=[Depends(require_integration_token)])
def hotspot_sync_status() -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT source_batch_id, source_snapshot_at, result_json "
                "FROM godp_hotspot_sync_run WHERE del_flag='N' "
                "ORDER BY source_snapshot_at DESC, id DESC LIMIT 1"
            )
            latest = cursor.fetchone()
            if not latest:
                return {"synced": False, "source_batch_id": None,
                        "snapshot_at": None, "received": None, "active_count": None}
            cursor.execute(
                "SELECT COUNT(*) AS active_count FROM godp_hotspot_topic_source "
                "WHERE del_flag='N' AND active_in_snapshot=1 AND enabled=1"
            )
            active_count = cursor.fetchone()["active_count"]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"synced": True, "source_batch_id": latest["source_batch_id"],
            "snapshot_at": latest["source_snapshot_at"].isoformat() + "Z",
            "received": json.loads(latest["result_json"])["received"],
            "active_count": active_count}


def queue_manual_slot(cursor, item_id: int, batch_id: int, batch_code: str, account_id: str,
                      topic_id: str, publish_date: str) -> bool:
    """Create local slot state; output only for synced customer facts."""
    slot_id = f"SLOT-{item_id}"
    if batch_code.startswith("DEMO-"):
        return False
    cursor.execute(
        "SELECT a.account_id FROM godp_account_source a JOIN godp_account p "
        "ON p.account_code=a.account_id WHERE a.account_id=%s AND a.active_in_snapshot=1 "
        "AND p.status='启用' AND p.del_flag='N'",
        (account_id,),
    )
    account_ready = cursor.fetchone() is not None
    cursor.execute(
        "SELECT s.topic_id FROM godp_topic_source s JOIN godp_topic t "
        "ON t.topic_code=s.topic_id WHERE s.topic_id=%s AND t.status='可用' AND t.del_flag='N' "
        "AND s.active_in_snapshot=1 AND (t.is_marketing=0 OR s.approval_status='approved') "
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


@router.get("/api/integrations/accounts/{account_id}/current-plan", dependencies=[Depends(require_integration_token)])
def current_producible_plan(account_id: str) -> dict:
    """IF-05: read the current effective, unpublished results without locking them."""
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    week_start = today - timedelta(days=today.weekday())
    sql = (
        "SELECT i.id AS planning_result_id, i.publish_date, i.topic_id, "
        "i.topic_title AS title, i.slot_type, i.topic_type, i.outline, i.content_type, "
        "s.slot_id, s.version AS result_version, "
        "t.is_marketing, ts.payload_json AS topic_payload, b.cycle_start, b.cycle_end "
        "FROM godp_planning_item i "
        "JOIN godp_planning_batch b ON b.id=i.batch_id "
        "JOIN godp_slot_state s ON s.item_id=i.id "
        "LEFT JOIN godp_topic t ON t.topic_code=i.topic_id AND t.del_flag='N' "
        "LEFT JOIN godp_topic_source ts ON ts.topic_id=i.topic_id AND ts.del_flag='N' "
        "WHERE i.account_id=%s AND b.cycle_start=%s "
        "AND i.del_flag='N' AND b.del_flag='N' AND s.del_flag='N' "
        "AND b.batch_code NOT LIKE 'DEMO-%%' "
        "AND i.topic_id<>'' AND s.topic_id=i.topic_id AND s.published_at IS NULL "
        "AND i.status<>'已发布' "
        "ORDER BY i.publish_date, i.id"
    )
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(sql, (account_id, week_start))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute(
                    "SELECT MIN(b.cycle_start) AS cycle_start "
                    "FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
                    "JOIN godp_slot_state s ON s.item_id=i.id "
                    "WHERE i.account_id=%s AND b.cycle_start>%s "
                    "AND i.del_flag='N' AND b.del_flag='N' AND s.del_flag='N' "
                    "AND b.batch_code NOT LIKE 'DEMO-%%' "
                    "AND i.topic_id<>'' AND s.topic_id=i.topic_id AND s.published_at IS NULL "
                    "AND i.status<>'已发布'",
                    (account_id, week_start),
                )
                next_cycle = cursor.fetchone()["cycle_start"]
                if next_cycle:
                    cursor.execute(sql, (account_id, next_cycle))
                    rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    if not rows:
        return {"account_id": account_id, "planning_cycle": None, "planning_contents": []}
    contents = []
    for row in rows:
        try:
            topic = json.loads(row["topic_payload"]) if row["topic_payload"] and row["topic_type"] not in ("营销", "热点") else {}
            if not isinstance(topic, dict):
                topic = {}
        except (TypeError, json.JSONDecodeError):
            topic = {}
        contents.append({
            "planning_result_id": row["planning_result_id"],
            "slot_id": row["slot_id"],
            "result_version": row["result_version"],
            "publish_date": row["publish_date"].isoformat(),
            "topic_id": row["topic_id"],
            "topic_type": effective_topic_type(row["slot_type"], bool(row["is_marketing"]), row["topic_type"]),
            "title": row["title"],
            "outline": row["outline"] or topic.get("outline") or topic.get("summary") or "",
            "content_type": row["content_type"] or topic.get("content_type") or "",
            "publish_status": "未发布",
        })
    return {
        "account_id": account_id,
        "planning_cycle": {
            "start": rows[0]["cycle_start"].isoformat(),
            "end": rows[0]["cycle_end"].isoformat(),
        },
        "planning_contents": contents,
    }


@router.post("/api/integrations/publication-status", dependencies=[Depends(require_integration_token)])
def receive_publication_status(payload: PublicationStatusCallback) -> Any:
    """IF-06: validate the effective result and persist the publication fact."""
    receipt_json = as_json(payload.model_dump(mode="json"))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json, validation_status FROM godp_publication_receipt "
                "WHERE event_id=%s", (payload.event_id,),
            )
            previous = cursor.fetchone()
            if previous:
                if previous["payload_json"] != receipt_json:
                    raise HTTPException(status_code=409, detail="相同事件 ID 的回传内容不同")
                if previous["validation_status"] == "mismatch":
                    return JSONResponse(status_code=409, content={
                        "accepted": False, "applied": False, "reason": "result_mismatch",
                    })
                return {"accepted": True, "applied": False, "reason": "duplicate_event"}
            cursor.execute(
                "SELECT i.id, i.topic_id, i.topic_type, i.slot_type, i.status, b.batch_code, "
                "s.version, s.topic_id AS slot_topic_id, s.slot_id, s.published_at, "
                "s.content_id, t.is_marketing "
                "FROM godp_planning_item i "
                "JOIN godp_planning_batch b ON b.id=i.batch_id "
                "JOIN godp_slot_state s ON s.item_id=i.id "
                "LEFT JOIN godp_topic t ON t.topic_code=i.topic_id AND t.del_flag='N' "
                "WHERE i.id=%s AND i.del_flag='N' AND b.del_flag='N' AND s.del_flag='N' "
                "FOR UPDATE", (payload.planning_result_id,),
            )
            item = cursor.fetchone()
            if not item or item["batch_code"].startswith("DEMO-"):
                raise HTTPException(status_code=404, detail="策划结果不存在")
            cursor.execute(
                "SELECT payload_json, validation_status FROM godp_publication_receipt "
                "WHERE event_id=%s", (payload.event_id,),
            )
            previous = cursor.fetchone()
            if previous:
                if previous["payload_json"] != receipt_json:
                    raise HTTPException(status_code=409, detail="相同事件 ID 的回传内容不同")
                if previous["validation_status"] == "mismatch":
                    return JSONResponse(status_code=409, content={
                        "accepted": False, "applied": False, "reason": "result_mismatch",
                    })
                return {"accepted": True, "applied": False, "reason": "duplicate_event"}
            current_status = "已发布" if item["published_at"] else "未发布"
            mismatch = (
                item["version"] != payload.result_version
                or not item["topic_id"]
                or item["slot_topic_id"] != item["topic_id"]
                or item["topic_id"] != payload.topic_id
                or effective_topic_type(item["slot_type"], bool(item["is_marketing"]), item["topic_type"]) != payload.topic_type
                or (current_status == "已发布" and payload.publish_status == "未发布")
                or (item["content_id"] is not None and payload.content_id is not None
                    and item["content_id"] != payload.content_id)
            )
            cursor.execute(
                "INSERT INTO godp_publication_receipt "
                "(event_id, planning_result_id, result_version, topic_id, topic_type, "
                "publish_status, validation_status, content_id, occurred_at, payload_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (payload.event_id, payload.planning_result_id, payload.result_version,
                 payload.topic_id, payload.topic_type, payload.publish_status,
                 "mismatch" if mismatch else "accepted", payload.content_id,
                 utc_naive(payload.occurred_at), receipt_json),
            )
            if mismatch:
                db.commit()
                return JSONResponse(status_code=409, content={
                    "accepted": False, "applied": False, "reason": "result_mismatch",
                    "current_publish_status": current_status,
                })
            applied = payload.publish_status == "已发布" and current_status != "已发布"
            if applied:
                cursor.execute(
                    "UPDATE godp_slot_state SET production_status='published', "
                    "content_id=COALESCE(%s, content_id), published_at=%s, update_by='integration' "
                    "WHERE item_id=%s",
                    (payload.content_id, utc_naive(payload.occurred_at), payload.planning_result_id),
                )
                cursor.execute(
                    "UPDATE godp_planning_item SET status='已发布', update_by='integration' "
                    "WHERE id=%s", (payload.planning_result_id,),
                )
            db.commit()
            return {
                "accepted": True,
                "applied": applied,
                "reason": "applied" if applied else "already_current",
                "current_publish_status": payload.publish_status,
            }
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


@router.get("/api/integrations/topics/{topic_id}/labels", dependencies=[Depends(require_integration_token)])
def ordinary_topic_labels(topic_id: str) -> dict:
    """IF-08: return saved T1-T6 labels without starting recognition."""
    if topic_id.startswith("DEMO-"):
        raise HTTPException(status_code=404, detail="普通选题不存在")
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT t.is_marketing, s.payload_json, tag.tags_json, tag.label_status "
                "FROM godp_topic t JOIN godp_topic_source s ON s.topic_id=t.topic_code "
                "LEFT JOIN godp_topic_tag tag ON tag.topic_id=t.topic_code AND tag.del_flag='N' "
                "WHERE t.topic_code=%s AND t.del_flag='N' AND s.del_flag='N'",
                (topic_id,),
            )
            row = cursor.fetchone()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    if not row or row["is_marketing"]:
        raise HTTPException(status_code=404, detail="普通选题不存在")
    try:
        source = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="选题来源数据不可用") from exc
    if not isinstance(source, dict):
        raise HTTPException(status_code=503, detail="选题来源数据不可用")
    if source.get("topic_type", "normal") not in ("normal", "ordinary", "普通"):
        raise HTTPException(status_code=404, detail="普通选题不存在")
    if not row["tags_json"]:
        return {"topic_id": topic_id, "label_status": "处理中", "labels": {}}
    try:
        labels = single_choice_labels(json.loads(row["tags_json"]))
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail="选题标签数据不可用") from exc
    status = row["label_status"]
    if status == "已完成" and labels is None:
        raise HTTPException(status_code=503, detail="已完成标签数据不完整")
    return {"topic_id": topic_id, "label_status": status,
            "labels": labels if status == "已完成" else {}}


@router.post("/api/integrations/topics/official-usage/query", dependencies=[Depends(require_integration_token)])
def official_topic_usage(payload: OfficialUsageQuery) -> dict:
    """IF-09: only read independently maintained official-use counts."""
    placeholders = ",".join(["%s"] * len(payload.topic_ids))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT topic_id, official_use_count FROM godp_topic_official_usage "
                f"WHERE topic_type=%s AND topic_id IN ({placeholders}) AND del_flag='N'",
                (payload.topic_type, *payload.topic_ids),
            )
            counts = {row["topic_id"]: row["official_use_count"] for row in cursor.fetchall()}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    missing = [topic_id for topic_id in payload.topic_ids if topic_id not in counts]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"{len(missing)} 个选题的正式使用次数尚未同步：{', '.join(missing[:5])}",
        )
    return {"topic_type": payload.topic_type, "items": [
        {"topic_id": topic_id, "official_use_count": counts[topic_id]}
        for topic_id in payload.topic_ids
    ]}


@router.put("/api/internal/topic-official-usage", dependencies=[Depends(require_integration_token)])
def update_official_topic_usage(payload: OfficialUsageUpdate) -> dict:
    """Internal snapshot import from the independent official-use counter."""
    counters = {"inserted": 0, "updated": 0, "unchanged": 0, "stale": 0}
    try:
        with connection() as db, db.cursor() as cursor:
            for record in payload.records:
                cursor.execute(
                    "SELECT official_use_count, source_revision, source_name "
                    "FROM godp_topic_official_usage WHERE topic_type=%s AND topic_id=%s "
                    "FOR UPDATE", (payload.topic_type, record.topic_id),
                )
                previous = cursor.fetchone()
                if previous and record.source_revision < previous["source_revision"]:
                    counters["stale"] += 1
                    continue
                if previous and record.source_revision == previous["source_revision"]:
                    if (record.official_use_count != previous["official_use_count"]
                            or payload.source_name != previous["source_name"]):
                        raise HTTPException(status_code=409, detail=f"{record.topic_id} 的同版本计数内容不同")
                    counters["unchanged"] += 1
                    continue
                cursor.execute(
                    "INSERT INTO godp_topic_official_usage "
                    "(topic_type, topic_id, official_use_count, source_revision, source_name, "
                    "create_by, update_by) VALUES (%s, %s, %s, %s, %s, 'usage-import', 'usage-import') "
                    "ON DUPLICATE KEY UPDATE official_use_count=VALUES(official_use_count), "
                    "source_revision=VALUES(source_revision), source_name=VALUES(source_name), "
                    "update_by='usage-import', del_flag='N'",
                    (payload.topic_type, record.topic_id, record.official_use_count,
                     record.source_revision, payload.source_name),
                )
                cursor.execute(
                    "INSERT INTO godp_topic_official_usage_history "
                    "(topic_type, topic_id, official_use_count, source_revision, source_name, "
                    "create_by, update_by) VALUES (%s, %s, %s, %s, %s, 'usage-import', 'usage-import')",
                    (payload.topic_type, record.topic_id, record.official_use_count,
                     record.source_revision, payload.source_name),
                )
                counters["updated" if previous else "inserted"] += 1
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_type": payload.topic_type, "received": len(payload.records), **counters}


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


class TagTaxonomyItemInput(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True


class TagTaxonomyInput(BaseModel):
    items: dict[str, list[TagTaxonomyItemInput]] | None = None
    tags: dict[str, list[str]] | None = None
    expected_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_tags(self):
        if (self.items is None) == (self.tags is None):
            raise ValueError("必须且只能提交 items 或旧版 tags")
        values_by_dimension = self.items if self.items is not None else self.tags
        if set(values_by_dimension) != set(DIMENSIONS):
            raise ValueError("固定标签必须包含 T1–T5")
        seen_ids = set()
        for values in values_by_dimension.values():
            if not 1 <= len(values) <= 100:
                raise ValueError("每个标签维度需有 1–100 个值")
            names = [value.name.strip() if isinstance(value, TagTaxonomyItemInput) else value.strip()
                     for value in values]
            if len(set(names)) != len(names) or any(not name or len(name) > 80 for name in names):
                raise ValueError("同一维度标签名称必须唯一且不超过 80 字")
            if self.items is not None:
                if not any(value.enabled for value in values):
                    raise ValueError("每个维度至少保留一个启用标签")
                for value in values:
                    if value.id is not None:
                        if value.id in seen_ids:
                            raise ValueError("标签 ID 不能重复")
                        seen_ids.add(value.id)
        return self


class TopicTagsInput(BaseModel):
    tags: dict[str, Any] = Field(default_factory=dict)
    label_status: str | None = None
    label_error: str = Field(default="", max_length=500)
    taxonomy_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def check_status(self):
        if self.label_status not in (None, "处理中", "已完成", "失败"):
            raise ValueError("label_status 只能是处理中、已完成或失败")
        status = self.label_status or ("已完成" if single_choice_labels(self.tags) else "处理中")
        if status == "已完成" and single_choice_labels(self.tags) is None:
            raise ValueError("已完成时必须提供 T1–T6 单选标签")
        if status == "失败" and not self.label_error.strip():
            raise ValueError("失败时必须提供 label_error")
        if status != "已完成" and self.taxonomy_version is not None:
            raise ValueError("只有已完成标签结果才能关联字典版本")
        return self


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
    if not row:
        return {"version": 0, "tags": {}, "items": {}}
    items = normalize_taxonomy(json.loads(row["config_json"]))
    return {"version": row["version"], "tags": active_tag_names(items), "items": items}


@router.put("/api/tag-taxonomy")
def put_tag_taxonomy(payload: TagTaxonomyInput) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            # Lock the row even when the first dictionary is being created.
            cursor.execute(
                "INSERT IGNORE INTO godp_strategy_config "
                "(config_key, config_json, version, create_by, update_by) "
                "VALUES ('tag_taxonomy', '{}', 0, 'system', 'system')"
            )
            cursor.execute(
                "SELECT version, config_json FROM godp_strategy_config "
                "WHERE config_key='tag_taxonomy' AND del_flag='N' FOR UPDATE"
            )
            current = cursor.fetchone()
            version = current["version"] if current else 0
            if payload.expected_version is not None and payload.expected_version != version:
                raise HTTPException(status_code=409, detail="标签配置已被其他操作更新，请刷新后重试")
            existing = normalize_taxonomy(json.loads(current["config_json"])) if current else {
                dimension: [] for dimension in DIMENSIONS
            }
            next_items = {}
            for dimension in DIMENSIONS:
                known = {item["id"]: item for item in existing[dimension]}
                incoming = payload.items[dimension] if payload.items is not None else [
                    TagTaxonomyItemInput(id=next((item["id"] for item in existing[dimension]
                                                  if item["name"] == name.strip()), None), name=name.strip())
                    for name in payload.tags[dimension]
                ]
                values = []
                supplied_ids = set()
                for item in incoming:
                    if item.id and item.id not in known:
                        raise HTTPException(status_code=409, detail=f"{dimension} 标签 ID 不存在，请刷新后重试")
                    tag_id = item.id or f"{dimension}-{uuid4().hex.upper()}"
                    supplied_ids.add(tag_id)
                    values.append({"id": tag_id, "name": item.name.strip(), "enabled": item.enabled})
                # Missing IDs are retained for historical references, but are disabled.
                values.extend({**item, "enabled": False} for item in existing[dimension]
                              if item["id"] not in supplied_ids)
                names = [item["name"] for item in values]
                if len(values) > 100 or len(names) != len(set(names)):
                    raise HTTPException(status_code=422, detail=f"{dimension} 标签名称重复或超过 100 个")
                next_items[dimension] = values
            if next_items == existing:
                return {"version": version, "tags": active_tag_names(existing), "items": existing}
            next_version = version + 1
            serialized = as_json(next_items)
            cursor.execute(
                "INSERT INTO godp_strategy_config "
                "(config_key, config_json, version, create_by, update_by) "
                "VALUES ('tag_taxonomy', %s, %s, 'system', 'system') "
                "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), "
                "version=VALUES(version), update_by='system', del_flag='N'",
                (serialized, next_version),
            )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, create_by, update_by) "
                "VALUES ('tag_taxonomy', %s, %s, '保存', 'system', 'system')",
                (next_version, serialized),
            )
            tags = active_tag_names(next_items)
            queue_event(cursor, "topics", "TOPIC_TAXONOMY_CHANGED", {
                "taxonomy_version": next_version, "tags": tags, "items": next_items,
            })
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"version": next_version, "tags": tags, "items": next_items}


def resolve_topic_tag_ids(cursor, labels: dict[str, str], requested_version: int | None
                          ) -> tuple[dict[str, str], int]:
    cursor.execute(
        "SELECT version, config_json FROM godp_strategy_config "
        "WHERE config_key='tag_taxonomy' AND del_flag='N' FOR UPDATE"
    )
    current = cursor.fetchone()
    if not current:
        raise HTTPException(status_code=409, detail="T1–T5 标签字典尚未保存")
    version = requested_version or current["version"]
    if version == current["version"]:
        snapshot = current["config_json"]
    else:
        cursor.execute(
            "SELECT config_json FROM godp_strategy_config_version "
            "WHERE config_key='tag_taxonomy' AND version=%s AND del_flag='N'",
            (version,),
        )
        historical = cursor.fetchone()
        if not historical:
            raise HTTPException(status_code=409, detail="指定的标签字典版本不存在")
        snapshot = historical["config_json"]
    items = normalize_taxonomy(json.loads(snapshot))
    ids = {}
    for dimension in DIMENSIONS:
        name = labels[dimension.lower()]
        matched = [item["id"] for item in items[dimension]
                   if item["enabled"] and item["name"] == name]
        if len(matched) != 1:
            raise HTTPException(status_code=422, detail=f"{dimension} 标签不在 V{version} 启用字典中：{name}")
        ids[dimension] = matched[0]
    return ids, version


@router.put("/api/internal/topic-tags/{topic_id}", dependencies=[Depends(require_integration_token)])
def put_topic_tags(topic_id: str, payload: TopicTagsInput) -> dict:
    if not topic_id or topic_id.startswith("DEMO-"):
        raise HTTPException(status_code=422, detail="无效的选题 ID")
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT t.is_marketing FROM godp_topic t JOIN godp_topic_source s "
                "ON s.topic_id=t.topic_code WHERE t.topic_code=%s "
                "AND t.del_flag='N' AND s.del_flag='N'", (topic_id,),
            )
            topic_row = cursor.fetchone()
            if not topic_row or topic_row["is_marketing"]:
                raise HTTPException(status_code=404, detail="普通选题不存在")
            label_status = payload.label_status or (
                "已完成" if single_choice_labels(payload.tags) else "处理中"
            )
            labels = single_choice_labels(payload.tags) if label_status == "已完成" else None
            tag_ids, taxonomy_version = (
                resolve_topic_tag_ids(cursor, labels, payload.taxonomy_version)
                if labels else ({}, None)
            )
            tags = ({dimension.upper(): [name] for dimension, name in labels.items()}
                    if labels else payload.tags)
            tags_json = as_json(tags)
            ids_json = as_json(tag_ids)
            cursor.execute(
                "SELECT version, tags_json, tag_ids_json, taxonomy_version, "
                "label_status, label_error, del_flag FROM godp_topic_tag "
                "WHERE topic_id=%s FOR UPDATE", (topic_id,),
            )
            previous = cursor.fetchone()
            if previous and previous["del_flag"] == "N" and (
                previous["tags_json"] == tags_json and
                previous["tag_ids_json"] == ids_json and
                previous["taxonomy_version"] == taxonomy_version and
                previous["label_status"] == label_status and
                previous["label_error"] == payload.label_error
            ):
                return {"topic_id": topic_id, "version": previous["version"],
                        "label_status": label_status, "taxonomy_version": taxonomy_version,
                        "tag_ids": tag_ids}
            version = previous["version"] + 1 if previous else 1
            cursor.execute(
                "INSERT INTO godp_topic_tag "
                "(topic_id, version, tags_json, tag_ids_json, taxonomy_version, "
                "label_status, label_error) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE version=VALUES(version), tags_json=VALUES(tags_json), "
                "tag_ids_json=VALUES(tag_ids_json), taxonomy_version=VALUES(taxonomy_version), "
                "label_status=VALUES(label_status), label_error=VALUES(label_error), "
                "update_by='system', del_flag='N'",
                (topic_id, version, tags_json, ids_json, taxonomy_version,
                 label_status, payload.label_error),
            )
            cursor.execute(
                "INSERT INTO godp_topic_tag_history "
                "(topic_id, version, tags_json, tag_ids_json, taxonomy_version, "
                "label_status, label_error) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (topic_id, version, tags_json, ids_json, taxonomy_version,
                 label_status, payload.label_error),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "version": version, "label_status": label_status,
            "taxonomy_version": taxonomy_version, "tag_ids": tag_ids}


@router.get("/api/internal/topic-tags/{topic_id}/history", dependencies=[Depends(require_integration_token)])
def topic_tag_history(topic_id: str, limit: int = 100) -> dict:
    limit = max(1, min(limit, 200))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT version, tags_json, tag_ids_json, taxonomy_version, "
                "label_status, label_error, create_time FROM godp_topic_tag_history "
                "WHERE topic_id=%s AND del_flag='N' ORDER BY version DESC LIMIT %s",
                (topic_id, limit),
            )
            rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "history": [
        {"version": row["version"], "tags": json.loads(row["tags_json"]),
         "tag_ids": json.loads(row["tag_ids_json"]),
         "taxonomy_version": row["taxonomy_version"],
         "label_status": row["label_status"], "label_error": row["label_error"],
         "created_at": row["create_time"]}
        for row in rows
    ]}


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
