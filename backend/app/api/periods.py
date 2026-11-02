"""periods HTTP adapters."""
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
from ..services import periods as service

router=APIRouter()

@router.get("/api/planning-cycles/{cycle_id}/items", response_model=list[AccountPlanRecord])
def list_cycle_items(cycle_id: date, limit: int = 1000) -> list[dict]:
    return invoke(service.list_cycle_items, cycle_id=cycle_id, limit=limit)

@router.get("/api/planning-cycles", response_model=list[PlanningCycleSummary])
def list_planning_cycles() -> list[dict]:
    return invoke(service.list_planning_cycles)

@router.get("/api/auto-planning/cycles", response_model=list[AutoCycleSummary])
def list_auto_cycles() -> list[dict]:
    return invoke(service.list_auto_cycles)

@router.get("/api/auto-planning/cycles/{cycle_id}/failures", response_model=list[AutoFailure])
def list_auto_failures(cycle_id: date) -> list[dict]:
    return invoke(service.list_auto_failures, cycle_id=cycle_id)

@router.get("/api/planning-cycles/{cycle_id}/failures", response_model=list[AutoFailure])
def list_cycle_failures(cycle_id: date) -> list[dict]:
    return invoke(service.list_cycle_failures, cycle_id=cycle_id)
