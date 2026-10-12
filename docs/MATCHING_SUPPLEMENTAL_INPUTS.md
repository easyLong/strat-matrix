# 匹配任务补充输入快照

更新日期：2026-10-12。为普通内容匹配提供基础兜底池、历史选题引用和独立正式使用计数。算法规则仍按[策略说明草稿](ALGORITHM_STRATEGY_V1.0.md)确认，本文只规定事实读取、冻结、未知语义和版本校验。

## 第二版契约与策略选项

第一版策略和任务继续只使用账号、AI选题、配置、日期输入。旧任务迁移后 `contract_version=1`、`supplemental_hash=null`；原有执行输入及策略文档指纹不重新生成。

第二版策略设置 `document.schema_version=2`，在 `required_inputs` 中显式声明所需的 `fallback_topics`、`history`、`official_usage`。四项基础输入仍必须声明。`input_options` 需明确对应选项，不能给未声明的依赖设置选项：

| 选项 | 所属输入 | 取值与含义 |
| --- | --- | --- |
| `fallback_unknown_heat` | `fallback_topics` | `block`阻断未知热度；`allow_unknown`保留未知值交给已确认策略处理 |
| `history_window_days` | `history` | 明确的滚动天数，1–3650；不提供业务默认窗口 |
| `history_completeness` | `history` | `require_complete`要求覆盖证明；`allow_unknown`显式接受覆盖未知 |
| `history_unknown_references` | `history` | `block`阻断缺少选题ID或类型的已观察记录；`allow_unknown`保留未知引用 |
| `official_usage_unknown` | `official_usage` | `block`要求所有相关普通选题都有正式计数；`allow_unknown`保留缺失计数 |

取值 `allow_unknown` 不代表按零或空历史执行。ALG-07/08须进一步说明执行器如何处理这些未知事实，系统不生成对应算法默认值。[第二版草稿模板](examples/matching-policy-v2-draft.json)列出字段但未填写业务规则与选项，只能保存为草稿，不能批准执行。

新任务创建时，根据绑定策略在同一可重复读事务中读取基础输入与补充来源，并一起保存任务、快照和绑定指纹。第二版执行指纹还包含 `supplemental_hash`；快照插入失败会回滚任务创建。每个任务只冻结一次，重复创建和失败重试不会刷新来源。

## 普通兜底池

读取正式、当前启用、可用、非营销、有效期满足且有非空标题的普通选题来源；排除 `DEMO-` 与营销/热点来源。此处为基础来源池，账号×选题的城市、资格和其他组合约束仍由确认后的ALG-02/08执行。

兜底池不要求标签或向量就绪，因此可包含不在AI可匹配池中的普通选题。保存原始来源、标题、来源更新时间、有效期、热度与 `heat_known`，以及当时已有的标签状态、版本和稳定ID。缺失标签、热度或字典引用保持未知，不补标签或角色；未知热度为 `null`，已知零热度仍为0。

第二版提案中 `matched` 只能引用冻结的AI选题池；已声明兜底池时，`fallback` 只能引用该冻结池。没有声明兜底池的任务继续使用原契约的AI池引用限制。引用检查不会替代最高合法热度排序、账号资格或同分规则验收。

## 历史去重事实

仅读取本次准备账号在 `[as_of - history_window_days×24小时, as_of]` 内、已有实际发布时间的历史内容；两个边界都包含。`as_of` 是任务创建读取时点，按UTC保存，所有重试使用相同截止时点。账号画像、生命周期和经营目标继续来自原准备快照，不由这些历史事实重算。

每条记录保存内容ID、账号ID、选题ID、选题类型、发布时间、来源更新时间及原始内容。去重引用必须同时使用类型与ID，不能把相同ID的普通、营销和热点选题混为一类。缺少ID或类型时 `reference_known=false`，对应值为 `null`，不能靠名称或ID外观猜测来源类型。

历史同步的 `HistoryFact` 新增可选 `topic_type`，值为“普通/营销/热点”；不提供时保持未知。旧请求未包含该字段时，写入JSON会省略新字段，保持同版本增量重传兼容。该字段仍通过既有 `/api/integrations/content-history/sync` 输入，没有新增客户同步接口。

当前接口提供逐条记录，未约定账号及时间窗口的完整覆盖证明。快照始终标记 `coverage=unknown`，每账号的 `observed_count` 只表示已观察条数。0条不能证明真实空历史，仅凭请求 `mode` 也不能推出覆盖完整；已有IF-01互动数据不包含可靠选题引用时，不用它补造去重历史。

因此当前 `history_completeness=require_complete` 会以 `history_coverage_unknown` 阻断任务创建。后续客户明确历史窗口覆盖协议后再接入证明，现阶段不会宣称完整历史已同步。

## 正式使用计数

从 `godp_topic_official_usage` 独立读取，类型限定“普通”，范围为冻结AI选题与已声明兜底池的ID并集。保存计数来源名称、来源版本和正式次数，不读取策划分配次数、槽位使用次数或页面演示计数。

已同步的0次记录为 `known=true, official_use_count=0`；缺失记录为 `known=false, official_use_count=null, source_revision=null, source_name=null`。`unknown_count` 单独统计。选题ID在其他来源类型下存在计数不能代替普通计数，已有[内部导入入口](IF08_IF09_本地对接契约.md)仍负责提供这些事实。

## 执行与审计

领取、续租、失败重试及首次提案保存时，校验补充快照本体、摘要、时点和绑定指纹，并复核来源：

- 冻结兜底选题仍在当前有效来源池，来源内容、更新时间、标签和有效期一致；过期、停用或变更会阻断。
- 历史仍按原窗口及账号读取；窗口内的迟到记录、修正或移除会使任务失效。截止时点之后的新帖子不会进入原窗口。
- 正式计数的已知/未知状态、来源名称、版本和数值一致；包括未知变为已知、版本递增但数值不变。

新出现且原来未冻结的兜底选题不会加入旧任务。任何上述变化记录 `invalidated` 和原因码，原快照保留用于审计；新一轮须重新创建准备与任务。校验反映该事务读取时点，正式运营结果提交仍须执行最终并发检查。

`GET /api/internal/matching-tasks/{task_id}/inputs` 使用 `X-Integration-Token`，返回完整基础输入、补充输入和策略，可用于读取已取消/失效任务的原始事实。返回 `source_currentness_checked=false` 表示审计读取，不能据此提交或执行结果。领取响应包含同样的 `inputs.supplemental`，领取时会复核当前来源。

每类事实最多20000条、补充JSON最多5MB；超过限制返回阻断原因，不截断历史或候选。内部快照不新增运营前台的向量、评分或调试信息，也不生成运营批次。

## 迁移与验证

在 `backend` 运行 `python3 -m app.init_db`，新增 `godp_matching_input_snapshot`，并给任务表增加 `contract_version`、`supplemental_hash`。新表、11个字段及两个新增字段均有中文说明。旧任务按第一版保留，不使用当前事实补造历史快照。更新后重启后端，本轮没有新增常驻进程或环境变量。

`python3 -m unittest discover -s tests -v` 验证第一版兼容、未知语义、源类型隔离、历史窗口、兜底池引用、来源变化、快照篡改、原子创建和鉴权，使用内存快照及模拟数据库，不写共享业务数据或调用模型。
