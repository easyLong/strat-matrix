from fastapi import APIRouter
from .common import invoke
from ..services.usage import topic_usage
router=APIRouter()
@router.get('/api/topics/{topic_id}/usage')
def usage(topic_id: str):
    return invoke(topic_usage, topic_id)
