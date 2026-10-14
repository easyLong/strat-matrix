# 算法策略版本与普通匹配执行任务

更新日期：2026-10-13。PRD V1.1 业务口径同步稿将算法公式交由后续算法说明确定。本轮先实现不可变策略版本和可重试执行任务，算法仍由[策略草稿](ALGORITHM_STRATEGY_V1.0.md)确认；代码没有预设召回数量、Fit权重或全局分配公式，也没有内置匹配执行器。

## 策略版本

策略系列由 `policy_key` 标识，创建时须提供当前 `expected_latest_version`，新系列为0；服务端按系列锁和唯一键生成下一版。每个版本保存完整策略文档及SHA256指纹，文档不可原地编辑。更新规则应创建新版本，已有任务继续绑定原版本；新版本不会隐式替换旧任务。

版本状态为 `draft`、`approved`、`disabled`。草稿可保存待定项，批准前必须满足：

- ALG-01至ALG-09九项均有明确规则说明和至少一个非空验收样例。参数作为有限JSON数据保存，整个文档不超过256KB。
- 声明具体 `implementation_key`、向量模型标识、维度以及供应方确认的语义空间标识。相同字符串与维度不能自动证明双侧模型语义空间相同，须在ALG-01明确确认。
- 声明账号、选题、配置、日期四类冻结输入依赖。第一版仅支持四项；第二版已支持基础兜底池、历史和正式使用计数，须明确对应输入选项，详见[补充输入快照](MATCHING_SUPPLEMENTAL_INPUTS.md)。其他未支持的 `required_inputs` 仍会被阻断，未知事实不能按零使用。

批准通过的是文档完整性和操作者的规则确认；服务端不会从自然语言规则自动生成算法，也不能仅凭这些文字证明执行器实现正确。`confirmed_by` 是内部调用提交的确认人记录，不是SSO验证身份。文档中不得放模型地址或凭据。没有默认策略，不会自动创建或批准版本。

可复制[策略创建草稿模板](examples/matching-policy-draft.json)，补齐规则后再提交。模板中的实现标识为待定、向量空间为空、规则为空，只能作为草稿，不能批准或创建执行任务。

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

领取接口一次检查一个候选。即使返回 `job=null`，只要 `next_after_id` 前进，也应继续扫描；遇到无前进的空结果结束本轮。下一轮从0开始，使旧ID任务的租约过期和显式失败重试能再次被读取。

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

所有任务标明 `evaluation_scope=ordinary_only`、`operations_result_committed=false`、`production_batch_id=null`。提案保存只验证契约、输入版本和引用完整性，不证明算法符合每条业务规则；按日期完整覆盖也不代表已完成营销/热点槽位组合。它不会创建运营批次、槽位结果或内容生产事件。

准备摘要继续描述画像与输入准备阶段；已绑定策略和执行状态以匹配任务接口为准。第二版已独立冻结基础兜底池、历史去重事实与独立正式计数，并明确未知状态；这些事实及引用检查不替代账号组合合法性、兜底排序、完整历史覆盖或算法验收。后续需实现与 `implementation_key` 对应的算法执行器及算法验收、客户历史覆盖证明、普通/营销/热点组合和原子结果提交。真实执行器未接入前，不会自动领取或调用模型。

## 部署与验证

在 `backend` 运行 `python3 -m app.init_db` 建立 `godp_matching_policy`、`godp_matching_task`、`godp_matching_attempt`，三张表及所有字段包含中文说明。更新后重启后端；本轮没有新增常驻进程或 `.env` 模型配置。

`python3 -m unittest discover -s tests -v` 用固定快照、模拟数据库和ASGI请求验证策略版本/完整性、待定项阻断、任务去重、输入改变、模型不兼容、领取/续租/过期、旧租约、失败重试、提案覆盖与幂等，以及所有新接口的令牌保护；不会连接业务库或调用真实执行器。
