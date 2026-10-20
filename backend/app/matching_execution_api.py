"""Internal policy review and leased matching evaluation endpoints."""

from fastapi import APIRouter, Depends, Query
import pymysql

from .ai_preparation_api import guarded
from .ai_preparation import utc_text
from .db import connection
from .integration import db_error, require_integration_token
from .matching_contracts import (ClaimTask, LeaseHeartbeat, MatchingEvaluation, MatchingFailure,
                                 MatchingTaskCreate, PolicyConfirmation, PolicyCreate, TaskVersion)
from .matching_policy import confirm_policy, create_policy, policy_summary, select_policy
from .matching_tasks import (cancel_task, claim_task, create_task, fail_task, heartbeat_task,
                             read_evaluation, read_task_inputs, retry_task, save_evaluation, select_task, task_summary)
from .planning_pipeline_api import router as planning_pipeline_router


router = APIRouter(dependencies=[Depends(require_integration_token)])
router.include_router(planning_pipeline_router)


@router.post("/api/internal/matching-policies")
def create_matching_policy(payload: PolicyCreate) -> dict:
    return guarded(create_policy, payload)


@router.get("/api/internal/matching-policies")
def list_matching_policies(after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT * FROM godp_matching_policy WHERE del_flag='N' AND id>%s "
                           "ORDER BY id LIMIT %s", (after_id, limit))
            rows = cursor.fetchall()
        return {"policies": [policy_summary(row) for row in rows],
                "next_after_id": rows[-1]["id"] if rows else after_id}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.get("/api/internal/matching-policies/{policy_id}")
def matching_policy_detail(policy_id: int) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            return policy_summary(select_policy(cursor, policy_id), include_document=True)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/internal/matching-policies/{policy_id}/approve")
def approve_matching_policy(policy_id: int, payload: PolicyConfirmation) -> dict:
    return guarded(confirm_policy, policy_id, payload)


@router.post("/api/internal/matching-policies/{policy_id}/disable")
def disable_matching_policy(policy_id: int, payload: PolicyConfirmation) -> dict:
    try:
        return confirm_policy(policy_id, payload, disable=True)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/internal/matching-tasks")
def create_matching_task(payload: MatchingTaskCreate) -> dict:
    return guarded(create_task, payload)


@router.post("/api/internal/matching-tasks/claim")
def claim_matching_task(payload: ClaimTask) -> dict:
    return guarded(claim_task, payload)


@router.get("/api/internal/matching-tasks")
def list_matching_tasks(after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
                        preparation_id: int | None = Query(None, ge=1)) -> dict:
    query = "SELECT * FROM godp_matching_task WHERE del_flag='N' AND id>%s "
    params = [after_id]
    if preparation_id is not None:
        query += "AND preparation_id=%s "
        params.append(preparation_id)
    query += "ORDER BY id LIMIT %s"
    params.append(limit)
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return {"tasks": [task_summary(row) for row in rows],
                "next_after_id": rows[-1]["id"] if rows else after_id}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.get("/api/internal/matching-tasks/{task_id}")
def matching_task_detail(task_id: int) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            task = select_task(cursor, task_id)
            cursor.execute("SELECT attempt_number,status,error_code,lease_expires_at,completed_at "
                           "FROM godp_matching_attempt WHERE task_id=%s AND del_flag='N' "
                           "ORDER BY attempt_number DESC", (task_id,))
            attempts = [{**row, "lease_expires_at": utc_text(row["lease_expires_at"]),
                         "completed_at": utc_text(row["completed_at"])} for row in cursor.fetchall()]
        return {**task_summary(task), "attempts": attempts}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.get("/api/internal/matching-tasks/{task_id}/result")
def matching_task_result(task_id: int) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            task = select_task(cursor, task_id)
        return {**task_summary(task), "evaluation": read_evaluation(task)}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.get("/api/internal/matching-tasks/{task_id}/inputs")
def matching_task_inputs(task_id: int) -> dict:
    return guarded(read_task_inputs, task_id)


@router.post("/api/internal/matching-tasks/{task_id}/heartbeat")
def matching_task_heartbeat(task_id: int, payload: LeaseHeartbeat) -> dict:
    return guarded(heartbeat_task, task_id, payload)


@router.put("/api/internal/matching-tasks/{task_id}/evaluation")
def matching_task_evaluation(task_id: int, payload: MatchingEvaluation) -> dict:
    return guarded(save_evaluation, task_id, payload)


@router.put("/api/internal/matching-tasks/{task_id}/failure")
def matching_task_failure(task_id: int, payload: MatchingFailure) -> dict:
    return guarded(fail_task, task_id, payload)


@router.post("/api/internal/matching-tasks/{task_id}/retry")
def matching_task_retry(task_id: int, payload: TaskVersion) -> dict:
    return guarded(retry_task, task_id, payload.expected_version)


@router.post("/api/internal/matching-tasks/{task_id}/cancel")
def matching_task_cancel(task_id: int, payload: TaskVersion) -> dict:
    return guarded(cancel_task, task_id, payload.expected_version)
