# Java 子项目驻场替换点清单

当前新增的[上下文、响应及分页扩展](../java-backend/host-integration/REQUEST_CONTEXT_RESPONSES_PAGING.md)将宿主差异进一步集中：可选`HostContextProvider`接可信会话及机构范围，可选`PlanningResponseAdapter`接统一页面返回格式。未提供则保持原Actor和响应，范围未指定不代表ALL。资料分页和营销账号批量关联直接复用；迁入时包含`planning/context`、`PlanningApiErrors`和`PlanningApiResponseAdvice`。内部资料及文件下载排除成功包装；真实机构权限SQL、宿主Advice优先级及Vue拆包约定仍需现场确认。

资料接入已有[BankSourceFacts骨架与查询契约](../java-backend/host-integration/BANK_SOURCE_CONTRACT.md)，[字段映射CSV](../java-backend/host-integration/BANK_SOURCE_FIELD_MAPPING.csv)留空行内表/字段。驻场集中替换`BankSourceQueries`的7个读取方法，或填`bank-source/BankSourceMapper.xml`的10条只读SQL，再注册唯一`SourceFacts`。分页、字段转换、关联和错误校验可直接复用；原始资料会话/事务与策划业务会话/事务分别绑定。没有真实源表时不得启用占位SQL冒充已接入。

