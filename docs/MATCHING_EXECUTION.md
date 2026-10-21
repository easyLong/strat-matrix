# 算法策略版本与普通匹配执行任务

更新日期：2026-10-21。Matching Task 负责不可变策略版本、冻结输入、租约、重试与普通选题提案回写；仓库提供确定性 V1 执行器 `builtin-cosine-balanced-v1` 和组合优化 V2 执行器 `builtin-cosine-portfolio-v2`。执行器只运行结构化参数契约，不会从 ALG-01 至 ALG-09 的自然语言自动生成算法。详细规则见 [Matching Executor](MATCHING_EXECUTOR.md)。

## 策略版本

策略系列由 `policy_key` 标识，创建时须提供当前 `expected_latest_version`，新系列为0；服务端按系列锁和唯一键生成下一版。每个版本保存完整策略文档及SHA256指纹，文档不可原地编辑。更新规则应创建新版本，已有任务继续绑定原版本；新版本不会隐式替换旧任务。

版本状态为 `draft`、`approved`、`disabled`。草稿可保存待定项，批准前必须满足：

- ALG-01至ALG-09九项均有明确规则说明和至少一个非空验收样例。参数作为有限JSON数据保存，整个文档不超过256KB。
- 声明具体 `implementation_key`、向量模型标识、维度以及供应方确认的语义空间标识。相同字符串与维度不能自动证明双侧模型语义空间相同，须在ALG-01明确确认。
- 声明账号、选题、配置、日期四类冻结输入依赖。第二版支持基础兜底池、历史和正式使用计数，须明确对应输入选项，详见[补充输入快照](MATCHING_SUPPLEMENTAL_INPUTS.md)。其他未支持的 `required_inputs` 仍会被阻断，未知事实不能按零使用。

批准通过的是文档完整性和操作者的规则确认；服务端不会从自然语言规则自动生成算法。对 `builtin-cosine-balanced-v1` 会校验其精确机器参数；对 `builtin-cosine-portfolio-v2` 还会要求完整组合参数、权重和为 1，并校验复用、召回和兜底配置。`confirmed_by` 是内部调用提交的确认人记录，不是SSO验证身份。文档中不得放模型地址或凭据。没有默认策略，不会自动创建或批准版本。

通用草稿可复制[策略创建草稿模板](examples/matching-policy-draft.json)。使用内置执行器时可复制 [builtin V1 模板](examples/matching-policy-builtin-v1-template.json)，但模板中的 `vector_space` 为空，必须补齐真实向量空间并人工批准后才可用于任务。

## 任务绑定与输入校验

任务按[准备记录](AI_PREPARATION.md)的 `preparation_id` 创建，必须指定准备版本及已确认的 `policy_id`。同一准备记录仅有一条任务；相同策略重复请求返回已有任务，不重启或清除执行历史；不同策略版本返回409，需要另建准备记录。

新任务绑定准备版本、准备输入指纹、策略ID、策略指纹，并生成包含契约版本及 `ordinary_only` 范围的执行输入指纹；第二版额外绑定不可变补充事实指纹。创建、领取、续租、失败重试及首次提案回写时，均校验：

1. 准备仍是 `inputs_frozen`、周期未结束且占用键有效。
2. 完整冻结输入指纹通过，策略文档完整且处于 `approved`。
3. 全部账号/选题向量的模型标识和维度符合绑定策略。
4. 每条冻结选题仍在当前有效普通池中，标签/画像向量就绪，来源内容、更新时间、有效期、标签ID/版本、画像及向量与冻结快照一致。

账号使用本次准备快照，不因后续IF-01更新重新计算阶段或人设。发现当前输入变化时任务记录 `invalidated`，不静默换成最新输入。

## 租约与执行记录

| 任务状态 | 含义 |
| --- | --- |
| `queued` | 等待内部执行器领取 |
| `processing` | 已领取且持有租约 |
| `evaluated` | 首次完整普通选题提案通过协议与输入引用校验并保存 |
| `failed` | 执行器报告系统执行失败，可按版本显式重试 |
| `cancelled` | 人工停止该执行任务 |
| `invalidated` | 准备、策略或输入失效，必须重新准备 |

领取发放唯一 `lease_id`，有效租约不能重复领取；过期后再次领取生成新租约和新尝试序号。内部 Worker 可按 `implementation_key` 过滤候选，因此多个实现可以共享任务表而不互相领取。

每次领取保存独立尝试，保留失败、过期或提案已保存状态及原因码。已保存提案不能被不同结果覆盖。策略停用或准备取消后，尚未结束任务在下一次执行动作时拒绝继续；已保存提案保留审计。

