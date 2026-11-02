"""Thin HTTP adapter; business operations live in services."""
from datetime import date
from fastapi import APIRouter, Depends, Query
from .common import invoke
from .security import require_integration_token
from ..services import account_vectors as service
from ..services.account_vectors import AccountVectorResult

router = APIRouter(dependencies=[Depends(require_integration_token)])

@router.get("/api/internal/account-profiles/{batch_id}/{account_id}")
def account_profile_status(batch_id: int, account_id: str) -> dict:
    return invoke(service.account_profile_status, batch_id=batch_id, account_id=account_id)

@router.get("/api/internal/account-vector-jobs")
def account_vector_jobs(limit: int = Query(100, ge=1, le=200),
                        after_id: int = Query(0, ge=0),
                        batch_id: int | None = Query(None, ge=1)) -> dict:
    return invoke(service.account_vector_jobs, limit=limit, after_id=after_id, batch_id=batch_id)

@router.put("/api/internal/account-vectors/{batch_id}/{account_id}")
def save_account_vector(batch_id: int, account_id: str, payload: AccountVectorResult) -> dict:
    return invoke(service.save_account_vector, batch_id=batch_id, account_id=account_id, payload=payload)

@router.get("/api/internal/ai-account-candidates")
def ai_account_candidates(batch_id: int = Query(..., ge=1),
                          limit: int = Query(100, ge=1, le=200),
                          after_id: int = Query(0, ge=0)) -> dict:
    return invoke(service.ai_account_candidates, batch_id=batch_id, limit=limit, after_id=after_id)

guarded = invoke
