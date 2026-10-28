# 多账号智能策划 · 开发版 V0.4

当前一级页面为 **AI策划配置、人工策划、策划结果**，策划结果提供账号列表和时间列表。最新口径与升级步骤见[近期修改汇总（2026-10-28）](docs/近期修改汇总_2026-10-28.md)，人工流程见[人工策划双流程](docs/人工策划双流程_2026-10-23.md)。内容生成由后台执行，已有正式批次提供“查看内容流水”。[前端调整恢复清单](docs/前端调整恢复清单_2026-10-22.md)和[会话交接](docs/会话交接_2026-10-22.md)保留为历史参考。

历史业务基线为[PRD V1.1 近期口径同步稿](docs/多账号智能策划_PRD_V1.1_近期口径同步稿.md)（2026-10-13；[Word](docs/多账号智能策划_PRD_V1.1_近期口径同步稿.docx)、[PDF预览](docs/多账号智能策划_PRD_V1.1_近期口径同步稿.pdf)），原V1.0正式版保留用于追溯。通用组件遵循 `docs/UI设计规范_后台产品通用版_V1.0.md`。历史实现对照见[PRD V1.1 开发对照](docs/PRD_V1.1_开发对照.md)，文档变更和逐页排版结果见[修订记录](docs/PRD_V1.1_修订记录.md)。这些历史材料尚未全部同步近期页面调整。

周度规则策划的定时调度、手动触发命令和数据准入规则见[周度规则策划首版](docs/ORDINARY_PLANNING.md)。

已实现[单账号普通选题正式闭环](docs/ORDINARY_WORKFLOW.md)：数据同步、真实模型画像与向量、V2匹配、正式策划提交及本地模拟内容生产回传和去重计数。后台Worker由启动脚本管理，已有规则定时调度暂未切换。

本项目作为整体业务页面嵌入客户系统。入口、登录和用户角色由宿主系统负责，本项目不建设独立登录页、运营账号管理或角色权限后台。

## 技术结构

- `frontend/`：Vue 3 + TypeScript + Vite + Vue Router + Pinia。
- `backend/`：Python 3.11 + FastAPI + PyMySQL。
- `backend/schema.sql`：MySQL 建表脚本。所有表使用 `godp_` 前缀、自增 ID 和规定的审计字段；不使用外键、存储过程、函数或视图。

## 启动

数据库连接配置读取根目录 `.env`（兼容旧 `docs/.env`），只保留 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`。MySQL `godp_system_config` 保存前后端监听地址/端口、模型标识和鉴权密钥，说明见[系统配置说明](docs/SYSTEM_CONFIG.md)。

先确认数据库和访问权限，再在项目根目录执行：

```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.init_db
uvicorn app.main:app --reload --port 6930
```

另开终端：

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://localhost:930`，直接进入业务页面。后端未启动或数据库不可用时，页面会显示连接状态。

## 当前能力与边界

- 访问方式：直接进入业务页面；配置、标签、手动策划及替换操作保留审计记录，人工操作统一标记为“运营人员”，自动任务使用 `system`。
- AI策划配置：查看态与编辑态分开，提供内容策划配置、策划规则配置、选题标签和历史配置。生命周期条件按组内且、组外或展示，编辑时直接展开。
- AI 自动策划：周度规则调度与热点 T-1 调度已接入；V2 匹配及单账号普通选题正式闭环已实现，运行需已批准策略、模型配置及相应 Worker。具体边界见[普通选题正式闭环](docs/ORDINARY_WORKFLOW.md)。
- 人工策划：营销为创建任务、单选选题并填写总分配数量、确认策划三步，账号由外部系统后续分配；非营销保留投放日期、账号选择、多选选题和确认四步。任务列表分页，保留“查看策划”入口。
- 策划结果：提供账号列表、时间列表以及账号、周期、批次策划详情；统计去重账号或批次、去重选题和 12 类选题分布。支持明细导出、失败原因查看和失败账号 UM 导出。周期账号数当前按各批次相加，详细口径见近期修改汇总。

可以在 `backend/` 目录运行 `python -m app.seed_demo` 写入演示配置、账号目录、选题目录与策划批次，并为 `DEMO-` 记录补齐选题大纲、内容类型和计划槽位状态，便于验收结果详情、人工替换和调整历史。脚本只处理固定演示前缀，真实业务记录不会被修改。这些记录不代表真实 AI 运行或内容生产结果。

需要较大目录时可运行 `python -m app.seed_large_demo`，幂等生成 100 个 `DEMO-LA` 账号和 600 个 `DEMO-LT` 选题，同时写入认证、粉丝量、选题大纲、内容类型和审核有效资料。

