# Java 业务后端子项目

已完成五模块拆分和`xiangliang`供应商隔离。聚合坐标为`com.pab.aitmp.aiis:godp-planning-parent:0.1.0-SNAPSHOT`；生产包位于`com.pab.aitmp.aiis.godp.digital.marketing`下各层的`xiangliang`目录。行外使用公开依赖构建，行内Parent/BOM及SDK由宿主提供。具体目录、Bean绑定及源码导出见[供应商并入说明](host-integration/MAVEN_MODULES.md)。

已补齐14表实体、业务Mapper类型化、声明式事务边界、页面请求对象、运行配置端口、四类Handler及人工任务持久化领取。页面业务已统一POST，旧GET/PUT兼容路由删除；健康检查保留GET。响应字段、SQL视图分页及POI默认实现保持现有业务契约。

| 模块 | 职责 | 直接项目依赖 |
| --- | --- | --- |
| `godp-planning-entity` | 现有请求、返回对象、配置行对象、上下文与基础异常 | 无 |
| `godp-planning-api` | 资料、计算、内容、查询、身份与响应适配契约 | entity |
| `godp-planning-client` | 统一Python HTTP客户端及各算法能力客户端 | api |
| `godp-planning-services` | 人工/自动/配置/内容/查询/资料/任务业务、Mapper与SQL | api、client |
| `godp-planning-server` | Controller、Web适配、宿主装配；dev下包含本地启动壳 | services、client |

14张正式业务表已按[六公共字段规范](../docs/表结构公共字段规范与升级_2026-11-05.md)更新。新增[DBA发布包V9](godp-planning-services/src/main/resources/db/release/20261107-v9/README.md)：新库安装、V8→V9升级、初始化核查、保留数据的兼容回退及索引检查分别交付。旧库须先完成V6/V7/V8，发布V9字段和查询视图后再部署新版；应用不执行升级DDL。审计UM上限50字符，记录可信请求身份；账号占用采用逻辑释放与复用。

三侧共同进场适配以[功能流程清单](../docs/三工程驻场功能流程适配清单_V1.0_2026-11-03.md)及[Excel跟踪表](../docs/三工程驻场功能流程适配清单_V1.0_2026-11-03.xlsx)为当前核查入口，明确资料SQL、权限、内容方、正式OP及宿主调度的真实待接边界。

当前行内合入入口见[宿主装配模板](host-integration/README.md)：六类宿主绑定、统一Python客户端、正式健康/标签接口、普通任务推进服务及关闭行外组件的三页面验收。完整变更见[接入准备](../docs/Java宿主接入准备_2026-11-03.md)。

行内资料适配已提供[BankSourceFacts查询契约](host-integration/BANK_SOURCE_CONTRACT.md)和[字段映射表](host-integration/BANK_SOURCE_FIELD_MAPPING.csv)：7项能力、可选MyBatis读取实现、显式SQL占位及合成适配测试。真实SQL/Service与权限仍需宿主实现；当前outside资料链路保持原装配。

请求身份、异常/响应和分页读取已进一步集中，见[宿主扩展说明](host-integration/REQUEST_CONTEXT_RESPONSES_PAGING.md)。可选绑定`HostContextProvider`与`PlanningResponseAdapter`，默认保持原Actor及前端协议。请求上下文在api/entity中，API Advice在server中；内部资料和下载不套页面响应壳。

环境名称统一为`outside`／`inside`：前者复用本地开发装配，后者排除本地数据源、代理与调度，要求宿主提供必要Bean。库内`PLANNING_ENV`由本地启动器映射到profile；宿主按实际工程合并inside配置片段。见[双环境切换](../docs/双环境切换_V0.1.md)。

行外使用公开Spring Boot 2.7.18 BOM，Java8源码／运行兼容；根POM不继承Boot启动工程，无内部Parent、Halo、Venus、用户中心或调度SDK。该版本是兼容开发基线，生产补丁最终随客户维护线确定。持久化使用MyBatis核心库与mybatis-spring，已退出mybatis-spring-boot-starter依赖；HikariCP和MySQL驱动只在server的Maven dev profile中，H2仅用于dev测试。当前业务状态见[双库迁移与验收](../docs/双库业务迁移与验收_2026-11-03.md)。

## 独立开发

