# AI策划配置三工程改造 V0.1

日期：2026-11-02。目标：按行内工程归属迁移配置，不改变运营页面已确认的“查看—编辑—统一保存—历史恢复”交互。

## 配置归属

| 配置 | 归属 | 现状 |
| --- | --- | --- |
| 每周策划日、自动策划调度星期与时间、营销内容周上限、热点选题占比 | Java业务库 | 已新增独立MyBatis读写、版本与恢复接口；页面暂未切换 |
| 滚动统计窗口、生命周期条件、阶段经营目标 | Python算法库 | 仍由原Python综合配置接口保存 |
| T1—T6选题标签字典 | Python算法库 | 仍由原Python标签接口保存 |

当前`StrategyConfig`同时含上述前两行，Python的自动策划准备、排期和画像仍直接读取`godp_strategy_config.operations`。因此不能仅把前端`/config`改指向新Java接口：那会让页面显示值、算法执行值及历史快照分裂。

## 本轮已实现

Java业务库增加`godp_business_planning_config`和`godp_business_planning_config_version`，字段全部有中文注释。`BusinessPlanningConfigMapper.xml`使用宿主可复用的MyBatis；`BusinessPlanningConfigService`要求请求显式提供全部业务字段、验证取值并按版本更新，恢复会创建新版本；并发版本不符返回409。行外入口为：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/plan/business-config` | 读取四项业务配置及版本；尚未迁入时返回409，避免默认值覆盖现有配置 |
| PUT | `/api/plan/business-config?expected_version=N` | 保存四项业务配置，按版本校验 |
| GET | `/api/plan/business-config/versions?limit=N` | 查询业务配置历史 |
| POST | `/api/plan/business-config/versions/{version}/restore?expected_version=N` | 基于历史版本恢复，并生成新版本 |

新接口只用于业务配置的迁移准备。当前Vue仍通过综合`/config`、`/tag-taxonomy`使用原页面流程；不能同时让页面分别调用Java和Python的保存接口。行内发布时由宿主业务库发布SQL，不复制行外自动建表类。

## 综合页面切换所需的下一段工作

1. **冻结旧配置来源**：一次性读取Python当前综合配置及版本，把四项业务字段导入Java配置表，记录原版本和校验值。已发生的旧历史要决定是否继续可查；不能用默认值覆盖现有配置。行外旧页面当前营销周上限为3，而Java代码默认值为1，因此迁移必须显式复制现值。
2. **建立算法配置内部契约**：Python提供按`command_id`幂等的内部更新和读取，只拥有滚动窗口、生命周期、阶段目标和标签。Java更新业务字段后向Python传递用于计算的完整冻结快照；Python保留的四项业务字段仅是计算读模型，不再接受页面直接修改。
3. **Java统一保存命令**：前端仍只发一次“保存配置”给Java。Java把命令持久化为待应用，向Python发送算法部分与业务配置快照；Python确认后Java才发布新的生效版本。失败时命令可重试，页面收到明确状态，不宣称保存成功。恢复历史也走同一命令。
4. **统一历史视图**：Java提供页面需要的综合版本列表与完整快照，同时保存业务版本和Python算法版本的对应关系。旧Python历史在迁移窗口内只读展示；不把单独的业务版本误当成整个页面的历史版本。
5. **切换页面和执行读取**：Vue的`/config`与历史接口改到Java；Python自动策划任务必须按Java发布的冻结配置版本读取计算快照。用一版配置修改验证页面、历史、恢复和下一次周策划结果使用同一个版本。

## 现场替换点和风险

- Java配置模块可迁入：`planning/config/**`、`mapper/BusinessPlanningConfigMapper.xml`、`db/business-planning-config.sql`。宿主MyBatis工厂将Mapper与同库事务管理器显式封装为`BusinessConfigDatabase`；登录人沿用可信UM上下文。
- 行外`standalone/LocalManualBusinessSchema`和`LocalManualBusinessConfiguration`不迁入。当前本地独立Java服务将配置Mapper绑定到`strat_matrix_bus`。
- 跨Java/Python数据库没有分布式事务；统一保存必须用持久化命令、幂等请求和重试收敛。简单的“先存Java再存Python”会制造半成功配置。
- 当前页面“历史配置”属于综合配置历史。两张新Java表只覆盖四项业务字段，不代表页面历史已完成迁移。