## 内部接口

全部要求 `X-Integration-Token`。

| 接口 | 用途 |
| --- | --- |
| `POST /api/internal/matching-policies` | 创建策略草稿 |
| `GET /api/internal/matching-policies` | 查询策略版本摘要及未确认项 |
| `GET /api/internal/matching-policies/{policy_id}` | 查询完整策略文档 |
| `POST /api/internal/matching-policies/{policy_id}/approve` | 确认策略 |
| `POST /api/internal/matching-policies/{policy_id}/disable` | 停用策略 |
| `POST /api/internal/matching-tasks` | 创建任务 |
| `GET /api/internal/matching-tasks` | 查询任务 |
| `GET /api/internal/matching-tasks/{task_id}` | 查询任务与尝试历史 |
| `POST /api/internal/matching-tasks/claim` | 领取任务 |
| `POST /api/internal/matching-tasks/{task_id}/heartbeat` | 当前租约续期 |
| `PUT /api/internal/matching-tasks/{task_id}/evaluation` | 保存普通内容匹配提案及阶段记录 |
| `PUT /api/internal/matching-tasks/{task_id}/failure` | 回写执行失败原因码 |
| `POST /api/internal/matching-tasks/{task_id}/retry` | 显式重试失败任务 |
| `POST /api/internal/matching-tasks/{task_id}/cancel` | 停止排队或执行 |
| `GET /api/internal/matching-tasks/{task_id}/result` | 读取已保存提案 |
| `GET /api/internal/matching-tasks/{task_id}/inputs` | 审计读取原冻结输入 |

领取响应包含 `lease_id`、执行 `input_hash`、`policy_hash`、完整冻结输入与绑定策略文档。续租、失败和提案回写均须提交这些身份。

提案回写提供匹配的 `implementation_key`，按顺序记录 `hard_gate`、`recall`、`fit`、`global_allocation`、`composition` 五个阶段摘要，以及完整 `positions`：

- `matched`：冻结选题ID、经营作用“流量/转化”和0–100 Fit分值；
- `fallback`：冻结普通兜底ID、经营作用和非空原因，不提供Fit分值；
- `failed`：非空原因，不提供选题、经营作用或分值。

提案须恰好覆盖全部冻结账号/日期，不能缺失、重复、增加账号日期或引用对应冻结池之外的选题。位置级 `failed` 是业务无合法选题，不等同于执行器系统失败。

## 与正式策划结果的关系

Matching Task 仍保持 `evaluation_scope=ordinary_only`。`evaluated` 只表示不可变的普通选题提案已经保存，并不把任务状态改造成运营批次状态。

Planning Pipeline 的 `result_commit` 现在负责下游组合和提交：

1. 再次复核 Preparation、策略、Matching 绑定、当前普通选题和补充输入；
2. 拒绝任何包含位置级 `failed` 的提案；
3. 在不改变 Matching Composition 流量/转化数量的前提下叠加营销优先槽和热点占位；
4. 一次事务写 `godp_planning_batch`、`godp_planning_item`、`godp_slot_state`、`godp_auto_plan_run` 及正式批次账号画像；
5. 同事务写回 `godp_matching_task.production_batch_id`、`operations_committed_at` 和 Pipeline 的 `production_batch_id`。

因此 Matching 状态仍然是 `evaluated`，而 `operations_result_committed` / `production_batch_id` 作为独立下游关系返回。这样不会把“算法提案完成”和“完整运营组合已提交”混成一个状态。

完整组合规则和原子事务边界见 [Planning Pipeline V1](PLANNING_PIPELINE.md)。内容生产事件仍不由 Matching Task 创建。

## 部署与验证

基础结构继续由：

```bash
cd backend
python3 -m app.init_db
python3 -m app.init_pipeline_db
python3 -m app.init_result_commit_db
```

维护。最后一步为已有 Matching Task 表增加正式批次关系字段，并更新 `godp_auto_plan_run.plan_mode` 说明以包含 `ai_matching`。

Matching Executor Worker 默认关闭，轮询和租约参数暂用代码默认值，尚未登记为运营配置。服务器完成策略审批后，可通过 `MATCHING_EXECUTOR_WORKER_ENABLED=1 ./start.sh` 显式开启 V1/V2 Worker。

启用前必须创建并人工批准真实可执行策略版本。代码不会自动猜测生产向量模型、维度或 `semantic_space_id`。

测试使用固定快照和模拟数据库时不连接业务库或外部模型；真实生产启用前仍应在目标数据库执行一次从 Preparation → Matching → result_commit 的端到端验证。