现场字段名和编码差异可以只改[映射配置示例](../java-backend/host-integration/BankSourceSiteMapping.java.example)，不用散改业务Service。互动明细可注入`MapperBankSourceQueries`四参数构造器的批量函数，复用分组、归属检查和只读事务。接通后运行[资料只读验收](../testing/README.md#资料适配只读验收)快速发现缺字段、关联错误和分页问题；不新增生产诊断接口。

最新接入准备见[Java宿主接入准备](Java宿主接入准备_2026-11-03.md)和[宿主装配模板](../java-backend/host-integration/README.md)。`PlanningHostConfiguration`已提供完整模块装配；宿主集中绑定六类输入，统一客户端和普通任务推进服务可复用。正式健康/标签入口已退出旧代理依赖；下文V0.1时期的“综合发布尚需实现”“等待历史查询退出”和local类名仅保留历史背景，以最新说明为准。

2026-11-03 增量：以[双库业务迁移与验收](双库业务迁移与验收_2026-11-03.md)为当前状态。宿主还需绑定 `ConfigReleaseMapper`、`PlanningQueryMapper`、`SlotCompletionMapper`、`AlgorithmConfigPort` 和 `PlanningContentPort`，均使用宿主对应的业务数据源与事务管理器；综合页面、正式自动结果、热点/营销业务及历史分页已继续迁移。下面各 V0.1 说明保留原迁移阶段背景。

营销/热点后续更新：宿主需实现`SourceFacts.approvedDemandContents`或相应`PlanningContentPort`过审分配查询，未接入时明确失败；内容状态只读投影。热点Job每天只检查明日空槽，不要求22:00，不扫描过去日期；分页处理至完成。`standalone/LocalDailyHotspotCheck`仅行外模拟，不迁入宿主。完整结果与范围见[增量验收](营销热点与模拟内容衔接验收_2026-11-03.md)。

依据：`D:\向量引擎\平安合作\数字营销技术栈和ui\数字营销技术栈和ui\工程侧技术.md`（文件日期 2026-09-24）与当前 `java-backend/` 代码。本清单区分已经隔离的接入点和仍需现场确认的宿主约束；不能把技术栈清单中的版本推断当成客户工程最终依赖树。

按三个工程迁入的执行顺序和复杂度见[行内三工程迁入执行清单](行内三工程迁入执行清单_V0.1.md)。

AI策划配置由`planning/config`管理综合页面发布，Python维护算法配置的权威版本；宿主接入`AlgorithmConfigPort`和业务配置/发布Mapper。早期设计见[配置改造 V0.1](AI策划配置三工程改造_V0.1.md)。

策划结果已由业务库SQL分页提供；宿主绑定`PlanningQueryMapper`及查询视图，发布存量库V3/V4/V5迁移。早期结构设计见[结果改造 V0.1](策划结果三工程改造_V0.1.md)。

人工营销任务迁移见[营销业务迁移 V0.1](人工营销策划业务迁移_V0.1.md)：同一个`ManualMapper.xml`增加营销任务SQL，新建`godp_manual_marketing_task`。宿主额外提供`ManualPorts.MarketingStatusSource`，只查询内容侧事实；不能把行外空观察实现带入生产。

自动周策划触发迁移见[自动周策划 V0.1](自动周策划触发迁入Java_V0.1.md)：宿主注册 `AutoScheduleMapper` 与 `AutoSchedulePort`，由宿主调度器调用 `AutoScheduleService.tick`。先发布带中文注释的业务任务表，并完成 Java／Python 配置冻结和正式结果迁移，再启用该模块；行外 `LocalJobPulse` 不迁入。

## 1. 可以直接保留的业务代码

`com.stratmatrix.planning.manual` 包内是普通人工策划的业务规则、任务状态、结果读写、换题、内容状态投影和页面接口。代码按 Java 8 编译，不引用行内私有 SDK。`ManualModuleConfiguration` 统一装配业务服务；宿主提供一个 `ManualDatabase` 和 `ManualPorts` 中的资料、计算、身份、过渡业务、普通内容状态、营销状态六类接口实现。业务服务的构造代码不应在客户工程重写。普通人工核心规则可迁入；查询和详情中的历史兼容逻辑需随过渡数据方案一起迁入或替换，不能把整个包当作已完全脱离旧业务。

当前正式业务表位于独立的 `strat_matrix_bus`；Python 计算库为 `strat_matrix`。两个库的同名表由数据库连接隔离，不需要在业务表名上添加语言前缀。

## 2. 需要在客户工程实现或绑定的地方

| 驻场事项 | 当前本地实现／代码位置 | 客户工程替换方式 | 是否已隔离 |
| --- | --- | --- | --- |
| 构建与模块落位 | `java-backend/pom.xml` 使用公开 Spring Boot 2.7.18 Parent；`standalone/PlanningDevelopmentApplication` 独立启动 | 放入客户 Maven 多模块工程，使用 `framework-parent:1.1.1` 和其 BOM；复用客户启动类，不复制本地 Parent、独立启动类和打包配置 | 是 |
| 业务库连接、MyBatis与事务 | `standalone/LocalManualBusinessConfiguration` 用 Hikari和本地MyBatis工厂；业务包使用`ManualMapper`与XML | 在客户既有MyBatis工厂中注册Mapper接口和XML，确保其绑定Venus业务数据源；用该Mapper及同库事务管理器创建`ManualDatabase` Bean。Repository已单独迁移，业务Service无需重写 | 是，需验证Mapper扫描与事务绑定 |
| 业务表发布 | `standalone/LocalManualBusinessSchema` 仅本地启动时运行 SQL | 由客户数据库发布流程执行 `db/manual-business.sql` 和后续迁移脚本；不迁入本地建表类 | 是 |
| 登录人和权限 | 本地从配置取固定操作人 | 用客户可信登录上下文实现 `ManualPorts.Actor`；在 Controller 外接入 UC／EA 权限、数据范围和审计，不信任浏览器传来的 UM 请求头 | 是，具体鉴权待接入 |
| 账号、选题和已策划资格 | `FixtureSourceFacts`在Java读取模拟资料；`OutsideSourceAdapter`只将已取实体交Python派生算法字段 | 实现`SourceFacts`的行内查询，以及`AccountFacts`、`TopicFacts`、`SnapshotFacts`、`HistoricalEligibility`装配；`HostSourceAdapter`组合为`ManualPorts.Source`。可复用资料Controller并适配宿主鉴权，不复制基础资料到策划业务库 | 是，实际SQL待行内表结构 |
| Python 人工计算 | 本地代理调用 `/api/internal/manual-computations` | 用客户认可的内网 HTTP 客户端实现 `ManualPorts.Computer`；保留现有请求编号、冻结输入、受理及结果契约 | 是 |
| 内容状态读取 | `ManualContentStatusService` 依赖 `ManualPorts.ContentStatusSource` | 客户 Java 查询内容侧状态；模块配置自动装配服务，宿主 Job 按游标调用 `reconcile(limit, afterId)`；不让 Python 直接读业务库，也不由策划系统启动内容生产 | 是，来源实现待接入 |
| 旧业务过渡 | 当前已导入历史并启用`business_only`，`ManualNewInstallTransition`关闭旧桥 | 绑定`PlanningReadQueries`查询业务库；宿主有历史时先迁移再关闭旧桥，不使用本地Python转接 | 已退出当前页面历史联合查询 |
| 定时唤醒 | `standalone/LocalJobPulse` 使用本地 `@Scheduled` | 客户Job推进配置发布、人工/自动任务、热点/营销和内容状态，再唤醒Python算法队列；复用现有服务，不迁入本地定时器 | 是，真实宿主调度待接 |
| 页面路由 | `ManualPlanningController` 默认 `/api/plan` | `planning.api-prefix` 可改普通人工 Controller 的类级路径；与客户网关、Vue 请求封装确认最终前缀。旧通配代理固定本地路径，驻场不迁入 | 是，页面子路径和响应字段保持稳定 |
| 配置与密钥 | 本地 `application*.properties`、忽略的 `run/java-backend.properties` | 由客户 Apollo／密钥管理注入数据库、Python 地址和内部鉴权配置；不复制本地配置文件 | 是 |
| 异常与响应 | `ManualPlanningController` 当前输出 HTTP 状态加 `detail`，策划明细支持 XLSX／CSV 下载 | 若宿主必须使用统一响应包装，在客户接入层映射；保持 Vue 现有错误语义及文件下载的原始字节、媒体类型、文件名 | 部分，需联调 |

## 3. 不应复制到客户业务模块的文件

- `com.stratmatrix.standalone/**`：独立启动类、本地 Hikari 装配、本地调度和开发健康检查。
- `com.stratmatrix.planning.adapter.local/**`：模拟文件读取、行外装配及旧业务代理；不迁入宿主。
- `com.stratmatrix.planning.adapter.legacy/**`：旧页面的本地通配转发及配置。
- `src/main/resources/application*.properties`、本地 `pom.xml` 的 Parent／打包配置、`run/`、`logs/`、`.tmp-tools/`。

`com.stratmatrix.planning.adapter.python.PythonExecutionClient` 可以作为内网 HTTP 契约参考；若客户统一要求 ESA、内部 HTTP 客户端或特定链路追踪，替换这一适配器，不改策划业务规则。

## 4. 最小迁入方式

**普通人工模块可迁入**：`planning/manual` 下的业务规则、MyBatis Mapper与XML、Repository、DTO、Controller、`ManualModuleConfiguration`，以及与 Python 的计算请求／结果契约。`ManualQueryService`、`ManualExportService`和`ManualPlanningController`仍会调用`ManualPorts.Transition`获取未迁移的旧业务事实；有历史时须实现该接口或迁移历史数据。明确没有历史策划数据的新安装可显式注册`ManualNewInstallTransition`，它返回空历史列表并对旧ID返回404，不应在有历史数据时启用。客户工程组件扫描范围需包含该包，或显式导入 `ManualModuleConfiguration` 与 `ManualPlanningController`；在 Apollo 置 `planning.manual.enabled=true`。

**只在宿主新写一份接入配置**：声明以下 Bean，并由各自的行内服务实现方法。缺少任何必需 Bean 时应启动失败，不静默回落到本地 Python 或错误数据库。

MyBatis持久化是**单独的迁移项**，本地已经完成到`ManualMapper`接口、`mapper/ManualMapper.xml`和`ManualRepository`。驻场需要先把XML纳入宿主业务库`SqlSessionFactory`的mapperLocations，再绑定Mapper与同库事务管理器。例如在宿主接入配置中：

```java
@Bean
ManualDatabase manualDatabase(SqlSessionTemplate businessSessions,
                              PlatformTransactionManager businessTransactions) {
    return new ManualDatabase(businessSessions.getMapper(ManualMapper.class),
                              businessTransactions);
}
```

多个数据源时应使用宿主实际Bean名加`@Qualifier`，不能依赖默认数据源。`ManualMapper.xml`漏加载、Mapper与事务管理器指向不同库，都必须在联调前发现。此示例只展示绑定，不替代宿主的数据源和MyBatis配置。

| 必需 Bean | 宿主提供的对象 |
| --- | --- |
| `ManualDatabase` | 已绑定业务库的`ManualMapper`与**同一个库**的`PlatformTransactionManager`；Mapper XML必须由该SqlSessionFactory加载 |
| `ManualPorts.Source` | 由 `HostSourceAdapter` 组合四个宿主实现：`AccountFacts`、`TopicFacts`、`SnapshotFacts`、`HistoricalEligibility`；见[业务迁入边界](行内三工程业务迁入边界_V0.2.md) |
| `ManualPorts.Computer` | Java 调 Python 人工分配计算的受理与结果查询 |
| `ManualPorts.Actor` | 当前可信登录人的 UM 号 |
| `ManualPorts.Transition` | 迁移期间旧任务、结果、批次及旧换题的过渡能力；新安装可显式注册`ManualNewInstallTransition` |
| `ManualPorts.ContentStatusSource` | 内容侧状态查询；尚无生产接口时不能伪造成功记录 |
| `ManualPorts.MarketingStatusSource` | 内容侧按营销任务编号查询分配账号数、完成数、失败数及状态时间；由宿主Job触发对账 |

**不修改的地方**：`ManualPlanningService`、`ManualItemService`、`ManualContentStatusService`、`ManualQueryService` 的业务判断与状态更新，以及页面请求／响应字段。若客户统一响应包装或数据库规范强制改动这些类，应先固定差异和回归用例，再做有范围的修改；不能把这种情况算作“只换适配器”。

## 5. 技术栈兼容性判断

| 规范所列 | 当前代码 | 判断 |
| --- | --- | --- |
| Java 1.8、UTF-8 | Java 8 源码，UTF-8 编译 | 可保持 |
| `framework-parent:1.1.1`、`halo-framework-bom:3.4.2` | 行外公开 Spring Boot 2.7.18 Parent | 驻场必须换宿主 Parent；规范只列 Spring Boot 打包插件 2.7.5，不能据此确认实际 Boot 核心版本 |
| Venus 2.0.13、MyBatis-Plus 3.5.7、PageHelper 2.1.0 | 本地 Hikari + MyBatis Mapper | MyBatis为强制约束；Repository已独立迁移，业务SQL集中在`ManualMapper.xml`。驻场需验证与宿主现有MyBatis版本、Mapper扫描、数据源路由和事务管理器兼容；这不是单纯替换接入配置 |
| MySQL Connector 8.0.11 | 本地由公开 Parent 管理的 `mysql-connector-j` | 驻场使用宿主驱动，不把本地驱动版本或坐标带入客户工程 |
| Horae 调度、Apollo 配置 | 本地定时脉冲和 properties | 已限制在独立启动壳；客户适配 Job 和配置中心 |
| Spring MVC、Jackson、Hibernate Validator | 当前 Controller／JSON／校验使用这些通用能力 | 优先复用宿主现有依赖；需核查 Jackson、Validator 实际版本和统一异常包装 |
| Apache POI `poi-ooxml:4.1.2` | 策划明细 XLSX 导出已用 POI；旧 CSV 请求仍可用 | 驻场使用宿主已有 POI，不另引 EasyExcel、poi-tl 或 Spire。流式工作簿使用临时文件并在请求结束时清理，需确认容器临时目录可写 |
| PageHelper 2.1.0 | 当前账号、任务和周期结果要合并迁移期新旧数据后分页 | 暂不对聚合后的列表直接套 PageHelper；待历史查询退出、列表改为单库查询后再使用宿主分页组件 |
| Hutool、Commons、Lombok、Fastjson | 当前代码用 Java 标准库、Jackson 和显式模型 | 不为减少几行代码增加重复工具依赖；必要时再按具体功能复用宿主已有包 |
| UC、EA、ESA、Halo、Venus | 当前没有这些私有依赖 | 驻场只在接入适配层使用，业务包不直接引用 |

## 6. 入场前需要客户确认的最少信息

1. 宿主工程的实际 `dependency:tree`、Java运行版本，以及MVC、Jackson、Validator、MyBatis/MyBatis-Spring的最终版本；清单只给了部分显式版本。
2. Venus 数据源的 Bean 名、事务管理器 Bean 名，业务库发布流程是否允许运行 DDL，以及 `strat_matrix_bus` 在行内的实际库名。
3. 可信登录人、数据权限与审计的接入方法；页面 API 的最终路径和错误包装格式。
4. 账号／选题／已策划资格查询所依赖的实体、字段与 SQL；内容状态的查询方法及字段。
5. Java 调 Python 的统一客户端、鉴权、超时与链路追踪；Horae Job 的触发接口和频率。
6. 历史 Python 业务数据是否迁移、保留过渡窗口多久，决定 `ManualPorts.Transition` 的实现与退出方式。

## 7. 当前已做的代码收口

- 本地 Hikari 装配移到 `standalone/LocalManualBusinessConfiguration`，开发健康检查移到 `standalone/ServiceHealthController`，旧 Python 资料代理移到 `adapter/local/LocalPythonAdapter`；迁入普通人工业务包时不会误带本地基础设施。
- `ManualRepository`已从Spring JDBC迁至MyBatis；接收宿主`ManualMapper`与`PlatformTransactionManager`，所有业务SQL位于`mapper/ManualMapper.xml`。
- `ManualPlanningController` 类级路径支持 `planning.api-prefix` 配置，默认仍为 `/api/plan`，页面接口契约不变。
- `ManualModuleConfiguration` 统一装配 Repository 与六个业务 Service；本地和宿主提供七个输入 Bean，模块内部不重复写装配逻辑。
- 旧业务HTTP路径已从普通人工业务包移至本地`LocalPythonAdapter`；新明细所需账号补全和换题候选已归入`ManualPorts.Source`，`Transition`只保留历史策划兼容语义，驻场无需在业务服务里逐个搜索和修改旧URL。
- `ManualHostWiringTest` 用独立 H2 数据源和宿主提供的接口 Bean 启动原业务模块，验证没有本地 Hikari、旧 Python 代理或模拟调度也能完成装配。

## 8. AI策划业务配置接入

将`planning/config/**`、`mapper/BusinessPlanningConfigMapper.xml`和`db/business-planning-config.sql`迁入宿主；使用业务库MyBatis工厂注册Mapper，并把该Mapper与同库事务管理器封装为`BusinessConfigDatabase` Bean。操作人取宿主可信UM上下文。行外`LocalManualBusinessSchema`和本地配置类不迁入。

四项业务字段的API已实现，综合页面仍需Java统一保存命令、Python算法配置幂等更新及两库版本对应关系后才能切换。当前不可把`/api/plan/business-config`直接替换前端`/config`，其返回不含生命周期、经营目标和滚动窗口。
