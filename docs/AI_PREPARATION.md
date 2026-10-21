# 正式 AI 策划输入准备流程

更新日期：2026-10-13。依据 PRD V1.1 业务口径同步稿，实现结果生成之前的账号与配置冻结、异步向量准备、普通选题输入冻结。算法规则见[策略评审草稿](ALGORITHM_STRATEGY_V1.0.md)。

## 状态与身份

内部准备使用 `preparation_id`，与运营页面的 `batch_id` 独立。创建准备记录时不写运营批次、策划结果、槽位状态或内容生产事件。

| 状态 | 含义 | 后续操作 |
| --- | --- | --- |
| `waiting_inputs` | 账号向量待生成或失败可重试，或尚无满足冻结条件的普通选题 | 模型进程处理任务后再次推进 |
| `blocked` | 账号快照/画像损坏、数量异常或账号使用多个向量空间 | 排查内部输入；取消并新建可重新读取账号与配置 |
| `inputs_frozen` | 本次账号、配置、投放日期与兼容选题输入已冻结 | 供后续正式匹配读取；再次推进复用输入 |
| `cancelled` | 人工取消准备，保留历史快照 | 释放周期，可重新创建准备记录 |
| `expired` | 策划周期已结束 | 停止向量回写；推进进程释放周期占用 |

`inputs_frozen` 表示输入准备完成。响应中的 `matching_executed=false`、`production_batch_id=null`、`algorithm_policy_configured=false` 描述准备阶段；算法策略改为由独立[匹配执行任务](MATCHING_EXECUTION.md)绑定并查询。评分、分配、营销/热点组合和运营“已规划”状态将在后续规则确认并完整生成结果后接入。

## 创建与冻结规则

- 只能为下周或更晚的自然周新建，默认下周一；按北京时间判断周期，必须从周一开始。
- 默认读取全部正式、启用、有完整人设的同步账号；可指定部分账号进行小批量准备。指定集合中有不可用账号时整个创建失败。
- 创建事务冻结运营配置版本、账号来源、人设、互动明细、指标、经营阶段和经营目标，并保存每个账号的独立画像任务。投放日期依冻结配置的策划日生成，保存星期与日期；尚不分配选题或决定槽位类型。
- 同周期、同账号选择请求复用原记录，即使来源和配置后来改变，也不覆盖冻结数据。省略账号选择与显式传入账号集合视为不同创建范围；不同范围返回 409。
- 准备记录占用正式周期，使用与规则策划相同的 MySQL 周期锁及唯一占用键。已有正式自动策划结果时拒绝创建；准备期间规则调度会等待，不会叠加生成结果。取消后释放周期，规则调度可在下一轮重试。创建准备记录前应明确该周期将走 AI 流程。
- 推进检查每个账号画像与原始冻结快照一致，要求全部账号向量有效、模型和维度一致；同一可重复读事务读取当前普通选题来源、标签及画像向量。
- 冻结所有当前有效、标签与画像版本一致、向量兼容且具有完整 T1–T5 稳定 ID、识别字典版本及 T6 稳定 ID 的普通候选。其他模型或未完成标签的记录不进入冻结池；至少存在一条可冻结选题。此检查尚未执行账号与选题组合的 Hard Gate。
- 选题按条保存来源内容、来源更新时间、有效期、标签名称与稳定 ID/版本、画像指纹、画像和向量。冻结完整输入的 SHA256 指纹；重复推进不重新读取当前选题，也不覆盖已冻结快照。
- 将来正式算法还需绑定已批准的策略版本、按规则冻结历史去重/正式使用计数等依赖，并在结果写入前重新检查选题有效性和版本。当前冻结不代表供应方已证明双侧语义空间相同，或所有账号都有可分配候选。

## 内部接口

均使用 `X-Integration-Token`，属于本项目内部控制及执行接口。