安装JDK8及Maven后，在本目录运行：

```bash
mvn -Pdev verify
java -jar godp-planning-server/target/planning-business.jar --spring.profiles.active=dev
```

可先`mvn -Pdev -DskipTests package`构建。可执行包在`godp-planning-server/target/planning-business.jar`，旧根`target`不再是新代码的构建产物。不提供数据库配置时仅启动开发壳；完整业务需要两侧服务与数据库。

- Java默认：`127.0.0.1:6931`。
- 自身存活：`GET /api/plan/service-health`，不检测Python或数据库。
- 旧业务健康：`GET /api/plan/health`，由Python实际检查数据库。
- 本地默认Spring profile：`dev`，通过profile组启用`local`；`outside`别名仍可用，业务环境名称仍为`outside/inside`，算法地址默认Python `127.0.0.1:6930`。
- 本地`LocalJobPulse`模拟宿主调度，向Python内部接口发送执行信号；缺少内部令牌时明确记录未就绪，不使用匿名降级。
- 其他profile默认不装配旧业务适配器，返回404，不伪造业务成功。

本地开发壳的代码默认值不替代MySQL业务配置。一键脚本从现有`JAVA_GATEWAY_URL`、Python监听参数和`INTEGRATION_TOKEN`生成忽略的启动配置文件；根目录`.env`仍只有MySQL参数。直接使用Maven启动适用于默认端口、开发夹具模式；需要实际内部令牌时使用下面的配置桥接，不将密钥放入命令参数。

```bash
# 在python-backend/目录执行
python -m app.java_development --output ../run/java-backend.properties

# 在java-backend/目录执行
java -jar godp-planning-server/target/planning-business.jar --spring.config.additional-location=file:../run/java-backend.properties
```

启动配置文件包含内部令牌，应随本地运行文件保护；POSIX按0600写入，Windows沿用当前用户目录访问权限，不提交、不复制到驻场包。修改库内端口或令牌后重新生成配置并重启Java。

