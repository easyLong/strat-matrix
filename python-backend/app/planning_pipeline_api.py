"""Protected control plane for the versioned planning Pipeline V1."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
import pymysql

from .db import connection
from .api.common import db_error
from .api.security import require_integration_token
from .planning_pipeline import (cancel_pipeline, create_pipeline,
                                pipeline_summary, read_pipeline, select_stages)
from .planning_pipeline_runner import (advance_pipeline_to_commit,
                                       retry_pipeline_to_commit)
from .ordinary_scheduler import start_v19_pipeline
from .ordinary_planning import PlanningError
from .business_snapshot import BusinessConfigSnapshot
from .model_capacity import model_api_admission, task_api_admission
from .planning_result_commit import (ResultCommitError, build_pipeline_proposal,
                                     acknowledge_pipeline_proposal)


router = APIRouter(dependencies=[Depends(require_integration_token)])


class PipelineCreate(BaseModel):
    cycle_start: date | None = None
    account_ids: list[str] | None = Field(default=None, min_length=1, max_length=2000)
    policy_id: int = Field(ge=1)
    planning_scope: Literal['full', 'ordinary_only'] = 'full'
    production_provider: Literal['disabled', 'local_mock'] = 'disabled'


class PipelineAction(BaseModel):
    expected_version: int = Field(ge=1)


class AutoStart(BaseModel):
    cycle_start: date
    business_config_version: int = Field(ge=1)
    business_config: BusinessConfigSnapshot


class AutoProposalRequest(BaseModel):
    business_config_version: int = Field(ge=1)
    business_config: dict[str, object]


class ProposalAcknowledgement(BaseModel):
    proposal_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    business_batch_id: int = Field(ge=1, le=9007199254740991)


def guarded(handler, *args):
    try:
        return handler(*args)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/internal/auto-planning/start", dependencies=[Depends(model_api_admission), Depends(task_api_admission('pipeline'))])
def start_auto_algorithm(payload: AutoStart) -> dict:
    """Java supplies the due cycle; Python selects the approved V19 algorithm policy."""
    try:
        return start_v19_pipeline(payload.cycle_start, commit_owner='java',
            business_config_version=payload.business_config_version,
            business_config=payload.business_config.model_dump(exclude_unset=True))
    except PlanningError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/internal/planning-pipelines", dependencies=[Depends(model_api_admission), Depends(task_api_admission('pipeline'))])
def create_planning_pipeline(payload: PipelineCreate) -> dict:
    return guarded(create_pipeline, payload.cycle_start, payload.account_ids, payload.policy_id,
                   payload.planning_scope, payload.production_provider)


@router.get("/api/internal/planning-pipelines")
def list_planning_pipelines(after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SELECT * FROM godp_planning_pipeline_run WHERE del_flag='N' AND id>%s "
                           "ORDER BY id LIMIT %s", (after_id, limit))
            rows = cursor.fetchall()
            pipelines = []
            for row in rows:
                pipelines.append(pipeline_summary(row, select_stages(cursor, row["id"])))
        return {"pipelines": pipelines, "next_after_id": rows[-1]["id"] if rows else after_id}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.get("/api/internal/planning-pipelines/{pipeline_id}")
def planning_pipeline_detail(pipeline_id: int) -> dict:
    return guarded(read_pipeline, pipeline_id)


@router.post("/api/internal/planning-pipelines/{pipeline_id}/proposal")
def planning_pipeline_proposal(pipeline_id: int, payload: AutoProposalRequest) -> dict:
    """Freeze an algorithm proposal; this endpoint never writes a formal business result."""
    try:
        return build_pipeline_proposal(pipeline_id, payload.business_config,
                                       payload.business_config_version)
    except ResultCommitError as exc:
        status = 422 if exc.code == "business_config_invalid" else 409
        raise HTTPException(status_code=status, detail={"code": exc.code,
                                                        "message": exc.message}) from exc
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/internal/planning-pipelines/{pipeline_id}/acknowledgement")
def planning_proposal_acknowledgement(pipeline_id: int, payload: ProposalAcknowledgement) -> dict:
    return guarded(acknowledge_pipeline_proposal, pipeline_id, payload.proposal_hash,
                   payload.business_batch_id)


@router.post("/api/internal/planning-pipelines/{pipeline_id}/advance")
def advance_planning_pipeline(pipeline_id: int, payload: PipelineAction) -> dict:
    return guarded(advance_pipeline_to_commit, pipeline_id, payload.expected_version)


@router.post("/api/internal/planning-pipelines/{pipeline_id}/retry", dependencies=[Depends(model_api_admission), Depends(task_api_admission('pipeline',retry=True))])
def retry_planning_pipeline(pipeline_id: int, payload: PipelineAction) -> dict:
    return guarded(retry_pipeline_to_commit, pipeline_id, payload.expected_version)


@router.post("/api/internal/planning-pipelines/{pipeline_id}/cancel")
def cancel_planning_pipeline(pipeline_id: int, payload: PipelineAction) -> dict:
    return guarded(cancel_pipeline, pipeline_id, payload.expected_version)
