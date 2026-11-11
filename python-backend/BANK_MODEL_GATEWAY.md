# 行内 doubaoNative 模型调用适配

本版依据 2026-11-11 提供的 curl 截图实现。所有文本调用仍由统一入口限流，协议转换不改变 V19 算法和业务职责。没有访问截图中的内网地址、调用真实模型或修改开发数据库配置。

## 1. 如何配置

独立运行在策划库 `godp_system_config` 配置；嵌入宿主时也可通过 `PlanningConfig.from_mapping()` 的 `PLANNING_` 前缀覆盖，无需改算法代码。

| 数据库配置键 | 本次行内配置 |
| --- | --- |
| `MODEL_PROTOCOL` | `doubao_native` |
| `MODEL_BASE_URL` | 填写截图中经批准的完整 `doubaoNative` 地址；FAT/生产分别配置。真实内网域名保留在行内配置中心，不提交公共仓库 |
| `MODEL_NAME` | `doubao-seed-2-1-pro-260915`，来自截图 |
| `ARK_API_KEY` | 原生文本接口不发送该密钥；仅向量兼容服务使用，可待确认后配置，不写进代码 |
| `EMBEDDING_BASE_URL` | 向量服务前缀，待行内提供；留空会明确拒绝向量请求，不调用文本地址、不自动回退公网 |
| `EMBEDDING_MODEL_NAME` | 实际向量模型名，仍由账号、选题、T6 共用；不能填写文本模型名 |

不新建表。现有库补配置使用 `database/content_planning/migrations/20261111_add_native_model_protocol.sql`，仅幂等新增两行默认值，不覆盖已有配置、不自动切换行内模式。按发布权限执行；应用不在启动时执行 DDL/DML。

宿主配置示例：

```python
from app.content_planning.config import PlanningConfig

config = PlanningConfig.from_mapping({
    # 与既有宿主配置合并；此示例只列模型相关键。
    'PLANNING_MODEL_PROTOCOL': 'doubao_native',
    'PLANNING_MODEL_BASE_URL': approved_native_endpoint,
    'PLANNING_MODEL_NAME': 'doubao-seed-2-1-pro-260915',
    'PLANNING_ARK_API_KEY': '',
    'PLANNING_EMBEDDING_BASE_URL': '',  # 获得向量契约后填写
    'PLANNING_EMBEDDING_MODEL_NAME': approved_embedding_model,
})
```

未提供的 `approved_native_endpoint` 等由宿主配置中心提供，示例不独立启动服务。既有 `PlanningConfig.model_protocol` 的显式非默认值优先；否则使用当前系统配置的 `MODEL_PROTOCOL`。默认 `chat_completions` 保持行外可用。

原生文本模式严格对应截图，不发送 Authorization，即使 `ARK_API_KEY` 已为向量服务配置，也不会将它转发给文本入口。宿主 `model_headers` 继续支持附加网关头。其他兼容协议下 `model_authorization_scheme='none'` 可显式关闭 Authorization；若行内文本将来明确要求 Bearer 等不同鉴权，由既有 `model_adapters['text']` 处理。不要把浏览器 Cookie 或前端透传 Header 直接拼入模型请求。

## 2. 协议变化

| 原内部调用 | 行内请求 |
| --- | --- |
| `base_url + /chat/completions` | 向完整 `MODEL_BASE_URL` POST，不再追加路径 |
| `messages` | `input` 数组；每项 `role / type=message / content` |
| `response_format.json_schema` | `text.format`：`type=json_schema / strict=true / name / schema` |
| `max_tokens` | `max_output_tokens` |
| 同步完整结果 | `stream=false` |

T1–T6 打标、批量主关联标注、受限账号画像映射、账号–选题精判均传实际输出 Schema，包含必填字段和 `additionalProperties=false`；字典打标还包含本次启用标签枚举。算法原有本地 Pydantic、标签归属、证据和评分校验继续执行。

截图的 `temperature=0.6`、`thinking=enabled` 是示例参数。本轮保留策划算法已有 `temperature=0`、`thinking=disabled`，避免把协议适配同时变成算法效果变更。

## 3. 响应解析与未确认项

截图只有请求。当前实现按**原始 Responses JSON**消费：

```json
{
  "status": "completed",
  "output": [
    {"type": "message", "role": "assistant", "status": "completed",
     "content": [{"type": "output_text", "text": "{\"ok\":true}"}]}
  ],
  "usage": {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16}
}
```

以上是**本地契约夹具**，不是行内实测回包。忽略 reasoning 输出，将最终助手文本归一为原有 `choices[0].message.content`，保留原始 `usage` Token 数据，不记录推理文本。截断、失败、拒绝、空结果、多条助手消息和非预期输出不会被判成成功；遇到 `code/data` 包装明确报协议不匹配，禁止猜测解包后误判成功。如真实回包有包装，通过既有 `PlanningDependencies.model_adapters['text']` 扩展解析；其输出归一约定不变。

HTTP 429、401/403、5xx、超时、响应大小限制、禁止重定向及凭据保护沿用统一网络层。限流令牌覆盖完整网络调用及读取，不因更换网关绕过。没有新增自动重试或另一套线程池。

向量请求仍按已实现的 `/embeddings/multimodal` 文本嵌入契约发送到**独立确认**的向量服务前缀；若行内向量也改为另一种协议，使用 `model_adapters['embedding']`，不能假定 `doubaoNative` 能生成向量。预检会分别报告文本与向量配置是否齐备。

## 4. 联调顺序

1. 合并代码及补配置脚本，填写原生文本协议、完整地址及模型名，核实网关是否需要附加鉴权头。
2. 先核对一条脱敏原始成功响应及一条错误响应，确认是否直接返回 Responses JSON；未核对前仅能称为本地契约通过。
3. 单独确认向量地址、模型、鉴权、维度与返回格式；缺少这一步，打标后 T6/账号/选题向量及完整匹配链路不会就绪。
4. `python -m app.content_planning.onsite_check --target inside` 只读预检；`--probe-models` 会真实调用文本和向量，须在行内确认后显式执行。
5. 通过小批测试后扩大账号规模；需回退时恢复发布前协议、地址与模型配置，不删除历史画像或策划结果。

离线回归入口：

```bash
python -m pytest -p testing.pytest_plugin tests/test_native_model_protocol.py tests/test_model_endpoint.py tests/test_doubao_labeling.py tests/test_model_capacity.py
```

从仓库根配置 `PYTHONPATH` 同时包含根目录和 `python-backend`，或按现有统一测试入口运行。测试只访问本机回环 HTTP，不调用行内或收费模型。
