"""ASGI composition, HTTP policy and the three workspace modules."""

import secrets
import pymysql

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import check_database
from .system_config import SystemConfigError, get_setting
from .api.topic_vector_api import router as topic_vector_router
from .api.account_vector_api import router as account_vector_router
from .matching_readiness_api import router as matching_readiness_router
from .api.ai_preparation_api import router as ai_preparation_router
from .matching_execution_api import router as matching_execution_router
from .topic_label_model_api import router as topic_label_model_router
from .embedding_model_api import router as embedding_model_router
from .manual_marketing_api import router as manual_marketing_router
from .bank_bridge.api import router as bank_bridge_router
from .api.labels import router as labels_router
from .bank_bridge.ports import DataContractError, IntegrationUnavailable
from .services.errors import ApplicationError


class ConfiguredCORSMiddleware(CORSMiddleware):
    def is_allowed_origin(self, origin: str) -> bool:
        try:
            port = get_setting("FRONTEND_PORT", "930")
        except SystemConfigError:
            return False
        return origin in (f"http://localhost:{port}", f"http://127.0.0.1:{port}")


app = FastAPI(title="多账号智能策划 API", version="0.2.0")
app.add_middleware(
    ConfiguredCORSMiddleware,
    allow_origins=[],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)
app.include_router(topic_vector_router)
app.include_router(account_vector_router)
app.include_router(matching_readiness_router)
app.include_router(ai_preparation_router)
app.include_router(matching_execution_router)
app.include_router(topic_label_model_router)
app.include_router(embedding_model_router)
# Content generation is triggered by the bank's scanner, not an HTTP submission queue.
app.include_router(manual_marketing_router)
app.include_router(bank_bridge_router)
app.include_router(labels_router)


@app.middleware("http")
async def integration_auth_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS":
        return await call_next(request)
    if path.startswith('/api/internal/content-scanner'):
        return JSONResponse(status_code=410, content={'detail': '内容扫描与生产由行内内容侧负责；策划侧只查询生产状态'})
    try:
        from .bank_bridge.factory import source_mode
        java_mode = source_mode() == 'java_http'
        if java_mode and path.startswith('/api/') and path != '/api/health':
            expected = get_setting('INTEGRATION_TOKEN', '')
            supplied = request.headers.get('x-integration-token', '')
            if not expected:
                return JSONResponse(status_code=503, content={'detail': 'Java接入鉴权尚未配置'})
            if not secrets.compare_digest(expected.encode('utf-8'), supplied.encode('utf-8')):
                return JSONResponse(status_code=401, content={'detail': '请通过行内Java服务访问策划接口'})
            if path.startswith('/api/integrations/bank/if'):
                return JSONResponse(status_code=410, content={'detail': '基础资料与生产状态查询由Java提供'})
    except SystemConfigError:
        return JSONResponse(status_code=503, content={'detail': '系统配置暂不可用'})
    if (path.endswith('/sync') or 'sync-status' in path or 'source-sync-status' in path
            or path.endswith('/outbox') or '/content-production' in path
            or path in ('/api/integrations/content-status', '/api/integrations/publication-status')):
        return JSONResponse(status_code=410, content={'detail': '旧同步及主动投递入口已停用，请通过Java查询资料和生产状态'})
    # Integration and worker APIs use their separate machine-to-machine token.
    if path.startswith("/api/integrations/") or path.startswith("/api/internal/"):
        try:
            expected = get_setting("INTEGRATION_TOKEN", "")
        except SystemConfigError:
            return JSONResponse(status_code=503, content={"detail": "系统配置暂不可用"})
        supplied = request.headers.get("x-integration-token", "")
        if not expected:
            return JSONResponse(status_code=503, content={"detail": "系统接口令牌尚未配置"})
        if not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
            return JSONResponse(status_code=401, content={"detail": "系统接口认证失败"})
        return await call_next(request)

    from .core.actor import use_actor
    actor = None
    try:
        gateway_token = get_setting('INTEGRATION_TOKEN', '')
        supplied = request.headers.get('x-integration-token', '')
        if gateway_token and secrets.compare_digest(gateway_token.encode('utf-8'), supplied.encode('utf-8')):
            candidate = request.headers.get('x-operator-id', '').strip()
            if candidate and len(candidate) <= 50 and not any(c in candidate for c in '\r\n\x00'):
                actor = candidate
    except SystemConfigError:
        return JSONResponse(status_code=503, content={'detail': '系统配置暂不可用'})
    with use_actor(actor):
        return await call_next(request)


@app.exception_handler(SystemConfigError)
async def system_config_error(request: Request, exc: SystemConfigError):
    return JSONResponse(status_code=503, content={"detail": "系统配置暂不可用"})


@app.exception_handler(ApplicationError)
async def application_error(request: Request, exc: ApplicationError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(pymysql.MySQLError)
async def mysql_unavailable(request: Request, exc: pymysql.MySQLError):
    return JSONResponse(status_code=503, content={"detail": "数据库暂不可用，请稍后重试"})


@app.exception_handler(IntegrationUnavailable)
async def bank_dependency_unavailable(request: Request, exc: IntegrationUnavailable):
    return JSONResponse(status_code=503, content={"detail": "行内对接方法尚未配置，请完成驻场适配"})


@app.exception_handler(DataContractError)
async def bank_contract_error(request: Request, exc: DataContractError):
    return JSONResponse(status_code=502, content={"detail": "行内返回数据与约定实体不一致，请核对字段映射及分页"})


from .api.configuration import router as configuration_router
app.include_router(configuration_router)

from .api.catalog import router as catalog_router
app.include_router(catalog_router)

from .api.results import router as results_router
app.include_router(results_router)

from .api.manual_planning import router as manual_planning_router
app.include_router(manual_planning_router)

from .api.periods import router as periods_router
app.include_router(periods_router)

@app.get("/api/health")
def health() -> dict:
    return {"service": "ok", "database": "ok" if check_database() else "unavailable"}

from .api.usage import router as usage_router
app.include_router(usage_router)
from .api.list_queries import router as list_queries_router
app.include_router(list_queries_router)