按运营前端原型初始化完整验收数据时运行 `python -m app.seed_prototype`。该脚本会写入原型中的 68 个账号、12 个示例选题、T1–T5 标签体系、5 个自动策划周期（39/40/42/54/60 个账号、117/120/126/146/180 条自动内容）、9/12/18/20/24 条手动策划任务和策划配置。选题二级分类已按 12 个 Agent 名称调整。脚本会软删除并重建演示目录和策划记录，请先确认使用环境。仅展示失败详情时可使用 `python -m app.seed_failure_demo`，建立固定的 18 账号失败演示批次。

已有原型数据需要按当前日期更新自动策划页时，可运行 `python -m app.refresh_auto_demo`：补齐历史策划、本周按 T-1 22:00 保留热点空槽，不提前生成下周批次。备份、时间口径与操作范围见[自动策划展示数据更新](docs/AUTO_PLANNING_DEMO.md)。

## 本地系统对接版

以下同步接口说明属于已有本地实现，历史 IF 编号不作为本次行内对接的最终编号。同库查询与扩展表方案见[同库对接能力定义 V1.16](docs/多账号智能策划_同库对接能力定义_V1.16_评审稿.md)，行内 SQL、实际来源表及营销账号分配仍需联调。营销人工创建接口的最新字段见[人工策划双流程](docs/人工策划双流程_2026-10-23.md)。

运行 `python -m app.init_db` 会补建本地来源数据、内容历史、槽位状态、待投递事件、回传记录及标签表，并将 `backend/schema.sql` 中的中文表说明和字段说明同步到已有表；已有业务记录保留。接口划分及数据归属见 [`docs/接口预留清单_V0.1.md`](docs/接口预留清单_V0.1.md)。

本项目提供下列**跨系统入站接口**，调用方在请求头发送 `X-Integration-Token`。令牌保存于 MySQL `godp_system_config` 的 `INTEGRATION_TOKEN` 配置项，配置查询默认脱敏。

| 路径 | 用途 |
| --- | --- |
| `POST /api/integrations/accounts/sync` | 批量接收账号事实 |
| `POST /api/integrations/topics/sync` | 批量接收选题和审核有效期事实 |
| `POST /api/integrations/marketing-topics/sync` | IF-03 接收带账号绑定的营销选题全量快照 |
| `POST /api/integrations/hotspot-topics/sync` | IF-04 接收热点选题全量快照 |
| `POST /api/integrations/content-history/sync` | 批量接收已发布内容与运营表现 |
| `POST /api/integrations/content-status` | 接收内容生成或发布状态 |
| `GET /api/integrations/accounts/{account_id}/current-plan` | IF-05 按账号查询当前可生产的有效策划结果 |
| `POST /api/integrations/publication-status` | IF-06 校验并回写实际发布状态 |
| `GET /api/integrations/topics/{topic_id}/labels` | IF-08 查询普通选题 T1–T6 标签识别结果 |
| `POST /api/integrations/topics/official-usage/query` | IF-09 批量查询三类选题正式使用次数 |

IF-01、IF-02 及历史内容同步请求均包含 `source_batch_id`、`mode`（`full` 或 `incremental`）和 `records`，每条记录使用稳定业务 ID 和带时区的 `updated_at`。IF-01/IF-02 按 ID 与更新时间更新本地副本；全量模式最多接收 5000 条，成功后停用缺席的正式账号或普通选题；增量模式每批最多 500 条，不处理缺席记录。IF-03、IF-04 有各自独立的全量快照契约。字段完整契约可在 `http://127.0.0.1:6930/docs` 查看。

IF-01 已接收账号别名、人设、粉丝量和近三个月帖子级互动，供生命周期与手动策划流量趋势计算；IF-02 已接收普通选题热度及可用状态。字段映射与计算口径见 [`docs/IF01_IF02_本地对接契约.md`](docs/IF01_IF02_本地对接契约.md)。

IF-05 / IF-06 的请求、返回、选期和一致性校验规则见 [`docs/IF05_IF06_本地对接契约.md`](docs/IF05_IF06_本地对接契约.md)。IF-05 不会锁定结果；IF-06 成功标记已发布后，结果页会显示已发布并禁止替换。

IF-08 / IF-09 的字段、标签状态和独立计数口径见 [`docs/IF08_IF09_本地对接契约.md`](docs/IF08_IF09_本地对接契约.md)。正式使用次数需由独立业务逻辑写入，现有内容生成槽位计数不能替代。

IF-03 营销选题全量同步的字段与空快照口径见 [`docs/IF03_营销选题同步契约.md`](docs/IF03_营销选题同步契约.md)。同步数据作为独立来源事实保存，周度规则策划按账号绑定和审核时间安排营销槽位。

IF-04 热点选题全量同步的字段与空快照口径见 [`docs/IF04_热点选题同步契约.md`](docs/IF04_热点选题同步契约.md)。热点来源数据独立保存；热点调度进程在 T-1 22:00 为待定槽位确定热点选题，候选不足时使用普通最热选题兜底。

