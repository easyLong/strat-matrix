"""Control-plane runner that advances Pipeline V1 through formal result commit."""

from datetime import datetime, timezone

from fastapi import HTTPException

from .account_profile import canonical_json
from .db import connection
from .planning_pipeline import advance_pipeline, read_pipeline, retry_pipeline
from .planning_result_commit import ResultCommitError, commit_pipeline_result


ACTOR = "planning-pipeline-api"


def _record_commit_failure(pipeline_id: int, expected_version: int,
                           error: ResultCommitError) -> dict:
    """Persist a retryable result-commit failure after the atomic transaction rolled back."""
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT * FROM godp_planning_pipeline_run WHERE id=%s AND del_flag='N' FOR UPDATE",
                       (pipeline_id,))
        pipeline = cursor.fetchone()
        if not pipeline:
            raise HTTPException(404, "Pipeline运行记录不存在")
        if pipeline["version"] != expected_version:
            raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
        if pipeline["production_batch_id"] is not None:
            db.rollback()
            return read_pipeline(pipeline_id)
        cursor.execute("SELECT * FROM godp_planning_stage_run WHERE pipeline_id=%s "
                       "AND stage_key='result_commit' AND del_flag='N' FOR UPDATE", (pipeline_id,))
        stage = cursor.fetchone()
        if not stage:
            raise HTTPException(409, "Pipeline正式提交阶段不存在")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        detail = canonical_json({"operations_result_committed": False,
                                 "matching_task_id": pipeline["matching_task_id"],
                                 "retryable": True})
        cursor.execute(
            "UPDATE godp_planning_stage_run SET status='failed',attempt_count=attempt_count+1,"
            "detail_json=%s,error_code=%s,error_message=%s,started_at=COALESCE(started_at,%s),"
            "finished_at=%s,version=version+1,update_by=%s WHERE id=%s",
            (detail, error.code[:64], error.message[:500], now, now, ACTOR, stage["id"]),
        )
        cursor.execute(
            "UPDATE godp_planning_pipeline_run SET status='failed',current_stage='result_commit',"
            "last_error_code=%s,last_error_message=%s,version=version+1,update_by=%s WHERE id=%s",
            (error.code[:64], error.message[:500], ACTOR, pipeline_id),
        )
        db.commit()
    return read_pipeline(pipeline_id)


def _maybe_commit(result: dict) -> dict:
    stages = {stage["stage_key"]: stage for stage in result["stages"]}
    if result["production_batch_id"] is not None or result["status"] == "succeeded":
        return result
    if result["active_stages"] != ["result_commit"]:
        return result
    if any(stages[key]["status"] != "succeeded"
           for key in ("single_account_matching", "matrix_allocation", "composition")):
        return result
    try:
        commit_pipeline_result(result["pipeline_id"], result["version"])
    except ResultCommitError as exc:
        return _record_commit_failure(result["pipeline_id"], result["version"], exc)
    return read_pipeline(result["pipeline_id"])


def advance_pipeline_to_commit(pipeline_id: int, expected_version: int) -> dict:
    return _maybe_commit(advance_pipeline(pipeline_id, expected_version))


def retry_pipeline_to_commit(pipeline_id: int, expected_version: int) -> dict:
    snapshot = read_pipeline(pipeline_id)
    if snapshot["version"] != expected_version:
        raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
    # The base V1 retry intentionally refused result_commit while it was not
    # implemented. Once the adapter exists, retry that stage directly without
    # re-running a successful immutable MatchingEvaluation.
    if snapshot["active_stages"] == ["result_commit"]:
        if snapshot["status"] not in ("failed", "waiting", "pending"):
            raise HTTPException(409, "正式提交阶段当前不属于可重试状态")
        return _maybe_commit(snapshot)
    return _maybe_commit(retry_pipeline(pipeline_id, expected_version))
