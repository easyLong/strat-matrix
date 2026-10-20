# 算法策略版本与普通匹配执行任务

更新日期：2026-10-20。Matching Task 继续负责不可变策略版本、冻结输入、租约、重试与提案回写；仓库现已提供第一版内置确定性执行器 `builtin-cosine-balanced-v1`。该实现只执行严格的结构化参数契约，不会从 ALG-01 至 ALG-09 的自然语言自动生成算法。详细规则见 [Matching Executor V1](MATCHING_EXECUTOR.md)。

## 策略版本

策略系列由 `policy_key` 标识，创建时须提供当前 `expected_latest_version`，新系列为0；服务端按系列锁和唯一键生成下一版。每个版本保存完整策略文档及SHA256指纹，文档不可原地编辑。更新规则应创建新版本，已有任务继续绑定原版本；新版本不会隐式替换旧任务。

版本状态为 `draft`、`approved`、`disabled`。草稿可保存待定项，批准前必须满足：

- ALG-01至ALG-09九项均有明确规则说明和至少一个非空验收样例。参数作为有限JSON数据保存，整个文档不超过256KB。
- 声明具体 `implementation_key`、向量模型标识、维度以及供应方确认的语义空间标识。相同字符串与维度不能自动证明双侧模型语义空间相同，须在ALG-01明确确认。
- 声明账号、选题、配置、日期四类冻结输入依赖。第一版契约支持四项；第二版已支持基础兜底池、历史和正式使用计数，须明确对应输入选项，详见[补充输入快照](MATCHING_SUPPLEMENTAL_INPUTS.md)。其他未支持的 `required_inputs` 仍会被阻断，未知事实不能按零使用。

批准通过的是文档完整性和操作者的规则确认；服务端不会从自然语言规则自动生成算法，也不能仅凭这些文字证明执行器实现正确。`confirmed_by` 是内部调用提交的确认人记录，不是SSO验证身份。文档中不得放模型地址或凭据。没有默认策略，不会自动创建或批准版本。

通用草稿可复制[策略创建草稿模板](examples/matching-policy-draft.json)。使用内置执行器时可复制 [builtin V1 模板](examples/matching-policy-builtin-v1-template.json)，但模板中的 `vector_space` 仍为空，且参数只是待评审起点；必须补齐真实向量空间并人工批准后才可用于任务。

## 任务绑定与输入校验

任务按[准备记录](AI_PREPARATION.md)的 `preparation_id` 创建，必须指定准备版本及已确认的 `policy_id`。同一准备记录仅有一条任务；相同策略重复请求返回已有任务，不重启或清除执行历史；不同策略版本返回409，需要另建准备记录。

新任务绑定准备版本、准备输入指纹、策略ID、策略指纹，并生成包含契约版本及 `ordinary_only` 范围的执行输入指纹；第二版额外绑定不可变补充事实指纹。创建、领取、续租、失败重试及首次提案回写时，均在同一可重复读事务中校验：

1. 准备仍是 `inputs_frozen`、周期未结束且占用键有效。
2. 完整冻结输入指纹通过，策略文档完整且处于 `approved`。
3. 全部账号/选题向量的模型标识和维度符合绑定策略。
4. 每条冻结选题仍在当前有效普通池中，标签/画像向量就绪，来源内容、更新时间、有效期、标签ID/版本、画像及向量与冻结快照一致。新增其他选题不会改变已绑定输入；已冻结选题任何上述事实变化会阻断任务。

账号仍使用本次准备快照，不因后续IF-01更新重新计算阶段或人设。发现当前输入变化时记录 `invalidated` 及原因码，保留历史，不静默换成最新输入；取消原准备并重新创建可以重新冻结当前数据。

## 租约与执行记录

| 任务状态 | 含义 |
| --- | --- |
| `queued` | 等待内部执行器领取 |
| `processing` | 已领取且持有租约 |
| `evaluated` | 首次完整提案通过协议与输入引用校验并保存 |
| `failed` | 执行器报告系统执行失败，可按版本显式重试 |
| `cancelled` | 人工停止该执行任务；准备记录及周期占用仍保留 |
| `invalidated` | 准备、策略或输入失效，必须重新准备 |

领取发放唯一 `lease_id`，默认300秒，可指定30–3600秒。有效租约不能重复领取；过期后再次领取生成新租约和新尝试序号，旧尝试标记过期。续租只允许当前未过期租约；续租不改变任务状态版本。领取和状态变化增加任务 `version`，失败重试和取消要求当前版本。

每次领取保存独立尝试，保留失败、过期或提案已保存状态及原因码。失败回写只接受 `engine_unavailable`、`execution_failed`、`invalid_response`，不保存模型错误正文。失败重试回到队列，已保存提案不能重试或覆盖。取消执行任务不会释放策划周期，需要另行取消准备记录才能释放。

领取接口一次检查一个候选。即使返回 `job=null`，只要 `next_after_id` 前进，也应继续扫描；遇到无前进的空结果结束本轮。下一轮从0开始，使旧ID任务的租约过期和显式失败重试能再次被读取。内部 Worker 还可以按 `implementation_key` 过滤候选，因此多个实现可以共享任务表而不互相领取。

