"""Optional authenticated wrappers for embedded content-side scanner methods."""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import pymysql

from .api.security import require_integration_token
from .bank_bridge.ports import DataContractError, IntegrationUnavailable
from .shared_production import claim_tasks, finish_task

router = APIRouter(prefix='/api/internal/content-scanner', tags=['同库内容扫描'],
                   dependencies=[Depends(require_integration_token)])


class ClaimInput(BaseModel):
    batch_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=20, ge=1, le=100)
    lease_seconds: int = Field(default=600, ge=30, le=7200)


class ResultInput(BaseModel):
    production_task_id: str = Field(min_length=1, max_length=64)
    status: Literal['已完成', '生产失败']
    content_id: str | None = Field(default=None, min_length=1, max_length=64)
    error: str = Field(default='', max_length=500)


def invoke(handler, *args):
    try:
        return handler(*args)
    except (DataContractError, IntegrationUnavailable):
        raise HTTPException(503, '内容生产关联数据暂不可用，请检查驻场查询方法') from None
    except pymysql.MySQLError:
        raise HTTPException(503, '内容生产状态暂不可用，请检查数据库和扩展字段') from None


@router.post('/claim')
def claim(payload: ClaimInput):
    return invoke(claim_tasks, payload.batch_id, payload.limit, payload.lease_seconds)


@router.post('/result')
def finish(payload: ResultInput):
    return invoke(finish_task, payload.production_task_id, payload.status, payload.content_id, payload.error)
