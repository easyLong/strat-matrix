"""Model endpoint selection shared by text, profile, labeling and V19 calls."""
from urllib.parse import urlsplit

DEFAULT_BASE_URL = 'https://ark.cn-beijing.volces.com/api/v3'


class ModelEndpointError(ValueError):
    """Messages contain configuration key names, never configured values."""


def resolve_base_url(values):
    value = values.get('MODEL_BASE_URL', '')
    if not isinstance(value, str):
        raise ModelEndpointError('MODEL_BASE_URL已停用或格式无效')
    if not value:
        from .deployment_environment import resolve
        if resolve(values)['PLANNING_ENV'] == 'inside':
            raise ModelEndpointError('inside必须明确配置MODEL_BASE_URL，不自动使用公网模型地址')
        return DEFAULT_BASE_URL
    try:
        address = urlsplit(value)
        # Reading .port also validates malformed/out-of-range ports.
        port = address.port
        if (len(value) > 2048 or any(ord(c) <= 32 or ord(c) == 127 for c in value)
                or '\\' in value or address.scheme not in ('http', 'https')
                or not address.hostname or address.username is not None
                or address.password is not None or address.query or address.fragment
                or port == 0):
            raise ValueError()
    except ValueError:
        raise ModelEndpointError('MODEL_BASE_URL必须是无凭据、无查询参数的HTTP服务前缀') from None
    return value.rstrip('/')