锁顺序为周期锁→准备记录→策略版本→任务。策略停用或准备取消后，尚未结束任务在下次领取、续租、重试或回写时拒绝执行并留痕。已保存提案保留用于审计；完全相同的成功回写可幂等返回历史结果，即使之后策略已停用，也不会重新执行。

## 内部接口

全部要求 `X-Integration-Token`，属于本项目内部执行能力，客户数据同步接口及四个运营Tab不展示这些策略、评分或任务状态。

| 接口 | 用途 |
| --- | --- |
| `POST /api/internal/matching-policies` | 创建草稿：`policy_key`、`expected_latest_version`、`document` |
| `GET /api/internal/matching-policies?after_id=0&limit=100` | 查询策略版本摘要及未确认项 |
| `GET /api/internal/matching-policies/{policy_id}` | 查询完整策略文档 |
| `POST /api/internal/matching-policies/{policy_id}/approve` | 确认规则：`expected_hash`、`confirmed_by` |
| `POST /api/internal/matching-policies/{policy_id}/disable` | 停用版本，同样使用指纹和操作者 |
| `POST /api/internal/matching-tasks` | 创建任务：`preparation_id`、`expected_preparation_version`、`policy_id` |
| `GET /api/internal/matching-tasks?preparation_id=123&after_id=0&limit=100` | 分页查询任务；准备ID可省略 |
| `GET /api/internal/matching-tasks/{task_id}` | 查询任务与历次执行尝试 |
| `POST /api/internal/matching-tasks/claim` | 领取：`after_id`、`lease_seconds`均可省略 |
| `POST /api/internal/matching-tasks/{task_id}/heartbeat` | 当前租约续期 |
| `PUT /api/internal/matching-tasks/{task_id}/evaluation` | 保存普通内容匹配提案及阶段记录 |
| `PUT /api/internal/matching-tasks/{task_id}/failure` | 回写执行失败原因码 |
| `POST /api/internal/matching-tasks/{task_id}/retry` | 显式重试失败任务：`expected_version` |
| `POST /api/internal/matching-tasks/{task_id}/cancel` | 停止排队或执行：`expected_version` |
| `GET /api/internal/matching-tasks/{task_id}/result` | 校验指纹后读取已保存提案 |
| `GET /api/internal/matching-tasks/{task_id}/inputs` | 校验指纹后审计读取原冻结输入，不代表当前来源仍可执行 |

领取响应包含 `lease_id`、执行 `input_hash`、`policy_hash`、完整冻结输入与绑定的策略文档。续租、失败和提案回写均须原样提交这些身份；错误或过期租约返回409，不能改变另一个合法尝试。

提案回写还须提供匹配的 `implementation_key`，按顺序记录 `hard_gate`、`recall`、`fit`、`global_allocation`、`composition` 五个阶段的 `summary`，以及完整 `positions` 数组。每项位置提供 `account_id`、`publish_date`、`outcome`：

- `matched`：提供冻结选题ID、经营作用“流量/转化”和有限的0–100 Fit分值。
- `fallback`：提供冻结选题ID、经营作用及非空原因，不提供Fit分值。
- `failed`：提供非空原因，不提供选题、经营作用或分值。

提案须恰好覆盖全部冻结账号/日期，不能缺失、重复、增加账号日期或引用对应冻结池以外的选题。匹配引用AI池，第二版声明了兜底池时兜底引用该池；不将尚未准备向量的兜底选题计为匹配成功。完整回写不超过2MB。提案及尝试结束状态在一个事务中保存，完全相同回写幂等，不同回写返回409。租约到期属于可再次领取的执行异常；位置级无合法选题以 `outcome=failed` 记录，二者含义不同。

## 当前范围与下一步

所有任务标明 `evaluation_scope=ordinary_only`、`operations_result_committed=false`、`production_batch_id=null`。提案保存只验证契约、输入版本和引用完整性；使用 `builtin-cosine-balanced-v1` 时，算法本身按 [Matching Executor V1](MATCHING_EXECUTOR.md) 中的固定机器契约执行。其他 `implementation_key` 仍必须由各自执行器实现，服务端不会解释自然语言代替算法。

内置执行器已经能够自动领取并完成绑定自身实现标识的任务，但按日期完整覆盖仍不代表已完成营销/热点槽位组合。它不会创建运营批次、槽位结果或内容生产事件。后续仍需补客户历史覆盖证明/策略口径收敛、完整普通/营销/热点组合以及原子正式结果提交。

## 部署与验证

数据库结构仍由 `python3 -m app.init_db` 维护；本轮没有新增匹配表。Matching Executor 新增可选常驻进程，默认关闭：

```text
MATCHING_EXECUTOR_WORKER_ENABLED=0
MATCHING_EXECUTOR_POLL_SECONDS=10
MATCHING_EXECUTOR_LEASE_SECONDS=1800
```

启用前必须先创建并人工批准真实可执行的策略版本。启动脚本会先运行 `python3 -m app.matching_executor_worker --check-config`，启用后再启动 Worker。

`python3 -m unittest discover -s tests -v` 继续验证原有策略/任务协议；`test_matching_executor.py` 额外验证内置算法的城市/历史 Hard Gate、Recall/Fit、全局分配、未知正式计数、兜底、Composition 与确定性。测试使用固定快照，不连接业务库或外部模型。
