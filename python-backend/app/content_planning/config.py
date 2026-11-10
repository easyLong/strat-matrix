"""Explicit installation configuration. Import never reads files or changes os.environ."""
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping


def _flag(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if str(value).lower() in ('true', '1', 'yes', 'on'):
        return True
    if str(value).lower() in ('false', '0', 'no', 'off'):
        return False
    raise ValueError('CONTENT_PLANNING_ENABLED must be a boolean')


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    user: str
    password: str = field(repr=False)
    database: str = ''
    port: int = 3306

    def __post_init__(self):
        if not all(isinstance(x, str) and x.strip() for x in (self.host, self.user, self.password, self.database)):
            raise ValueError('Planning MySQL connection fields are incomplete')
        if not 1 <= int(self.port) <= 65535:
            raise ValueError('Planning MySQL port is invalid')

    def connection_options(self):
        from pymysql.cursors import DictCursor
        return dict(host=self.host, port=int(self.port), user=self.user, password=self.password,
                    database=self.database, charset='utf8mb4', cursorclass=DictCursor,
                    connect_timeout=5, read_timeout=10, write_timeout=10, autocommit=False)


@dataclass(frozen=True)
class PlanningConfig:
    enabled: bool = False
    database: DatabaseConfig | None = field(default=None, repr=False)
    settings: Mapping[str, str | None] = field(default_factory=dict, repr=False)
    standalone: bool = False
    check_schema: bool = True
    validate_deployment: bool = True
    max_workers: int = 2
    pool_size: int = 16
    pool_timeout: float = 5
    cache_seconds: float = 5
    resource_directory: Path | None = None
    fixture_path: Path | None = None
    workspace_directory: Path | None = None
    model_protocol: str = 'chat_completions'
    model_authorization_scheme: str = 'Bearer'
    model_headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    max_forward_body_bytes: int = 16 * 1024 * 1024

    def __post_init__(self):
        if not isinstance(self.enabled, bool):
            raise ValueError('Planning enabled flag must be a boolean')
        if not 1 <= self.max_workers <= 32 or not 1 <= self.pool_size <= 256:
            raise ValueError('Planning resource limits are invalid')
        if self.pool_timeout <= 0 or self.cache_seconds < 0 or self.max_forward_body_bytes < 1:
            raise ValueError('Planning timeout/cache/body limit is invalid')
        if self.model_protocol not in ('chat_completions', 'custom'):
            raise ValueError('Unsupported planning model protocol; provide a custom model adapter')
        if not self.model_authorization_scheme or any(c in self.model_authorization_scheme for c in '\r\n\x00'):
            raise ValueError('Planning model authorization scheme is invalid')
        headers = dict(self.model_headers)
        for key, value in headers.items():
            if (not isinstance(key, str) or not isinstance(value, str) or not key.strip()
                    or any(c in key + value for c in '\r\n\x00')
                    or key.lower() in ('host', 'content-length', 'transfer-encoding', 'authorization')):
                raise ValueError('Planning model gateway headers are invalid')
        values = dict(self.settings)
        if any(not isinstance(k, str) or v is not None and not isinstance(v, str) for k, v in values.items()):
            raise ValueError('Planning connection settings must be strings or disabled null values')
        object.__setattr__(self, 'settings', MappingProxyType(values))
        object.__setattr__(self, 'model_headers', MappingProxyType(headers))
        for name in ('resource_directory', 'fixture_path', 'workspace_directory'):
            value = getattr(self, name)
            if value is not None:
                path = Path(value)
                if not path.is_absolute():
                    raise ValueError('Planning resource paths must be absolute')
                object.__setattr__(self, name, path)

    @classmethod
    def from_mapping(cls, values):
        """Host settings use CONTENT_PLANNING_ENABLED and PLANNING_* exclusively."""
        from .system_config_catalog import CATALOG
        enabled = _flag(values.get('CONTENT_PLANNING_ENABLED'))
        db = None
        if enabled and any('PLANNING_MYSQL_' + k in values for k in ('HOST','USER','PASSWORD','DATABASE')):
            db = DatabaseConfig(host=values.get('PLANNING_MYSQL_HOST', ''),
                                user=values.get('PLANNING_MYSQL_USER', ''),
                                password=values.get('PLANNING_MYSQL_PASSWORD', ''),
                                database=values.get('PLANNING_MYSQL_DATABASE', ''),
                                port=int(values.get('PLANNING_MYSQL_PORT', 3306)))
        settings = {key: values['PLANNING_' + key] for key in CATALOG if 'PLANNING_' + key in values}
        # This catalog key already carries the module prefix; avoid requiring a double prefix.
        if 'PLANNING_ENV' in values and 'PLANNING_ENV' not in settings:
            settings['PLANNING_ENV'] = values['PLANNING_ENV']
        return cls(enabled=enabled, database=db,
                   settings=settings,
                   resource_directory=values.get('PLANNING_RESOURCE_DIRECTORY'),
                   fixture_path=values.get('PLANNING_FIXTURE_PATH'),
                   workspace_directory=values.get('PLANNING_WORKSPACE_DIRECTORY'),
                   max_workers=int(values.get('PLANNING_MAX_WORKERS', 2)),
                   pool_size=int(values.get('PLANNING_POOL_SIZE', 16)),
                   pool_timeout=float(values.get('PLANNING_POOL_TIMEOUT', 5)),
                   cache_seconds=float(values.get('PLANNING_CACHE_SECONDS', 5)),
                   max_forward_body_bytes=int(values.get('PLANNING_MAX_FORWARD_BODY_BYTES', 16 * 1024 * 1024)),
                   model_authorization_scheme=values.get('PLANNING_MODEL_AUTHORIZATION_SCHEME', 'Bearer'),
                   model_headers=values.get('PLANNING_MODEL_HEADERS', {}),
                   model_protocol=values.get('PLANNING_MODEL_PROTOCOL', 'chat_completions'))


@dataclass(frozen=True)
class PlanningDependencies:
    """Owned resources are closed by this module; providers themselves remain host-owned."""
    database_pool_factory: Callable | None = None
    settings_provider: Callable | None = None
    executor_factory: Callable | None = None
    source_adapter: object = None
    production_adapter: object = None
    model_adapters: Mapping[str, object] = field(default_factory=dict)
    model_adapters_owned: bool = False
