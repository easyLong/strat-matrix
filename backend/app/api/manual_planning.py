"""manual planning HTTP adapters."""
from datetime import date
from fastapi import APIRouter
from ..models import (
    AccountOption,
    AccountPlanRecord,
    AutoCycleSummary,
    AutoFailure,
    BatchDetail,
    BatchSummary,
    ConfigResponse,
    ConfigVersionSummary,
    ManualPlanCreate,
    ManualItem,
    ManualAccountAvailability,
    ManualPreviewInput,
    ManualPreviewResponse,
    ManualTaskSummary,
    PlanningAccountSummary,
    PlanningCycleSummary,
    ReplaceTopicInput,
    ReplaceTopicResponse,
    AdjustmentRecord,
    StrategyConfig,
    TopicOption,
)
from .common import invoke
from ..services import manual_planning as service

router=APIRouter()

@router.post("/api/batches/manual", response_model=BatchDetail, status_code=201)
def create_manual_batch(payload: ManualPlanCreate) -> dict:
    return invoke(service.create_manual_batch, payload=payload)

@router.get("/api/manual-plans/account-availability", response_model=ManualAccountAvailability)
def manual_account_availability(publish_date: date) -> dict:
    return invoke(service.manual_account_availability, publish_date=publish_date)

@router.post("/api/manual-plans/previews", response_model=ManualPreviewResponse, status_code=201)
def preview_manual_plan(payload: ManualPreviewInput) -> dict:
    return invoke(service.preview_manual_plan, payload=payload)

@router.post("/api/manual-plans/previews/{preview_id}/submit", response_model=ManualTaskSummary, status_code=202)
def submit_manual_preview(preview_id: str) -> dict:
    return invoke(service.submit_manual_preview, preview_id=preview_id)

@router.get("/api/manual-plans/tasks", response_model=list[ManualTaskSummary])
def list_manual_tasks(limit: int = 20, offset: int = 0) -> list[dict]:
    return invoke(service.list_manual_tasks, limit=limit, offset=offset)
