"""Build the current ordinary-topic profile and invalidate stale vectors."""

import hashlib
import json
import math


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
    if not isinstance(model, str) or not model.strip() or len(model.strip()) > 100:
        raise ValueError("选题向量模型标识必须为 1–100 字")
    if not isinstance(values, list) or not 1 <= len(values) <= 4096:
        raise ValueError("选题向量维度必须在 1–4096 之间")
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           for value in values):
        raise ValueError("选题向量必须全部是数值")
    vector = [float(value) for value in values]
    if any(not math.isfinite(value) or abs(value) > 1e6 for value in vector):
        raise ValueError("选题向量存在无效数值")
    length = math.sqrt(math.fsum(value * value for value in vector))
    if length == 0 or not math.isfinite(length):
        raise ValueError("选题向量不能是零向量")
    return [value / length for value in vector]
