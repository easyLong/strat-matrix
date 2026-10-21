# 单账号普通选题正式闭环

本轮实现范围：从同步账号和普通选题开始，经真实豆包打标、共享向量模型、V2匹配、正式结果提交，到本地模拟内容生产、回传和选题使用统计。营销优先及热点T-1生产暂不包含在此验收范围。

## 执行关系

```text
账号/选题增量同步
  → Pipeline创建普通选题准备记录
  → 选题首次打标及T6向量、选题画像向量、账号画像向量
  → 就绪检查及冻结输入
  → V2 Matching Task领取、执行、保存评估
  → 正式批次、槽位、版本、账号画像原子提交
  → 本地模拟内容方持久化受理（生产中）
  → 异步生产及结果回传
  → 槽位已完成 + 使用事实 + 累计次数在同一事务内生效
```

`planning_scope=ordinary_only` 只在本次准备快照中令营销上限和热点占比为0，保留生命周期判定及流量/转化目标；运营全局配置不随验收改变。普通选题也可以承担转化作用。

`planning_workflow_worker` 持续推进已经创建的Pipeline，调用现有租约、模型适配器、向量回写校验和正式提交模块。它不会自行批准策略，也不会自动为所有账号建立周计划。原规则周调度暂未切换到该流程。

## 安装及运行

```bash
cd backend
python -m app.init_workflow_db
python -m app.planning_workflow_worker
```

`init_db` 和 Linux `start.sh` 已包含新增流程迁移；`start.sh/stop.sh/status.sh` 管理新Worker。新增两张内容任务与使用事实表，所有表和字段均有中文注释。

生产模式配置位于 `godp_system_config.CONTENT_PRODUCTION_MODE`：

- `disabled`：默认，未接入内容方时拒绝页面提交。
- `local_mock`：本地模拟内容方，持久化受理后再由Worker处理并回传。任务及前端内容流水均标注“本地模拟”。模拟内容由选题标题/大纲构造，用于验证接口流程，不是正式内容Agent生成的稿件。

```bash
python -m app.system_config set CONTENT_PRODUCTION_MODE --value local_mock
```

模型沿用MySQL中的 `MODEL_NAME`、`EMBEDDING_MODEL_NAME` 和 `ARK_API_KEY`。没有新增环境文件模型配置。

## 创建一次普通策划

在现有受保护接口提交：

```http
POST /api/internal/planning-pipelines
X-Integration-Token: 本地配置的内部密钥
Content-Type: application/json

{
  "cycle_start": "2026-11-09",
  "account_ids": ["ACCOUNT-001"],
  "policy_id": 5,
  "planning_scope": "ordinary_only",
  "production_provider": "local_mock"
}
```

账号和选题须已通过同步接口入库；策略须是已批准且向量模型、维度一致的V2策略。`production_provider=disabled` 时只生成正式策划，随后可由页面发起内容生产。`local_mock` 表示本次Pipeline正式提交后自动请求本地模拟内容方。

查询 `GET /api/internal/planning-pipelines/{id}`，直到 `production_batch_id` 有值。七阶段成功表示正式策划提交完成，内容生产状态单独查询。

## 页面与内容接口

| 入口 | 行为 |
| --- | --- |
| 策划结果 → 账号视图/周期视图 | 自动读取正式批次及槽位，无需另写展示数据 |
| 批次策划详情 → 生成内容 | 调用后端受理接口，不再通过浏览器本地存储伪造状态 |
| 人工策划 → 生成内容 | 同一生产接口；人工结果仍由原有创建流程生成 |
| 查看内容流水 | 查看持久化任务、账号、选题、状态、生产时间及本地模拟内容 |
| `POST /api/batches/{id}/content-production` | 按槽位版本受理，重复提交返回复用；未定题槽位继续等待 |
| `POST /api/internal/slots/{slot_id}/content-ready` | 兼容单槽位入口，复用同一持久化生产队列 |
| `GET /api/batches/{id}/content-production` | 读取持久化请求/响应和执行记录 |
| `POST /api/integrations/content-production-results` | 简化回传接口，仅传 `production_task_id` 和 `status` |
| `POST /api/integrations/topics/usage/query` | 传 `topic_ids` 查询正式使用次数；兼容原计数查询路径 |

简化回传示例：`{"production_task_id":"SLOT-123-v1","status":"completed"}`，返回 `{"success":true}`。失败为 `failed`，同时兼容“已完成”“生产失败”。槽位、版本、选题等由任务记录解析，旧完整回传接口保留。

查询响应提供 `queried_at`、`status`、`topic_results`；每项包括 `topic_id`、`official_use_count`。已同步但尚未成功使用的选题返回0。

## 持久化与恢复

- 任务以槽位ID和结果版本唯一，受理事务提交后才进入生产中。
- 重启可继续读取已受理任务；已领取但未完成的任务在租约到期后重新领取。
- 技术异常按30至600秒退避；真实业务生产失败保持失败状态，不伪装成成功。
- 当前版本首次成功回传，原子写入使用事实和累计次数。重复回传不增加次数，晚到失败不覆盖成功，旧版本不改变当前槽位。
- 计划条数保持原值，内容进度从槽位状态计算；生产进度不改变已完成的策划状态。
- 流程明确失败时通过现有Pipeline重试接口处理；Worker不静默重新批准策略或覆盖冻结快照。

## 可重复验收

```bash
cd backend
python -m app.run_ordinary_workflow_demo --cycle-start 2026-11-09
```

该命令通过增量同步建立明确命名的 `E2E-ORD-ACCOUNT-001` 和6个普通选题，真实调用当前模型准备标签及向量；创建单独的V2验收策略和普通策划Pipeline。不会复制旧账号向量或补造冻结输入。普通候选使用当前可用选题池，因此也可能选中已有选题。

首次验收会注入一次使用事实写入失败，确认回传事务回滚；模拟一次租约过期，确认后台接续；再验证重复提交、重复成功回传和晚到失败。重复执行相同周期会复用已完成批次，回滚及租约注入仅在任务尚未完成时执行。

报告：`backend/artifacts/ordinary-workflow-report.json`。新一轮从零验收请指定另一个未被占用的未来自然周，不删除历史结果。

本地验收记录：Pipeline 1，策略5，准备记录5，匹配任务4，正式批次109，周期2026-11-09至2026-11-15。3条策划全部生产完成，形成3条使用事实；重复通知未增加计数。