本项目前端仍调用 `/api/accounts`、`/api/topics`、`/api/batches` 等**内部前后端接口**。从已同步且可用的账号与选题创建手动批次，会生成 `SLOT_PLAN_CREATED` 待投递事件。项目内的策划工作进程拿到完整 Fit、T1–T7 和 Content Agent Input 后，调用受令牌保护的 `POST /api/internal/slots/{slot_id}/content-ready`，生成 `CONTENT_READY` 事件。内容生产系统再通过状态接口回传 `generated`、`failed` 或 `published`。状态和选题使用次数仅在有效回传后更新；重复 `event_id` 不重复生效。

`GET /api/internal/outbox` 使用同一令牌读取本地事件，目标 `planning` 指向客户内容生产系统，目标 `topics` 指向客户选题库。`PUT /api/tag-taxonomy` 保存 T1–T5 固定标签并生成本地待投递事件；`PUT /api/internal/topic-tags/{topic_id}` 保存单个选题的识别标签，由选题方通过 IF-08 主动查询，不推送标签结果。客户尚未提供接收地址，本地版将待投递事件保存在数据库中供查看和后续投递，不会自动发送。`DEMO-` 演示记录及未通过客户同步接口建立的手工目录记录只保存在本地。

T1–T5 字典的稳定 ID、改名、启停、选题标签 ID 关联和逐版历史见 [`docs/TAG_TAXONOMY.md`](docs/TAG_TAXONOMY.md)。

正式普通选题首次同步会创建内部标签识别任务；可配置的本地识别进程、模型服务 JSON 契约、领取租约、失败重试和结果回写见 [`docs/TOPIC_LABEL_JOBS.md`](docs/TOPIC_LABEL_JOBS.md)。T6 候选会在同一向量模型下按相似度复用已有标签，绑定稳定 ID；旧标签按名称补 ID，历史向量不补造。未配置模型服务时识别进程默认关闭，任务不会自动产出标签。

标签完成后的当前选题画像、内容变化引起的向量失效、可配置的向量执行进程、内部向量回写和 AI 候选准入见 [`docs/TOPIC_PROFILE_VECTOR.md`](docs/TOPIC_PROFILE_VECTOR.md)。具体向量服务地址尚未配置；正式周策划仍运行规则热度兜底。

正式新批次同步冻结账号基本信息、人设、互动明细、阶段与经营目标，保存该批次独立的账号画像及向量准备状态。内部准备任务、共享向量接口、按批次的账号候选查询和账号向量执行进程见 [`docs/ACCOUNT_PROFILE_VECTOR.md`](docs/ACCOUNT_PROFILE_VECTOR.md)。账号画像、选题画像与 T6 标签共用系统配置中的向量模型；执行进程默认关闭，启用后支持常驻处理、失败重试和指定批次单轮处理。旧批次不使用当前来源补造历史画像。

正式 AI 主链准备提供受令牌保护的 `GET /api/internal/matching-readiness?batch_id=123`，以批次账号快照和当前有效选题池检查画像完整性、单位向量、模型与维度兼容性，返回内部阻断原因，不改写现有结果。接口口径见[匹配输入准备检查](docs/MATCHING_PREPARATION.md)；正式算法参数待[算法与策略草稿](docs/ALGORITHM_STRATEGY_V1.0.md)评审确认。

结果生成前的[正式AI输入准备流程](docs/AI_PREPARATION.md)已接入，按独立 `preparation_id` 冻结账号、配置、投放日期和兼容普通选题输入，支持重复请求去重、版本校验、取消释放周期和可配置的后台推进。更新后先运行 `python3 -m app.init_db` 建立三张准备表；模型服务及算法规则确认后再接入评分、分配和结果提交。

[算法策略与匹配任务](docs/MATCHING_EXECUTION.md)已提供不可变策略版本、冻结输入绑定、租约领取/续租、失败重试与提案留痕。当前没有预置算法或匹配执行器，保存提案不会创建运营批次；新版本同样需初始化数据库后重启后端。

第二版任务支持[兜底池、历史与正式计数补充快照](docs/MATCHING_SUPPLEMENTAL_INPUTS.md)，记录来源、窗口和未知状态，并在执行时复核版本；第一版任务指纹保持兼容。当前历史接口尚无完整窗口覆盖证明，不能将未观察到的历史视为真实空历史。

本地版已产生的策划事件为 `SLOT_PLAN_CREATED` 和 `CONTENT_READY`；槽位状态变化及内容 Agent 的实际执行仍需继续接入。周度规则调度和热点 T-1 确定已在项目内部运行，内容生成失败后的再次生产需要创建新版本，本地版会阻止复用同一版本重复提交。

生产部署前应由客户确认系统间鉴权、接收地址、重试和状态字段映射；本地令牌仅用于当前受控开发环境。

本地依赖安装已将文档中的 Vite 6.4.1 更新为 6.4.3，修复同一版本线的已知开发服务器问题。当前开发机尚未安装 Python 3.11；代码曾在已安装的 Python 3.14 下完成导入检查，正式运行环境仍以文档要求的 3.11 为准。

