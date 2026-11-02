"""configuration HTTP adapters."""
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
from ..services import configuration as service

router=APIRouter()

@router.get("/api/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return invoke(service.get_config)

@router.put("/api/config", response_model=ConfigResponse)
def put_config(config: StrategyConfig,
               expected_version: int | None = None) -> ConfigResponse:
    return invoke(service.put_config, config=config, expected_version=expected_version)

@router.get("/api/config/versions", response_model=list[ConfigVersionSummary])
def list_config_versions(limit: int = 30) -> list[dict]:
    return invoke(service.list_config_versions, limit=limit)

@router.post("/api/config/versions/{version}/restore", response_model=ConfigResponse)
def restore_config(version: int,
                   expected_version: int | None = None) -> ConfigResponse:
    return invoke(service.restore_config, version=version, expected_version=expected_version)

@router.get("/api/config/modules/{module}/versions", response_model=list[ConfigVersionSummary])
def list_module_versions(module: str, limit: int = 30) -> list[dict]:
    return invoke(service.list_module_versions, module=module, limit=limit)

@router.put("/api/config/modules/{module}", response_model=ConfigResponse)
def put_config_module(module: str, config: StrategyConfig,
                      expected_version: int | None = None) -> ConfigResponse:
    return invoke(service.put_config_module, module=module, config=config, expected_version=expected_version)

@router.post("/api/config/modules/{module}/versions/{version}/restore",
          response_model=ConfigResponse)
def restore_config_module(module: str, version: int,
                          expected_version: int | None = None) -> ConfigResponse:
    return invoke(service.restore_config_module, module=module, version=version, expected_version=expected_version)
