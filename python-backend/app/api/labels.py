"""Taxonomy and labeling HTTP routes."""
from fastapi import APIRouter, Depends, Request
from .common import invoke
from .security import require_integration_token
from ..services import labels as service
from ..services.labels import TagTaxonomyItemInput, TagTaxonomyInput, TopicTagsInput

router = APIRouter()

@router.get("/api/tag-taxonomy")
def get_tag_taxonomy() -> dict:
    return invoke(service.get_tag_taxonomy)

@router.put("/api/tag-taxonomy", dependencies=[Depends(require_integration_token)])
def put_tag_taxonomy(payload: TagTaxonomyInput, request: Request = None) -> dict:
    # Only the authenticated Java service may supply the trusted operator header.
    operator = request.headers.get('x-operator-id', '运营人员') if request else '运营人员'
    return invoke(service.put_tag_taxonomy, payload=payload, operator=operator)

@router.get("/api/internal/topic-label-jobs", dependencies=[Depends(require_integration_token)])
def list_topic_label_jobs(limit: int = 100, after_id: int = 0) -> dict:
    return invoke(service.list_topic_label_jobs, limit=limit, after_id=after_id)

@router.post("/api/internal/topic-label-jobs/{topic_id}/claim", dependencies=[Depends(require_integration_token)])
def claim_topic_label_job(topic_id: str, lease_seconds: int = 1800) -> dict:
    return invoke(service.claim_topic_label_job, topic_id=topic_id, lease_seconds=lease_seconds)

@router.put("/api/internal/topic-tags/{topic_id}", dependencies=[Depends(require_integration_token)])
def put_topic_tags(topic_id: str, payload: TopicTagsInput) -> dict:
    return invoke(service.put_topic_tags, topic_id=topic_id, payload=payload)

@router.get("/api/internal/topic-tags/{topic_id}/history", dependencies=[Depends(require_integration_token)])
def topic_tag_history(topic_id: str, limit: int = 100) -> dict:
    return invoke(service.topic_tag_history, topic_id=topic_id, limit=limit)
