"""Shared taxonomy, leased labeling and tag-result operations."""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
import json
import pymysql
from pydantic import BaseModel, Field, model_validator
from ..db import connection
from ..core.serialization import as_json, single_choice_labels
from ..taxonomy import DIMENSIONS, active_tag_names, normalize_taxonomy, selectable_tags
from ..t6_tags import normalized_embedding, resolve_t6_tag
from ..topic_profile import upsert_topic_profile
from .errors import ApplicationError, db_error
from ..bank_bridge.input_snapshot import frozen_java_inputs


class TagTaxonomyItemInput(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    enabled: bool = True
    node_type: str = "tag"
    parent_id: str | None = None
    client_id: str | None = Field(default=None, max_length=100)

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
        for dimension, values in values_by_dimension.items():
            if not 1 <= len(values) <= 256:
                raise ValueError("每个标签维度需有 1–256 个分类及标签")
            names = [(value.node_type, value.name.strip()) if isinstance(value, TagTaxonomyItemInput)
                     else ("tag", value.strip()) for value in values]
            if len(set(names)) != len(names) or any(not name or len(name) > 80 for _, name in names):
                raise ValueError("同一维度的分类名、标签名分别唯一且不超过80字")
            if self.items is not None:
                if not any(value.enabled for value in values):
                    raise ValueError("每个维度至少保留一个启用标签")
                for value in values:
                    if value.node_type not in ("group", "tag"):
                        raise ValueError("节点类型只能是分类或标签")
                    if dimension in ("T1", "T2") and (value.node_type == "group" or value.parent_id):
                        raise ValueError("T1、T2不支持分类树")
                    if value.node_type == "group" and value.parent_id:
                        raise ValueError("一级分类不能有父节点")
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
    lease_id: str | None = Field(default=None, min_length=1, max_length=64)
    t6_embedding: list[float] | None = Field(default=None, min_length=1, max_length=4096)
    t6_embedding_model: str | None = Field(default=None, min_length=1, max_length=100)

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
        if self.t6_embedding is not None or self.t6_embedding_model is not None:
            if status != "已完成":
                raise ValueError("只有已完成标签结果才能关联 T6 语义向量")
            normalized_embedding(self.t6_embedding, self.t6_embedding_model)
        return self

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

def put_tag_taxonomy(payload: TagTaxonomyInput, operator: str = "运营人员") -> dict:
    if not operator.strip() or len(operator) > 64 or any(char in operator for char in '\r\n\0'):
        raise ApplicationError(status_code=422, detail="操作人无效")
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
                raise ApplicationError(status_code=409, detail="标签配置已被其他操作更新，请刷新后重试")
            existing = normalize_taxonomy(json.loads(current["config_json"])) if current else {
                dimension: [] for dimension in DIMENSIONS
            }
            next_items = {}
            for dimension in DIMENSIONS:
                known = {item["id"]: item for item in existing[dimension]}
                if payload.items is not None:
                    incoming = payload.items[dimension]
                else:
                    incoming = []
                    for name in payload.tags[dimension]:
                        previous = next((item for item in existing[dimension]
                                         if item.get("node_type") != "group" and item["name"] == name.strip()), {})
                        incoming.append(TagTaxonomyItemInput(id=previous.get("id"), name=name.strip(),
                                                             parent_id=previous.get("parent_id")))
                values = []
                supplied_ids = set()
                draft_ids = {}
                for item in incoming:
                    if item.client_id:
                        if item.id or item.client_id in draft_ids or item.client_id in known:
                            raise ApplicationError(status_code=422, detail="新增节点临时标识重复或与已有ID冲突")
                        draft_ids[item.client_id] = f"{dimension}-{uuid4().hex.upper()}"
                for item in incoming:
                    if item.id and item.id not in known:
                        raise ApplicationError(status_code=409, detail=f"{dimension} 标签 ID 不存在，请刷新后重试")
                    tag_id = item.id or draft_ids.get(item.client_id) or f"{dimension}-{uuid4().hex.upper()}"
                    supplied_ids.add(tag_id)
                    value = {"id": tag_id, "name": item.name.strip(), "enabled": item.enabled}
                    parent_id = draft_ids.get(item.parent_id, item.parent_id)
                    if item.node_type == "group" or parent_id:
                        value.update(node_type=item.node_type, parent_id=parent_id)
                    values.append(value)
                # Missing IDs are retained for historical references, but are disabled.
                values.extend({**item, "enabled": item["enabled"] if payload.tags is not None and item.get("node_type") == "group" else False} for item in existing[dimension]
                              if item["id"] not in supplied_ids)
                names = [(item.get("node_type", "tag"), item["name"]) for item in values]
                if len(values) > 256 or len(names) != len(set(names)):
                    raise ApplicationError(status_code=422, detail=f"{dimension} 分类或标签名称重复，或节点超过256个")
                groups = {item["id"] for item in values if item.get("node_type") == "group"}
                if any(item.get("parent_id") and item["parent_id"] not in groups for item in values):
                    raise ApplicationError(status_code=422, detail="标签只能归属于同一维度的一级分类")
                if any(item["id"] in known and known[item["id"]].get("node_type", "tag") != item.get("node_type", "tag") for item in values):
                    raise ApplicationError(status_code=422, detail="已有节点不能改变分类或标签类型")
                if not selectable_tags(values):
                    raise ApplicationError(status_code=422, detail=f"{dimension} 至少保留一个有效标签及其所属分类")
                next_items[dimension] = values
            if next_items == existing:
                return {"version": version, "tags": active_tag_names(existing), "items": existing}
            next_version = version + 1
            serialized = as_json(next_items)
            cursor.execute(
                "INSERT INTO godp_strategy_config "
                "(config_key, config_json, version, create_by, update_by) "
                "VALUES ('tag_taxonomy', %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), "
                "version=VALUES(version), update_by=VALUES(update_by), del_flag='N'",
                (serialized, next_version, operator, operator),
            )
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, create_by, update_by) "
                "VALUES ('tag_taxonomy', %s, %s, '保存', %s, %s)",
                (next_version, serialized, operator, operator),
            )
            tags = active_tag_names(next_items)
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
        raise ApplicationError(status_code=409, detail="T1–T5 标签字典尚未保存")
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
            raise ApplicationError(status_code=409, detail="指定的标签字典版本不存在")
        snapshot = historical["config_json"]
    items = normalize_taxonomy(json.loads(snapshot))
    ids = {}
    for dimension in DIMENSIONS:
        name = labels[dimension.lower()]
        matched = [item["id"] for item in selectable_tags(items[dimension]) if item["name"] == name]
        if len(matched) != 1:
            raise ApplicationError(status_code=422, detail=f"{dimension} 标签不在 V{version} 启用字典中：{name}")
        ids[dimension] = matched[0]
    return ids, version

