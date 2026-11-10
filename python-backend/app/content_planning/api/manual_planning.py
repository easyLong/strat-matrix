"""manual planning HTTP adapters."""
from datetime import date
from fastapi import APIRouter, Request
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
def submit_manual_preview(preview_id: str, request: Request = None) -> dict:
    result = invoke(service.submit_manual_preview, preview_id=preview_id)
    executor = getattr(request.app.state, 'background_executor', None) if request else None
    if executor is not None:
        try:
            executor.wake(['manual'])
        except RuntimeError:
            pass  # Already persisted; next host pulse recovers the task after shutdown.
    return result

@router.get("/api/manual-plans/tasks", response_model=list[ManualTaskSummary])
def list_manual_tasks(limit: int = 20, offset: int = 0) -> list[dict]:
    return invoke(service.list_manual_tasks, limit=limit, offset=offset)
