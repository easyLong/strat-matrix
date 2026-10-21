# Matching Executor V1

更新日期：2026-10-21。

本页描述仓库内普通内容匹配执行器。V1 对应 `builtin-cosine-balanced-v1`；V2 组合执行器对应 `builtin-cosine-portfolio-v2`。两者消费 Matching Task 的不可变冻结输入和租约，生成并回写完整 `MatchingEvaluation`。它们不会直接创建正式运营策划批次。

## 1. 边界

执行器只做普通内容匹配主链：

`Hard Gate → Recall → Fit → Global Allocation → Composition`

它复用已有 Matching Task 的策略绑定、输入指纹、补充输入快照、租约、失败重试、结果幂等与回写校验，不建立第二套任务表。

执行器**不解释策略中的自然语言**。只有当已批准策略的 `implementation_key`、`schema_version`、`required_inputs` 以及 ALG-01 至 ALG-09 的结构化 `parameters` 与本页契约严格一致时才执行；缺字段、多字段、未知枚举或越界数值都会作为执行契约错误处理。

当前范围仍是 `ordinary_only`。营销选题、热点槽位以及完整运营组合尚未进入 Matching Evaluation，因此 Pipeline 的 `result_commit` 仍保持阻断，执行器完成不等于正式策划结果已提交。

## 2. 输入要求

V1 只支持 Matching Policy `schema_version=2`，并要求冻结以下全部输入：

- `accounts`：账号快照、画像、向量；
- `topics`：AI 普通选题池、画像、向量；
- `config`：冻结运营配置，包含生命周期阶段经营目标；
- `positions`：账号与发布日期蓝图；
- `fallback_topics`：普通选题兜底池与热度事实；
- `history`：冻结历史观察事实；
- `official_usage`：独立正式使用计数事实。

向量模型、维度、语义空间仍由策略版本显式声明，并继续由 Matching Task 在领取和结果回写前检查。

## 3. 固定机器参数契约

策略可修改数值参数，但参数名和枚举语义固定。示例见 `docs/examples/matching-policy-builtin-v1-template.json`。

| 决策 | 参数 | V1 语义 |
| --- | --- | --- |
| ALG-01 | `similarity=cosine_unit_vectors` | 冻结单位向量点积作为余弦相似度 |
| ALG-02 | `city_gate=allow_empty_or_exact` | 适用城市为空则不限，否则账号城市精确命中 |
| ALG-02 | `history_gate=exclude_observed_account_history` | 已观察到该账号使用过的普通选题排除 |
| ALG-03 | `top_k`、`min_cosine` | 相似度阈值后，按相似度降序、topic_id 升序保留 Top-K |
| ALG-04 | `score_scale=positive_cosine_0_100` | `Fit = clamp(cosine, 0, 1) × 100` |
| ALG-05 | `same_account_topic_max` | 同账号正常匹配中单一普通选题最多使用次数 |
| ALG-05 | `global_topic_max` | 正常匹配中全矩阵单一普通选题最多使用次数；`null` 表示不设硬上限 |
| ALG-05 | `global_reuse_penalty` | 本批次已使用次数的排序惩罚 |
| ALG-05 | `official_usage_penalty` | 已知正式使用次数按 `penalty × log1p(count)` 降低排序 |
| ALG-06 | `rounding=half_up` | 生命周期流量槽位数采用四舍五入 |
| ALG-06 | `role_order=even_spread` | 流量/转化角色在账号日期序列中稳定均匀铺开 |
| ALG-07 | `official_usage_unknown_rank=after_known` | 未知正式计数不补零，排在已知计数候选之后 |
| ALG-08 | `fallback_sort=heat_desc_topic_id` | 兜底按已知热度降序、topic_id 升序；未知热度在已知之后 |
| ALG-08 | `fallback_same_account_max` | 同账号同一兜底选题最多使用次数 |
| ALG-09 | `no_candidate=fallback_then_failed` | 正常候选耗尽后兜底，兜底也无结果则槽位 `failed` |
| ALG-09 | `system_error=task_failure` | 系统执行错误进入 Matching Task 失败/重试语义 |

