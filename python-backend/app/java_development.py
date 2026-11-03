"""Local three-project launcher bridge; never part of the bank runtime contract.

Read existing MySQL settings without exposing secrets in shell output or process arguments.
Standalone Java still starts without Python using its own code defaults.
"""

import argparse
import os
import re
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from dotenv import dotenv_values

from .system_config import get_setting


def java_database_settings():
    """Read launcher connection values only; never connect to the Java business database."""
    from .db import settings
    original = settings()
    base = original.copy()
    root = Path(__file__).resolve().parents[2]
    values = dict(os.environ)
    for path in (root / 'docs' / '.env', root / '.env'):
        values.update({k: v for k, v in dotenv_values(path).items()
                       if k.startswith('JAVA_MYSQL_') and v is not None})
    for name, key in [('HOST', 'host'), ('PORT', 'port'), ('USER', 'user'),
                      ('PASSWORD', 'password'), ('DATABASE', 'database')]:
        base[key] = values.get('JAVA_MYSQL_' + name,
                               base[key] if key != 'database' else base[key] + '_business')
    base['port'] = int(base['port'])
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', base['database']):
        raise ValueError('Java数据库名称无效')
    if (base['host'], base['port'], base['database']) == (
            original['host'], original['port'], original['database']):
        raise ValueError('Java业务库不可与Python算法库相同')
    return base


def local_java_address(value: str) -> tuple[str, int]:
    address = urlsplit(value or "http://127.0.0.1:6931")
    if (address.scheme != "http" or address.hostname not in ("localhost", "127.0.0.1", "::1")
            or address.username or address.password or address.query or address.fragment
            or address.path not in ("", "/")):
        raise ValueError("本地Java开发壳须使用回环HTTP根地址；远程宿主请使用bank模式")
    port = address.port if address.port is not None else 80
    if not 1 <= port <= 65535:
        raise ValueError("Java端口必须在1到65535之间")
    return address.hostname, port


def properties_text(values: dict[str, str]) -> str:
    def escape(value):
        # Java .properties files default to ISO-8859-1; keep all output ASCII.
        result = []
        for char in value:
            if char in "\\:=#! ":
                result.append("\\" + char)
            elif char in "\r\n\x00":
                raise ValueError("启动配置必须是单行值")
            elif ord(char) > 127:
                encoded = char.encode("utf-16-be")
                result.extend("\\u" + encoded[index:index + 2].hex() for index in range(0, len(encoded), 2))
            else:
                result.append(char)
        return "".join(result)
    return "".join(f"{key}={escape(value)}\n" for key, value in values.items())


def write_local_configuration(destination: Path):
    if get_setting("JAVA_ACCESS_MODE") != "local_development":
        raise ValueError("行内宿主模式不生成本地Java配置")
    host, port = local_java_address(get_setting("JAVA_GATEWAY_URL"))
    python_host = get_setting("BACKEND_HOST")
    if python_host in ("0.0.0.0", "::"):
        python_host = "127.0.0.1"
    if ":" in python_host:
        python_host = f"[{python_host}]"
    values = {
        "server.address": host,
        "server.port": str(port),
        "planning.legacy.base-url": f"http://{python_host}:{get_setting('BACKEND_PORT')}",
        "planning.legacy.integration-token": get_setting("INTEGRATION_TOKEN"),
    }
    java_db = java_database_settings()
    values.update({
        'planning.manual.enabled': 'true',
        'planning.manual.initialize-schema': 'true',
        'planning.config-release.enabled': 'true',
        'planning.history.mode': 'business_only',
        'planning.auto-schedule.enabled': 'true',
        'planning.manual.jdbc-url': f"jdbc:mysql://{java_db['host']}:{java_db['port']}/{java_db['database']}?characterEncoding=UTF-8&serverTimezone=UTC",
        'planning.manual.username': java_db['user'],
        'planning.manual.password': java_db['password'],
    })
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="java-", suffix=".properties", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
            stream.write(properties_text(values))
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description="生成本地Java启动配置；配置来自MySQL，密钥不输出")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        write_local_configuration(args.output.resolve())
    except Exception:
        # Do not expose DB exceptions, connection strings or configuration values.
        parser.exit(2, "Java本地配置生成失败，请检查数据库连接参数及Java接入配置；业务表由Java启动时初始化\n")


if __name__ == "__main__":
    main()
