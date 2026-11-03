"""Internal host-triggered execution and process-local operational status."""
import asyncio
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .security import require_integration_token
from ..jobs.runtime import BackgroundExecutor


@asynccontextmanager
async def execution_lifespan(app):
    executor = BackgroundExecutor()
    app.state.background_executor = executor
    try:
        yield
    finally:
        await asyncio.to_thread(executor.close)
        del app.state.background_executor


class WakeupInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    jobs: list[Literal['manual', 'planning', 'weekly', 'hotspot', 'manual_compute']] = Field(
        default_factory=lambda: ['manual', 'planning', 'weekly', 'hotspot'], min_length=1, max_length=5)


router = APIRouter(prefix='/api/internal', dependencies=[Depends(require_integration_token)])


def executor_for(request):
    executor = getattr(request.app.state, 'background_executor', None)
    if executor is None:
        raise HTTPException(503, '后台执行器尚未就绪')
    return executor


@router.post('/wakeup', status_code=202)
def wakeup(payload: WakeupInput, request: Request):
    try:
        return executor_for(request).wake(payload.jobs)
    except RuntimeError:
        raise HTTPException(503, '后台执行器正在停止') from None


@router.get('/executor')
def executor_status(request: Request):
    return executor_for(request).snapshot()