def list_topic_label_jobs(limit: int = 100, after_id: int = 0, *, topic_ids: list[str] | None = None) -> dict:
    limit = max(1, min(limit, 200))
    after_id = max(0, after_id)
    if topic_ids == []:
        return {'jobs': []}
    scope_sql = ('AND j.topic_id IN (' + ','.join(['%s'] * len(topic_ids)) + ') ' if topic_ids else '')
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT j.id, j.topic_id, j.status, j.attempt_count, j.last_error, "
                "j.source_updated_at, j.lease_expires_at FROM godp_topic_label_job j "
                "WHERE j.id>%s AND j.del_flag='N' "
                "AND j.topic_id NOT LIKE 'DEMO-%%' "
                "AND (j.status IN ('pending','failed') OR "
                "(j.status='processing' AND j.lease_expires_at<=UTC_TIMESTAMP(6))) "
                + scope_sql + "ORDER BY j.id LIMIT %s", (after_id, *(topic_ids or []), limit),
            )
            rows = cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"jobs": rows}

def claim_topic_label_job(topic_id: str, lease_seconds: int = 1800) -> dict:
    lease_seconds = max(60, min(lease_seconds, 7200))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        with frozen_java_inputs(topic_ids=[topic_id]), connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT status, attempt_count, lease_expires_at, "
                "source_payload_json, source_updated_at FROM godp_topic_label_job "
                "WHERE topic_id=%s AND del_flag='N' FOR UPDATE", (topic_id,),
            )
            job = cursor.fetchone()
            if not job:
                raise ApplicationError(status_code=404, detail="待识别普通选题任务不存在")
            from ..bank_bridge.current_topics import source_row
            current = source_row(cursor, topic_id)
            if current is None:
                raise ApplicationError(status_code=409, detail="普通选题当前不可用")
            from ..source_discovery import source_signature
            if source_signature(job['source_payload_json']) != source_signature(current['payload_json']):
                raise ApplicationError(409, '选题内容已变化，等待重新准备任务')
            if job["status"] not in ("pending", "failed") and not (
                job["status"] == "processing" and job["lease_expires_at"]
                and job["lease_expires_at"] <= now
            ):
                raise ApplicationError(status_code=409, detail="任务已被领取、完成或取消")
            cursor.execute(
                "SELECT version, config_json FROM godp_strategy_config "
                "WHERE config_key='tag_taxonomy' AND del_flag='N' FOR UPDATE"
            )
            config = cursor.fetchone()
            if not config:
                raise ApplicationError(status_code=409, detail="T1–T5 标签字典尚未保存")
            tags = active_tag_names(normalize_taxonomy(json.loads(config["config_json"])))
            if any(not values for values in tags.values()):
                raise ApplicationError(status_code=409, detail="T1–T5 标签字典存在空维度")
            lease_id = uuid4().hex.upper()
            expires_at = now + timedelta(seconds=lease_seconds)
            cursor.execute(
                "UPDATE godp_topic_label_job SET status='processing', "
                "attempt_count=attempt_count+1, lease_id=%s, lease_expires_at=%s, "
                "taxonomy_version=%s, last_error='', update_by='label-worker' "
                "WHERE topic_id=%s",
                (lease_id, expires_at, config["version"], topic_id),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "lease_id": lease_id,
            "lease_expires_at": expires_at.isoformat() + "Z",
            "attempt_count": job["attempt_count"] + 1,
            "taxonomy_version": config["version"], "taxonomy": tags,
            "topic": json.loads(job["source_payload_json"]),
            "source_updated_at": job["source_updated_at"].isoformat() + "Z"}

