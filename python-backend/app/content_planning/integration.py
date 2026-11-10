"""Explicit FastAPI installation: allowlisted HTTP forwarding and owned lifespans."""
from contextlib import AsyncExitStack, asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import re
from starlette.requests import Request

LOG = logging.getLogger('content_planning.integration')
_HOP_HEADERS = {b'connection', b'keep-alive', b'proxy-authenticate', b'proxy-authorization',
                b'te', b'trailer', b'transfer-encoding', b'upgrade'}


def _headers(raw):
    tokens = {token.strip().lower() for key, value in raw if key.lower() == b'connection'
              for token in value.split(b',')}
    return [(key, value) for key, value in raw if key.lower() not in _HOP_HEADERS | tokens]


def delivery_route(route):
    """The embedded module delivers algorithm capabilities, not the old Python business UI."""
    return (route.path == '/api/health' or route.path.startswith('/api/internal/')
            or route.path in ('/api/tag-taxonomy/query', '/api/tag-taxonomy/save',
                              '/api/integrations/bank/op03/topic-labels/query',
                              '/api/integrations/bank/op04/topic-labels/test'))


@dataclass(frozen=True)
class DeliveryRoute:
    path: str
    methods: frozenset
    name: str


def declared_routes(child):
    # Use the public API contract rather than FastAPI's private included-router
    # representation, which differs between dependency versions. The child
    # remains responsible for all request validation and business dispatch.
    for path, item in child.openapi().get('paths', {}).items():
        for method, operation in item.items():
            if method in ('get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'trace'):
                yield DeliveryRoute(path, frozenset({method.upper()}), operation['operationId'])


class PlanningInstallation:
    def __init__(self, app, prefix):
        self.app, self.prefix, self.client = app, prefix, None
        self.runtime = app.state.planning_runtime

    async def forward(self, request: Request):
        from fastapi.responses import JSONResponse, Response
        import httpx
        if self.client is None or self.runtime.status != 'ready':
            disabled = not self.runtime.config.enabled
            return JSONResponse({'detail': '策划模块已关闭' if disabled else '策划模块尚未就绪',
                                 'code': 'planning_disabled' if disabled else 'planning_not_ready'}, status_code=503)
        raw = request.scope.get('raw_path', request.scope['path'].encode('utf-8'))
        prefix = self.prefix.encode('ascii')
        root = request.scope.get('root_path', '').encode('utf-8')
        if root and raw.startswith(root + prefix + b'/'):
            raw = raw[len(root):]
        if not raw.startswith(prefix + b'/'):
            return JSONResponse({'detail': '策划接口路径无效'}, status_code=404)
        raw = raw[len(prefix):]
        query = request.scope.get('query_string', b'')
        target = httpx.URL(scheme='http', host='content-planning.internal',
                           raw_path=raw + (b'?' + query if query else b''))
        chunks, total = [], 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > self.runtime.config.max_forward_body_bytes:
                return JSONResponse({'detail': '策划请求超过允许大小'}, status_code=413)
            chunks.append(chunk)
        # Construct directly, avoiding client-level cookies, credentials or implicit service tokens.
        message = httpx.Request(request.method, target, headers=_headers(request.scope['headers']), content=b''.join(chunks))
        upstream = await self.client.send(message, stream=True, follow_redirects=False)
        try:
            body = b''.join([chunk async for chunk in upstream.aiter_raw()])
            response = Response(body, status_code=upstream.status_code)
            response.raw_headers = _headers(upstream.headers.raw)
            return response
        finally:
            await upstream.aclose()


def _install_openapi(host, child, prefix, routes):
    original = host.openapi
    suffix = sha256(prefix.encode()).hexdigest()[:8]
    namespace = 'ContentPlanning_' + suffix + '_'
    allowed = {(route.path, method.lower()) for route in routes for method in route.methods}

    def schema():
        merged = deepcopy(original())
        current = deepcopy(child.openapi())
        # Rename every component category and all JSON references, not only request models.
        components = current.get('components', {})
        replacements = {'#/components/' + group + '/' + name: '#/components/' + group + '/' + namespace + name
                        for group, definitions in components.items() for name in definitions}
        def rewrite(value):
            if isinstance(value, list): return [rewrite(x) for x in value]
            if isinstance(value, dict):
                out = {k: rewrite(v) for k, v in value.items()}
                if '$ref' in out: out['$ref'] = replacements.get(out['$ref'], out['$ref'])
                if 'security' in out:
                    out['security'] = [{namespace + k: v for k,v in rule.items()} for rule in out['security']]
                return out
            return replacements.get(value, value) if isinstance(value, str) else value
        for group, definitions in components.items():
            target = merged.setdefault('components', {}).setdefault(group, {})
            for name, definition in definitions.items(): target[namespace + name] = rewrite(definition)
        security = merged.setdefault('components', {}).setdefault('securitySchemes', {})
        security[namespace + 'IntegrationToken'] = {'type': 'apiKey', 'in': 'header', 'name': 'X-Integration-Token'}
        for path, item in current.get('paths', {}).items():
            for method, operation in item.items():
                if (path, method) not in allowed: continue
                operation = rewrite(operation)
                operation['operationId'] = namespace + operation.get('operationId', method + '_' + path)
                operation['tags'] = ['content_planning']
                if path != '/api/health': operation['security'] = [{namespace + 'IntegrationToken': []}]
                merged.setdefault('paths', {}).setdefault(prefix + path, {})[method] = operation
        return merged
    host.openapi_schema = None
    host.openapi = schema


def install_content_planning(host, config=None, *, config_provider=None, dependencies=None,
                             prefix='/planning', allowed_routes=None):
    """Install before host startup. Returns a handle; never opens a second TCP port."""
    from .config import PlanningConfig
    from .main import create_app
    if not re.fullmatch(r'/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*', prefix):
        raise ValueError('Planning prefix must be an explicit, non-root HTTP path')
    installed = getattr(host.state, 'content_planning_modules', {})
    if prefix in installed:
        raise ValueError('Content planning is already installed at this prefix')
    if config is not None and config_provider is not None:
        raise ValueError('Provide either planning config or a config provider')
    config = config_provider() if config_provider is not None else config
    config = config if isinstance(config, PlanningConfig) else PlanningConfig.from_mapping(config or {})
    if config.standalone:
        raise ValueError('Host installation requires embedded configuration')
    child = create_app(config, dependencies=dependencies)
    routes = [r for r in declared_routes(child)
              if (delivery_route(r) if allowed_routes is None else r.path in allowed_routes)]
    if allowed_routes is not None and set(allowed_routes) - {r.path for r in routes}:
        raise ValueError('Unknown planning route in the delivery allowlist')
    for route in routes:
        for existing in host.routes:
            if getattr(existing, 'path', None) == prefix + route.path and route.methods & getattr(existing, 'methods', set()):
                raise ValueError('Planning route conflicts with an existing host route')
    handle = PlanningInstallation(child, prefix)
    for route in routes:
        host.add_api_route(prefix + route.path, handle.forward, methods=sorted(route.methods),
                           include_in_schema=False, name='content_planning_' + route.name)
    installed[prefix] = handle
    host.state.content_planning_modules = installed
    _install_openapi(host, child, prefix, routes)
    original_lifespan = host.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        import httpx
        async with original_lifespan(app) as state:
            stack = AsyncExitStack()
            try:
                if config.enabled:
                    try:
                        await stack.enter_async_context(child.router.lifespan_context(child))
                        handle.client = await stack.enter_async_context(httpx.AsyncClient(
                            transport=httpx.ASGITransport(app=child, raise_app_exceptions=False),
                            base_url='http://content-planning.internal', trust_env=False))
                    except Exception as error:
                        await stack.aclose()
                        handle.client = None
                        LOG.error('Planning module is unavailable: %s', type(error).__name__)
                yield state  # Preserve the host's lifespan state exactly.
            finally:
                handle.client = None
                await stack.aclose()
    host.router.lifespan_context = lifespan
    return handle
