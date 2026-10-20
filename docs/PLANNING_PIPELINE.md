# Planning Pipeline V1

更新日期：2026-10-20。

## 目标

Planning Pipeline V1 先统一正式智能策划的运行生命周期，不在本轮实现新的匹配公式。它复用现有数据同步、AI Preparation、Matching Task 与后续策划结果表，解决“各模块都存在，但没有统一运行ID、阶段状态、重试/取消/恢复入口”的问题。

V1 的成功标准是：同一次正式策划拥有稳定 `pipeline_id`，能够看到当前阶段、并行准备状态、后端执行引用和失败原因；可以安全地推进、重试和取消；不会因为骨架尚未完成而把模拟或不完整匹配结果写成正式运营结果。

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

| stage_key | 中文含义 | V1 后端映射 |
| --- | --- | --- |
| `source_ingestion` | 数据源接入 | 不主动调用客户系统；以当前已同步本地正式数据能否创建 AI Preparation 作为本轮数据可用性门槛 |
| `topic_profile` | 选题打标与画像 | 复用 AI Preparation 对普通选题标签、画像、向量就绪度的检查与冻结 |
| `account_profile` | 账号画像 | 复用 AI Preparation 独立账号画像及向量任务 |
| `single_account_matching` | 单账号选题匹配 | 复用 Matching Task 的 `hard_gate`、`recall`、`fit` 执行记录 |
| `matrix_allocation` | 全账号矩阵分配 | 复用同一个 Matching Task 的 `global_allocation` 执行记录 |
| `composition` | 选题组合编排 | 复用同一个 Matching Task 的 `composition` 执行记录 |
| `result_commit` | 结果校验与正式提交 | V1 明确保持 `waiting`，不写 `godp_planning_batch` / `godp_planning_item` / `godp_slot_state` |

`topic_profile` 与 `account_profile` 是并行依赖。API 返回 `active_stages`，因此不会用一个单值“当前阶段”掩盖并行状态；数据库中的 `current_stage` 仅保存当前依赖前沿的第一个稳定标识，便于索引与简表展示。

## 为什么 4-6 暂时不能独立重试

现有 Matching Task 的一个 `MatchingEvaluation` 必须一次性提交按顺序排列的 `hard_gate`、`recall`、`fit`、`global_allocation`、`composition` 五段记录，并一次性校验完整账号/日期覆盖。V1 不复制这套租约、输入指纹、策略绑定与审计机制。

因此 Pipeline 把 4-6 展示成三个业务阶段，但它们在 V1 是**同一 Matching Task 的阶段投影**：

- `queued`：单账号匹配等待真实执行器，后两段保持 `pending`；
- `processing`：单账号匹配为 `running`；
- `failed` / `invalidated`：单账号匹配为 `failed`，走现有 Matching Task retry/重新准备语义；
- `evaluated`：读取已校验提案，把单账号匹配、全局分配、组合三个业务阶段同时标记为 `succeeded`，并保存各自对应的执行摘要。

等后续确实需要“全局分配单独失败后只重跑全局分配”时，应升级 Matching 执行契约或新增真正的 stage-level execution protocol，而不是让 Pipeline 表伪造独立执行能力。

## 状态机

Pipeline 与 Stage 共用状态集合：`pending`、`running`、`waiting`、`succeeded`、`failed`、`cancelled`。

- `pending`：依赖尚未满足或尚未启动；
- `running`：后端正在执行；
- `waiting`：已启动但等待外部 Worker、真实匹配执行器或尚未实现的正式提交适配器；
- `succeeded`：该阶段已有可审计完成证据；
- `failed`：当前后端状态明确阻断，可修复后显式重试；
- `cancelled`：Pipeline 取消后尚未成功的阶段终止。

Pipeline 总状态从阶段状态派生：任一阶段失败为 `failed`；否则存在运行阶段为 `running`；否则存在等待阶段为 `waiting`；全部成功才是 `succeeded`。V1 因 `result_commit` 尚未实现，真实匹配提案完成后会停在 `waiting`，不会伪装成完整正式策划成功。

## 数据表

新增 `backend/pipeline_schema.sql`：

