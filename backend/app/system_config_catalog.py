"""Definitions for application settings persisted in MySQL."""

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


CATALOG = {
    "INTEGRATION_TOKEN": Setting("integration", "系统内部接口与平台对接令牌", secret=True),
    "BACKEND_HOST": Setting("server", "后端监听地址", "0.0.0.0"),
    "BACKEND_PORT": Setting("server", "后端监听端口", "6930", "int", minimum=1, maximum=65535),
    "FRONTEND_HOST": Setting("server", "前端监听地址", "0.0.0.0"),
    "FRONTEND_PORT": Setting("server", "前端监听端口", "930", "int", minimum=1, maximum=65535),
    "BUILD_FRONTEND": Setting("server", "启动时是否构建前端", "1", "bool"),
    "RUN_DIR": Setting("server", "进程文件目录；相对路径以项目根目录为基准", "run"),
    "LOG_DIR": Setting("server", "运行日志目录；相对路径以项目根目录为基准", "logs"),
    "CHECK_HOST": Setting("server", "服务健康检查地址", "127.0.0.1"),
    "ORDINARY_SCHEDULER_ENABLED": Setting("scheduler", "普通策划调度开关", "1", "bool"),
    "HOTSPOT_SCHEDULER_ENABLED": Setting("scheduler", "热点策划调度开关", "1", "bool"),
    "TOPIC_LABEL_WORKER_ENABLED": Setting("labeling", "选题打标进程开关", "0", "bool"),
    "TOPIC_LABEL_PROVIDER": Setting("labeling", "选题打标供应方", "doubao", choices=("http", "doubao")),
    "TOPIC_LABEL_API_URL": Setting("labeling", "标签进程访问本项目后端的地址；留空使用本机后端端口"),
    "LABEL_MODEL_URL": Setting("labeling", "外部 HTTP 打标服务地址"),
    "LABEL_MODEL_TOKEN": Setting("labeling", "外部 HTTP 打标服务令牌", secret=True),
    "LABEL_MODEL_TIMEOUT_SECONDS": Setting("labeling", "打标单次模型调用超时秒数", "120", "int", minimum=1, maximum=600),
    "TOPIC_LABEL_POLL_SECONDS": Setting("labeling", "标签任务轮询间隔秒数", "30", "int", minimum=5, maximum=3600),
    "TOPIC_LABEL_RETRY_SECONDS": Setting("labeling", "标签失败重试冷却秒数", "600", "int", minimum=60, maximum=86400),
    "ARK_API_KEY": Setting("doubao", "火山方舟豆包 API 密钥", secret=True),
    "DOUBAO_BASE_URL": Setting("doubao", "豆包方舟 API 基地址", "https://ark.cn-beijing.volces.com/api/v3"),
    "DOUBAO_CHAT_MODEL": Setting("doubao", "豆包标签生成模型或接入点", "doubao-seed-2-0-lite-260215"),
    "DOUBAO_EMBEDDING_MODEL": Setting("doubao", "豆包 T6 向量模型或接入点"),
    "DOUBAO_EMBEDDING_API": Setting("doubao", "豆包向量接口类型", "multimodal", choices=("text", "multimodal")),
    "TOPIC_VECTOR_WORKER_ENABLED": Setting("topic_vector", "选题画像向量进程开关", "0", "bool"),
    "TOPIC_VECTOR_MODEL_URL": Setting("topic_vector", "选题画像向量模型服务地址"),
    "TOPIC_VECTOR_MODEL_TOKEN": Setting("topic_vector", "选题画像向量模型令牌", secret=True),
    "TOPIC_VECTOR_API_URL": Setting("topic_vector", "选题向量进程访问后端的地址；留空使用本机后端端口"),
    "TOPIC_VECTOR_MODEL_TIMEOUT_SECONDS": Setting("topic_vector", "选题向量调用超时秒数", "120", "int", minimum=1, maximum=600),
    "TOPIC_VECTOR_POLL_SECONDS": Setting("topic_vector", "选题向量轮询间隔秒数", "30", "int", minimum=5, maximum=3600),
    "TOPIC_VECTOR_RETRY_SECONDS": Setting("topic_vector", "选题向量失败重试秒数", "600", "int", minimum=60, maximum=86400),
    "ACCOUNT_VECTOR_WORKER_ENABLED": Setting("account_vector", "账号画像向量进程开关", "0", "bool"),
    "ACCOUNT_VECTOR_MODEL_URL": Setting("account_vector", "账号画像向量模型服务地址"),
    "ACCOUNT_VECTOR_MODEL_TOKEN": Setting("account_vector", "账号画像向量模型令牌", secret=True),
    "ACCOUNT_VECTOR_API_URL": Setting("account_vector", "账号向量进程访问后端的地址；留空使用本机后端端口"),
    "ACCOUNT_VECTOR_MODEL_TIMEOUT_SECONDS": Setting("account_vector", "账号向量调用超时秒数", "120", "int", minimum=1, maximum=600),
    "ACCOUNT_VECTOR_POLL_SECONDS": Setting("account_vector", "账号向量轮询间隔秒数", "30", "int", minimum=5, maximum=3600),
    "ACCOUNT_VECTOR_RETRY_SECONDS": Setting("account_vector", "账号向量失败重试秒数", "600", "int", minimum=60, maximum=86400),
    "AI_PREPARATION_WORKER_ENABLED": Setting("preparation", "AI 输入准备推进进程开关", "0", "bool"),
    "AI_PREPARATION_POLL_SECONDS": Setting("preparation", "AI 输入准备轮询秒数", "60", "int", minimum=5, maximum=3600),
    "MATCHING_EXECUTOR_WORKER_ENABLED": Setting("matching", "匹配执行进程开关", "0", "bool"),
    "MATCHING_EXECUTOR_POLL_SECONDS": Setting("matching", "匹配任务轮询秒数", "10", "int", minimum=5, maximum=3600),
    "MATCHING_EXECUTOR_LEASE_SECONDS": Setting("matching", "匹配任务租约秒数", "1800", "int", minimum=30, maximum=3600),
}

