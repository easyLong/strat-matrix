# Planning Pipeline V1

更新日期：2026-10-20。

## 目标

Planning Pipeline V1 统一正式智能策划的运行生命周期，复用现有数据同步、AI Preparation、Matching Task、正式策划结果表和热点 T-1 调度，不复制第二套执行栈。

同一次正式策划拥有稳定 `pipeline_id`，能够看到当前阶段、并行准备状态、后端执行引用和失败原因；可以安全推进、重试和取消。Matching 提案通过完整组合校验后，Pipeline 会将普通、营销和热点占位一次性原子提交为正式策划结果；只有正式结果事务成功后，`result_commit` 和 Pipeline 才进入 `succeeded`。

内容生产仍属于正式策划之后的下游流程，不并入本 Pipeline。

## 阶段图

```text
source_ingestion
  ├─> topic_profile ─┐
  └─> account_profile ─┤
                       └─> single_account_matching
                            -> matrix_allocation
                            -> composition
                            -> result_commit
```

| stage_key | 中文含义 | 后端映射 |
| --- | --- | --- |
| `source_ingestion` | 数据源接入 | 以当前已同步本地正式数据能否创建 AI Preparation 作为数据可用性门槛 |
| `topic_profile` | 选题打标与画像 | AI Preparation 对普通选题标签、画像、向量就绪度的检查与冻结 |
| `account_profile` | 账号画像 | AI Preparation 独立账号画像及向量任务 |
| `single_account_matching` | 单账号选题匹配 | Matching Task 的 `hard_gate`、`recall`、`fit` 执行记录 |
| `matrix_allocation` | 全账号矩阵分配 | 同一个 Matching Task 的 `global_allocation` 执行记录 |
| `composition` | 选题组合编排 | 同一个 Matching Task 的 `composition` 执行记录及冻结经营作用 |
| `result_commit` | 结果校验与正式提交 | 普通匹配提案叠加营销优先和热点占位，原子写入正式批次、槽位及状态 |

`topic_profile` 与 `account_profile` 是并行依赖。API 返回 `active_stages`；数据库 `current_stage` 仅保存当前依赖前沿的第一个稳定标识，便于索引与简表展示。

## 4-6 阶段与 Matching Task

现有 `MatchingEvaluation` 必须一次性提交按顺序排列的 `hard_gate`、`recall`、`fit`、`global_allocation`、`composition` 五段记录，并一次校验完整账号/日期覆盖。Pipeline 不复制租约、输入指纹、策略绑定与审计机制，因此 4-6 仍是同一 Matching Task 的业务阶段投影：

- `queued`：单账号匹配等待执行器，后两段保持 `pending`；
- `processing`：单账号匹配为 `running`；
- `failed` / `invalidated`：单账号匹配为 `failed`；
- `evaluated`：读取已校验提案，把匹配、矩阵分配、组合三个阶段标记为 `succeeded`，再进入正式提交。

如果以后需要“全局分配单独失败后只重跑全局分配”，应升级 Matching 执行契约，而不是让 Pipeline 表伪造独立执行能力。

## 正式结果组合规则

Matching Task 只负责普通选题提案。`result_commit` 在同一事务中复核冻结输入、策略和 MatchingEvaluation，然后增加运营层组合：

1. **普通槽位**：使用 MatchingEvaluation 的 `matched` 或 `fallback` 普通选题；任何位置级 `failed` 都阻断正式提交，不能把不完整周计划写成成功。
2. **热点占位**：按冻结配置的 `hotspot_ratio` 和稳定随机种子确定占位位置。热点槽保留 Matching Composition 已计算的“流量/转化”经营作用，同时把该位置原普通匹配结果冻结为 T-1 热点不足时的兜底。
3. **营销优先**：沿用 IF-03 账号绑定、审核、有效期和 `marketing_max` 规则。为避免破坏已经审计的经营作用结构，营销只占用非热点且 Composition 已标记为“转化”的位置；合法营销不足时，该营销优先槽回落到该位置的 Matching 普通选题。
4. **角色不漂移**：叠加营销/热点后，最终流量/转化数量必须与 Matching `composition` 阶段的实际数量完全一致，否则提交失败。

热点真正选题仍由现有 T-1 Hotspot Scheduler 决定。对于 `ai_matching` 批次：有合法热点时填热点但保持该槽原经营作用；热点不足时使用正式提交时冻结的该槽普通兜底，不重新读取“当前热度最高普通选题”。

## 原子提交边界

`result_commit` 成功事务一次性写入或更新：

- `godp_planning_batch`：正式 `AUTO-AI-YYYYMMDD` 自动策划批次；
- `godp_planning_item`：全部账号/日期槽位；
- `godp_slot_state`：每个正式槽位的初始版本；
- `godp_auto_plan_run`：`plan_mode=ai_matching` 的输入/组合审计快照；
- `godp_account_profile`：与正式批次绑定的冻结账号画像；
- `godp_matching_task.production_batch_id` / `operations_committed_at`：普通匹配提案到正式结果的下游关系；
- `godp_planning_stage_run.result_commit`：成功状态和批次摘要；
- `godp_planning_pipeline_run.production_batch_id`：正式批次引用并将 Pipeline 标为 `succeeded`。

