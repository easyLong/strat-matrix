"""Per-application owned resources, with no import/startup DDL and no timers."""
import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from threading import RLock

from .config import PlanningConfig, PlanningDependencies
from .context import use_runtime

LOG = logging.getLogger('content_planning.runtime')


@dataclass
class ConfigurationCache:
    values: dict = field(default_factory=dict)
    expires_at: float = 0
    lock: object = field(default_factory=RLock)


class PlanningRuntime:
    def __init__(self, config: PlanningConfig, dependencies=None):
        self.config = config
        self.dependencies = dependencies or PlanningDependencies()
        self.database_pool = None
        self.background_executor = None
        self.configuration_cache = ConfigurationCache()
        self.capacity_controls = None
        self.source_adapter = self.dependencies.source_adapter
        self.production_adapter = self.dependencies.production_adapter
        self.model_adapters = dict(self.dependencies.model_adapters)
        self.status = 'not_started' if config.enabled else 'disabled'
        self.error_type = None
        self._lock = RLock()

    def bind(self):
        return use_runtime(self)

    def pool(self):
        with self._lock:
            if not self.config.enabled or self.status in ('stopping', 'closed', 'failed'):
                raise RuntimeError('Planning database resources are not accepting work')
            if self.database_pool is None:
                if self.dependencies.database_pool_factory is not None:
                    self.database_pool = self.dependencies.database_pool_factory(self.config)
                else:
                    if self.config.database is None:
                        raise RuntimeError('Planning database configuration is missing')
                    from .connection_pool import MySQLPool
                    self.database_pool = MySQLPool(self.config.database.connection_options(),
                                                  size=self.config.pool_size, timeout=self.config.pool_timeout)
            return self.database_pool

    def budget(self):
        with self._lock:
            if self.capacity_controls is None:
                from .model_capacity import ConcurrentBudget
                self.capacity_controls = ConcurrentBudget()
            return self.capacity_controls

    def _start(self):
        if not self.config.enabled:
            self.status = 'disabled'
            return
        self.error_type = None
        with self.bind():
            if self.config.validate_deployment:
                from .deployment_environment import require_ready
                require_ready()
            if self.config.check_schema:
                from .db import check_database
                if not check_database():
                    raise RuntimeError('Planning algorithm schema is not ready')
            if self.config.model_protocol == 'custom' and not all(k in self.model_adapters for k in ('text', 'embedding')):
                raise RuntimeError('Custom model protocol requires explicit text and embedding adapters')
            if self.dependencies.executor_factory is not None:
                self.background_executor = self.dependencies.executor_factory(self)
            else:
                from .api.background_execution import BackgroundExecutor
                self.background_executor = BackgroundExecutor(max_workers=self.config.max_workers)
            self.status = 'ready'

    async def start(self):
        with self._lock:
            if self.config.enabled and self.status != 'not_started':
                raise RuntimeError('Planning runtime cannot be started more than once; create a new app')
            if self.config.enabled:
                self.status = 'starting'
        try:
            await asyncio.to_thread(self._start)
        except Exception as error:
            self.error_type = type(error).__name__
            await self.close(failed=True)
            LOG.error('Planning resources did not start: %s', self.error_type)
            raise RuntimeError('Content planning resources could not be started') from None

    async def close(self, *, failed=False):
        if self.status in ('closed', 'failed'):
            return
        with self.bind():
            # Stop accepting hints before waiting; in-flight jobs retain DB access until finished.
            self.status = 'draining'
            executor, self.background_executor = self.background_executor, None
            try:
                if executor is not None:
                    try:
                        await asyncio.to_thread(executor.close)
                    except Exception as error:
                        # Cleanup must not prevent the host from completing its own shutdown.
                        LOG.error('Planning executor shutdown failed: %s', type(error).__name__)
            finally:
                self.status = 'stopping'
                pool, self.database_pool = self.database_pool, None
                resources = ([pool] if pool is not None else [])
                if self.dependencies.model_adapters_owned:
                    resources += list({id(v): v for v in self.model_adapters.values()}.values())
                for resource in resources:
                    close = getattr(resource, 'close', None)
                    if callable(close):
                        try:
                            await asyncio.to_thread(close)
                        except Exception as error:
                            LOG.error('Planning resource shutdown failed: %s', type(error).__name__)
                self.configuration_cache.values.clear()
                self.configuration_cache.expires_at = 0
                self.capacity_controls = None
                self.status = 'failed' if failed else 'closed'

    @asynccontextmanager
    async def lifespan(self, app):
        await self.start()
        if self.background_executor is not None:
            app.state.background_executor = self.background_executor
        try:
            # Do not bind a ContextVar across yield: that would leak the child
            # runtime into host code executing after __aenter__. Requests and
            # background entry points bind their own explicit context instead.
            yield {'content_planning_runtime': self}
        finally:
            await self.close()
            if hasattr(app.state, 'background_executor'):
                del app.state.background_executor


class RuntimeContextMiddleware:
    def __init__(self, app, runtime):
        self.app, self.runtime = app, runtime

    async def __call__(self, scope, receive, send):
        with self.runtime.bind():
            if scope['type'] == 'http':
                status = self.runtime.status
                if (not self.runtime.config.enabled or status in ('failed', 'draining', 'stopping', 'closed')
                        or status != 'ready' and not self.runtime.config.standalone):
                    from starlette.responses import JSONResponse
                    code = 'planning_disabled' if not self.runtime.config.enabled else 'planning_not_ready'
                    await JSONResponse({'detail': '策划模块已关闭' if code == 'planning_disabled' else '策划模块尚未就绪',
                                        'code': code}, status_code=503)(scope, receive, send)
                    return
            await self.app(scope, receive, send)
