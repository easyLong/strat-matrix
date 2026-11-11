"""Operator-editable model credentials, listening ports and content-provider mode."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Setting:
    group: str
    name: str
    default: str = ""
    kind: str = "string"
    secret: bool = False
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()


# Keep model/authentication values, model capacity limits, listeners and integration modes.
# Worker switches and implementation details remain code defaults.
CATALOG = {
    "PLANNING_ENV": Setting("integration", "部署环境：outside行外模拟接入，inside行内宿主接入", "outside", choices=('outside', 'inside')),
    "BACKEND_HOST": Setting("ports", "后端监听地址", "0.0.0.0"),
    "BACKEND_PORT": Setting("ports", "后端监听端口", "6930", "int", minimum=1, maximum=65535),
    "FRONTEND_HOST": Setting("ports", "前端监听地址", "0.0.0.0"),
    "FRONTEND_PORT": Setting("ports", "前端监听端口", "930", "int", minimum=1, maximum=65535),
    "JAVA_GATEWAY_URL": Setting("integration", "Java业务服务根地址，本地留空使用回环6931，行内填写宿主地址", ""),
    "JAVA_ACCESS_MODE": Setting("integration", "旧页面接入方式兼容项；新部署由PLANNING_ENV统一选择", "local_development", choices=('local_development', 'bank')),
    "BANK_SOURCE_MODE": Setting("integration", "旧资料来源兼容项；新部署由PLANNING_ENV统一选择", "local_fixture", choices=('local_fixture', 'java_http')),
    "JAVA_API_BASE_URL": Setting("integration", "Java资料与生产状态查询服务前缀", ""),
    "JAVA_API_TOKEN": Setting("keys", "Python访问Java资料服务的鉴权密钥", secret=True),
    "INTEGRATION_TOKEN": Setting("keys", "系统内部接口鉴权密钥", secret=True),
    "ARK_API_KEY": Setting("keys", "火山方舟豆包 API Key", secret=True),
    "MODEL_BASE_URL": Setting("models", "模型地址：chat_completions为服务前缀，doubao_native为完整文本接口地址；行内必须填写", ""),
    "MODEL_PROTOCOL": Setting("models", "文本模型协议；行内doubaoNative选择doubao_native", "chat_completions", choices=('chat_completions', 'doubao_native')),
    "EMBEDDING_BASE_URL": Setting("models", "行内原生文本协议下单独配置的向量服务前缀；未确认前留空并阻止向量请求", ""),
    "MODEL_NAME": Setting("models", "全项目文本生成模型名称或接入点", "doubao-seed-2-1-lite-260915"),
    "EMBEDDING_MODEL_NAME": Setting("models", "全项目向量模型名称或接入点", "doubao-embedding-vision-251215"),
    "AI_API_MAX_CONCURRENT_REQUESTS": Setting('model_limits','模型能力入口最大并发请求数','4','int',minimum=1,maximum=64),
    "MODEL_MAX_CONCURRENT_REQUESTS": Setting('model_limits','所有文本模型实际调用共享并发上限','2','int',minimum=1,maximum=64),
    "EMBEDDING_MAX_CONCURRENT_REQUESTS": Setting('model_limits','账号及选题向量模型共享并发上限','2','int',minimum=1,maximum=64),
    "AI_PENDING_TASK_LIMIT": Setting('model_limits','每类外部创建的待处理算法任务上限','32','int',minimum=1,maximum=1000),
    "AI_LIMIT_SCOPE": Setting('model_limits','实际模型调用限流范围：process单进程，mysql跨进程共享','process',choices=('process','mysql')),
    "CONTENT_PRODUCTION_MODE": Setting('production', '内容生产模式', 'disabled', choices=('disabled', 'local_mock')),
    "AUTO_PLANNING_POLICY_ID": Setting('planning', '周自动策划绑定的已批准V19策略ID，0表示尚未绑定', '0', 'int', minimum=0),
    "AUTO_PLANNING_ACCOUNT_IDS": Setting('planning', '周自动策划试运行账号ID的JSON数组；空数组表示全部可参与账号', '[]'),
    "AUTO_SCHEDULE_OWNER": Setting('planning', '周自动策划触发方；切换到Java后Python不再自行判定调度时间', 'python', choices=('python', 'java')),
}

MYSQL_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
PORT_KEYS = ("BACKEND_HOST", "BACKEND_PORT", "FRONTEND_HOST", "FRONTEND_PORT")

# Bootstrap defaults belong to the application, not godp_system_config.
RUNTIME_DEFAULTS = {
    "BACKEND_HOST": "0.0.0.0",
    "BACKEND_PORT": "6930",
    "FRONTEND_HOST": "0.0.0.0",
    "FRONTEND_PORT": "930",
    "BUILD_FRONTEND": "1",
    "RUN_DIR": "run",
    "LOG_DIR": "logs",
    "CHECK_HOST": "127.0.0.1",
}

FRONTEND_KEYS = ("BACKEND_HOST", "BACKEND_PORT", "FRONTEND_HOST", "FRONTEND_PORT", "JAVA_GATEWAY_URL", "JAVA_ACCESS_MODE", "PLANNING_ENV")
LAUNCH_KEYS = (*RUNTIME_DEFAULTS, 'JAVA_ACCESS_MODE', 'JAVA_GATEWAY_URL', 'PLANNING_ENV')


def validate_value(key: str, value: str, spec: Setting | None = None) -> str:
    spec = spec or CATALOG.get(key)
    if not isinstance(value, str) or any(char in value for char in ("\x00", "\r", "\n")):
        raise ValueError(f"{key} 必须是单行配置值")
    if spec and spec.kind == "int":
        try:
            number = int(value)
        except ValueError:
            raise ValueError(f"{key} 必须是整数") from None
        if ((spec.minimum is not None and number < spec.minimum)
                or (spec.maximum is not None and number > spec.maximum)):
            raise ValueError(f"{key} 超出允许范围")
    if spec and spec.choices and value not in spec.choices:
        raise ValueError(f'{key} 不在允许的配置范围内')
    if key in ('JAVA_GATEWAY_URL', 'JAVA_API_BASE_URL') and value:
        from urllib.parse import urlsplit
        address = urlsplit(value)
        if (address.scheme not in ('http', 'https') or not address.hostname
                or address.username or address.password or address.query or address.fragment):
            raise ValueError(f'{key} 必须是无凭据的HTTP服务地址')
        if key == 'JAVA_GATEWAY_URL' and address.path not in ('', '/'):
            raise ValueError('JAVA_GATEWAY_URL 必须是服务根地址')
    if key in ('MODEL_BASE_URL', 'EMBEDDING_BASE_URL') and value:
        from .model_endpoint import resolve_base_url
        resolve_base_url({'PLANNING_ENV':'outside', 'MODEL_BASE_URL':value})
    return value
