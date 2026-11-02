"""catalog HTTP adapters."""
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
from ..services import catalog as service

router=APIRouter()

@router.get("/api/accounts", response_model=list[AccountOption])
def list_accounts(limit: int = 200, include_disabled: bool = False) -> list[dict]:
    return invoke(service.list_accounts, limit=limit, include_disabled=include_disabled)

@router.get("/api/topics", response_model=list[TopicOption])
def list_topics(limit: int = 200) -> list[dict]:
    return invoke(service.list_topics, limit=limit)

@router.get("/api/topics/{topic_id}/detail", response_model=TopicOption)
def topic_detail(topic_id: str, topic_type: str | None = None) -> dict:
    return invoke(service.topic_detail, topic_id=topic_id, topic_type=topic_type)

@router.get("/api/items/{item_id}/replacement-candidates", response_model=list[TopicOption])
def list_replacement_candidates(item_id: int) -> list[dict]:
    return invoke(service.list_replacement_candidates, item_id=item_id)
