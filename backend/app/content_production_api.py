from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
import pymysql

from .content_production import batch_flow, enqueue_batch, receive_result
from .integration import db_error, require_integration_token

router = APIRouter()


def guarded(handler, *args):
    try:
        return handler(*args)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise db_error(exc) from exc


@router.post('/api/batches/{batch_id}/content-production', status_code=202)
def submit_batch_content(batch_id: int):
    return guarded(enqueue_batch, batch_id)


@router.get('/api/batches/{batch_id}/content-production')
def get_batch_content(batch_id: int):
    return guarded(batch_flow, batch_id)


class ProductionResult(BaseModel):
    production_task_id: str = Field(min_length=1, max_length=64)
    status: Literal['completed', 'generated', 'failed', '已完成', '生产失败']


@router.post('/api/integrations/content-production-results', dependencies=[Depends(require_integration_token)])
def content_production_result(payload: ProductionResult):
    return guarded(receive_result, payload.production_task_id, payload.status)
