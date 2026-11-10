"""MySQL connection and schema helpers for the first release."""

from contextlib import contextmanager
import atexit
from threading import RLock

import pymysql
from pymysql.cursors import DictCursor

_pool=None
_pool_settings=None
_pool_lock=RLock()


def settings() -> dict:
    from .context import current_runtime
    runtime = current_runtime()
    if runtime is not None:
        config = runtime.config
    else:
        from ..standalone_config import load_config
        config = load_config()
    if config.database is None:
        raise RuntimeError('缺少策划数据库连接配置')
    return config.database.connection_options()


@contextmanager
def connection():
    from .context import current_runtime
    runtime = current_runtime()
    if runtime is not None:
        with runtime.pool().connection() as db:
            yield db
        return
    global _pool,_pool_settings
    values=settings()
    with _pool_lock:
        if _pool is None or values!=_pool_settings:
            from .connection_pool import MySQLPool
            if _pool is not None:_pool.close()
            _pool=MySQLPool(values)
            _pool_settings=values
        pool=_pool
    with pool.connection() as db:yield db


def close_pool():
    from .context import current_runtime
    runtime = current_runtime()
    if runtime is not None:
        pool, runtime.database_pool = runtime.database_pool, None
        if pool is not None:
            pool.close()
        return
    global _pool,_pool_settings
    with _pool_lock:
        if _pool is not None:_pool.close()
        _pool,_pool_settings=None,None


atexit.register(close_pool)


def check_database() -> bool:
    from .algorithm_schema import REQUIRED_TABLES
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = {next(iter(row.values())) for row in cursor.fetchall()}
            return REQUIRED_TABLES.issubset(tables)
    except (pymysql.MySQLError, RuntimeError, ValueError):
        return False

