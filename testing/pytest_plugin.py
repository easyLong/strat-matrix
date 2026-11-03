"""Process-local guards: unit tests may use loopback HTTP fixtures, never real MySQL/models."""
import socket
from urllib.parse import urlsplit
import urllib.request
from unittest.mock import patch
import pytest


@pytest.fixture(autouse=True)
def synthetic_system_settings(request):
    # Older tests mocked business SQL but still read live system settings. Supply isolated settings;
    # the dedicated config-store tests must exercise their own mocked provider and failure paths.
    if request.path.name == "test_system_config.py":
        yield
        return
    from app.system_config import override_config
    with override_config({"BANK_SOURCE_MODE": "local_fixture", "INTEGRATION_TOKEN": "regression-only-token",
                          "AUTO_SCHEDULE_OWNER": "python"}):
        yield


def pytest_configure(config):
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    urlopen = urllib.request.urlopen

    def deny_database(*_args, **_kwargs):
        raise RuntimeError("统一回归禁止真实数据库连接；请使用测试替身")

    def local_connection(original, client, address):
        if not isinstance(address, tuple) or str(address[0]) not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("统一回归禁止公网连接")
        return original(client, address)

    def local_url(request, *args, **kwargs):
        target = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        if urlsplit(target).hostname not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("统一回归禁止真实模型与外部HTTP")
        return urlopen(request, *args, **kwargs)

    config._planning_guards = [
        patch("pymysql.connect", deny_database),
        patch("socket.socket.connect", lambda client, address: local_connection(connect, client, address)),
        patch("socket.socket.connect_ex", lambda client, address: local_connection(connect_ex, client, address)),
        patch("urllib.request.urlopen", local_url),
    ]
    for guard in config._planning_guards:
        guard.start()


def pytest_unconfigure(config):
    for guard in reversed(getattr(config, "_planning_guards", [])):
        guard.stop()