本实现不会为策略缺少的参数填默认值。模板中的数值只是待评审起点，只有被人工批准进不可变策略版本后才生效。

## 4. 阶段算法

### 4.1 Hard Gate

对每个账号与 AI 普通选题形成候选边：

1. 选题 `applicable_cities` 为空时不限城市，否则账号画像中的城市必须精确命中；
2. 冻结历史中，若该账号已明确引用该普通选题，则排除；
3. 未知历史引用不会被猜成某个选题，处理方式由补充输入快照策略在任务创建前决定。

### 4.2 Recall

对通过 Hard Gate 的边计算账号向量与选题向量的点积。低于 `min_cosine` 的边移除，剩余边按：

1. cosine 降序；
2. `topic_id` 升序；

稳定排序，并为每个账号保留最多 `top_k` 条。

### 4.3 Fit

正常召回边的 Fit 为 `clamp(cosine, 0, 1) × 100`。兜底不是 AI Fit 成功，不生成 Fit 分数。

### 4.4 Global Allocation

V1 使用**确定性贪心分配**，不是全局最优化求解器。槽位按 `publish_date`、`account_id` 排序后依次分配。

正常候选首先满足账号内复用上限和可选全局硬上限，再使用以下稳定排序：

1. 正式使用次数是否已知：已知优先，未知在后；
2. 调整分：`Fit - global_reuse_penalty × 当前批次已用次数 - official_usage_penalty × log1p(正式使用次数)`，高分优先；
3. 原始 Fit 高分优先；
4. 当前批次已用次数少者优先；
5. `topic_id` 升序。

因此相同冻结输入、策略版本和实现版本会得到相同输出。未知正式使用次数始终保留“未知”语义，不按 0 次使用处理。

### 4.5 普通选题兜底

账号当前槽位无正常候选时，进入冻结兜底池：

- 仍执行城市约束与已观察历史去重；
- 执行账号内正常复用上限和独立的兜底复用上限；
- 已知热度按降序，热度相同按 `topic_id` 升序；
- 热度未知排在已知热度之后；
- 无合法兜底时，该槽位输出 `failed`，原因 `no_eligible_normal_or_fallback_topic`。

V1 的 `global_topic_max` 是正常 AI 匹配硬约束，不作用于应急兜底池；兜底的跨账号全局硬上限尚未定义。如果业务需要该约束，应创建新的策略/实现版本，而不是改变本实现既有语义。

### 4.6 Composition

按账号冻结的 `lifecycle_stage` 查找冻结配置中的 `stage_targets`：

- 账号流量槽位数 = `round_half_up(账号槽位数 × traffic%)`；
- 其余为转化槽位；
- 角色按账号发布日期序列稳定均匀铺开；
- 匹配和兜底结果绑定相应经营作用；
- 业务失败槽位不伪造经营作用。

这一步仍只是“普通内容提案的经营作用编排”，不是营销/热点完整组合。

## 5. 结果与审计

回写结果包含五个有序阶段摘要以及完整位置数组。Matching Task 服务会再次验证：

- 租约、输入指纹、策略指纹仍一致；
- 冻结输入和补充输入仍满足当前执行约束；
- `implementation_key` 与策略绑定一致；
- 全部账号/日期恰好覆盖一次；
- 正常匹配只能引用冻结 AI 池，兜底只能引用冻结兜底池；
- 已保存提案不可被不同结果覆盖。

Worker 对策略/冻结输入与实现契约不一致回写 `invalid_response`；非预期执行异常回写 `execution_failed`。位置级没有合法选题属于业务结果 `failed`，不是 Worker 系统失败。

## 6. Worker

