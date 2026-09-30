# 多账号智能策划 · 开发版 V0.4

当前需求基线为 `docs/多账号智能策划_PRD_V2.1_页面型精修评审稿.docx`，四个一级页面为策划配置、AI 自动策划、手动策划、策划结果。通用组件遵循 `docs/UI设计规范_后台产品通用版_V1.0.md`。PRD 仍为评审稿，待确认业务规则和当前落地范围见 [V2.1 开发对照](docs/PRD_V2.1_开发对照.md)。

## 技术结构

- `frontend/`：Vue 3 + TypeScript + Vite + Vue Router + Pinia。
- `backend/`：Python 3.11 + FastAPI + PyMySQL。
- `backend/schema.sql`：MySQL 建表脚本。所有表使用 `godp_` 前缀、自增 ID 和规定的审计字段；不使用外键、存储过程、函数或视图。

## 启动

数据库连接配置读取 `docs/.env`，也可放在项目根目录 `.env` 覆盖。需要 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`。

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

访问 `http://localhost:930`。后端未启动或数据库不可用时，四个页面以只读方式展示，页面顶部会显示连接状态。

## 当前能力与边界

- 策划配置：营销、经营策略分别保存和恢复，模块版本独立追溯；恢复只修改所选模块，保存与恢复校验预期有效配置版本。旧热点固定比例已移除。五阶段目标比例已校验；阶段条件与回退触发规则仍待冻结。
- AI 自动策划：服务端按周汇总自动批次、账号成功与失败数量，展示已记录的失败原因。自动策划调度和匹配引擎仍需业务规则及客户数据接入。
- 手动策划：按规划数量、投放日期、账号筛选、随机抽取、选题选择和确认发起操作。支持多选选题并保存确定分配预览；服务端在预览和提交时复核可用性。流量趋势筛选等待计算规则。
- 策划结果：按周期汇总 AI 参与账号、自动/手动条目、最终内容属性、策划层选题分配次数及 AI 成功/失败账号；“查看详情”展示本周期账号与选题，另有单账号查询。正式选题使用计数仍由内容生成回传维护。

可以在 `backend/` 目录运行 `python -m app.seed_demo` 写入演示配置、账号目录、选题目录与策划批次，并为 `DEMO-` 记录补齐选题大纲、内容类型和计划槽位状态，便于验收结果详情、人工替换和调整历史。脚本只处理固定演示前缀，真实业务记录不会被修改。这些记录不代表真实 AI 运行或内容生产结果。

需要较大目录时可运行 `python -m app.seed_large_demo`，幂等生成 100 个 `DEMO-LA` 账号和 600 个 `DEMO-LT` 选题，同时写入认证、粉丝量、选题大纲、内容类型和审核有效资料。

按运营前端原型初始化完整验收数据时运行 `python -m app.seed_prototype`。该脚本会写入原型中的 68 个账号、8 个示例选题、T1–T5 标签体系、5 个自动策划周期（39/40/42/54/60 个账号、117/120/126/146/180 条自动内容）、9/12/18/20/24 条手动策划任务和策划配置。脚本只软删除并重建 `DEMO-` 演示目录和策划记录，真实业务数据不会被修改。

## 本地系统对接版

运行 `python -m app.init_db` 会补建本地来源数据、内容历史、槽位状态、待投递事件、回传记录及标签表，并将 `backend/schema.sql` 中的中文表说明和字段说明同步到已有表；已有业务记录保留。接口划分及数据归属见 [`docs/接口预留清单_V0.1.md`](docs/接口预留清单_V0.1.md)。

本项目提供下列**跨系统入站接口**，调用方在请求头发送 `X-Integration-Token`。本地开发令牌保存在被 Git 忽略的项目根目录 `.env`，示例键见 `.env.example`。

| 路径 | 用途 |
| --- | --- |
| `POST /api/integrations/accounts/sync` | 批量接收账号事实 |
| `POST /api/integrations/topics/sync` | 批量接收选题和审核有效期事实 |
| `POST /api/integrations/content-history/sync` | 批量接收已发布内容与运营表现 |
| `POST /api/integrations/content-status` | 接收内容生成或发布状态 |

前三个同步请求均包含 `source_batch_id`、`mode`（`full` 或 `incremental`）和 `records`。每条记录必须有稳定业务 ID、带时区的 `updated_at`；服务端按 ID 和更新时间更新本地副本，重复数据可重传，旧版本不会覆盖新版本。`mode=full` 不会因为本批缺少某条记录而自动删除它，停用使用记录中的 `enabled=false`。单批最多 500 条。字段完整契约可在 `http://127.0.0.1:6930/docs` 查看。

本项目前端仍调用 `/api/accounts`、`/api/topics`、`/api/batches` 等**内部前后端接口**。从已同步且可用的账号与选题创建手动批次，会生成 `SLOT_PLAN_CREATED` 待投递事件。项目内的策划工作进程拿到完整 Fit、T1–T7 和 Content Agent Input 后，调用受令牌保护的 `POST /api/internal/slots/{slot_id}/content-ready`，生成 `CONTENT_READY` 事件。内容生产系统再通过状态接口回传 `generated`、`failed` 或 `published`。状态和选题使用次数仅在有效回传后更新；重复 `event_id` 不重复生效。

`GET /api/internal/outbox` 使用同一令牌读取本地事件，目标 `planning` 指向客户内容生产系统，目标 `topics` 指向客户选题库。`PUT /api/tag-taxonomy` 保存 T1–T5 固定标签并生成选题库待投递事件；`PUT /api/internal/topic-tags/{topic_id}` 保存单个选题的识别标签并生成待投递事件。客户尚未提供接收地址，本地版将这些事件保存在数据库中供查看和后续投递，不会自动发送。`DEMO-` 演示记录及未通过客户同步接口建立的手工目录记录只保存在本地。

本地版已产生的策划事件为 `SLOT_PLAN_CREATED` 和 `CONTENT_READY`；槽位状态变化、选题替换带来的 `SLOT_STATUS_CHANGED` 和 `CONTENT_VERSION_CHANGED`、自动策划调度及内容 Agent 的实际执行仍按后续 PRD 接入。内容生成失败后的再次生产也需要创建新版本，本地版会阻止复用同一版本重复提交。

生产部署前应由客户确认系统间鉴权、接收地址、重试和状态字段映射；本地令牌仅用于当前受控开发环境。

本地依赖安装已将文档中的 Vite 6.4.1 更新为 6.4.3，修复同一版本线的已知开发服务器问题。当前开发机尚未安装 Python 3.11；代码曾在已安装的 Python 3.14 下完成导入检查，正式运行环境仍以文档要求的 3.11 为准。

