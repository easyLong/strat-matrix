"""Protected control plane for the versioned planning Pipeline V1."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
import pymysql

from .db import connection
from .integration import db_error, require_integration_token
from .planning_pipeline import (advance_pipeline, cancel_pipeline, create_pipeline,
                                pipeline_summary, read_pipeline, retry_pipeline,
                                select_stages)


router = APIRouter(dependencies=[Depends(require_integration_token)])


class PipelineCreate(BaseModel):
    cycle_start: date | None = None
    account_ids: list[str] | None = Field(default=None, min_length=1, max_length=2000)
    policy_id: int = Field(ge=1)


class PipelineAction(BaseModel):
    expected_version: int = Field(ge=1)


def guarded(handler, *args):
    try:
        return handler(*args)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post("/api/internal/planning-pipelines")
def create_planning_pipeline(payload: PipelineCreate) -> dict:
    return guarded(create_pipeline, payload.cycle_start, payload.account_ids, payload.policy_id)


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


@router.post("/api/internal/planning-pipelines/{pipeline_id}/advance")
def advance_planning_pipeline(pipeline_id: int, payload: PipelineAction) -> dict:
    return guarded(advance_pipeline, pipeline_id, payload.expected_version)


@router.post("/api/internal/planning-pipelines/{pipeline_id}/retry")
def retry_planning_pipeline(pipeline_id: int, payload: PipelineAction) -> dict:
    return guarded(retry_pipeline, pipeline_id, payload.expected_version)


@router.post("/api/internal/planning-pipelines/{pipeline_id}/cancel")
def cancel_planning_pipeline(pipeline_id: int, payload: PipelineAction) -> dict:
    return guarded(cancel_pipeline, pipeline_id, payload.expected_version)