- `godp_planning_pipeline_run`：一次正式策划 Pipeline 的周期、账号选择指纹、策略版本、乐观锁版本、AI Preparation / Matching Task / 正式批次引用和当前错误；
- `godp_planning_stage_run`：七个稳定阶段的状态、尝试次数、后端引用、审计摘要、等待/失败原因和起止时间。

不增加外键，保持与现有 schema 一致；跨模块关系使用逻辑 ID。`reservation_key` 保证同一正式周期只有一个活动 Pipeline；取消后置空，可重新创建。相同周期、相同账号范围、相同策略的重复创建返回原记录，不重复启动。

## 内部 API

全部位于 `/api/internal/`，继续使用现有 `X-Integration-Token` 保护。

| 接口 | 用途 |
| --- | --- |
| `POST /api/internal/planning-pipelines` | 创建周期 Pipeline；指定 `policy_id`，可选 `cycle_start` 与账号范围 |
| `GET /api/internal/planning-pipelines` | 分页查询 Pipeline 摘要和七阶段状态 |
| `GET /api/internal/planning-pipelines/{pipeline_id}` | 查询单次运行、依赖前沿、后端引用与错误 |
| `POST /api/internal/planning-pipelines/{pipeline_id}/advance` | 用 `expected_version` 推进/对账一次；可创建或复用 AI Preparation、创建或复用 Matching Task |
| `POST /api/internal/planning-pipelines/{pipeline_id}/retry` | 对当前可恢复失败执行一次受控重试；不会绕过正式提交缺口 |
| `POST /api/internal/planning-pipelines/{pipeline_id}/cancel` | 取消未正式提交的 Pipeline，并按现有规则取消可取消 Matching Task / AI Preparation |

所有变更接口使用 Pipeline `expected_version`，避免两个控制端同时推进后静默覆盖状态。AI Preparation 和 Matching Task 继续使用它们自己的版本、周期锁、输入指纹和租约规则。

## 推进语义

`advance` 是一次**幂等对账**，不是常驻 Worker：

1. 若还没有 AI Preparation，使用当前已经同步到本地库的正式数据创建或复用准备记录；成功后 `source_ingestion=succeeded`。
2. 对 `waiting_inputs` 的 Preparation 执行一次现有 readiness 推进；`inputs_frozen` 时双侧准备阶段成功，`waiting_inputs` 时等待，`blocked` 时失败。
3. 输入冻结后，按 Pipeline 绑定的 `policy_id` 创建或复用 Matching Task。
4. 读取 Matching Task 状态并投影到 4-6 阶段。
5. 匹配提案 `evaluated` 后，`result_commit` 固定进入 `waiting/result_commit_not_implemented`。

后续可以单独增加 Pipeline Worker 周期性调用 `advance`；本轮不新增常驻进程，避免在尚未确认调度频率、并发上限和正式提交协议前引入第二套调度机制。

## 取消与重试

取消时：

- 尚在 `queued` / `processing` / `failed` 的 Matching Task 走现有 `cancel_task`；已 `evaluated` 的提案保留审计，不伪删；
- 活动 AI Preparation 走现有 `cancel_preparation`，释放原周期占用；
- Pipeline 自己释放 `reservation_key`；已成功阶段保留，其他阶段标记 `cancelled`。

重试时：

- `blocked` 的 Preparation 可重新执行 readiness；
- `failed` 的 Matching Task 走现有 `retry_task`；
- `result_commit_not_implemented` 明确拒绝重试成“成功”，防止调用方绕过完整组合与原子提交设计。

## 部署

先执行现有主 schema，再安装 Pipeline V1 两张表：

```bash
cd backend
python3 -m app.init_db
python3 -m app.init_pipeline_db
```

然后重启后端。V1 没有新增环境变量、模型地址或常驻 Worker。

## 下一版边界

V1 合并后，下一步不是继续加 Pipeline 表，而是补齐两个真实执行边界：

1. 与 `implementation_key` 对应的真实匹配执行器；如果产品要求 4-6 独立恢复，再升级 Matching Task 契约；
2. 完整普通/营销/热点选题组合校验后，将最终提案原子提交为 `godp_planning_batch`、`godp_planning_item`、`godp_slot_state`，成功后再把 `result_commit` 与 Pipeline 标为 `succeeded`。

内容生产仍属于正式策划结果之后的下游流程，不并入本 Pipeline。