MYSQL_KEYS = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
FRONTEND_KEYS = ("BACKEND_HOST", "BACKEND_PORT", "FRONTEND_HOST", "FRONTEND_PORT")
LAUNCH_KEYS = FRONTEND_KEYS + (
    "BUILD_FRONTEND", "RUN_DIR", "LOG_DIR", "CHECK_HOST", "ORDINARY_SCHEDULER_ENABLED",
    "HOTSPOT_SCHEDULER_ENABLED", "TOPIC_LABEL_WORKER_ENABLED", "TOPIC_VECTOR_WORKER_ENABLED",
    "ACCOUNT_VECTOR_WORKER_ENABLED", "AI_PREPARATION_WORKER_ENABLED", "MATCHING_EXECUTOR_WORKER_ENABLED",
)


def validate_value(key: str, value: str, spec: Setting | None = None) -> str:
    spec = spec or CATALOG.get(key)
    if not isinstance(value, str) or any(char in value for char in ("\x00", "\r", "\n")):
        raise ValueError(f"{key} 必须是单行配置值")
    if spec is None:
        return value
    if spec.kind == "bool" and value not in ("0", "1"):
        raise ValueError(f"{key} 只允许 0 或 1")
    if spec.kind == "int":
        try:
            number = int(value)
        except ValueError:
            raise ValueError(f"{key} 必须是整数") from None
        if ((spec.minimum is not None and number < spec.minimum)
                or (spec.maximum is not None and number > spec.maximum)):
            raise ValueError(f"{key} 超出允许范围")
    if spec.choices and value not in spec.choices:
        raise ValueError(f"{key} 不属于允许的配置选项")
    if key in ("BACKEND_HOST", "FRONTEND_HOST", "CHECK_HOST") and (not value or any(c.isspace() for c in value)):
        raise ValueError(f"{key} 不能为空或包含空白")
    return value
