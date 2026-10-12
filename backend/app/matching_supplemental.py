"""Freeze factual fallback, history and official counts without inferring rules."""

from datetime import datetime, timedelta, timezone
from collections import Counter
import json
import math

from .account_profile import canonical_json
from .ai_preparation import utc_text
from .matching_policy import digest


MAX_ROWS = 20000
MAX_BYTES = 5_000_000


class SupplementalInputError(Exception):
    def __init__(self, code: str):
        self.code = code


def chunks(values: list, size: int = 500):
    for index in range(0, len(values), size):
        yield values[index:index + size]


def json_object(raw: str | None) -> dict | None:
    if raw is None:
        return None
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("输入不是JSON对象")
    return result


def fallback_topic(row: dict) -> dict | None:
    source = json_object(row["payload_json"])
    enabled = source.get("status") if source.get("status") is not None else source.get("enabled", True)
    if not enabled or source.get("is_marketing", False) \
            or source.get("topic_type", "normal") not in ("normal", "ordinary", "普通"):
        return None
    heat = source.get("topic_heat", source.get("heat"))
    if heat is not None and (type(heat) not in (int, float) or not math.isfinite(heat) or heat < 0):
        raise SupplementalInputError("fallback_heat_invalid")
    return {"topic_id": row["topic_id"], "topic_type": "普通", "title": row["title"],
            "source_payload": source, "source_updated_at": utc_text(row["source_updated_at"]),
            "valid_from": utc_text(row["valid_from"]), "valid_to": utc_text(row["valid_to"]),
            "topic_heat": float(heat) if heat is not None else None, "heat_known": heat is not None,
            "label_status": row["label_status"], "tag_version": row["tag_version"],
            "tags": json_object(row["tags_json"]), "tag_ids": json_object(row["tag_ids_json"]),
            "taxonomy_version": row["taxonomy_version"], "t6_tag_id": row["t6_tag_id"]}


def load_fallback_topics(cursor, checked_at: datetime, identifiers: list[str] | None = None) -> list[dict]:
    if identifiers == []:
        return []
    base = ("SELECT s.topic_id,s.payload_json,s.source_updated_at,s.valid_from,s.valid_to,t.title, "
            "tag.label_status,tag.version AS tag_version,tag.tags_json,tag.tag_ids_json, "
            "tag.taxonomy_version,tag.t6_tag_id FROM godp_topic_source s "
            "JOIN godp_topic t ON t.topic_code=s.topic_id AND t.del_flag='N' "
            "LEFT JOIN godp_topic_tag tag ON tag.topic_id=s.topic_id AND tag.del_flag='N' "
            "WHERE s.del_flag='N' AND s.active_in_snapshot=1 AND t.status='可用' AND t.is_marketing=0 "
            "AND s.topic_id NOT LIKE 'DEMO-%%' AND TRIM(t.title)<>'' "
            "AND (s.valid_from IS NULL OR s.valid_from<=%s) AND (s.valid_to IS NULL OR s.valid_to>=%s) ")
    result = []
    groups = chunks(sorted(set(identifiers))) if identifiers is not None else [None]
    for group in groups:
        params = [checked_at.replace(tzinfo=None), checked_at.replace(tzinfo=None)]
        query = base
        if group is not None:
            query += "AND s.topic_id IN (" + ",".join(["%s"] * len(group)) + ") "
            params.extend(group)
        query += "ORDER BY s.topic_id LIMIT %s"
        params.append(MAX_ROWS + 1)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        if len(rows) > MAX_ROWS:
            raise SupplementalInputError("supplemental_input_too_large")
        try:
            for row in rows:
                topic = fallback_topic(row)
                if topic is not None:
                    result.append(topic)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise SupplementalInputError("fallback_source_invalid") from exc
        if len(result) > MAX_ROWS:
            raise SupplementalInputError("supplemental_input_too_large")
    return sorted(result, key=lambda topic: topic["topic_id"])


