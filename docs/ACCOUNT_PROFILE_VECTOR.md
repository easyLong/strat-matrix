# 批次账号画像与向量准备

依据《多账号智能策划_PRD_V1.0.docx》：账号画像、生命周期和向量必须使用本轮策划读取的同一份账号数据快照，不允许沿用其他批次的账号向量。

## 批次冻结

正式周度规则策划及普通内容兜底命令创建新批次时，使用同一数据库事务保存批次、槽位、运行输入和 `godp_account_profile`。事务采用可重复读，账号来源与兼容的历史互动读取保持一致。画像唯一键为 `batch_id + account_id`，不会通过查询最新 IF-01 数据修改已有批次。

冻结数据包括：

- 账号原始同步事实、来源更新时间、完整人设、账号基本信息及营销资格。
- 本次读取的近三个月帖子明细、统一的指标计算时点及滚动篇数。
- 同一批次计算出的有效内容数、滚动篇均互动数、流量趋势和生命周期阶段。
- 同一批次配置版本下该阶段的流量、转化目标百分比。

IF-01 的 `interaction_data` 优先；显式空数组表示没有帖子，不读取旧历史补齐。未提供该字段的旧同步协议仍使用本次读取的独立历史内容，记录 `interaction_source=legacy_content_history`。三个互动计数为红星、收藏和评论。明细和指标使用同一个三个月时间窗口，不包含未来帖子。

新建账号画像的向量状态为 `pending`，成功回写为 `ready`，失败为 `failed`。画像指纹 `profile_hash` 包含批次身份、配置版本和冻结输入；即使账号没有更新，新批次也有独立的准备记录。已有批次重跑返回原批次，不重新生成画像或覆盖就绪向量。规则批次的“已规划”状态与内部向量准备状态独立。

`python -m app.init_db` 补建画像表并同步中文注释。迁移不会用当前账号信息补造历史画像；旧批次及 `DEMO-` 演示批次不自动创建准备任务。可查询其既有策划结果，画像接口返回 404。

## 内部接口

全部使用 `X-Integration-Token`，属于本项目内部任务接口，不是客户账号系统接口。

| 接口 | 用途 |
| --- | --- |
| `GET /api/internal/account-profiles/{batch_id}/{account_id}` | 查询指定批次账号状态、来源版本、配置版本和画像指纹。快照完整性不匹配时为 `stale`。 |
| `GET /api/internal/account-vector-jobs?batch_id=123&limit=100&after_id=0` | 读取当前及未来周期的待生成或失败待重试画像；`batch_id` 可省略。每项包含批次、账号、指纹和画像。 |
| `PUT /api/internal/account-vectors/{batch_id}/{account_id}` | 回写指定批次账号的向量或失败原因。 |
| `GET /api/internal/ai-account-candidates?batch_id=123&limit=100&after_id=0` | 只查询该批次已就绪账号，返回冻结画像、单位向量和模型标识。不会读取账号当前来源或其他批次的向量。 |

分页使用响应中的 `next_after_id`，即使一页因快照完整性校验而过滤为空，也应继续按游标读取。每页最多 200 条。任务与候选只包括北京时间当天仍未结束的正式自动策划周期；历史画像状态可以单独查询，已结束周期不再接受向量回写。

成功回写示例：

```json
{
  "profile_hash": "任务接口返回的64位小写SHA256指纹",
  "status": "ready",
  "vector_model": "your-shared-embedding-model-version",
  "vector": [0.12, 0.34, 0.56]
}
```

数字仅展示协议格式。服务端校验模型标识、有限数值和非零向量，支持 1–4096 维，并保存单位向量。失败回写提交 `profile_hash`、`status="failed"`、`error`，不提交向量和模型标识。

其他批次的指纹、损坏的冻结输入或已结束的周期返回 409。首次就绪后，完全相同的向量和模型回写幂等返回；不同向量、不同模型或退回失败返回 409。失败可重新生成。任务没有领取租约，多个执行器可能重复计算，由回写接口锁定记录保证首个就绪结果不被覆盖。

## 配置账号向量执行进程

执行器 `python3 -m app.account_vector_worker` 按批次读取冻结画像，调用项目约定的模型服务 JSON 接口，并回写该批次的向量。它不会查询最新账号来源，不会复用其他批次的账号向量。模型地址未配置时默认关闭，不自动生成向量。

在项目根目录 `.env` 配置：

