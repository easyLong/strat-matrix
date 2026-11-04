"""MySQL connection and schema helpers for the first release."""

from contextlib import contextmanager
from pathlib import Path
import os
import atexit
from threading import RLock

from dotenv import dotenv_values
import pymysql
from pymysql.cursors import DictCursor

_pool=None
_pool_settings=None
_pool_lock=RLock()


ROOT = Path(__file__).resolve().parents[2]
# Only MySQL bootstrapping may come from a file or process environment.
# Application settings are read independently from godp_system_config.
for _file in (ROOT / "docs" / ".env", ROOT / ".env"):
    for _key, _value in dotenv_values(_file).items():
        if _key in ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE") and _value is not None:
            os.environ[_key] = _value


def settings() -> dict:
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"缺少数据库配置：{', '.join(missing)}")
    return {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
        "autocommit": False,
    }


@contextmanager
def connection():
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