def load_history(cursor, account_ids: list[str], as_of: datetime, days: int) -> dict:
    start = as_of - timedelta(days=days)
    records = []
    for group in chunks(sorted(set(account_ids))):
        query = ("SELECT content_id,account_id,topic_id,published_at,source_updated_at,payload_json "
                 "FROM godp_content_history WHERE del_flag='N' AND account_id IN ("
                 + ",".join(["%s"] * len(group)) + ") "
                 "AND content_id NOT LIKE 'DEMO-%%' AND published_at>=%s AND published_at<=%s "
                 "ORDER BY account_id,published_at,content_id LIMIT %s")
        cursor.execute(query, (*group, start.replace(tzinfo=None), as_of.replace(tzinfo=None), MAX_ROWS + 1))
        rows = cursor.fetchall()
        if len(records) + len(rows) > MAX_ROWS:
            raise SupplementalInputError("supplemental_input_too_large")
        try:
            for row in rows:
                source = json_object(row["payload_json"])
                topic_type = source.get("topic_type")
                if topic_type not in (None, "普通", "营销", "热点"):
                    raise ValueError("历史选题类型错误")
                records.append({"content_id": row["content_id"], "account_id": row["account_id"],
                                "topic_id": row["topic_id"] or None, "topic_type": topic_type,
                                "reference_known": bool(row["topic_id"] and topic_type is not None),
                                "published_at": utc_text(row["published_at"]),
                                "source_updated_at": utc_text(row["source_updated_at"]), "source_payload": source})
        except (KeyError, TypeError, ValueError) as exc:
            raise SupplementalInputError("history_source_invalid") from exc
    records.sort(key=lambda row: (row["account_id"], row["published_at"], row["content_id"]))
    counts = Counter(row["account_id"] for row in records)
    return {"source": "content_history", "window_days": days, "window_start": start.isoformat(),
            "window_end": as_of.isoformat(), "coverage": "unknown", "observed_records": records,
            "accounts": [{"account_id": account_id, "coverage": "unknown",
                          "observed_count": counts[account_id]}
                         for account_id in sorted(set(account_ids))]}


def load_official_usage(cursor, topic_ids: list[str]) -> dict:
    current = {}
    identifiers = sorted(set(topic_ids))
    if len(identifiers) > MAX_ROWS:
        raise SupplementalInputError("supplemental_input_too_large")
    for group in chunks(identifiers):
        cursor.execute(
            "SELECT topic_id,official_use_count,source_revision,source_name FROM godp_topic_official_usage "
            "WHERE topic_type='普通' AND del_flag='N' AND topic_id IN (" + ",".join(["%s"] * len(group)) + ")",
            group,
        )
        for row in cursor.fetchall():
            if type(row["official_use_count"]) is not int or row["official_use_count"] < 0 \
                    or type(row["source_revision"]) is not int or row["source_revision"] < 1 \
                    or not row["source_name"].strip():
                raise SupplementalInputError("official_usage_source_invalid")
            current[row["topic_id"]] = row
    records = []
    for topic_id in identifiers:
        row = current.get(topic_id)
        records.append({"topic_id": topic_id, "topic_type": "普通", "known": row is not None,
                        "official_use_count": row["official_use_count"] if row else None,
                        "source_revision": row["source_revision"] if row else None,
                        "source_name": row["source_name"] if row else None})
    return {"source": "independent_official_counter", "records": records,
            "unknown_count": sum(not row["known"] for row in records)}