任何一项失败，整个正式结果事务回滚，不留下半个批次。营销快照不可用、Matching 槽位失败、冻结输入失效、正式批次冲突等业务问题会记录为可重试的 `result_commit=failed`；重试只重新执行正式提交校验，不重跑已经不可变保存的 MatchingEvaluation。

## 状态机

Pipeline 与 Stage 共用：`pending`、`running`、`waiting`、`succeeded`、`failed`、`cancelled`。

- `pending`：依赖尚未满足；
- `running`：后端正在执行；
- `waiting`：等待 Worker 或后端异步输入；
- `succeeded`：有可审计完成证据；
- `failed`：当前后端或业务校验明确阻断，可修复后显式重试；
- `cancelled`：Pipeline 取消后尚未成功的阶段终止。

Pipeline 总状态从阶段状态派生，正式批次成功写入后才会全部 `succeeded`。

## 数据表

Pipeline 自身使用 `backend/pipeline_schema.sql`：

- `godp_planning_pipeline_run`：周期、账号选择指纹、策略版本、乐观锁版本、AI Preparation / Matching Task / 正式批次引用和当前错误；
- `godp_planning_stage_run`：七个稳定阶段的状态、尝试次数、后端引用、审计摘要、等待/失败原因和起止时间。

不增加外键，跨模块使用逻辑 ID。`reservation_key` 保证同一正式周期只有一个活动 Pipeline；取消后可释放并重建。

正式提交额外为 `godp_matching_task` 增加下游关系字段，不改变 Matching Task 的提案状态语义：Matching 仍以 `evaluated` 表示不可变普通提案已保存，是否已进入正式运营结果由 `production_batch_id` 单独表达。

## 内部 API

全部位于 `/api/internal/`，继续使用 `X-Integration-Token`。

| 接口 | 用途 |
| --- | --- |
| `POST /api/internal/planning-pipelines` | 创建周期 Pipeline；指定 `policy_id`，可选周期与账号范围 |
| `GET /api/internal/planning-pipelines` | 分页查询 Pipeline 摘要和七阶段状态 |
| `GET /api/internal/planning-pipelines/{pipeline_id}` | 查询运行、依赖前沿、后端引用与错误 |
| `POST /api/internal/planning-pipelines/{pipeline_id}/advance` | 推进/对账一次；当 Matching 已 evaluated 时同一次控制调用继续尝试正式提交 |
| `POST /api/internal/planning-pipelines/{pipeline_id}/retry` | 对当前可恢复失败重试；若仅 `result_commit` 失败，不重跑 Matching |
| `POST /api/internal/planning-pipelines/{pipeline_id}/cancel` | 取消尚未正式提交的 Pipeline |

所有变更接口继续使用 Pipeline `expected_version`。AI Preparation 和 Matching Task 使用各自版本、周期锁、输入指纹和租约规则。

## 推进语义

一次 `advance` 最多完成以下连续对账：

1. 创建或复用 AI Preparation；
2. 推进双侧画像/向量就绪并冻结输入；
3. 创建或复用 Matching Task；
4. 投影 Matching Task 状态到 4-6 阶段；
5. Matching `evaluated` 后执行完整普通/营销/热点组合校验；
6. 通过后原子写正式结果并将 `result_commit`、Pipeline 标为 `succeeded`。

Matching Worker 仍是异步的，因此调用方通常需要在 `queued/processing` 后再次 `advance` 或通过后续 Pipeline Worker 周期对账。

## 取消与重试

取消时：

- `queued` / `processing` / `failed` 的 Matching Task 走现有 `cancel_task`；已 `evaluated` 的提案保留审计；
- 活动 AI Preparation 走现有 `cancel_preparation`；
- Pipeline 释放 `reservation_key`；已成功阶段保留，其他阶段标记 `cancelled`；
- 一旦 `production_batch_id` 已存在，禁止取消 Pipeline。

重试时：

- Preparation `blocked` 可重新 readiness；
- Matching Task `failed` 走现有 `retry_task`；
- 只有 `result_commit` 失败时，直接重新做正式提交前校验与事务，不重跑 MatchingEvaluation。

## 部署

先应用现有主 schema和 Pipeline schema，再安装正式提交元数据：

```bash
cd backend
python3 -m app.init_db
python3 -m app.init_pipeline_db
python3 -m app.init_result_commit_db
```

`init_result_commit_db` 为已有 `godp_matching_task` 增加 `production_batch_id`、`operations_committed_at` 和索引，并更新 `godp_auto_plan_run.plan_mode` 的字段说明以包含 `ai_matching`。

部署后仍需存在一个**真实、已人工批准且向量语义空间与生产账号/选题一致**的 Matching Policy；代码不会自动猜测或批准生产向量空间。

## 当前边界

Pipeline 现在可以从输入准备推进到正式策划结果提交，但以下仍是独立下游或后续增强：

- 内容生产 IF-05 / OP-02 不属于本 Pipeline；
- T-1 热点实际选题仍由 Hotspot Scheduler 处理；
- Global Allocation V1 仍是当前 Matching Executor 定义的确定性贪心算法，不宣称数学全局最优；
- 若产品要求 Matching 4-6 独立恢复，需要升级 Matching execution protocol，而不是增加假的 Pipeline 状态。
