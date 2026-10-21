# 豆包选题打标服务

项目内置豆包火山方舟适配器。标签 Worker 领取任务后，调用本项目内部模型接口生成 T1–T6 标签及 T6 语义向量，再沿用已有事务回写标签、稳定 ID 和选题画像。本轮未新增数据表或字段。全项目文本任务统一使用 `MODEL_NAME`，T6、普通选题画像及账号画像向量统一使用 `EMBEDDING_MODEL_NAME`；凭据共用 `ARK_API_KEY`。

## 配置

模型与密钥保存在 MySQL `godp_system_config`，通过[系统配置命令](SYSTEM_CONFIG.md)修改；`.env` 只保留数据库连接。当前只需关心以下三项：

```text
ARK_API_KEY=
MODEL_NAME=doubao-seed-2-1-lite-260915
EMBEDDING_MODEL_NAME=doubao-embedding-vision-251215
```

聊天模型填写标准方舟 API 可用的版本化 Model ID 或推理接入点 ID。当前默认 `doubao-seed-2-1-lite-260915`；Coding Plan 的别名 `doubao-seed-2.1-lite` 不能直接用于项目当前的标准 `/api/v3` 地址。

所有项目向量都使用方舟 `/embeddings/multimodal` 的纯文本输入能力；账号画像和选题画像将规范化画像 JSON 作为文本输入，T6 将需求短语作为文本输入，不发送图片或视频。保存上游响应中实际 `model` 作为统一向量空间标识。当前默认模型支持纯文本输入，详见[方舟向量化接口文档](https://docs.volcengine.com/docs/ark/vectorization?lang=zh&redirect=1)。

T6 标签向量用于需求标签归并；选题画像和账号画像由各自 Worker 生成，但三者复用相同的向量适配器、模型配置、API Key 和向量空间。

## 流程

1. 正式普通选题首次同步后，后端创建任务并保存原始输入快照。
2. Worker 领取租约、当时字典版本和启用的 T1–T5 叶子名称。
3. 内置服务调用豆包 Chat Completions，以 JSON 模式生成六维单选标签。
4. 本项目校验字典约束、单选格式及长度。非法标签不会进入向量调用。
5. 豆包向量接口为 T6 名称生成真实语义向量；服务检查数值与维度并归一化。
6. Worker 带原租约及版本回写 `/api/internal/topic-tags/{topic_id}`。
7. 后端在现有事务中解析稳定 ID、合并 T6 同义标签、完成任务并生成选题画像。

当前生产队列仍只处理正式普通选题。选题标题和大纲作为待分类数据传入，分类规则由服务固定；不会使用聊天模型编造的数字数组作为语义向量。

## 内部模型接口

`POST /api/internal/topic-label-model`，使用 `X-Integration-Token` 鉴权。Worker 已自动调用它，不需要另起模型微服务。此接口只做推理，不领取任务或更新业务数据，可用于小样本联调。

```json
{
  "task": "ordinary_topic_labels",
  "topic_id": "TOPIC-001",
  "topic": {"title": "年轻人如何分配日常资金", "outline": "介绍支出、应急储备和长期储蓄的分配方法", "content_type": "图文"},
  "taxonomy_version": 3,
  "taxonomy": {
    "T1": ["非营销"], "T2": ["流量", "转化"], "T3": ["金融知识"],
    "T4": ["年轻客群"], "T5": ["日常理财"]
  }
}
```

字典仅演示格式。生产调用使用领取响应中的真实字典，五个维度均须非空、名称无重复，不可将分类节点作为叶子。

返回沿用原模型服务契约：

```json
{
  "labels": {"T1": "非营销", "T2": "流量", "T3": "金融知识", "T4": "年轻客群", "T5": "日常理财", "T6": "管理日常资金"},
  "t6_embedding_model": "实际向量模型版本",
  "t6_embedding": [0.6, 0.8]
}
```

示例向量只说明格式。实际返回由豆包生成，当前存储契约支持 1–4096 维有效非零向量。

| 情况 | HTTP 状态 | 处理 |
| --- | --- | --- |
| 内部令牌无效 | 401 | 不调用模型 |
| 输入不完整或字典不合规 | 422 | 不调用模型 |
| 凭据或模型配置缺失 | 503 | 不调用模型，Worker 预检阻止领取任务 |
| 限流、超时、上游暂时不可用 | 503 | Worker 记录失败，冷却后重试 |
| 字典外标签、响应截断、非法向量或上游拒绝 | 502 | 不回写成功标签 |
| 回写时租约或字典过期 | 原回写接口返回 409 | 忽略旧结果 |

失败原因不记录上游正文、密钥或完整选题内容。每次上游调用独立使用模型超时；Worker 调用内置服务的超时为两次模型超时之和加 15 秒。

## 启用与验证

先重启后端，使新增接口生效。以下命令在 `backend` 目录执行：

```bash
# 不领取任务、不调用豆包
python -m app.topic_label_worker --check-config

# 凭据和模型填妥后，处理一轮真实队列
python -m app.topic_label_worker --once

# 常驻处理
python -m app.topic_label_worker
```

`--once` 会调用模型并更新真实标签；有任务失败时退出码为 1，配置错误为 2。Worker 默认不随服务启动；需要运行时手动启动 Worker 命令。超时与重试间隔采用代码默认值。

当前固定使用豆包服务；其它模型供应方接入后，再按实际运营需求补充配置项。

```bash
cd backend
python -m unittest discover -s tests -p test_doubao_labeling.py -v
python -m unittest discover -s tests -v
```

新增测试使用本地 HTTP 替身，不请求真实豆包或消耗额度，覆盖模型协议、鉴权、字典与向量校验、错误脱敏、租约失效及 Worker 完整交接。

## 官方接口资料

- [结构化输出与 Chat Completions JSON 模式](https://docs.volcengine.com/docs/ark/structured-output-beta?lang=en)
- [豆包多模态向量化](https://docs.volcengine.com/docs/ark/vectorization?lang=en&redirect=1)
- [文本向量化 API](https://api.volcengine.com/api-docs/view?action=Embeddings&serviceCode=ark&version=2024-01-01)
