"""Compute algorithm-owned page fields from Java-supplied facts; never fetch a second source."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from .security import require_integration_token
from ..bank_bridge.contracts import Account, Topic
from ..services.catalog_projection import project_catalog

router = APIRouter(prefix='/api/internal/catalog-projection', dependencies=[Depends(require_integration_token)])


class ProjectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    accounts: list[Account] = Field(default_factory=list, max_length=1000)
    topics: list[Topic] = Field(default_factory=list, max_length=1000)
    available_only: bool = True


@router.post('')
def project(query: ProjectionInput):
    return project_catalog(query.accounts, query.topics, available_only=query.available_only)
