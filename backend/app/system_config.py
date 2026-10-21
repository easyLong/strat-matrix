"""Read runtime settings from MySQL; expose only masked or allowlisted CLI output."""

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
import json
import shlex
import sys
from threading import RLock
import time

import pymysql

from .db import connection
from .system_config_catalog import CATALOG, FRONTEND_KEYS, LAUNCH_KEYS, validate_value


class SystemConfigError(RuntimeError):
    pass


_overrides = ContextVar("system_config_test_overrides", default=None)
_cache: dict[str, str | None] = {}
_expires_at = 0.0
_lock = RLock()
CACHE_SECONDS = 5


@contextmanager
def override_config(values: dict):
    """Explicit isolated configuration for tests; never activated by environment variables."""
    token = _overrides.set({key: str(value) for key, value in values.items()})
    try:
        yield
    finally:
        _overrides.reset(token)


def clear_cache():
    global _expires_at
    with _lock:
        _cache.clear()
        _expires_at = 0.0


def snapshot(*, force=False) -> dict[str, str | None]:
    global _expires_at
    overrides = _overrides.get()
    if overrides is not None:
        return dict(overrides)
    with _lock:
        if force or time.monotonic() >= _expires_at:
            try:
                with connection() as db, db.cursor() as cursor:
                    cursor.execute("SELECT config_key,config_value,enabled FROM godp_system_config WHERE del_flag='N'")
                    rows = cursor.fetchall()
            except (pymysql.MySQLError, RuntimeError, ValueError):
                # An expired secret must not silently remain usable after DB failure.
                raise SystemConfigError("系统配置读取失败，请检查 MySQL 连接及 godp_system_config 初始化状态") from None
            values = {}
            for row in rows:
                value = str(row["config_value"])
                try:
                    validate_value(row["config_key"], value)
                except ValueError as exc:
                    raise SystemConfigError(str(exc)) from None
                values[row["config_key"]] = value if row["enabled"] else None
            _cache.clear()
            _cache.update(values)
            _expires_at = time.monotonic() + CACHE_SECONDS
        return dict(_cache)


def get_setting(key: str, default: str | None = None) -> str:
    values = snapshot()
    if key in values:
        if values[key] is None:
            raise SystemConfigError(f"系统配置 {key} 已停用")
        return values[key]
    if _overrides.get() is None and key in CATALOG:
        raise SystemConfigError(f"系统配置 {key} 尚未初始化")
    if default is not None:
        return default
    return CATALOG[key].default if key in CATALOG else ""


def public_settings(frontend=False) -> dict[str, str]:
    keys = FRONTEND_KEYS if frontend else LAUNCH_KEYS
    result = {key: get_setting(key) for key in keys}
    if not frontend:
        result["TOPIC_VECTOR_MODEL_CONFIGURED"] = "1" if get_setting("TOPIC_VECTOR_MODEL_URL") else "0"
    return result


def masked_settings(group: str | None = None) -> list[dict]:
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT config_key,config_group,config_name,config_value,value_type,is_secret,"
                       "enabled,version FROM godp_system_config WHERE del_flag='N' ORDER BY config_group,id")
        rows = cursor.fetchall()
    for row in rows:
        if row["is_secret"] or (row["config_key"] in CATALOG and CATALOG[row["config_key"]].secret):
            row["config_value"] = "******" if row["config_value"] else ""
    return [row for row in rows if group is None or row["config_group"] == group]


def set_setting(key: str, value: str, expected_version: int | None = None) -> int:
    if key not in CATALOG:
        raise ValueError("只能通过配置命令修改已登记的系统参数")
    validate_value(key, value)
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT version FROM godp_system_config WHERE config_key=%s AND del_flag='N' FOR UPDATE", (key,))
        row = cursor.fetchone()
        if not row:
            raise SystemConfigError(f"系统配置 {key} 尚未初始化")
        if expected_version is not None and row["version"] != expected_version:
            raise SystemConfigError("系统配置版本已变化，请重新查询")
        cursor.execute("UPDATE godp_system_config SET config_value=%s,version=version+1,"
                       "update_by='config-cli' WHERE config_key=%s", (value, key))
        db.commit()
    clear_cache()
    return row["version"] + 1


def main():
    parser = argparse.ArgumentParser(description="MySQL 系统配置；默认查询密钥脱敏")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--group")
    sub.add_parser("frontend-json")
    sub.add_parser("launch-shell")
    setting = sub.add_parser("set")
    setting.add_argument("key")
    source = setting.add_mutually_exclusive_group(required=True)
    source.add_argument("--value")
    source.add_argument("--stdin", action="store_true")
    setting.add_argument("--expected-version", type=int)
    args = parser.parse_args()
    try:
        if args.command == "set":
            if CATALOG.get(args.key) and CATALOG[args.key].secret and not args.stdin:
                raise ValueError("密钥配置请通过 --stdin 输入，避免进入命令行参数")
            value = sys.stdin.read().rstrip("\r\n") if args.stdin else args.value
            version = set_setting(args.key, value, args.expected_version)
            print(f"配置 {args.key} 已更新，版本 {version}")
        elif args.command == "list":
            print(json.dumps(masked_settings(args.group), ensure_ascii=False, indent=2))
        elif args.command == "frontend-json":
            print(json.dumps(public_settings(frontend=True)))
        else:
            for key, value in public_settings().items():
                print(f"{key}={shlex.quote(value)}")
        return 0
    except (SystemConfigError, ValueError):
        # Error messages contain configuration names, never raw values or SQL.
        print("系统配置操作失败，请检查数据库初始化、配置值和版本", file=sys.stderr)
        return 2
    except pymysql.MySQLError:
        print("系统配置数据库操作失败", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
