"""Shared topic_vectors operations used by HTTP and workers."""

import json
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, model_validator
import pymysql
from ..db import connection
from ..topic_profile import normalized_topic_vector, profile_from_source
from .errors import ApplicationError, db_error
from ..bank_bridge.input_snapshot import frozen_java_inputs



class TopicVectorResult(BaseModel):
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tag_version: int = Field(ge=1)
    status: Literal["ready", "failed"] = "ready"
    vector: list[float] | None = Field(default=None, min_length=1, max_length=4096)
    vector_model: str | None = Field(default=None, min_length=1, max_length=100)
    error: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def check_result(self):
        if self.status == "ready":
            normalized_topic_vector(self.vector, self.vector_model)
            if self.error:
                raise ValueError("已就绪结果不能包含错误原因")
        elif not self.error.strip() or self.vector is not None or self.vector_model is not None:
            raise ValueError("失败结果必须包含错误原因，且不能包含向量")
        return self

def topic_profile_status(topic_id: str) -> dict:
    if topic_id.startswith("DEMO-"):
        raise ApplicationError(status_code=404, detail="正式普通选题不存在")
    try:
        with connection() as db, db.cursor() as cursor:
            from ..bank_bridge.current_topics import source_row
            row = source_row(cursor, topic_id)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    if not row or row["is_marketing"]:
        raise ApplicationError(status_code=404, detail="正式普通选题不存在")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not row["active_in_snapshot"] or row["topic_status"] != "可用" \
            or (row["valid_from"] and row["valid_from"] > now) \
            or (row["valid_to"] and row["valid_to"] < now):
        status = "unavailable"
    elif row["label_status"] != "已完成":
        status = "label_failed" if row["label_status"] == "失败" else "awaiting_labels"
    elif row["content_hash"] is None:
        status = "pending"
    else:
        try:
            _, current_hash = profile_from_source(row["payload_json"], row["tags_json"])
            status = (row["profile_status"] if current_hash == row["content_hash"]
                      and row["tag_version"] == row["profile_tag_version"]
                      and (row["profile_status"] != "ready" or row["vector_json"] is not None)
                      else "stale")
        except (TypeError, ValueError):
            status = "stale"
    return {"topic_id": topic_id, "status": status,
            "content_hash": row["content_hash"],
            "tag_version": row["profile_tag_version"],
            "vector_model": row["vector_model"] if status == "ready" else None,
            "last_error": row["last_error"] if status == "failed" else ""}

def topic_vector_jobs(limit: int = 100, after_id: int = 0) -> dict:
    limit = max(1, min(limit, 200))
    after_id = max(0, after_id)
    try:
        with connection() as db, db.cursor() as cursor:
            from ..bank_bridge.current_topics import rows as current_rows
            rows = [r for r in current_rows(cursor) if r.get('id') and r['id'] > after_id
                    and r['profile_status'] in ('pending', 'failed') and r['label_status'] == '已完成'
                    and r['tag_version'] == r['profile_tag_version']]
            rows = sorted(rows, key=lambda r: r['id'])[:limit]
            for row in rows:
                row['status'] = row['profile_status']
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    jobs = []
    for row in rows:
        try:
            _, current_hash = profile_from_source(row["payload_json"], row["tags_json"])
            if current_hash != row["content_hash"]:
                continue
            jobs.append({
                "id": row["id"], "topic_id": row["topic_id"],
                "content_hash": row["content_hash"], "tag_version": row["tag_version"],
                "profile": json.loads(row["profile_json"]), "status": row["status"],
                "last_error": row["last_error"],
            })
        except (TypeError, ValueError):
            continue
    return {"next_after_id": rows[-1]["id"] if rows else after_id, "jobs": jobs}

def save_topic_vector(topic_id: str, payload: TopicVectorResult) -> dict:
    if topic_id.startswith("DEMO-"):
        raise ApplicationError(status_code=404, detail="正式普通选题不存在")
    try:
        with frozen_java_inputs(topic_ids=[topic_id]), connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT content_hash, tag_version, status, vector_json, vector_model "
                "FROM godp_topic_profile WHERE topic_id=%s AND del_flag='N' FOR UPDATE",
                (topic_id,),
            )
            profile = cursor.fetchone()
            if not profile:
                raise ApplicationError(status_code=404, detail="选题画像尚未建立")
            from ..bank_bridge.current_topics import source_row
            current = source_row(cursor, topic_id)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if not current or not current["active_in_snapshot"] or current["is_marketing"] \
                    or current["topic_status"] != "可用" or current["label_status"] != "已完成" \
                    or (current["valid_from"] and current["valid_from"] > now) \
                    or (current["valid_to"] and current["valid_to"] < now):
                raise ApplicationError(status_code=409, detail="选题当前不在 AI 准备范围")
            _, current_hash = profile_from_source(current["payload_json"], current["tags_json"])
            if profile["content_hash"] != current_hash or profile["tag_version"] != current["tag_version"]:
                raise ApplicationError(status_code=409, detail="选题内容或标签已变化，请重新生成画像")
            if payload.content_hash != current_hash or payload.tag_version != current["tag_version"]:
                raise ApplicationError(status_code=409, detail="向量结果对应的画像版本已过期")
            vector = (normalized_topic_vector(payload.vector, payload.vector_model)
                      if payload.status == "ready" else None)
            vector_json = json.dumps(vector, separators=(",", ":")) if vector else None
            vector_model = payload.vector_model.strip() if vector else None
            if profile["status"] == "ready":
                if payload.status == "ready" and profile["vector_json"] == vector_json \
                        and profile["vector_model"] == vector_model:
                    return {"topic_id": topic_id, "status": "ready",
                            "content_hash": current_hash, "tag_version": current["tag_version"]}
                raise ApplicationError(status_code=409, detail="当前画像向量已就绪，不支持覆盖")
            cursor.execute(
                "UPDATE godp_topic_profile SET status=%s, vector_json=%s, "
                "vector_model=%s, last_error=%s, completed_at=%s, "
                "update_by='vector-worker' WHERE topic_id=%s",
                (payload.status, vector_json, vector_model,
                 payload.error.strip() if payload.status == "failed" else "",
                 now if payload.status == "ready" else None, topic_id),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "status": payload.status,
            "content_hash": payload.content_hash, "tag_version": payload.tag_version}

def ai_topic_candidates(limit: int = 100, after_id: int = 0) -> dict:
    limit = max(1, min(limit, 200))
    after_id = max(0, after_id)
    try:
        with connection() as db, db.cursor() as cursor:
            from ..bank_bridge.current_topics import rows as current_rows
            rows = [r for r in current_rows(cursor) if r.get('id') and r['id'] > after_id
                    and r['profile_status'] in ('ready',) and r['label_status'] == '已完成'
                    and r['tag_version'] == r['profile_tag_version']]
            rows = sorted(rows, key=lambda r: r['id'])[:limit]
            for row in rows:
                row['status'] = row['profile_status']
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    candidates = []
    for row in rows:
        try:
            _, current_hash = profile_from_source(row["payload_json"], row["tags_json"])
            if current_hash != row["content_hash"]:
                continue
            candidates.append({
                "id": row["id"], "topic_id": row["topic_id"],
                "content_hash": row["content_hash"], "tag_version": row["tag_version"],
                "profile": json.loads(row["profile_json"]),
                "vector": json.loads(row["vector_json"]),
                "vector_model": row["vector_model"],
            })
        except (TypeError, ValueError):
            continue
    return {"next_after_id": rows[-1]["id"] if rows else after_id,
            "candidates": candidates}
