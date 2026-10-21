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


# Keep current model/authentication values, listeners and the active content-provider mode.
# Worker switches and implementation details remain code defaults.
CATALOG = {
    "BACKEND_HOST": Setting("ports", "后端监听地址", "0.0.0.0"),
    "BACKEND_PORT": Setting("ports", "后端监听端口", "6930", "int", minimum=1, maximum=65535),
    "FRONTEND_HOST": Setting("ports", "前端监听地址", "0.0.0.0"),
    "FRONTEND_PORT": Setting("ports", "前端监听端口", "930", "int", minimum=1, maximum=65535),
    "INTEGRATION_TOKEN": Setting("keys", "系统内部接口鉴权密钥", secret=True),
    "ARK_API_KEY": Setting("keys", "火山方舟豆包 API Key", secret=True),
    "MODEL_NAME": Setting("models", "全项目文本生成模型名称或接入点", "doubao-seed-2-1-lite-260915"),
    "EMBEDDING_MODEL_NAME": Setting("models", "全项目向量模型名称或接入点", "doubao-embedding-vision-251215"),
    "CONTENT_PRODUCTION_MODE": Setting('production', '内容生产模式', 'disabled', choices=('disabled', 'local_mock')),
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
    "ORDINARY_SCHEDULER_ENABLED": "1",
    "HOTSPOT_SCHEDULER_ENABLED": "1",
    "TOPIC_LABEL_WORKER_ENABLED": "0",
    "TOPIC_VECTOR_WORKER_ENABLED": "0",
    "ACCOUNT_VECTOR_WORKER_ENABLED": "0",
    "AI_PREPARATION_WORKER_ENABLED": "0",
    "MATCHING_EXECUTOR_WORKER_ENABLED": "0",
    "PLANNING_WORKFLOW_WORKER_ENABLED": "1",
}

FRONTEND_KEYS = ("BACKEND_HOST", "BACKEND_PORT", "FRONTEND_HOST", "FRONTEND_PORT")
LAUNCH_KEYS = tuple(RUNTIME_DEFAULTS)


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
    return value