配置生成器不连接Java业务库。请先提供可访问的Java业务库；新库启用业务模块后，本地Java通过`LocalManualBusinessSchema`创建14张业务表，并在`business_only`模式发布查询视图。表和字段含中文注释，重复建表保留数据，但不替代存量库增量迁移。存量部署先按[数据库发布步骤](../docs/双库业务迁移与验收_2026-11-03.md#数据库发布)发布V3/V4/V5及算法库迁移；`planning.manual.initialize-schema=false`可关闭运行期建表。驻场不迁入本地DDL类，分别由宿主发布业务库和Python算法库脚本。

## 代码边界

```text
com.pab.aitmp.aiis.godp.digital.marketing/
  entity/xiangliang/{vo/req,vo/res,context,error,support,...}/
  api/xiangliang/{port,host,context,response}/
  client/xiangliang/{python,config}/
  services/service/xiangliang/{manual,auto,config,content,query,source,tasks,...}/
  services/mapper/xiangliang/       7个独立Mapper接口
  server/xiangliang/{controller,web,config}/
  server/xiangliang/dev/           仅行外，inside构建与源码导出均排除

godp-planning-services/src/main/resources/mapper/xiangliang/
  *Mapper.xml                     6份业务SQL
  source/BankSourceMapper.xml      行内资料只读SQL占位
```

`planning.manual.enabled=true`启用人工及结果业务。通配符页面转发已删除，只保留显式Controller。默认独立空壳不启用数据库模块；本地配置生成器开启业务模块、综合配置、自动策划和业务库SQL查询。历史真实开发库验收不代表本轮代码已经部署；V9仍需按DBA步骤核对发布。

`ManualModuleConfiguration`统一装配业务服务，直接接收ManualMapper与BusinessTransactions；ManualDatabase包装类已删除。宿主已有`xiangliangBusinessTransactions`管理器通过独立声明式代理承接事务。原始资料接SourceFacts/BankSourceQueries，计算、身份和内容状态分别接现有端口；不再使用页面通配代理。完整装配见[宿主说明](host-integration/README.md)。

普通人工策划的内容状态由`ManualContentStatusService`读取投影。宿主实现`ManualPorts.ContentStatusSource`查询内容方，Job按游标调用`reconcile(limit, afterId)`；服务校验明细版本和状态时间，更新策划明细与批次进度。行外无内容方接口，不自动模拟生产成功。字段和调用方式见[迁移说明](../docs/JAVA_MANUAL_MIGRATION.md)。

策划明细导出支持`format=xlsx`，使用宿主已有的Apache POI 4.1.2生成Excel；未传格式或传`format=csv`保留原CSV响应。前端优先请求XLSX，并根据实际响应类型决定下载扩展名。账号导入模板和导入异常明细目前仍是前端CSV，尚未迁入Java文件处理链路。

正式明细以`批次ID + 槽位ID`唯一，可容纳同批次同账号的多个投放日期。`planning.history.mode=business_only`启用`SqlPlanningReadQueries`：列表、分组详情、完整范围统计、失败详情及导出均查询业务库；原Python历史已导入并退出联合查询。`Transition`关闭旧桥，找不到记录时明确返回错误。

`planning.config-release.enabled=true`时，综合`/config`由Java接收完整页面配置，以持久化命令调用Python保存算法字段，再事务发布Java业务字段与历史。待确认期间不允许新自动任务取得混合配置；独立`/business-config`写入和旧模块写入口关闭。Java业务版本及值传入Python冻结输入，配置、算法提案和正式结果可追溯。

人工营销任务由`MarketingTaskService`保存；旧任务由业务库只读归档提供详情。宿主通过`PlanningContentPort`提供已分配且过审的内容，`MarketingPlacementService`确定投放日期并写正式结果。内容状态通过`ManualPorts.ContentStatusSource`、`MarketingStatusSource`读取；行外空实现不会伪造完成。

普通自动策划由`AutoScheduleService`管理触发及确认重试，`AutoResultCommitService`在同一业务事务写批次、槽位和凭证，再确认Python。基础模块须显式启用`planning.auto-schedule.enabled`；本地配置生成器已启用并配合`AUTO_SCHEDULE_OWNER=java`。当前开发环境完成真实双库与确认丢响应验收，宿主环境须自行发布并验收后启用。

`SlotCompletionService`处理热点T-1和自动营销引用，无营销内容时回到原普通选题。原legacy目录仅剩行外本地HTTP配置，不包含页面Controller或通配转发。真实登录、授权、资料、内容状态与宿主调度仍需现场接入。

账号列表、选题列表和选题详情由Java显式接口提供。outside的`FixtureSourceFacts`直接读取模拟资料，`OutsideSourceAdapter`将已获取的实体交Python计算生命周期/标签；`LocalPythonAdapter`不再实现`Source`。统一资料入口为`/api/plan/internal/source/{capability}/query`，需内部令牌。宿主提供真实`SourceFacts`及`ManualPorts.Source`装配，保留业务服务。见[统一资料链路](../docs/统一资料链路_2026-11-03.md)。

此适配器仅用于本地`local`环境，不应作为客户生产鉴权方案。迁移业务时新增Java应用服务／持久化实现，再移除对应旧路由；不让Java和Python同时写同一业务。

## 迁入客户Java工程

五模块已按包名和目录落位。`mvn -Pinside package`生成`godp-planning-server/target/inside/planning-business.jar`普通library JAR，排除本地启动壳、模拟数据、旧代理和application配置，不执行Boot repackage。该Maven profile仅校验模块交付边界，不代表真实Halo工程已编译验收。现场复用宿主Parent/BOM、启动类、配置、MyBatis工厂和业务数据源，按[五模块并入说明](host-integration/MAVEN_MODULES.md)接入；不要同时激活Maven的dev和inside profile。

`server.xiangliang.dev.LocalExecutionConfiguration`和`LocalJobPulse`只用于行外模拟，驻场不复制；由客户Job调用`client.xiangliang.python.PythonExecutionClient.wakeup`。Python内部唤醒受理返回202，业务是否完成仍查询业务任务；受理完整性、网络失败重试和角色执行间隔不能通过浏览器转发处理。详见[后台执行说明](../docs/BACKGROUND_EXECUTION.md)。

共用约定及迁移顺序见[三工程契约](../docs/contracts/README.md)。工程侧技术栈、需替换的接入点与不应迁入的本地代码见[驻场替换点清单](../docs/JAVA_HOST_REPLACEMENT_POINTS.md)。