| 接口 | 用途 |
| --- | --- |
| `POST /api/internal/ai-preparations` | 创建准备，JSON：`{"cycle_start":"2026-10-19","account_ids":["ACCOUNT-001"]}`；两个字段均可省略 |
| `GET /api/internal/ai-preparations?after_id=0&limit=100` | 分页查询准备记录摘要 |
| `GET /api/internal/ai-preparations/{preparation_id}` | 查询状态、版本、数量和最近一次检查报告 |
| `POST /api/internal/ai-preparations/{preparation_id}/advance` | 检查并推进，JSON：`{"expected_version":1}` |
| `POST /api/internal/ai-preparations/{preparation_id}/cancel` | 取消并释放周期，JSON：`{"expected_version":1}` |
| `GET /api/internal/ai-preparations/{preparation_id}/inputs?after_id=0&limit=100` | 读取已冻结输入；每页包含完整配置、日期及账号输入，选题按游标分页 |
| `GET /api/internal/preparation-account-vector-jobs?preparation_id=123&after_id=0&limit=100` | 读取该准备记录的待生成/失败账号画像；准备 ID 可省略 |
| `PUT /api/internal/preparation-account-vectors/{preparation_id}/{account_id}` | 按画像指纹回写向量或失败状态 |

推进和取消要求当前 `version`；冲突返回 409，应重新查询。一次等待检查会更新报告、版本和尝试次数；已冻结记录重复推进不修改版本。向量回写不会修改准备记录版本，推进时再读取并检查向量。

冻结输入接口检查完整输入指纹后分页返回；`input_hash` 对应全部输入，不是单页。分页采用 `next_after_id` 和 `has_more`，每页最多 200 条选题。历史已取消/过期记录可读取原冻结输入用于审计；其状态不允许进入执行。摘要不含画像或向量，完整输入仅通过受保护的输入接口提供。

账号向量回写格式与[既有批次向量接口](ACCOUNT_PROFILE_VECTOR.md)相同，使用 `profile_hash`、`status`、`vector_model`、`vector` 或失败 `error`。账号准备指纹包含 `preparation_id` 身份域，不能与相同数字的运营 `batch_id` 混用。首个就绪结果不可覆盖，完全相同回写幂等；取消、过期、画像版本错误或不同就绪结果返回 409。

## 命令与进程

先更新代码，在 `backend` 目录执行 `python3 -m app.init_db`。新增三张表及所有字段均有中文注释：`godp_ai_preparation`、`godp_ai_preparation_account`、`godp_ai_preparation_topic`。

```bash
# 创建小批量准备；省略 --account-id 则选择全部可用正式账号
python3 -m app.ai_preparation create --cycle-start 2026-10-19 --account-id ACCOUNT-001

# 使用创建响应中的 preparation_id 和当前 version
python3 -m app.ai_preparation status --preparation-id 123
python3 -m app.ai_preparation advance --preparation-id 123 --expected-version 1
python3 -m app.ai_preparation cancel --preparation-id 123 --expected-version 2

# 已有账号向量进程也处理准备记录；指定 ID 时只处理这一类任务
python3 -m app.account_vector_worker --once --preparation-id 123

# 推进已有准备记录一轮，或常驻等待并冻结输入
python3 -m app.ai_preparation_worker --once
python3 -m app.ai_preparation_worker
```

以上账号和 ID 为协议示例，需使用实际创建响应。新建准备需要正式同步账号；演示账号不进入任务。

账号向量进程默认轮询准备记录与已有运营批次两种独立队列。两种任务都调用 `/api/internal/embedding-model` 和全局向量模型；准备任务请求携带 `preparation_id`，已有批次请求携带 `batch_id`，二者不会同时出现。画像字段及向量响应格式一致。进程按身份类型、ID、账号、指纹分别记录重试及成功结果缓存，不能跨身份复用。

准备推进进程当前仅支持手工运行，开关和轮询间隔采用代码默认值，尚未加入 `godp_system_config`。启动预检只验证配置，不访问数据库或模型。该进程扫描已创建的等待/阻断准备及已过期冻结记录，不自动创建新周期准备，不调用模型，不运行评分或生成生产结果。选题标签可调用全局文本模型；T6、选题画像和账号画像向量统一调用全局向量模型，不再分别配置模型服务地址。

## 验证

`python3 -m unittest discover -s tests -v` 使用内存输入与模拟数据库/模型响应，覆盖创建幂等、日期与星期、版本冲突、等待与冻结、快照篡改、混合向量空间、缺失标签 ID、取消/过期、事务异常、首个向量结果不可覆盖及执行器身份隔离。验证不会新建共享库的运营批次或发送模型请求。