def build_snapshot(cursor, inputs: dict, document, as_of: datetime, *, validity_at: datetime | None = None,
                   fallback_ids: list[str] | None = None) -> dict:
    if as_of.tzinfo is None:
        raise SupplementalInputError("supplemental_time_invalid")
    as_of = as_of.astimezone(timezone.utc)
    required = set(document.required_inputs)
    options = document.input_options
    snapshot = {"schema_version": 2, "as_of": as_of.isoformat()}
    topic_ids = {topic["topic_id"] for topic in inputs["topics"]}
    if "fallback_topics" in required:
        topics = load_fallback_topics(cursor, validity_at or as_of, fallback_ids)
        if any(not topic["heat_known"] for topic in topics) and options.fallback_unknown_heat == "block":
            raise SupplementalInputError("fallback_heat_unknown")
        snapshot["fallback_topics"] = topics
        topic_ids.update(topic["topic_id"] for topic in topics)
    if "history" in required:
        history = load_history(cursor, [account["account_id"] for account in inputs["accounts"]],
                               as_of, options.history_window_days)
        if options.history_completeness == "require_complete":
            raise SupplementalInputError("history_coverage_unknown")
        if options.history_unknown_references == "block" and any(
                not row["reference_known"] for row in history["observed_records"]):
            raise SupplementalInputError("history_topic_reference_unknown")
        snapshot["history"] = history
    if "official_usage" in required:
        usage = load_official_usage(cursor, sorted(topic_ids))
        if usage["unknown_count"] and options.official_usage_unknown == "block":
            raise SupplementalInputError("official_usage_unknown")
        snapshot["official_usage"] = usage
    if len(canonical_json(snapshot).encode("utf-8")) > MAX_BYTES:
        raise SupplementalInputError("supplemental_input_too_large")
    return snapshot


def snapshot_counts(snapshot: dict) -> dict:
    history, usage = snapshot.get("history"), snapshot.get("official_usage")
    return {"fallback_topics": len(snapshot["fallback_topics"]) if "fallback_topics" in snapshot else None,
            "history_records": len(history["observed_records"]) if history else None,
            "history_coverage": history["coverage"] if history else None,
            "official_usage_topics": len(usage["records"]) if usage else None,
            "unknown_official_usage": usage["unknown_count"] if usage else None}


def save_snapshot(cursor, task_id: int, snapshot: dict) -> str:
    encoded = canonical_json(snapshot)
    fingerprint = digest(encoded)
    as_of = datetime.fromisoformat(snapshot["as_of"]).astimezone(timezone.utc).replace(tzinfo=None)
    cursor.execute("INSERT INTO godp_matching_input_snapshot "
                   "(task_id,as_of,snapshot_json,snapshot_hash,counts_json,create_by,update_by) "
                   "VALUES (%s,%s,%s,%s,%s,'matching-task-api','matching-task-api')",
                   (task_id, as_of, encoded, fingerprint, canonical_json(snapshot_counts(snapshot))))
    return fingerprint


def read_snapshot(cursor, task: dict) -> dict:
    cursor.execute("SELECT * FROM godp_matching_input_snapshot WHERE task_id=%s AND del_flag='N'",
                   (task["id"],))
    row = cursor.fetchone()
    if not row:
        raise SupplementalInputError("supplemental_snapshot_missing")
    try:
        snapshot = json_object(row["snapshot_json"])
        as_of = datetime.fromisoformat(snapshot["as_of"])
        if as_of.tzinfo is None:
            raise ValueError("补充快照时间缺少时区")
        if snapshot["schema_version"] != 2 or digest(canonical_json(snapshot)) != row["snapshot_hash"] \
                or row["snapshot_hash"] != task["supplemental_hash"] \
                or canonical_json(snapshot_counts(snapshot)) != canonical_json(json.loads(row["counts_json"])) \
                or as_of.astimezone(timezone.utc).replace(tzinfo=None) != row["as_of"]:
            raise ValueError("补充快照指纹或摘要不一致")
        return snapshot
    except (KeyError, TypeError, ValueError) as exc:
        raise SupplementalInputError("supplemental_snapshot_integrity_error") from exc


def validate_snapshot(cursor, task: dict, inputs: dict, document, checked_at: datetime) -> dict:
    snapshot = read_snapshot(cursor, task)
    try:
        as_of = datetime.fromisoformat(snapshot["as_of"])
        fallback_ids = [row["topic_id"] for row in snapshot.get("fallback_topics", [])]
        current = build_snapshot(cursor, inputs, document, as_of, validity_at=checked_at,
                                 fallback_ids=fallback_ids)
    except (KeyError, TypeError, ValueError) as exc:
        raise SupplementalInputError("supplemental_snapshot_integrity_error") from exc
    if canonical_json(current) != canonical_json(snapshot):
        raise SupplementalInputError("supplemental_inputs_stale")
    return snapshot