```dotenv
ACCOUNT_VECTOR_WORKER_ENABLED=1
ACCOUNT_VECTOR_MODEL_URL=https://your-trusted-model-service.example/account-embedding
ACCOUNT_VECTOR_MODEL_TOKEN=your-model-service-token
ACCOUNT_VECTOR_MODEL_TIMEOUT_SECONDS=120
ACCOUNT_VECTOR_POLL_SECONDS=30
ACCOUNT_VECTOR_RETRY_SECONDS=600
```

`INTEGRATION_TOKEN` 用于调用后端内部接口，必须配置。`ACCOUNT_VECTOR_MODEL_TOKEN` 可留空，非空时向模型服务发送 `Authorization: Bearer <token>`。后端接口默认使用 `http://127.0.0.1:<BACKEND_PORT>`；跨主机部署时另外设置 `ACCOUNT_VECTOR_API_URL`。

| 配置 | 默认值 | 范围或用途 |
| --- | --- | --- |
| `ACCOUNT_VECTOR_WORKER_ENABLED` | `0` | Linux 脚本设为 `1` 时启动常驻进程 |
| `ACCOUNT_VECTOR_MODEL_URL` | 空 | 完整的模型服务 HTTP(S) 地址 |
| `ACCOUNT_VECTOR_API_URL` | 本机后端地址 | 后端基础地址，不带 `/api` |
| `ACCOUNT_VECTOR_MODEL_TIMEOUT_SECONDS` | `120` | 模型请求超时，1–600 秒 |
| `ACCOUNT_VECTOR_POLL_SECONDS` | `30` | 队列扫描间隔，5–3600 秒 |
| `ACCOUNT_VECTOR_RETRY_SECONDS` | `600` | 同一批次、账号和画像指纹的重试间隔，60–86400 秒 |

模型服务接收 JSON `POST`：

```json
{
  "task": "account_profile_embedding",
  "batch_id": 123,
  "account_id": "ACCOUNT-001",
  "profile_hash": "任务接口返回的64位小写SHA256指纹",
  "config_version": 3,
  "profile": {
    "schema_version": 1,
    "account": {"account_id": "ACCOUNT-001", "account_name": "示例账号", "persona": "本地生活分享", "city": "杭州"},
    "interaction": {"valid_content_count": 12, "rolling_interaction_count": 80, "traffic_trend": "平稳"},
    "lifecycle_stage": "流量增长期",
    "business_goal": {"traffic": 70, "conversion": 30}
  }
}
```

上例画像字段为节选；执行器原样发送任务接口返回的完整 `profile`，其中包含冻结的基本信息、互动时间窗口与帖子明细。模型响应：

```json
{"vector_model": "your-shared-embedding-model-version", "vector": [0.12, 0.34, 0.56]}
```

执行器先校验响应中的模型标识和向量，再交给后端按画像指纹保存单位向量。模型请求失败或返回无效向量时，回写 `failed`。如果模型成功、后端回写暂时失败，则在当前进程内保留该向量，等待重试回写，不将回写异常标记为模型失败。缓存不写磁盘，进程重启后可能重新调用模型。后端返回 404/409 时丢弃本次结果；已经就绪的记录不会被覆盖。

每轮分页扫描所有待处理任务，包括被过滤为空但游标仍推进的页面。重试间隔按 `batch_id + account_id + profile_hash` 记录，一个批次的失败不会阻止同账号其他批次生成向量。失败不会停止整轮其余任务。

可在 `backend` 目录使用以下命令：

```bash
# 仅检查配置；不读取任务、不调用模型
python3 -m app.account_vector_worker --check-config

# 处理一轮全部任务
python3 -m app.account_vector_worker --once

# 只处理指定批次的一轮任务
python3 -m app.account_vector_worker --once --batch-id 123
```

配置无效返回退出码 2；单轮全部任务处理正常或无任务返回 0，发生模型、队列读取或回写错误返回 1。Linux `start.sh` 在启动服务前检查已启用进程的配置，`stop.sh` 和 `status.sh` 管理该进程；PID 保存到 `run/account-vector-worker.pid`，日志写入 `logs/account-vector-worker.log`。日志不记录令牌、完整 URL、账号画像或模型响应正文。

## 当前开发边界

批次画像冻结、准备接口和可配置执行进程已完成。具体模型服务地址仍需提供，并须遵循上述项目 JSON 契约；这些配置不是直接调用某个厂商 SDK 的参数。账号和选题向量用于后续匹配前，还须核对模型标识、维度和向量空间一致性，不能直接比较不同模型的向量。

正式周策划继续采用规则热度兜底，尚未使用账号候选执行 Recall、Fit 或全局分配。向量准备不重新分配已产生的规则策划结果，也不自动投递内容生产任务。下一步实现匹配所需的向量一致性检查、正式匹配与降级分支。
