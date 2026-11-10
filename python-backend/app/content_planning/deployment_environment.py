"""One deployment selector; legacy switches are compatibility inputs, never HTTP parameters."""
from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlsplit


class EnvironmentConfigurationError(ValueError):
    """Contains configuration key names only; safe for the local CLI/startup message."""


def resolve(values):
    explicit = "PLANNING_ENV" in values
    mode = values.get("PLANNING_ENV")
    if explicit:
        if mode not in ("outside", "inside"):
            raise EnvironmentConfigurationError("PLANNING_ENV必须为outside或inside，不能停用或留空")
    else:
        legacy = values.get("JAVA_ACCESS_MODE", "local_development")
        if legacy not in ("local_development", "bank"):
            raise EnvironmentConfigurationError("旧JAVA_ACCESS_MODE无效，请明确设置PLANNING_ENV")
        mode = "inside" if legacy == "bank" else "outside"
    # Both environments use the same transport. Only Java's facts implementation changes.
    source = "java_http"
    if not explicit and mode == "outside":
        source = values.get("BANK_SOURCE_MODE", "local_fixture")
    return dict(PLANNING_ENV=mode, JAVA_ACCESS_MODE="bank" if mode == "inside" else "local_development",
                BANK_SOURCE_MODE=source, compatibility_mode=not explicit)


def current():
    from .system_config import snapshot
    return resolve(snapshot())


def validation_errors(values):
    resolved = resolve(values)
    if resolved["PLANNING_ENV"] != "inside":
        return []
    errors = []
    for key in ("JAVA_GATEWAY_URL", "JAVA_API_BASE_URL"):
        try:
            address = urlsplit(values.get(key) or "")
            if (address.scheme not in ("http", "https") or not address.hostname or address.username
                    or address.password or address.query or address.fragment
                    or key == "JAVA_GATEWAY_URL" and address.path not in ("", "/")):
                errors.append(f"{key}未配置为有效的无凭据Java服务地址")
        except ValueError:
            errors.append(f"{key}地址无效")
    for key in ("JAVA_API_TOKEN", "INTEGRATION_TOKEN"):
        value = values.get(key)
        if not isinstance(value, str) or not value.strip() or value != value.strip() or any(c in value for c in '\r\n\x00'):
            errors.append(f"{key}尚未配置")
    if values.get("CONTENT_PRODUCTION_MODE", "disabled") != "disabled":
        errors.append("inside禁止启用local_mock内容生产")
    return errors


def require_ready(values=None):
    from .system_config import snapshot
    values = snapshot() if values is None else values
    errors = validation_errors(values)
    if errors:
        raise EnvironmentConfigurationError("行内接入配置不完整：" + "；".join(errors))
    return resolve(values)


def select(mode):
    """Persist only the selector after validation; never rewrite addresses, secrets or business rules."""
    from .db import connection
    from .system_config import snapshot, clear_cache
    from .system_config_catalog import CATALOG
    values = {**snapshot(force=True), "PLANNING_ENV": mode}
    require_ready(values)
    spec = CATALOG["PLANNING_ENV"]
    with connection() as db, db.cursor() as cursor:
        cursor.execute("INSERT INTO godp_system_config (config_key,config_group,config_name,config_value,value_type,is_secret,create_by,update_by,created_by,updated_by) VALUES('PLANNING_ENV',%s,%s,%s,'string',0,'environment-cli','environment-cli',create_by,update_by) ON DUPLICATE KEY UPDATE config_value=VALUES(config_value),enabled=1,del_flag='N',version=version+1,update_by='environment-cli', updated_by=update_by ", (spec.group, spec.name, mode))
        db.commit()
    clear_cache()
    return resolve(values)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="查看或选择outside/inside；配置保存在MySQL，不输出密钥")
    parser.add_argument("action", choices=("show", "check", "select"))
    parser.add_argument("mode", nargs="?", choices=("outside", "inside"))
    args = parser.parse_args()
    if args.action == "select" and not args.mode or args.action == "show" and args.mode:
        parser.error("select需要环境名称；show不接收环境名称；check可选环境名称且不修改配置")
    try:
        if args.action == 'select':
            result = select(args.mode)
        elif args.action == 'check':
            from .system_config import snapshot
            values = snapshot(force=True)
            result = require_ready({**values, 'PLANNING_ENV': args.mode} if args.mode else values)
        else:
            result = current()
        print(json.dumps(result, ensure_ascii=True))
        if args.action == "select":
            print("Environment selected. Restart the deployed services; no data was copied.")
        return 0
    except (ValueError, RuntimeError) as error:
        # Validation messages contain only key names; SQL/network errors never print connection details.
        print(str(error) if isinstance(error, EnvironmentConfigurationError) else "环境配置读取失败，请检查MySQL与系统配置")
        return 2
    except Exception:
        print("环境配置操作失败，请检查MySQL权限及系统配置")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