匹配执行器通过命令手工运行 `python -m app.matching_executor_worker`。Worker 分别领取绑定 V1、V2 实现标识的任务；未知实现标识的任务不会被领取。策略必须先显式创建并批准，V2 不会自动成为默认策略。

单次手工验证：

```bash
cd backend
python3 -m app.matching_executor_worker --check-config
python3 -m app.matching_executor_worker --once
```

## 7. 策略启用步骤

1. 复制 `docs/examples/matching-policy-builtin-v1-template.json`；
2. 填入实际 `vector_space.vector_model`、`dimension`、`semantic_space_id`；
3. 评审 ALG-01 至 ALG-09 的定义、参数和验收样例；
4. 通过现有内部策略接口创建不可变草稿；
5. 人工确认并批准该版本；
6. Pipeline/Matching Task 显式绑定该 `policy_id`；
7. 开启 Matching Executor Worker。

仓库不会自动创建默认策略，也不会自动批准模板。没有已批准且向量空间真实可用的策略时，Executor 不会凭模板自行开始生产匹配。

## 8. V2 组合执行器

V2 使用 `docs/examples/matching-policy-builtin-cosine-portfolio-v2-template.json`。先填写实际 `vector_space` 的模型、维度和语义空间，再通过 `POST /api/internal/matching-policies` 创建草稿；检查返回的 `approval_errors` 为空后，使用 `POST /api/internal/matching-policies/{policy_id}/approve` 批准。V2 沿用 V1 的冻结向量、城市/历史门槛、cosine Fit、生命周期角色和兜底输入，并增加 T2 经营作用硬门槛：槽位为流量/转化时，只召回相同 T2 的普通选题，兜底也应用相同规则。组合分配使用容量约束矩阵、MMR 候选缩减和组合目标局部优化。`portfolio` 参数必须完整写入策略文档并随任务审计；当前复用 V1 的单一 `global_topic_max`/不设上限，以及 `same_account_topic_max`，暂不支持逐选题容量表。

V2 组合审计摘要保存在既有五阶段结果中：`global_allocation` 记录最终分配汇总，`composition` 记录 R/C/B/D、总效用、实际权重、MMR输入/保留/裁剪边数、迭代次数及是否达到局部最优。全局选题容量同时约束普通匹配和兜底选择。创建 Matching Task 时显式传入该 V2 `policy_id`；位置结果仍通过现有提案校验和保存接口。

当前 V2 Fit 仍是冻结账号/选题向量的 cosine 相关性分，不是 T1–T6 多特征 Fit。T3/T4/T5 稳定选题标签用于覆盖度，账号侧 taxonomy 映射仍未冻结，因此不能把本版本描述为完整的账号标签适配方案。后续完整多特征版本必须使用新的 `implementation_key` 或 V3 策略版本，不能在已批准 V2 策略下改写计算口径。Worker 由 `MATCHING_EXECUTOR_WORKER_ENABLED` 控制，默认关闭；策略批准后，在服务器显式启用：

```bash
MATCHING_EXECUTOR_WORKER_ENABLED=1 ./start.sh
MATCHING_EXECUTOR_WORKER_ENABLED=1 ./status.sh
```

启用后 Worker 会同时消费 V1 和 V2 已批准策略的任务。关闭 Worker 执行 `./stop.sh`。

## 9. 仍未解决的下一步

- 当前 V2 Global Allocation 先运行容量约束矩阵分配，再做确定性局部改进；非线性组合目标仍不保证数学全局最优。
- 历史快照当前可表达 `coverage=unknown`；是否必须完整由策略输入选项决定。本实现不会把未知覆盖率解释成“没有历史”。
- 当前任务在执行时校验选题当前有效性，但未来正式发布日期的精确有效期语义仍应在完整结果提交适配器中再次校验。
- 营销/热点完整组合和 `godp_planning_batch` / `godp_planning_item` / `godp_slot_state` 原子提交仍未实现；Pipeline V1 的正式提交闸门继续保留。
