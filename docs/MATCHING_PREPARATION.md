# 正式 AI 匹配输入准备检查

更新日期：2026-10-12。依据正式 PRD V1.0 的双侧画像准备要求，提供本项目内部的只读检查。算法规则评审见[算法与策略说明草稿](ALGORITHM_STRATEGY_V1.0.md)。

## 接口

`GET /api/internal/matching-readiness?batch_id=123`，请求头使用 `X-Integration-Token`。

检查对象为正式自动策划批次及其 `godp_auto_plan_run` 运行快照。演示批次、手动批次或没有正式运行快照的批次返回 404；同一批次存在重复运行快照返回 409；数据库或必需表不可用返回脱敏后的 503。合法请求即使输入被阻断，仍返回 HTTP 200 的诊断报告。

整个报告使用同一数据库可重复读事务和统一 UTC 检查时点；周期是否结束按北京时间判断。接口不更新批次、槽位、画像、向量或事件，不读取模型凭据，不调用模型。

## 检查口径

- **账号**：以运行记录中被冻结的账号集合为准，数量须与运行记录及批次一致。画像须属于同一批次和配置版本，并与原始批次账号快照、画像文本及指纹一致。后续 IF-01 更新不会改变本报告的账号输入，也不使用最新来源补造旧批次。
- **选题**：检查当前正式普通选题来源池中的已启用、当前有效记录。使用当前 T1–T6 标签和当前内容画像，标签版本、画像文本与指纹均须一致。未完成标签、失效画像或失败向量不会成为 AI 就绪候选。
- **向量**：检查模型标识、1–4096 维有限非零数值，以及已经保存的单位向量。不能在诊断过程中通过重新归一化掩盖损坏数据。
- **兼容性**：所有本批次账号须就绪，且使用同一模型标识和维度。选题可以包含其他模型版本，仅统计与该批次账号兼容的有效就绪选题；至少存在 1 条兼容选题，才满足输入准备条件。

报告的 `topic_input_scope=current_eligible_pool` 明确表示当前选题池，尚未冻结为本批次的正式匹配输入。账号范围为 `account_input_scope=batch_snapshot`。报告是检查时点的结果，未来正式匹配必须重新校验并冻结输入；不能拿旧报告直接提交分配结果。

## 返回字段

| 字段 | 用途 |
| --- | --- |
| `status` / `inputs_ready` | `ready/true` 表示本报告检查的输入条件满足；否则为 `blocked/false`。 |
| `matching_executed` | 本接口恒为 `false`，输入就绪不代表完成 Recall、Fit 或分配。 |
| `checked_at` | 带 UTC 时区的检查时点。 |
| `vector_space` | 当前已就绪账号的唯一模型标识及维度；存在多个账号向量空间时为空。部分账号待准备时，该字段可能存在，但输入仍会被阻断。 |
| `accounts.expected` / `accounts.counts` | 冻结账号总数及各准备状态的数量。 |
| `topics.inspected` / `topics.counts` | 当前有效来源池的检查数量及各准备状态数量。 |
| `topics.compatible_ready` / `incompatible_ready` | 兼容或不兼容的已就绪选题数量；账号没有唯一已知向量空间时兼容性无法确认，两者返回 0。 |
| `*.vector_spaces` | 已就绪记录按模型及维度统计的数量。 |
| `*.samples` | 每个非就绪状态最多 10 个业务 ID，用于定位；不返回原始画像、向量或失败正文。 |
| `blocking_reasons` | 机器可读原因码和中文摘要，可以同时存在多个原因。 |

账号状态包含 `ready`、`missing`、`incomplete_snapshot`、`pending`、`failed`、`stale`、`invalid_vector`。选题额外包含 `awaiting_labels`、`label_failed`、`unavailable`，不包含账号专用的 `incomplete_snapshot`。`counts` 中各状态均返回数量，未出现的状态为 0。

常见原因码：

| 原因码 | 处理方向 |
| --- | --- |
| `batch_expired` | 查询仍有效的策划周期。 |
| `invalid_config_snapshot` / `invalid_account_snapshot` | 排查运行记录及冻结数据；不能用当前配置或来源覆盖历史输入。 |
| `no_batch_accounts` / `account_count_mismatch` / `unexpected_account_profiles` | 排查参与账号与画像集合完整性。 |
| `account_inputs_not_ready` | 按账号状态检查是否缺失完整快照、待生成向量、生成失败、版本错误或数据损坏。 |
| `mixed_account_vector_spaces` | 检查账号向量服务的统一模型配置；已有就绪向量不支持直接覆盖。 |
| `no_ready_topics` | 完成普通选题标签和当前画像向量准备。 |
| `no_compatible_topics` | 对齐双侧向量服务的模型标识、版本和维度。 |

其他模型的选题被排除不必阻断整个输入检查，只要还有兼容候选。未完成标签的其他选题也不要求全部等待。这里不规定召回数量、Hard Gate 组合约束、Fit 权重、全局复用限制或目标取整规则，因此不能保证每个账号都有合法候选或全局分配有解。

## 部署与验证

本轮没有新增数据库表，复用账号画像、选题画像和运行快照表。若尚未部署账号画像版本，先按[部署说明](DEPLOYMENT.md)运行 `python3 -m app.init_db`。旧批次缺少完整账号快照时，报告会以 `incomplete_snapshot` 阻断；不会自动回填。

在 `backend` 目录运行 `python3 -m unittest discover -s tests -v` 验证准备检查。测试使用固定日期、内存快照和模拟数据库，不连接共享业务数据库或模型服务。

现有 `AUTO-RULE-*` / `AUTO-REG-*` 仍是规则兜底结果。报告 `ready` 后也不会改写这些结果、发起内容生产或改变页面状态。结果生成前的独立[AI准备流程](AI_PREPARATION.md)已接入，按 `preparation_id` 冻结选题输入；本文接口继续按现有运营 `batch_id` 只读诊断。算法策略版本、评分、分配和结果提交在规则明确后接入。
