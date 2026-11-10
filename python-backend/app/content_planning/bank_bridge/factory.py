"""One assembly point; never selects a provider from an HTTP request or env file."""

from contextlib import contextmanager
from contextvars import ContextVar
from .ports import IntegrationUnavailable

# Optional explicit binding for tests/acceptance. Runtime mode lives in MySQL.
SOURCE_MODE = None
# Explicit process-local acceptance binding; never selected by a request or persisted setting.
SOURCE_PROVIDER = None
_override = ContextVar('bank_source_override', default=None)
_production_override = ContextVar('bank_production_override', default=None)


def external_source_enabled():
    return True  # All live reads use a provider; retired SQL paths stay unreachable.


def source_mode():
    from ..context import current_runtime
    runtime = current_runtime()
    if SOURCE_MODE is not None and (runtime is None or runtime.config.standalone):
        return SOURCE_MODE
    from ..deployment_environment import current, EnvironmentConfigurationError
    from ..system_config import SystemConfigError
    try:
        return current()['BANK_SOURCE_MODE']
    except EnvironmentConfigurationError as error:
        raise SystemConfigError(str(error)) from None


def get_source(cursor):
    if _override.get() is not None:
        return _override.get()
    from ..context import current_runtime
    runtime = current_runtime()
    if runtime is not None and runtime.source_adapter is not None:
        return runtime.source_adapter
    if SOURCE_PROVIDER is not None and (runtime is None or runtime.config.standalone):
        return SOURCE_PROVIDER(cursor)
    mode = source_mode()
    if mode in ('local_sql', 'bank_sql'):
        raise IntegrationUnavailable('生产资料只能通过Java接口读取，不允许Python查询行内业务库')
    if mode == 'java_http':
        from .java_http import JavaHTTPClient, JavaHTTPSource
        return JavaHTTPSource(JavaHTTPClient.from_settings())
    if mode == 'local_fixture':
        from .local_fixture import load_fixture
        return load_fixture()
    if mode == 'fixture':
        from .memory import fixture_source
        return fixture_source()
    raise IntegrationUnavailable('未知的业务数据访问实现')


def get_production(cursor):
    if _production_override.get() is not None:
        return _production_override.get()
    from ..context import current_runtime
    runtime = current_runtime()
    if runtime is not None and runtime.production_adapter is not None:
        return runtime.production_adapter
    if source_mode() == 'java_http':
        from .java_http import JavaHTTPClient, JavaProductionStatus
        return JavaProductionStatus(JavaHTTPClient.from_settings())
    raise IntegrationUnavailable('Java生产状态查询未装配；测试状态必须显式注入')


@contextmanager
def use_adapters(source, production=None):
    """Scoped injection for offline tests and embedded host composition."""
    token = _override.set(source)
    production_token = _production_override.set(production)
    try:
        yield
    finally:
        _production_override.reset(production_token)
        _override.reset(token)
