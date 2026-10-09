"""Keep one stable T6 label for semantically similar user needs."""

import json
import math

from fastapi import HTTPException


T6_REUSE_THRESHOLD = 0.80


def normalized_embedding(values: object, model: object) -> list[float]:
    if not isinstance(model, str) or not model.strip() or len(model.strip()) > 100:
        raise ValueError("T6 向量模型标识必须为 1–100 字")
    if not isinstance(values, list) or not 1 <= len(values) <= 4096:
        raise ValueError("T6 语义向量维度必须在 1–4096 之间")
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           for value in values):
        raise ValueError("T6 语义向量必须全部是数值")
    vector = [float(value) for value in values]
    if any(not math.isfinite(value) or abs(value) > 1e6 for value in vector):
        raise ValueError("T6 语义向量存在无效数值")
    length = math.sqrt(math.fsum(value * value for value in vector))
    if length == 0 or not math.isfinite(length):
        raise ValueError("T6 语义向量不能是零向量")
    return [value / length for value in vector]


def resolve_t6_tag(cursor, candidate: str, embedding: list[float], model: str
                   ) -> tuple[int, str]:
    """Reuse the closest same-model label above 80%, or create a new label."""
    cursor.execute("SELECT GET_LOCK('godp:t6-tag-registry', 5) AS acquired")
    if cursor.fetchone()["acquired"] != 1:
        raise HTTPException(status_code=409, detail="T6 标签库正在更新，请稍后重试")
    cursor.execute(
        "SELECT id, name, embedding_model, embedding_json FROM godp_t6_tag "
        "WHERE name=%s AND del_flag='N' FOR UPDATE", (candidate,),
    )
    exact = cursor.fetchone()
    if exact:
        if exact["embedding_model"] == model and exact["embedding_json"] is not None:
            if len(json.loads(exact["embedding_json"])) != len(embedding):
                raise HTTPException(status_code=422, detail="同一 T6 向量模型返回了不同维度")
        if exact["embedding_json"] is None:
            cursor.execute(
                "UPDATE godp_t6_tag SET embedding_model=%s, embedding_json=%s, "
                "update_by='label-worker' WHERE id=%s",
                (model, json.dumps(embedding, separators=(",", ":")), exact["id"]),
            )
        return exact["id"], exact["name"]
    cursor.execute(
        "SELECT id, name, embedding_json FROM godp_t6_tag "
        "WHERE embedding_model=%s AND embedding_json IS NOT NULL "
        "AND del_flag='N' ORDER BY id FOR UPDATE", (model,),
    )
    closest = None
    best_similarity = T6_REUSE_THRESHOLD
    for row in cursor.fetchall():
        stored = json.loads(row["embedding_json"])
        if len(stored) != len(embedding):
            raise HTTPException(status_code=422, detail="同一 T6 向量模型返回了不同维度")
        similarity = math.fsum(left * right for left, right in zip(embedding, stored))
        if similarity > best_similarity:
            closest = row
            best_similarity = similarity
    if closest:
        return closest["id"], closest["name"]
    cursor.execute(
        "INSERT INTO godp_t6_tag "
        "(name, embedding_model, embedding_json, create_by, update_by) "
        "VALUES (%s, %s, %s, 'label-worker', 'label-worker')",
        (candidate, model, json.dumps(embedding, separators=(",", ":"))),
    )
    return cursor.lastrowid, candidate
