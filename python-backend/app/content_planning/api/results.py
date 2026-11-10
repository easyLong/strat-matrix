"""results HTTP adapters."""
from datetime import date
from fastapi import APIRouter, BackgroundTasks
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
from ..services import results as service

router=APIRouter()

@router.get("/api/batches", response_model=list[BatchSummary])
def list_batches(plan_type: str | None = None, limit: int = 200) -> list[dict]:
    return invoke(service.list_batches, plan_type=plan_type, limit=limit)

@router.get("/api/batches/{batch_id}", response_model=BatchDetail)
def get_batch(batch_id: int) -> dict:
    return invoke(service.get_batch, batch_id=batch_id)

@router.get("/api/items", response_model=list[AccountPlanRecord])
def search_items(account: str, limit: int = 1000) -> list[dict]:
    return invoke(service.search_items, account=account, limit=limit)

@router.get("/api/planning-accounts", response_model=list[PlanningAccountSummary])
def list_planning_accounts(limit: int = 5000) -> list[dict]:
    return invoke(service.list_planning_accounts, limit=limit)

@router.post("/api/items/{item_id}/replace-topic", response_model=ReplaceTopicResponse)
def replace_topic(item_id: int, payload: ReplaceTopicInput) -> dict:
    return invoke(service.replace_topic, item_id=item_id, payload=payload)

@router.get("/api/items/{item_id}/adjustments", response_model=list[AdjustmentRecord])
def list_adjustments(item_id: int, limit: int = 50) -> list[dict]:
    return invoke(service.list_adjustments, item_id=item_id, limit=limit)
