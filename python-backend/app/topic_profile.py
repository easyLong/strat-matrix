"""Build the current ordinary-topic profile and invalidate stale vectors."""

import hashlib
import json
from .vector_utils import normalized_vector


PROFILE_TEXT_FIELDS = (
    "title", "summary", "outline", "content_type", "category", "source",
    "product_or_activity",
)


def profile_from_source(source_json: str, tags_json: str) -> tuple[str, str]:
    source = json.loads(source_json)
    tags = json.loads(tags_json)
    if not isinstance(source, dict) or not isinstance(tags, dict):
        raise ValueError("选题内容或标签不是 JSON 对象")
    labels = {}
    for number in range(1, 7):
        dimension = f"T{number}"
        value = tags.get(dimension, tags.get(dimension.lower()))
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{dimension} 标签尚未完成")
        labels[dimension] = value.strip()
    cities = source.get("applicable_cities") or []
    if not isinstance(cities, list):
        raise ValueError("applicable_cities 不是数组")
    profile = {
        "content": {key: source.get(key) or "" for key in PROFILE_TEXT_FIELDS},
        "applicable_cities": sorted({str(city).strip() for city in cities if str(city).strip()}),
        "labels": labels,
    }
    serialized = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def upsert_topic_profile(cursor, topic_id: str, source_json: str,
                         tags_json: str, tag_version: int) -> bool:
    profile_json, content_hash = profile_from_source(source_json, tags_json)
    cursor.execute(
        "SELECT content_hash, tag_version FROM godp_topic_profile "
        "WHERE topic_id=%s FOR UPDATE", (topic_id,),
    )
    current = cursor.fetchone()
    if current and current["content_hash"] == content_hash and current["tag_version"] == tag_version:
        return False
    cursor.execute(
        "INSERT INTO godp_topic_profile "
        "(topic_id, content_hash, tag_version, profile_json, create_by, update_by) "
        "VALUES (%s, %s, %s, %s, 'system', 'system') "
        "ON DUPLICATE KEY UPDATE content_hash=VALUES(content_hash), "
        "tag_version=VALUES(tag_version), profile_json=VALUES(profile_json), "
        "status='pending', vector_json=NULL, vector_model=NULL, completed_at=NULL, "
        "last_error='', update_by='system', del_flag='N'",
        (topic_id, content_hash, tag_version, profile_json),
    )
    return True


def normalized_topic_vector(values: object, model: object) -> list[float]:
    return normalized_vector(values, model, "选题")
