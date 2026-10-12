"""Leased ordinary matching evaluations bound to immutable inputs and policy."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from fastapi import HTTPException

from .account_profile import canonical_json
from .ai_preparation import (cycle_transaction, freeze_topic, load_frozen_inputs, select_preparation, utc_text)
from .db import connection
from .matching_contracts import (ClaimTask, LeaseIdentity, LeaseHeartbeat, MatchingEvaluation,
                                 MatchingFailure, MatchingTaskCreate)
from .matching_inputs import load_matching_topics
from .matching_policy import digest, intact_document, select_policy
from .matching_readiness import topic_state
from .planning_reservation import reservation_key


class InvalidInputs(Exception):
    def __init__(self, code: str):
        self.code = code


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def task_summary(row: dict, *, reused: bool = False) -> dict:
    return {"task_id": row["id"], "preparation_id": row["preparation_id"],
            "preparation_version": row["preparation_version"], "policy_id": row["policy_id"],
            "policy_hash": row["policy_hash"], "input_hash": row["input_hash"],
            "status": row["status"], "version": row["version"], "attempt_count": row["attempt_count"],
            "lease_expires_at": utc_text(row["lease_expires_at"]), "error_code": row["error_code"],
            "result_hash": row["result_hash"], "completed_at": utc_text(row["completed_at"]),
            "evaluation_scope": "ordinary_only", "operations_result_committed": False,
            "production_batch_id": None, "reused": reused}


def select_task(cursor, task_id: int, *, lock: bool = False) -> dict:
    cursor.execute("SELECT * FROM godp_matching_task WHERE id=%s AND del_flag='N'"
                   + (" FOR UPDATE" if lock else ""), (task_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "匹配执行任务不存在")
    return row


def execution_hash(preparation: dict, policy: dict) -> str:
    return digest(canonical_json({"contract_version": 1, "evaluation_scope": "ordinary_only",
                                  "preparation_id": preparation["id"],
                                  "preparation_version": preparation["version"],
                                  "preparation_input_hash": preparation["input_hash"],
                                  "policy_id": policy["id"], "policy_hash": policy["document_hash"]}))


def checked_inputs(cursor, preparation: dict, policy: dict, checked_at: datetime) -> dict:
    from zoneinfo import ZoneInfo
    if preparation["status"] != "inputs_frozen" \
            or preparation["reservation_key"] != reservation_key(preparation["cycle_start"]):
        raise InvalidInputs("preparation_not_active")
    if preparation["cycle_end"] < checked_at.astimezone(ZoneInfo("Asia/Shanghai")).date():
        raise InvalidInputs("cycle_expired")
    try:
        inputs, _ = load_frozen_inputs(cursor, preparation)
        document = intact_document(policy)
    except HTTPException as exc:
        raise InvalidInputs("snapshot_integrity_error") from exc
    if policy["status"] != "approved" or document.approval_errors():
        raise InvalidInputs("policy_not_approved")
    space = document.vector_space
    for row in inputs["accounts"] + inputs["topics"]:
        if row["vector_model"] != space.vector_model or len(row["vector"]) != space.dimension:
            raise InvalidInputs("policy_vector_space_mismatch")
    current = {topic["topic_id"]: topic for topic in load_matching_topics(cursor, checked_at)}
    for frozen in inputs["topics"]:
        row = current.get(frozen["topic_id"])
        if not row or topic_state(row, checked_at) != ("ready", (space.vector_model, space.dimension)):
            raise InvalidInputs("topic_inputs_stale")
        try:
            if canonical_json(freeze_topic(row)) != canonical_json(frozen):
                raise InvalidInputs("topic_inputs_stale")
        except (TypeError, ValueError, KeyError) as exc:
            raise InvalidInputs("topic_inputs_stale") from exc
    return inputs


def check_binding(task: dict, preparation: dict, policy: dict) -> None:
    if task["preparation_version"] != preparation["version"] \
            or task["preparation_input_hash"] != preparation["input_hash"] \
            or task["policy_hash"] != policy["document_hash"] \
            or task["input_hash"] != execution_hash(preparation, policy):
        raise InvalidInputs("task_binding_changed")


@contextmanager
def locked_task(task_id: int):
    # Always cycle -> preparation -> policy -> task. A disabled policy and
    # cancelled preparation cannot race a result acceptance in this order.
    with connection() as db, db.cursor() as cursor:
        initial = select_task(cursor, task_id)
        start = select_preparation(cursor, initial["preparation_id"])["cycle_start"]
    with cycle_transaction(start) as (db, cursor):
        preparation = select_preparation(cursor, initial["preparation_id"], lock=True)
        policy = select_policy(cursor, initial["policy_id"], lock=True)
        task = select_task(cursor, task_id, lock=True)
        if task["preparation_id"] != preparation["id"] or task["policy_id"] != policy["id"]:
            raise HTTPException(409, "执行任务绑定发生变化")
        yield db, cursor, preparation, policy, task


def finish_attempt(cursor, task: dict, state: str, code: str = "") -> None:
    if task["lease_id"]:
        cursor.execute("UPDATE godp_matching_attempt SET status=%s,error_code=%s, "
                       "completed_at=UTC_TIMESTAMP(6),update_by='matching-task-api' "
                       "WHERE task_id=%s AND lease_id=%s AND status='processing'",
                       (state, code, task["id"], task["lease_id"]))


def invalidate(db, cursor, task: dict, code: str) -> None:
    finish_attempt(cursor, task, "expired", code)
    cursor.execute("UPDATE godp_matching_task SET status='invalidated',error_code=%s, "
                   "version=version+1,lease_id=NULL,lease_expires_at=NULL, "
                   "update_by='matching-task-api' WHERE id=%s", (code, task["id"]))
    db.commit()


def read_evaluation(task: dict) -> dict:
    if task["status"] != "evaluated":
        raise HTTPException(409, "任务尚未保存有效匹配提案")
    try:
        result = MatchingEvaluation.model_validate_json(task["result_json"])
        encoded = result.model_dump(mode="json")
        if digest(canonical_json(encoded)) != task["result_hash"] \
                or result.input_hash != task["input_hash"] or result.policy_hash != task["policy_hash"] \
                or result.lease_id != task["lease_id"]:
            raise ValueError("提案指纹不一致")
        return encoded
    except (TypeError, ValueError) as exc:
        raise HTTPException(409, "已保存匹配提案完整性校验未通过") from exc


def require_current_inputs(db, cursor, preparation, policy, task, checked_at) -> dict:
    try:
        check_binding(task, preparation, policy)
        return checked_inputs(cursor, preparation, policy, checked_at)
    except InvalidInputs as exc:
        invalidate(db, cursor, task, exc.code)
        raise HTTPException(409, {"message": "执行输入或策略已失效", "code": exc.code}) from exc


def create_task(payload: MatchingTaskCreate) -> dict:
    with connection() as db, db.cursor() as cursor:
        start = select_preparation(cursor, payload.preparation_id)["cycle_start"]
    with cycle_transaction(start) as (db, cursor):
        preparation = select_preparation(cursor, payload.preparation_id, lock=True)
        policy = select_policy(cursor, payload.policy_id, lock=True)
        if preparation["version"] != payload.expected_preparation_version:
            raise HTTPException(409, "准备记录版本不一致，请重新查询")
        cursor.execute("SELECT * FROM godp_matching_task WHERE preparation_id=%s FOR UPDATE",
                       (payload.preparation_id,))
        existing = cursor.fetchone()
        if existing:
            if existing["policy_id"] != payload.policy_id:
                raise HTTPException(409, "该准备记录已绑定其他策略版本，请新建准备记录")
            db.rollback()
            return task_summary(existing, reused=True)
        try:
            checked_inputs(cursor, preparation, policy, now_utc())
        except InvalidInputs as exc:
            raise HTTPException(409, {"message": "匹配输入或算法策略尚不可执行", "code": exc.code}) from exc
        fingerprint = execution_hash(preparation, policy)
        cursor.execute("INSERT INTO godp_matching_task "
                       "(preparation_id,preparation_version,preparation_input_hash,policy_id,policy_hash, "
                       "input_hash,create_by,update_by) VALUES (%s,%s,%s,%s,%s,%s,'matching-task-api','matching-task-api')",
                       (preparation["id"], preparation["version"], preparation["input_hash"], policy["id"],
                        policy["document_hash"], fingerprint))
        task = select_task(cursor, cursor.lastrowid)
        db.commit()
        return task_summary(task)


def claim_task(payload: ClaimTask) -> dict:
    now = now_utc()
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT id FROM godp_matching_task WHERE del_flag='N' AND id>%s "
                       "AND (status='queued' OR (status='processing' AND lease_expires_at<=%s)) "
                       "ORDER BY id LIMIT 1", (payload.after_id, now.replace(tzinfo=None)))
        candidate = cursor.fetchone()
    if not candidate:
        return {"job": None, "next_after_id": payload.after_id}
    with locked_task(candidate["id"]) as (db, cursor, preparation, policy, task):
        now = now_utc()
        if task["status"] not in ("queued", "processing") or (task["status"] == "processing"
                and task["lease_expires_at"] > now.replace(tzinfo=None)):
            db.rollback()
            return {"job": None, "next_after_id": task["id"]}
        try:
            check_binding(task, preparation, policy)
            inputs = checked_inputs(cursor, preparation, policy, now)
        except InvalidInputs as exc:
            invalidate(db, cursor, task, exc.code)
            return {"job": None, "next_after_id": task["id"], "invalidated_code": exc.code}
        finish_attempt(cursor, task, "expired", "lease_expired")
        lease_id = uuid4().hex
        expires = (now + timedelta(seconds=payload.lease_seconds)).replace(tzinfo=None)
        attempt = task["attempt_count"] + 1
        cursor.execute("UPDATE godp_matching_task SET status='processing',version=version+1, "
                       "attempt_count=%s,lease_id=%s,lease_expires_at=%s,error_code='', "
                       "update_by='matching-task-api' WHERE id=%s", (attempt, lease_id, expires, task["id"]))
        cursor.execute("INSERT INTO godp_matching_attempt "
                       "(task_id,attempt_number,lease_id,lease_expires_at,create_by,update_by) "
                       "VALUES (%s,%s,%s,%s,'matching-task-api','matching-task-api')",
                       (task["id"], attempt, lease_id, expires))
        claimed = select_task(cursor, task["id"])
        db.commit()
        return {"next_after_id": task["id"], "job": {**task_summary(claimed), "lease_id": lease_id,
                "contract_version": 1, "inputs": inputs, "policy": json.loads(policy["document_json"])}}


def require_lease(task: dict, payload: LeaseIdentity, checked_at: datetime) -> None:
    if task["lease_id"] != payload.lease_id or task["input_hash"] != payload.input_hash \
            or task["policy_hash"] != payload.policy_hash:
        raise HTTPException(409, "执行租约或输入版本不一致")
    if task["status"] != "processing" or not task["lease_expires_at"] \
            or task["lease_expires_at"] <= checked_at.replace(tzinfo=None):
        raise HTTPException(409, "执行租约已结束或过期")


def heartbeat_task(task_id: int, payload: LeaseHeartbeat) -> dict:
    with locked_task(task_id) as (db, cursor, preparation, policy, task):
        now = now_utc()
        require_lease(task, payload, now)
        require_current_inputs(db, cursor, preparation, policy, task, now)
        expires = (now + timedelta(seconds=payload.lease_seconds)).replace(tzinfo=None)
        cursor.execute("UPDATE godp_matching_task SET lease_expires_at=%s, "
                       "update_by='matching-task-api' WHERE id=%s", (expires, task_id))
        cursor.execute("UPDATE godp_matching_attempt SET lease_expires_at=%s, "
                       "update_by='matching-task-api' WHERE task_id=%s AND lease_id=%s",
                       (expires, task_id, payload.lease_id))
        db.commit()
        return {"task_id": task_id, "lease_id": payload.lease_id, "lease_expires_at": utc_text(expires)}


def validate_positions(result: MatchingEvaluation, inputs: dict, policy: dict) -> None:
    document = intact_document(policy)
    if result.implementation_key != document.implementation_key:
        raise HTTPException(409, "执行器实现与策略绑定不一致")
    expected = {(p["account_id"], p["publish_date"]) for p in inputs["positions"]}
    actual = [(p.account_id, p.publish_date.isoformat()) for p in result.positions]
    if len(actual) != len(expected) or set(actual) != expected:
        raise HTTPException(422, "匹配提案须完整覆盖冻结日期安排，不能重复或新增账号日期")
    topics = {p["topic_id"] for p in inputs["topics"]}
    if any(p.topic_id not in topics for p in result.positions if p.topic_id is not None):
        raise HTTPException(422, "匹配提案引用了冻结输入以外的选题")


def save_evaluation(task_id: int, payload: MatchingEvaluation) -> dict:
    encoded = canonical_json(payload.model_dump(mode="json"))
    fingerprint = digest(encoded)
    with locked_task(task_id) as (db, cursor, preparation, policy, task):
        if task["status"] == "evaluated":
            if task["result_hash"] != fingerprint:
                raise HTTPException(409, "执行提案已保存，不允许覆盖")
            db.rollback()
            return task_summary(task, reused=True)
        now = now_utc()
        require_lease(task, payload, now)
        inputs = require_current_inputs(db, cursor, preparation, policy, task, now)
        validate_positions(payload, inputs, policy)
        cursor.execute("UPDATE godp_matching_task SET status='evaluated',version=version+1, "
                       "result_json=%s,result_hash=%s,completed_at=%s,error_code='', "
                       "update_by='matching-task-api' WHERE id=%s", (encoded, fingerprint, now.replace(tzinfo=None), task_id))
        finish_attempt(cursor, task, "evaluated")
        saved = select_task(cursor, task_id)
        db.commit()
        return task_summary(saved)


def fail_task(task_id: int, payload: MatchingFailure) -> dict:
    with locked_task(task_id) as (db, cursor, preparation, policy, task):
        now = now_utc()
        if task["status"] == "failed" and task["lease_id"] == payload.lease_id \
                and task["input_hash"] == payload.input_hash and task["policy_hash"] == payload.policy_hash \
                and task["error_code"] == payload.error_code:
            db.rollback()
            return task_summary(task, reused=True)
        require_lease(task, payload, now)
        require_current_inputs(db, cursor, preparation, policy, task, now)
        cursor.execute("UPDATE godp_matching_task SET status='failed',version=version+1,error_code=%s, "
                       "update_by='matching-task-api' WHERE id=%s", (payload.error_code, task_id))
        finish_attempt(cursor, task, "failed", payload.error_code)
        saved = select_task(cursor, task_id)
        db.commit()
        return task_summary(saved)


def retry_task(task_id: int, expected_version: int) -> dict:
    with locked_task(task_id) as (db, cursor, preparation, policy, task):
        if task["version"] != expected_version or task["status"] != "failed":
            raise HTTPException(409, "任务版本不一致或不属于可重试失败状态")
        require_current_inputs(db, cursor, preparation, policy, task, now_utc())
        cursor.execute("UPDATE godp_matching_task SET status='queued',version=version+1, "
                       "lease_id=NULL,lease_expires_at=NULL,error_code='',update_by='matching-task-api' WHERE id=%s", (task_id,))
        saved = select_task(cursor, task_id)
        db.commit()
        return task_summary(saved)


def cancel_task(task_id: int, expected_version: int) -> dict:
    with locked_task(task_id) as (db, cursor, preparation, policy, task):
        if task["version"] != expected_version:
            raise HTTPException(409, "任务版本不一致")
        if task["status"] in ("evaluated", "invalidated"):
            raise HTTPException(409, "提案已保存或输入已失效，不能取消")
        if task["status"] != "cancelled":
            finish_attempt(cursor, task, "expired", "task_cancelled")
            cursor.execute("UPDATE godp_matching_task SET status='cancelled',version=version+1, "
                           "lease_id=NULL,lease_expires_at=NULL,error_code='task_cancelled', "
                           "update_by='matching-task-api' WHERE id=%s", (task_id,))
        saved = select_task(cursor, task_id)
        db.commit()
        return task_summary(saved)
