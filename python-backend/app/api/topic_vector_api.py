"""Thin HTTP adapter; business operations live in services."""
from datetime import date
from fastapi import APIRouter, Depends, Query
from .common import invoke
from .security import require_integration_token
from ..services import topic_vectors as service
from ..services.topic_vectors import TopicVectorResult

router = APIRouter(dependencies=[Depends(require_integration_token)])

@router.get("/api/internal/topic-profiles/{topic_id}")
def topic_profile_status(topic_id: str) -> dict:
    return invoke(service.topic_profile_status, topic_id=topic_id)

@router.get("/api/internal/topic-vector-jobs")
def topic_vector_jobs(limit: int = 100, after_id: int = 0) -> dict:
    return invoke(service.topic_vector_jobs, limit=limit, after_id=after_id)

@router.put("/api/internal/topic-vectors/{topic_id}")
def save_topic_vector(topic_id: str, payload: TopicVectorResult) -> dict:
    return invoke(service.save_topic_vector, topic_id=topic_id, payload=payload)

@router.get("/api/internal/ai-topic-candidates")
def ai_topic_candidates(limit: int = 100, after_id: int = 0) -> dict:
    return invoke(service.ai_topic_candidates, limit=limit, after_id=after_id)

guarded = invoke
