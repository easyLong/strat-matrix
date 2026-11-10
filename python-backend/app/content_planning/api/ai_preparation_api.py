"""Thin HTTP adapter; business operations live in services."""
from datetime import date
from fastapi import APIRouter, Depends, Query
from .common import invoke
from .security import require_integration_token
from ..services import preparations as service
from ..services.account_vectors import AccountVectorResult
from ..services.preparations import PreparationCreate, PreparationAction
from ..model_capacity import model_api_admission, task_api_admission

router = APIRouter(dependencies=[Depends(require_integration_token)])

@router.post("/api/internal/ai-preparations", dependencies=[Depends(model_api_admission), Depends(task_api_admission('preparation'))])
def create_ai_preparation(payload: PreparationCreate) -> dict:
    return invoke(service.create_ai_preparation, payload=payload)

@router.get("/api/internal/ai-preparations")
def list_ai_preparations(after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)) -> dict:
    return invoke(service.list_ai_preparations, after_id=after_id, limit=limit)

@router.get("/api/internal/ai-preparations/{preparation_id}")
def ai_preparation_status(preparation_id: int) -> dict:
    return invoke(service.ai_preparation_status, preparation_id=preparation_id)

@router.post("/api/internal/ai-preparations/{preparation_id}/advance")
def advance_ai_preparation(preparation_id: int, payload: PreparationAction) -> dict:
    return invoke(service.advance_ai_preparation, preparation_id=preparation_id, payload=payload)

@router.post("/api/internal/ai-preparations/{preparation_id}/cancel")
def cancel_ai_preparation(preparation_id: int, payload: PreparationAction) -> dict:
    return invoke(service.cancel_ai_preparation, preparation_id=preparation_id, payload=payload)

@router.get("/api/internal/ai-preparations/{preparation_id}/inputs")
def ai_preparation_inputs(preparation_id: int, after_id: int = Query(0, ge=0),
                          limit: int = Query(100, ge=1, le=200)) -> dict:
    return invoke(service.ai_preparation_inputs, preparation_id=preparation_id, after_id=after_id, limit=limit)

@router.get("/api/internal/preparation-account-vector-jobs")
def preparation_account_jobs(after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
                             preparation_id: int | None = Query(None, ge=1)) -> dict:
    return invoke(service.preparation_account_jobs, after_id=after_id, limit=limit, preparation_id=preparation_id)

@router.put("/api/internal/preparation-account-vectors/{preparation_id}/{account_id}")
def save_preparation_account_vector(preparation_id: int, account_id: str, payload: AccountVectorResult) -> dict:
    return invoke(service.save_preparation_account_vector, preparation_id=preparation_id, account_id=account_id, payload=payload)

guarded = invoke
