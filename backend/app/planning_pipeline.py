"""Versioned orchestration for the formal planning pipeline.

V1 deliberately reuses AI preparation and the existing matching task instead of
inventing a second execution stack. Matching stages 4-6 are projections of one
matching task; they are not independently retryable until the matching contract
is split in a later version. The final operations commit is performed by the
planning_pipeline_runner after this control-plane projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import HTTPException

from .account_profile import canonical_json
from .ai_preparation import (advance_preparation, cancel_preparation,
                             create_preparation, read_preparation)
from .db import connection
from .matching_contracts import MatchingTaskCreate
from .matching_policy import intact_document, select_policy
from .matching_tasks import (cancel_task, create_task, read_evaluation,
                             retry_task, select_task, task_summary)
from .ordinary_planning import current_next_monday


ACTOR = "planning-pipeline-api"
PIPELINE_SCHEMA_VERSION = 1
STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_WAITING = "waiting"
STAGE_SUCCEEDED = "succeeded"
STAGE_FAILED = "failed"
STAGE_CANCELLED = "cancelled"
STAGE_STATES = {STAGE_PENDING, STAGE_RUNNING, STAGE_WAITING,
                STAGE_SUCCEEDED, STAGE_FAILED, STAGE_CANCELLED}


@dataclass(frozen=True)
class StageSpec:
    key: str
    label: str
    order: int
    dependencies: tuple[str, ...]


STAGES = (
    StageSpec("source_ingestion", "数据源接入", 10, ()),
    StageSpec("topic_profile", "选题打标与画像", 20, ("source_ingestion",)),
    StageSpec("account_profile", "账号画像", 30, ("source_ingestion",)),
    StageSpec("single_account_matching", "单账号选题匹配", 40,
              ("topic_profile", "account_profile")),
    StageSpec("matrix_allocation", "全账号矩阵分配", 50,
              ("single_account_matching",)),
    StageSpec("composition", "选题组合编排", 60, ("matrix_allocation",)),
    StageSpec("result_commit", "结果校验与正式提交", 70, ("composition",)),
)
STAGE_BY_KEY = {stage.key: stage for stage in STAGES}
MATCHING_STAGE_KEYS = ("single_account_matching", "matrix_allocation", "composition")


def now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _selection(account_ids: list[str] | None) -> tuple[str, str]:
    if account_ids is not None:
        if (not account_ids or len(set(account_ids)) != len(account_ids)
                or any(not value.strip() or len(value) > 64 or value.startswith("DEMO-")
                       for value in account_ids)):
            raise HTTPException(422, "参与账号须为非空、无重复的正式账号编码")
        normalized: list[str] | None = sorted(account_ids)
    else:
        normalized = None
    encoded = canonical_json(normalized)
    return encoded, sha256(encoded.encode("utf-8")).hexdigest()


def pipeline_reservation_key(start: date) -> str:
    return f"formal-planning:{start.isoformat()}"


def _validate_policy(policy_id: int) -> None:
    with connection() as db, db.cursor() as cursor:
        row = select_policy(cursor, policy_id)
        document = intact_document(row)
    if row["status"] != "approved" or document.approval_errors():
        raise HTTPException(409, "Pipeline只能绑定已批准且规则完整的算法策略版本")


def _json(value) -> dict | list | None:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _time_text(value) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def stage_summary(row: dict) -> dict:
    spec = STAGE_BY_KEY[row["stage_key"]]
    return {
        "stage_key": row["stage_key"],
        "label": spec.label,
        "stage_order": row["stage_order"],
        "dependencies": list(spec.dependencies),
        "status": row["status"],
        "attempt_count": row["attempt_count"],
        "version": row["version"],
        "backend_type": row["backend_type"] or None,
        "backend_id": row["backend_id"],
        "detail": _json(row["detail_json"]),
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "started_at": _time_text(row["started_at"]),
        "finished_at": _time_text(row["finished_at"]),
    }


def _frontier(stage_rows: list[dict]) -> list[str]:
    states = {row["stage_key"]: row["status"] for row in stage_rows}
    active: list[str] = []
    for spec in STAGES:
        if states.get(spec.key) == STAGE_SUCCEEDED:
            continue
        if all(states.get(key) == STAGE_SUCCEEDED for key in spec.dependencies):
            active.append(spec.key)
    return active


def _run_status(stage_rows: list[dict]) -> str:
    states = [row["status"] for row in stage_rows]
    if states and all(state == STAGE_SUCCEEDED for state in states):
        return STAGE_SUCCEEDED
    if STAGE_FAILED in states:
        return STAGE_FAILED
    if STAGE_RUNNING in states:
        return STAGE_RUNNING
    if STAGE_WAITING in states:
        return STAGE_WAITING
    return STAGE_PENDING


def pipeline_summary(row: dict, stage_rows: list[dict], *, reused: bool = False) -> dict:
    frontier = _frontier(stage_rows)
    return {
        "pipeline_id": row["id"],
        "pipeline_code": row["pipeline_code"],
        "schema_version": row["schema_version"],
        "cycle_start": row["cycle_start"],
        "cycle_end": row["cycle_end"],
        "status": row["status"],
        "version": row["version"],
        "policy_id": row["policy_id"],
        "planning_scope": row.get('planning_scope', 'full'),
        "production_provider": row.get('production_provider', 'disabled'),
        "preparation_id": row["preparation_id"],
        "matching_task_id": row["matching_task_id"],
        "production_batch_id": row["production_batch_id"],
        "operations_result_committed": row["production_batch_id"] is not None,
        "current_stage": row["current_stage"],
        "active_stages": frontier,
        "last_error_code": row["last_error_code"],
        "last_error_message": row["last_error_message"],
        "stages": [stage_summary(item) for item in stage_rows],
        "reused": reused,
    }


def select_pipeline(cursor, pipeline_id: int, *, lock: bool = False) -> dict:
    cursor.execute("SELECT * FROM godp_planning_pipeline_run WHERE id=%s AND del_flag='N'"
                   + (" FOR UPDATE" if lock else ""), (pipeline_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Pipeline运行记录不存在")
    if row.get("schema_version") != PIPELINE_SCHEMA_VERSION:
        raise HTTPException(409, "Pipeline编排契约版本不受当前服务支持")
    return row


def select_stages(cursor, pipeline_id: int, *, lock: bool = False) -> list[dict]:
    cursor.execute("SELECT * FROM godp_planning_stage_run WHERE pipeline_id=%s AND del_flag='N' "
                   "ORDER BY stage_order,id" + (" FOR UPDATE" if lock else ""), (pipeline_id,))
    rows = cursor.fetchall()
    if len(rows) != len(STAGES) or {row["stage_key"] for row in rows} != set(STAGE_BY_KEY):
        raise HTTPException(409, "Pipeline阶段记录不完整")
    if any(row["stage_order"] != STAGE_BY_KEY[row["stage_key"]].order
           or row["status"] not in STAGE_STATES for row in rows):
        raise HTTPException(409, "Pipeline阶段契约或状态已损坏")
    return rows


def _read_selection(row: dict) -> list[str] | None:
    value = _json(row["selection_json"])
    if value is not None and (not isinstance(value, list)
                              or any(not isinstance(item, str) for item in value)):
        raise HTTPException(409, "Pipeline账号范围快照格式已损坏")
    encoded = canonical_json(value)
    if sha256(encoded.encode("utf-8")).hexdigest() != row["selection_hash"]:
        raise HTTPException(409, "Pipeline账号范围快照指纹校验未通过")
    return value


def read_pipeline(pipeline_id: int) -> dict:
    with connection() as db, db.cursor() as cursor:
        row = select_pipeline(cursor, pipeline_id)
        stages = select_stages(cursor, pipeline_id)
    return pipeline_summary(row, stages)


def create_pipeline(cycle_start: date | None, account_ids: list[str] | None, policy_id: int,
                    planning_scope: str = 'full', production_provider: str = 'disabled') -> dict:
    if planning_scope not in ('full', 'ordinary_only') or production_provider not in ('disabled', 'local_mock'):
        raise HTTPException(422, '无效的策划范围或内容生产方式')
    start = cycle_start or current_next_monday()
    if start.weekday() != 0:
        raise HTTPException(422, "策划周期必须从周一开始")
    if start < current_next_monday():
        raise HTTPException(422, "只能为下周或更晚的周期新建Pipeline")
    selection_json, selection_hash = _selection(account_ids)
    _validate_policy(policy_id)
    reservation = pipeline_reservation_key(start)
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        lock_name = f"godp:ordinary:live:{start:%Y%m%d}"
        cursor.execute("SELECT GET_LOCK(%s,5) AS acquired", (lock_name,))
        if cursor.fetchone()["acquired"] != 1:
            raise HTTPException(409, "该周期策划正在处理，请稍后重试")
        try:
            cursor.execute("SELECT * FROM godp_planning_pipeline_run WHERE reservation_key=%s "
                           "AND del_flag='N' FOR UPDATE", (reservation,))
            existing = cursor.fetchone()
            if existing:
                if (existing["selection_hash"] != selection_hash or existing["policy_id"] != policy_id
                        or existing.get('planning_scope', 'full') != planning_scope
                        or existing.get('production_provider', 'disabled') != production_provider):
                    raise HTTPException(409, "该周期已有不同账号范围或算法策略的Pipeline")
                stages = select_stages(cursor, existing["id"])
                db.rollback()
                return pipeline_summary(existing, stages, reused=True)
            cursor.execute(
                "INSERT INTO godp_planning_pipeline_run "
                "(pipeline_code,reservation_key,schema_version,cycle_start,cycle_end,selection_json,"
                "selection_hash,policy_id,planning_scope,production_provider,status,current_stage,create_by,update_by) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending','source_ingestion',%s,%s)",
                (f"PIPE-{start:%Y%m%d}-{uuid4().hex[:12]}", reservation, PIPELINE_SCHEMA_VERSION,
                 start, start + timedelta(days=6), selection_json, selection_hash, policy_id,
                 planning_scope, production_provider, ACTOR, ACTOR),
            )
            pipeline_id = cursor.lastrowid
            for spec in STAGES:
                cursor.execute(
                    "INSERT INTO godp_planning_stage_run "
                    "(pipeline_id,stage_key,stage_order,status,create_by,update_by) "
                    "VALUES (%s,%s,%s,'pending',%s,%s)",
                    (pipeline_id, spec.key, spec.order, ACTOR, ACTOR),
                )
            row = select_pipeline(cursor, pipeline_id)
            stages = select_stages(cursor, pipeline_id)
            db.commit()
            return pipeline_summary(row, stages)
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


def _error_parts(exc: HTTPException, default_code: str) -> tuple[str, str]:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or default_code)[:64]
        message = str(detail.get("message") or detail)[:500]
        return code, message
    return default_code, str(detail)[:500]


def _desired(status: str, *, backend_type: str | None = None, backend_id: int | None = None,
             detail=None, error_code: str = "", error_message: str = "") -> dict:
    if status not in STAGE_STATES:
        raise ValueError(f"unsupported pipeline stage state: {status}")
    return {
        "status": status,
        "backend_type": backend_type,
        "backend_id": backend_id,
        "detail": detail,
        "error_code": error_code[:64],
        "error_message": error_message[:500],
    }


def _preparation_projection(preparation: dict) -> dict[str, dict]:
    detail = {
        "preparation_status": preparation["status"],
        "preparation_version": preparation["version"],
        "last_report": preparation.get("last_report"),
    }
    common = {"backend_type": "ai_preparation", "backend_id": preparation["preparation_id"], "detail": detail}
    if preparation["status"] == "inputs_frozen":
        state = _desired(STAGE_SUCCEEDED, **common)
        return {"topic_profile": state, "account_profile": dict(state)}
    if preparation["status"] == "waiting_inputs":
        state = _desired(STAGE_WAITING, **common, error_code="preparation_waiting_inputs",
                         error_message="等待选题标签/画像/向量或账号画像/向量准备完成")
        return {"topic_profile": state, "account_profile": dict(state)}
    if preparation["status"] == "blocked":
        state = _desired(STAGE_FAILED, **common, error_code="preparation_blocked",
                         error_message="AI准备输入存在结构性阻断，请修复后重试Pipeline")
        return {"topic_profile": state, "account_profile": dict(state)}
    code = f"preparation_{preparation['status']}"
    state = _desired(STAGE_FAILED, **common, error_code=code,
                     error_message="AI准备记录已不可继续执行")
    return {"topic_profile": state, "account_profile": dict(state)}


def _matching_projection(task: dict) -> dict[str, dict]:
    summary = task_summary(task)
    common = {"backend_type": "matching_task", "backend_id": task["id"]}
    if task["status"] == "queued":
        return {"single_account_matching": _desired(
            STAGE_WAITING, **common, detail=summary, error_code="matching_executor_queued",
            error_message="匹配任务已入队，等待真实执行器领取")}
    if task["status"] == "processing":
        return {"single_account_matching": _desired(STAGE_RUNNING, **common, detail=summary)}
    if task["status"] == "failed":
        return {"single_account_matching": _desired(
            STAGE_FAILED, **common, detail=summary,
            error_code=task["error_code"] or "matching_execution_failed",
            error_message="匹配执行失败，可通过Pipeline retry重试")}
    if task["status"] == "cancelled":
        return {"single_account_matching": _desired(
            STAGE_FAILED, **common, detail=summary, error_code="matching_task_cancelled",
            error_message="匹配执行任务已被取消")}
    if task["status"] == "invalidated":
        return {"single_account_matching": _desired(
            STAGE_FAILED, **common, detail=summary,
            error_code=task["error_code"] or "matching_task_invalidated",
            error_message="匹配执行输入或策略已失效，需要重新准备")}
    if task["status"] != "evaluated":
        return {"single_account_matching": _desired(
            STAGE_FAILED, **common, detail=summary, error_code="unknown_matching_state",
            error_message="匹配任务状态无法映射到Pipeline")}

    evaluation = read_evaluation(task)
    by_stage = {item["stage"]: item["summary"] for item in evaluation["stages"]}
    single_detail = {
        "task": summary,
        "hard_gate": by_stage.get("hard_gate"),
        "recall": by_stage.get("recall"),
        "fit": by_stage.get("fit"),
    }
    return {
        "single_account_matching": _desired(STAGE_SUCCEEDED, **common, detail=single_detail),
        "matrix_allocation": _desired(
            STAGE_SUCCEEDED, **common,
            detail={"task": summary, "global_allocation": by_stage.get("global_allocation")}),
        "composition": _desired(
            STAGE_SUCCEEDED, **common,
            detail={"task": summary, "composition": by_stage.get("composition")}),
    }


def _apply_stage(cursor, row: dict, desired: dict, now: datetime) -> dict:
    detail_json = canonical_json(desired["detail"]) if desired["detail"] is not None else None
    changed = any((
        row["status"] != desired["status"],
        (row["backend_type"] or None) != desired["backend_type"],
        row["backend_id"] != desired["backend_id"],
        row["detail_json"] != detail_json,
        row["error_code"] != desired["error_code"],
        row["error_message"] != desired["error_message"],
    ))
    if not changed:
        return row
    active = desired["status"] in (STAGE_WAITING, STAGE_RUNNING)
    starting = active and row["status"] not in (STAGE_WAITING, STAGE_RUNNING)
    attempt_count = row["attempt_count"] + (1 if starting else 0)
    started_at = row["started_at"] or (now if active else None)
    finished_at = now if desired["status"] in (STAGE_SUCCEEDED, STAGE_FAILED, STAGE_CANCELLED) else None
    cursor.execute(
        "UPDATE godp_planning_stage_run SET status=%s,attempt_count=%s,backend_type=%s,backend_id=%s,"
        "detail_json=%s,error_code=%s,error_message=%s,started_at=%s,finished_at=%s,"
        "version=version+1,update_by=%s WHERE id=%s",
        (desired["status"], attempt_count, desired["backend_type"], desired["backend_id"], detail_json,
         desired["error_code"], desired["error_message"], started_at, finished_at, ACTOR, row["id"]),
    )
    return {**row, "status": desired["status"], "attempt_count": attempt_count,
            "backend_type": desired["backend_type"], "backend_id": desired["backend_id"],
            "detail_json": detail_json, "error_code": desired["error_code"],
            "error_message": desired["error_message"], "started_at": started_at,
            "finished_at": finished_at, "version": row["version"] + 1}


def _persist(pipeline_id: int, expected_version: int, desired: dict[str, dict], *,
             preparation_id: int | None = None, matching_task_id: int | None = None) -> dict:
    with connection() as db, db.cursor() as cursor:
        row = select_pipeline(cursor, pipeline_id, lock=True)
        if row["version"] != expected_version:
            raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
        if row["status"] == STAGE_CANCELLED:
            db.rollback()
            return pipeline_summary(row, select_stages(cursor, pipeline_id), reused=True)
        stages = select_stages(cursor, pipeline_id, lock=True)
        now = now_utc_naive()
        updated = []
        for item in stages:
            update = desired.get(item["stage_key"])
            updated.append(_apply_stage(cursor, item, update, now) if update else item)
        status = _run_status(updated)
        frontier = _frontier(updated)
        current_stage = frontier[0] if frontier else None
        failed = next((item for item in updated if item["status"] == STAGE_FAILED), None)
        error_code = failed["error_code"] if failed else ""
        error_message = failed["error_message"] if failed else ""
        prep = preparation_id if preparation_id is not None else row["preparation_id"]
        task = matching_task_id if matching_task_id is not None else row["matching_task_id"]
        cursor.execute(
            "UPDATE godp_planning_pipeline_run SET status=%s,current_stage=%s,preparation_id=%s,"
            "matching_task_id=%s,last_error_code=%s,last_error_message=%s,version=version+1,update_by=%s "
            "WHERE id=%s",
            (status, current_stage, prep, task, error_code, error_message, ACTOR, pipeline_id),
        )
        saved = select_pipeline(cursor, pipeline_id)
        saved_stages = select_stages(cursor, pipeline_id)
        db.commit()
        return pipeline_summary(saved, saved_stages)


def _read_task(task_id: int) -> dict:
    with connection() as db, db.cursor() as cursor:
        return select_task(cursor, task_id)


def advance_pipeline(pipeline_id: int, expected_version: int, *, retry: bool = False) -> dict:
    snapshot = read_pipeline(pipeline_id)
    if snapshot["version"] != expected_version:
        raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
    if snapshot["status"] == STAGE_CANCELLED:
        return {**snapshot, "reused": True}
    if snapshot["status"] == STAGE_SUCCEEDED:
        return {**snapshot, "reused": True}

    desired: dict[str, dict] = {}
    preparation_id = snapshot["preparation_id"]
    matching_task_id = snapshot["matching_task_id"]
    with connection() as db, db.cursor() as cursor:
        row = select_pipeline(cursor, pipeline_id)
        account_ids = _read_selection(row)

    if preparation_id is None:
        try:
            if snapshot.get('planning_scope', 'full') == 'ordinary_only':
                preparation = create_preparation(snapshot["cycle_start"], account_ids, planning_scope='ordinary_only')
            else:
                preparation = create_preparation(snapshot["cycle_start"], account_ids)
            preparation_id = preparation["preparation_id"]
            desired["source_ingestion"] = _desired(
                STAGE_SUCCEEDED, backend_type="ai_preparation", backend_id=preparation_id,
                detail={"mode": "current_local_source_snapshot", "preparation_id": preparation_id})
        except HTTPException as exc:
            code, message = _error_parts(exc, "preparation_create_failed")
            desired["source_ingestion"] = _desired(
                STAGE_FAILED, error_code=code, error_message=message,
                detail={"mode": "current_local_source_snapshot"})
            return _persist(pipeline_id, expected_version, desired)
    else:
        preparation = read_preparation(preparation_id)
        desired["source_ingestion"] = _desired(
            STAGE_SUCCEEDED, backend_type="ai_preparation", backend_id=preparation_id,
            detail={"mode": "current_local_source_snapshot", "preparation_id": preparation_id})

    if preparation["status"] == "waiting_inputs" or (retry and preparation["status"] == "blocked"):
        preparation = advance_preparation(preparation_id, preparation["version"])
    desired.update(_preparation_projection(preparation))
    if preparation["status"] != "inputs_frozen":
        return _persist(pipeline_id, expected_version, desired, preparation_id=preparation_id)

    if matching_task_id is None:
        try:
            task_result = create_task(MatchingTaskCreate(
                preparation_id=preparation_id,
                expected_preparation_version=preparation["version"],
                policy_id=snapshot["policy_id"],
            ))
            matching_task_id = task_result["task_id"]
        except HTTPException as exc:
            code, message = _error_parts(exc, "matching_task_create_failed")
            desired["single_account_matching"] = _desired(
                STAGE_FAILED, error_code=code, error_message=message,
                detail={"preparation_id": preparation_id, "policy_id": snapshot["policy_id"]})
            return _persist(pipeline_id, expected_version, desired,
                            preparation_id=preparation_id)

    task = _read_task(matching_task_id)
    if retry and task["status"] == "failed":
        retry_task(matching_task_id, task["version"])
        task = _read_task(matching_task_id)
    try:
        desired.update(_matching_projection(task))
    except HTTPException as exc:
        code, message = _error_parts(exc, "matching_result_invalid")
        desired["single_account_matching"] = _desired(
            STAGE_FAILED, backend_type="matching_task", backend_id=matching_task_id,
            error_code=code, error_message=message, detail=task_summary(task))
        return _persist(pipeline_id, expected_version, desired,
                        preparation_id=preparation_id, matching_task_id=matching_task_id)
    if task["status"] == "evaluated":
        desired["result_commit"] = _desired(
            STAGE_WAITING, backend_type="matching_task", backend_id=matching_task_id,
            detail={"matching_task_id": matching_task_id,
                    "evaluation_scope": "ordinary_only",
                    "operations_result_committed": False},
            error_code="result_commit_pending",
            error_message="匹配已完成，等待正式结果校验与原子提交")
    return _persist(pipeline_id, expected_version, desired,
                    preparation_id=preparation_id, matching_task_id=matching_task_id)


def retry_pipeline(pipeline_id: int, expected_version: int) -> dict:
    snapshot = read_pipeline(pipeline_id)
    if snapshot["version"] != expected_version:
        raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
    if snapshot["status"] not in (STAGE_FAILED, STAGE_WAITING):
        raise HTTPException(409, "当前Pipeline不属于可重试或可恢复状态")
    frontier = snapshot["active_stages"]
    if frontier == ["result_commit"]:
        raise HTTPException(409, "请通过正式结果提交执行器重试，不能绕过业务校验")
    return advance_pipeline(pipeline_id, expected_version, retry=True)


def cancel_pipeline(pipeline_id: int, expected_version: int) -> dict:
    snapshot = read_pipeline(pipeline_id)
    if snapshot["version"] != expected_version:
        raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
    if snapshot["status"] == STAGE_CANCELLED:
        return {**snapshot, "reused": True}
    if snapshot["production_batch_id"] is not None:
        raise HTTPException(409, "正式策划结果已经提交，不能取消Pipeline")

    if snapshot["matching_task_id"] is not None:
        task = _read_task(snapshot["matching_task_id"])
        if task["status"] in ("queued", "processing", "failed"):
            cancel_task(task["id"], task["version"])
    if snapshot["preparation_id"] is not None:
        preparation = read_preparation(snapshot["preparation_id"])
        if preparation["status"] not in ("cancelled", "expired"):
            cancel_preparation(snapshot["preparation_id"], preparation["version"])

    with connection() as db, db.cursor() as cursor:
        row = select_pipeline(cursor, pipeline_id, lock=True)
        if row["version"] != expected_version:
            raise HTTPException(409, "Pipeline版本已变化，请重新查询后再操作")
        stages = select_stages(cursor, pipeline_id, lock=True)
        now = now_utc_naive()
        for item in stages:
            if item["status"] == STAGE_SUCCEEDED:
                continue
            _apply_stage(cursor, item, _desired(
                STAGE_CANCELLED, backend_type=item["backend_type"], backend_id=item["backend_id"],
                detail=_json(item["detail_json"]), error_code="pipeline_cancelled",
                error_message="Pipeline已取消"), now)
        cursor.execute(
            "UPDATE godp_planning_pipeline_run SET status='cancelled',reservation_key=NULL,current_stage=NULL,"
            "last_error_code='',last_error_message='',version=version+1,update_by=%s WHERE id=%s",
            (ACTOR, pipeline_id),
        )
        saved = select_pipeline(cursor, pipeline_id)
        saved_stages = select_stages(cursor, pipeline_id)
        db.commit()
        return pipeline_summary(saved, saved_stages)
