# 普通选题首次标签识别任务

依据《多账号智能策划_PRD_V1.1_近期口径同步稿.docx》3.4.5 节。本项目在正式普通选题首次同步时创建一条内部识别任务；同一选题后续标题、大纲和内容类型更新不会创建第二条任务，也不会重算已完成的 T1–T6 标签。营销选题与 `DEMO-` 演示选题不入队。全量快照停用选题时取消未完成任务，重新纳入且仍未识别的选题可以恢复待处理。

任务存于 `godp_topic_label_job`，保存首次入库的选题内容快照、来源更新时间、状态、领取次数、租约和字典版本。首次部署运行 `cd backend && python3 -m app.init_db` 后，既有正式普通选题中尚未完成标签识别的记录会补建任务；这类迁移任务只能使用当前已保存的来源内容，无法恢复更早的首次入库内容。

所有下列接口都要求 `X-Integration-Token`，属于**本项目内部识别器接口**，不是客户选题库接口：

1. `GET /api/internal/topic-label-jobs?limit=100&after_id=0` 按任务 ID 升序列出待领取、失败或租约过期的任务。返回记录含 `id`，下一页把上一页最后一条 `id` 传入 `after_id`。
2. `POST /api/internal/topic-label-jobs/{topic_id}/claim` 领取任务，默认租约 1800 秒，可传 `lease_seconds=60…7200`。返回 `lease_id`、首次入库内容快照、当前启用的 T1–T5 字典和锁定的 `taxonomy_version`。同一未过期任务不能重复领取；过期后可重新领取。
3. 识别器完成后调用 `PUT /api/internal/topic-tags/{topic_id}`，提交 T1–T6 单选 `tags`、`label_status="已完成"`、领取时返回的 `lease_id` 与 `taxonomy_version`，以及 `t6_embedding` 和 `t6_embedding_model`。识别失败时提交 `label_status="失败"`、`label_error` 和 `lease_id`；失败任务之后可以再次领取。过期或旧租约的结果返回 409。

写入标签与任务状态在同一数据库事务中完成；已完成的结果仅接受与已保存结果一致的重复提交，T6 候选被归并为同一已有标签时也按归并后的结果判断。后续选题编辑不触发重算。IF-08 只查询已保存的名称和状态，不领取任务，也不触发模型调用。内部任务失败时 IF-08 返回“失败”；尚未写入结果时返回“处理中”。

## 配置本地识别进程

项目内已有 `python3 -m app.topic_label_worker` 执行器。它使用上述内部接口领取任务，将首次入库选题快照与领取时的 T1–T5 字典交给本项目内置模型服务，校验响应后提交 T1–T6 单选结果。文本生成使用全局 `MODEL_NAME`；T6 向量使用与选题、账号画像共用的 `EMBEDDING_MODEL_NAME`；三类调用共用 `ARK_API_KEY`。默认不开启 Worker，配置不完整时不领取任务。

方舟 API Key 和两类全局模型配置保存在 MySQL `godp_system_config`。Worker 开关和轮询参数使用代码默认值。内部打标模型接口接收 JSON `POST`，请求示例：

```json
{
  "task": "ordinary_topic_labels",
  "topic_id": "TOPIC-001",
  "topic": {"topic_id": "TOPIC-001", "title": "示例标题"},
  "taxonomy_version": 3,
  "taxonomy": {"T1": ["标签 A"], "T2": ["标签 B"], "T3": ["标签 C"], "T4": ["标签 D"], "T5": ["标签 E"]}
}
```

其中 `topic` 是客户首次同步的完整原始记录；字典中的名称由接口实际返回，示例仅用于说明格式。模型服务响应：

```json
{
  "labels": {"T1": "标签 A", "T2": "标签 B", "T3": "标签 C", "T4": "标签 D", "T5": "标签 E", "T6": "模型生成标签"},
  "t6_embedding_model": "your-embedding-model-version",
  "t6_embedding": [0.12, 0.34, 0.56]
}
```

T1–T5 必须各选一个当前字典名称；T6 必须是 1–80 字的单个名称。`t6_embedding` 是该 T6 候选名称的语义向量，必须为 1–4096 维有效数值；`t6_embedding_model` 是可区分模型版本的标识。同一标识下的向量维度必须一致。上面的三维数字只是协议示例，不是项目预设维度。响应格式或标签不合规时任务记为失败，同一进程至少等待 `TOPIC_LABEL_RETRY_SECONDS` 后再次领取。进程每轮按任务 ID 翻页扫描，避免较早失败任务占满首批结果。可在 `backend` 目录运行 `python3 -m app.topic_label_worker --once` 单轮处理；`start.sh` 在开关为 1 时启动常驻进程，`stop.sh` 与 `status.sh` 同步管理。

T6 标签库保存在 `godp_t6_tag`，选题当前记录及历史记录保存 `t6_tag_id`。服务端先按名称复用已有 T6；其余候选只与**同一向量模型标识、相同维度**的已有 T6 计算余弦相似度，最高值**严格大于 0.80** 时复用该稳定 ID 和已有名称，否则新增标签。标签库比较、关联回写和任务完成在同一数据库事务中执行，并用数据库锁避免并发新增重复标签。这个余弦口径是当前工程实现，后续算法文档确认时可调整。

部署更新后先运行 `cd backend && python3 -m app.init_db`。迁移会按名称给既有已完成的 T6 标签补稳定 ID；由于历史记录没有向量，不会伪造语义向量。模型返回同名 T6 时可为其补入向量；在此之前，这些旧标签只能按名称复用，不能参与相似度比较。T6、选题画像和账号画像调用同一向量适配器及全局向量配置。[选题画像与向量生成](TOPIC_PROFILE_VECTOR.md)、[账号画像及向量准备](ACCOUNT_PROFILE_VECTOR.md)、[正式匹配执行](MATCHING_EXECUTOR.md)及[策划流水线](PLANNING_PIPELINE.md)由各自模块负责。