def put_topic_tags(topic_id: str, payload: TopicTagsInput) -> dict:
    if not topic_id or topic_id.startswith("DEMO-"):
        raise ApplicationError(status_code=422, detail="无效的选题 ID")
    try:
        with connection() as db, db.cursor() as cursor:
            from ..bank_bridge.current_topics import source_row
            topic_row = source_row(cursor, topic_id)
            if not topic_row or topic_row["is_marketing"]:
                raise ApplicationError(status_code=404, detail="普通选题不存在")
            label_status = payload.label_status or (
                "已完成" if single_choice_labels(payload.tags) else "处理中"
            )
            cursor.execute(
                "SELECT status, lease_id, lease_expires_at, taxonomy_version, source_payload_json "
                "FROM godp_topic_label_job "
                "WHERE topic_id=%s AND del_flag='N' FOR UPDATE", (topic_id,),
            )
            job = cursor.fetchone()
            from ..source_discovery import source_signature
            if job and job.get('source_payload_json') and source_signature(job['source_payload_json']) != source_signature(topic_row['payload_json']):
                raise ApplicationError(409, '选题内容已变化，当前识别结果已失效')
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            labels = single_choice_labels(payload.tags) if label_status == "已完成" else None
            tags = ({dimension.upper(): [name] for dimension, name in labels.items()}
                    if labels else payload.tags)
            tags_json = as_json(tags)
            cursor.execute(
                "SELECT version, tags_json, tag_ids_json, taxonomy_version, t6_tag_id, "
                "label_status, label_error, del_flag FROM godp_topic_tag "
                "WHERE topic_id=%s FOR UPDATE", (topic_id,),
            )
            previous = cursor.fetchone()
            if previous and previous["del_flag"] == "N" and (
                previous["label_status"] == "已完成" and label_status == "已完成" and
                previous["tags_json"] == tags_json and
                previous["label_error"] == payload.label_error and
                payload.taxonomy_version in (None, previous["taxonomy_version"])
            ):
                upsert_topic_profile(cursor, topic_id, topic_row["payload_json"],
                                     previous["tags_json"], previous["version"])
                db.commit()
                return {"topic_id": topic_id, "version": previous["version"],
                        "label_status": "已完成",
                        "taxonomy_version": previous["taxonomy_version"],
                        "tag_ids": json.loads(previous["tag_ids_json"] or "{}"),
                        "t6_tag_id": previous["t6_tag_id"]}
            if job:
                if job["status"] == "cancelled":
                    raise ApplicationError(status_code=409, detail="选题已退出待识别范围")
                if label_status not in ("已完成", "失败"):
                    raise ApplicationError(status_code=409, detail="任务结果只能是已完成或失败")
                if job["status"] == "processing":
                    if payload.lease_id != job["lease_id"] or not job["lease_expires_at"] \
                            or job["lease_expires_at"] <= now:
                        raise ApplicationError(status_code=409, detail="识别任务租约无效或已过期")
                    if label_status == "已完成" and payload.taxonomy_version != job["taxonomy_version"]:
                        raise ApplicationError(status_code=409, detail="识别结果的字典版本与任务租约不一致")
                elif payload.lease_id is not None and not (
                    job["status"] == "completed" and label_status == "已完成" and
                    previous and previous["label_status"] == "已完成"
                ):
                    raise ApplicationError(status_code=409, detail="识别任务尚未领取或租约已失效")
            elif payload.lease_id is not None:
                raise ApplicationError(status_code=409, detail="识别任务不存在")
            if labels and (payload.t6_embedding is None or payload.t6_embedding_model is None):
                raise ApplicationError(status_code=422, detail="首次完成标签识别必须提供 T6 语义向量及模型标识")
            tag_ids, taxonomy_version = (
                resolve_topic_tag_ids(cursor, labels, payload.taxonomy_version)
                if labels else ({}, None)
            )
            t6_tag_id = None
            if labels:
                t6_tag_id, canonical_t6 = resolve_t6_tag(
                    cursor, labels["t6"],
                    normalized_embedding(payload.t6_embedding, payload.t6_embedding_model),
                    payload.t6_embedding_model.strip(),
                )
                tags["T6"] = [canonical_t6]
                tags_json = as_json(tags)
            ids_json = as_json(tag_ids)
            if previous and previous["del_flag"] == "N" and (
                previous["tags_json"] == tags_json and
                previous["tag_ids_json"] == ids_json and
                previous["taxonomy_version"] == taxonomy_version and
                previous["t6_tag_id"] == t6_tag_id and
                previous["label_status"] == label_status and
                previous["label_error"] == payload.label_error
            ):
                if label_status == "已完成":
                    upsert_topic_profile(cursor, topic_id, topic_row["payload_json"],
                                         tags_json, previous["version"])
                if job and job["status"] != ("completed" if label_status == "已完成" else "failed"):
                    cursor.execute(
                        "UPDATE godp_topic_label_job SET status=%s, completed_at=%s, "
                        "lease_id=NULL, lease_expires_at=NULL, last_error=%s, "
                        "update_by='label-worker' WHERE topic_id=%s",
                        ("completed" if label_status == "已完成" else "failed",
                         now if label_status == "已完成" else None,
                         payload.label_error if label_status == "失败" else "", topic_id),
                    )
                db.commit()
                return {"topic_id": topic_id, "version": previous["version"],
                        "label_status": label_status, "taxonomy_version": taxonomy_version,
                        "tag_ids": tag_ids, "t6_tag_id": t6_tag_id}
            if previous and previous["del_flag"] == "N" and previous["label_status"] == "已完成":
                raise ApplicationError(status_code=409, detail="普通选题标签已完成，不支持重新计算")
            if job and job["status"] == "completed":
                raise ApplicationError(status_code=409, detail="普通选题标签任务已完成")
            version = previous["version"] + 1 if previous else 1
            cursor.execute(
                "INSERT INTO godp_topic_tag "
                "(topic_id, version, tags_json, tag_ids_json, taxonomy_version, t6_tag_id, "
                "label_status, label_error) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE version=VALUES(version), tags_json=VALUES(tags_json), "
                "tag_ids_json=VALUES(tag_ids_json), taxonomy_version=VALUES(taxonomy_version), "
                "t6_tag_id=VALUES(t6_tag_id), "
                "label_status=VALUES(label_status), label_error=VALUES(label_error), "
                "update_by='system', del_flag='N'",
                (topic_id, version, tags_json, ids_json, taxonomy_version, t6_tag_id,
                 label_status, payload.label_error),
            )
            cursor.execute(
                "INSERT INTO godp_topic_tag_history "
                "(topic_id, version, tags_json, tag_ids_json, taxonomy_version, t6_tag_id, "
                "label_status, label_error) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (topic_id, version, tags_json, ids_json, taxonomy_version, t6_tag_id,
                 label_status, payload.label_error),
            )
            if label_status == "已完成":
                upsert_topic_profile(cursor, topic_id, topic_row["payload_json"],
                                     tags_json, version)
            if job:
                cursor.execute(
                    "UPDATE godp_topic_label_job SET status=%s, lease_id=NULL, "
                    "lease_expires_at=NULL, completed_at=%s, last_error=%s, "
                    "update_by='label-worker' WHERE topic_id=%s",
                    ("completed" if label_status == "已完成" else "failed",
                     now if label_status == "已完成" else None,
                     payload.label_error if label_status == "失败" else "", topic_id),
                )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc
    return {"topic_id": topic_id, "version": version, "label_status": label_status,
            "taxonomy_version": taxonomy_version, "tag_ids": tag_ids,
            "t6_tag_id": t6_tag_id}

def topic_tag_history(topic_id: str, limit: int = 100) -> dict:
    limit = max(1, min(limit, 200))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT version, tags_json, tag_ids_json, taxonomy_version, t6_tag_id, "
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
          "t6_tag_id": row["t6_tag_id"],
         "label_status": row["label_status"], "label_error": row["label_error"],
         "created_at": row["create_time"]}
        for row in rows
    ]}
