"""Shared catalog use cases; no HTTP routing."""
import json
import pymysql
from ..db import connection
from ..models import StrategyConfig
from .errors import ApplicationError, database_error
from ..core.planning_items import replacement_block_reason

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
            from ..bank_bridge.bridge import account_options
            return account_options(cursor, config, limit)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def list_topics(limit: int = 200) -> list[dict]:
    limit = max(1, min(limit, 1000))
    try:
        with connection() as db, db.cursor() as cursor:
            from ..bank_bridge.bridge import topic_options
            rows = topic_options(cursor, limit)
            attach_topic_labels(cursor, rows)
            for row in rows:
                row.pop('topic_payload', None)
                row.pop('_catalog_topic', None)
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
            "SELECT topic_id, tags_json, label_status, version, taxonomy_version FROM godp_topic_tag WHERE del_flag='N' AND topic_id IN (", ordinary,
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

def topic_detail(topic_id: str, topic_type: str | None = None) -> dict:
    if not topic_id.strip() or len(topic_id) > 64 or topic_type not in (None, "普通", "营销", "热点"):
        raise ApplicationError(status_code=422, detail="选题ID或类型无效")
    try:
        with connection() as db, db.cursor() as cursor:
            from ..bank_bridge.bridge import topic_options
            rows = topic_options(cursor, topic_ids=[topic_id], available_only=False)
            rows = [r for r in rows if topic_type is None or r['topic_type'] == topic_type]
            if not rows:
                raise ApplicationError(404, '选题不存在')
            attach_topic_labels(cursor, rows)
            row = rows[0]
            row.pop('topic_payload', None)
            row.pop('_catalog_topic', None)
            return row
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def available_topics(cursor, topic_ids: list[str]) -> dict[str, dict]:
    from ..bank_bridge.bridge import topic_options
    rows = topic_options(cursor, topic_ids=topic_ids)
    return {row['topic_id']: {**row, 'topic_payload': json.dumps(row['topic_payload'], ensure_ascii=False)}
            for row in rows}

def available_replacement_topics(cursor, account_id: str, topic_id: str | None = None) -> list[dict]:
    """Read current, account-eligible ordinary, marketing, and hotspot candidates."""
    from ..bank_bridge.bridge import topic_options, collect
    from ..bank_bridge.contracts import AccountQuery
    from ..bank_bridge.factory import get_source
    accounts = list(collect(get_source(cursor), 'accounts', AccountQuery(account_ids=[account_id])))
    if not accounts:
        return []
    rows = topic_options(cursor, topic_ids=[topic_id] if topic_id is not None else None)
    return [row for row in rows if not row['is_marketing'] or accounts[0].account_type == '认证']

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
                raise ApplicationError(status_code=404, detail="策划结果不存在")
            reason = replacement_block_reason(item, item["plan_type"])
            if reason:
                raise ApplicationError(status_code=409, detail=reason)
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
    except ApplicationError:
        raise
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
