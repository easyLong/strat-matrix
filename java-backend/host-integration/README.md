# 行内宿主接入模板

2026-11-09：正式页面业务与Java→Python算法配置、标签、流水线状态使用单套POST。旧页面GET/PUT、重复包装入口和前端协议协商已删除，健康检查保持GET。配置恢复版本通过JSON提交；综合发布开启时不能从单独业务配置绕过统一保存。接口与验收见[POST最终契约](../../docs/业务接口POST收口_2026-11-09.md)。

2026-11-07补充：当前实体、事务、请求及调度边界见[执行记录V0.2](../../docs/行外独立改造执行记录_V0.2_2026-11-07.md)。ManualDatabase已删除，宿主继续提供同名业务事务管理器；模块通过BusinessTransactions声明式代理接入。Mapper已类型化，旧页面通配代理已删除。

新增可选端口为PythonRuntimeSettings（完整URL/令牌快照）和PlanningSpreadsheetWriter（宿主Excel库）。PlanningPermission把可信能力标识写到请求属性供HostAccess读取；它不是权限放行实现。BankSourceFacts会在inside启动时检查资料实现，SQL读取器需调用verifyWith绑定真实SqlSessionFactory。

优先通过四类[Handler薄壳](PlanningHandlersHostJob.java.example)对接宿主调度；低层PlanningTaskService仍可用。内容流水写入须在每天三次触发时显式传dispatchContentFlow=true。

本目录用于将业务模块合入现有Java工程，不另建一套行内Java应用。公共装配入口为`PlanningHostConfiguration`；它没有私有SDK、数据源创建、自动建表或定时器。部署参数示例见[inside-sample.properties](inside-sample.properties)。

已按`godp-planning-api/entity/client/services/server`五模块拆分，包名前缀统一为`com.pab.aitmp.aiis.godp.planning`。行外聚合POM只管理公开依赖，不模拟行内Parent/BOM。现场注册模块、替换父POM并由宿主server装配，见[五模块并入说明](MAVEN_MODULES.md)。Maven `inside` profile产出不含本地启动壳的library JAR；`dev` profile产出行外可执行包，两者输出目录隔离。

2026-11-05更新：业务库14张表统一六公共字段。迁入时包含`context/AuditFields`，可信UM须为1至50字符；存量表先发布[表结构V6及查询视图](../../docs/表结构公共字段规范与升级_2026-11-05.md)，再部署新版Mapper。原业务编号和唯一约束保留，宿主不必改前端接口对象。

2026-11-07更新：新增[DBA发布包V9](../godp-planning-services/src/main/resources/db/release/20261107-v9/README.md)，包含独立DDL、初始数据核查、发布前后检查、兼容回退、表/索引和容量清单及源码校验和。当前源码要求批次`write_state/write_cursor`两列；V8存量库须先由DBA发布V9及三个视图，再部署新版。实际开发库尚未执行本轮DDL，运行中的旧服务不受源码变更影响。

## 1. 保留和迁入

迁入`planning/{manual,config,auto,content,query,source,tasks,context,api,host}`和`planning/adapter/python`、`resources/mapper/*.xml`、经过发布审核的`resources/db`脚本。使用宿主父POM、依赖管理、启动类和配置来源。

不要迁入`standalone`、`adapter/local`、`adapter/legacy`、本地`application-local.properties`、`run`或启动配置桥。旧算法库业务历史若需要保留，先按迁移脚本导入业务表；模板的`ManualNewInstallTransition`关闭旧接口回退，不能指望它读取尚未迁移的数据。

在宿主配置类显式导入：

```java
@Import(PlanningHostConfiguration.class)
```

启用`inside` profile与`planning.host.enabled=true`。模板导入配置、人工、自动、内容、查询、任务服务及正式页面Controller；模块开关见参数示例。宿主需扫描或导入这些类，避免重复复制相同配置类。

## 2. 宿主只需提供的六类绑定

| 必需Bean或接口 | 宿主提供什么 |
| --- | --- |
| `planningBusinessSessions`：`SqlSessionTemplate` | 宿主业务库的MyBatis会话；加载六个Mapper XML。可用别名绑定已有Bean，不新建数据源 |
| `planningBusinessTransactions`：`PlatformTransactionManager` | 上述同一业务库的事务管理器 |
| `planningPythonHttp`：`RestTemplate` | 宿主认可的内网HTTP客户端，设置连接/读取超时并禁止自动重定向；其余鉴权和错误转换交公共`PythonClient` |
| `SourceFacts` | 行内账号、选题、营销内容、有效投放、生产进度、营销进度、过审账号分配等查询。真实SQL/服务实现在此处填写 |
| `ManualPorts.Actor` | 从宿主可信用户上下文返回当前UM号，不能取浏览器自报的操作人请求头 |
| `HostAccess` | 宿主认证、功能授权及数据范围上下文；对所有页面路径生效。无默认放行实现，缺失即装配失败 |

另有两个可选扩展：`HostContextProvider`统一提供可信UM、机构范围和追踪号；`PlanningResponseAdapter`集中适配页面成功/错误响应。未提供时沿用原Actor和前端格式，数据范围标记为UNSPECIFIED，绝不默认ALL。内部资料协议及文件下载保持原样。详细说明和代码示例见[请求上下文、响应与分页](REQUEST_CONTEXT_RESPONSES_PAGING.md)。

`SourceFacts`现有可复用的[BankSourceFacts骨架与查询契约](BANK_SOURCE_CONTRACT.md)、[67项字段映射表](BANK_SOURCE_FIELD_MAPPING.csv)和[装配示例](BankSourceBindings.java.example)。宿主可填MyBatis SQL，也可接已有Service，两种方式共用字段、分页、状态及关联校验。真实表名和状态编码尚待驻场填写；默认SQL及未实现方法明确返回503。它没有自动注册，不会替换当前outside模拟资料。

字段/编码差异可集中放在[现场映射规则](BankSourceSiteMapping.java.example)；账号互动支持每页一次批量查询，无需逐账号组装。现场可用`python -m testing.bank_source`有限样本只读验收，行外/行内使用同一命令，步骤见[测试说明](../../testing/README.md#资料适配只读验收)。

共享`SourceCatalogAdapter`、`ContentFactsAdapter`、`ContentObservations`会把`SourceFacts`拼装成现有业务端口，现场不必再重复编写账号、选题、冻结输入、普通内容状态、营销状态等转换逻辑。宿主也可在自己的装配类选择其他端口实现，不强制沿用整套模板。

资料页循环已统一到`SourcePageReader`，区分前N条和完整读取，检查页码、总数变化、重复ID及读取预算。营销过审分配的账号快照也采用批量资料读取。

HTTP客户端的公开实现参考：

```java
@Bean("planningPythonHttp")
RestTemplate planningPythonHttp() {
    return PythonClient.boundedHttp(1000, 3000);
}
```

统一`PythonClient`负责服务地址、令牌、可信操作人、响应及异常处理。能力类只声明请求/结果契约。行内如强制使用其他HTTP基础设施，应集中改这一边界；不要逐个业务Service修改URL。

六个XML：`ManualMapper.xml`、`BusinessPlanningConfigMapper.xml`、`ConfigReleaseMapper.xml`、`AutoScheduleMapper.xml`、`PlanningQueryMapper.xml`、`SlotCompletionMapper.xml`。模板显式绑定到同一个业务会话，宿主不要再对这些Mapper重复注册不同数据源的代理。事务管理器必须与该会话的业务库一致。

## 3. 权限与两个访问方向

```text
浏览器 → 宿主认证/HostAccess → Java正式页面接口 → 业务库或Python能力
Python → Java内部资料接口 → 独立内部令牌校验 → SourceFacts查询
```

- `HostAccess`覆盖`planning.api-prefix/**`的页面操作，包括导出；内部资料路径使用`SourceFactsController`的独立令牌检查，不以页面登录替代机器身份。
- 本项目不实现宿主SSO或权限SDK。`HostAccess`只能建立权限上下文，数据范围还必须由宿主资料查询及业务MyBatis权限机制实际执行；不能将模板测试中的全范围样本视为生产数据权限已完成。
- `/health`现在检查Java业务库及Python数据库健康，返回前端现有契约；依赖失败返回503。它是页面就绪检查，不替代宿主容器存活探针。
- `/tag-taxonomy`是正式Java入口，保存时只使用`Actor`返回的操作人；Python维护标签和版本。浏览器伪造`X-Operator-Id`不会透传。
- 页面路由不开放任务唤醒入口；宿主Job直接调用Java任务服务。

## 4. 宿主调度调用

注入`PlanningTaskService`，每次调用`run(kind, now, limit, afterId)`处理一个有限批次，无内部定时器。示例：

```java
Map<String, Object> result = tasks.run(
    PlanningTaskService.Kind.CONTENT_STATUS, Instant.now(), 100, afterId);
```

| Kind | 推进内容 | 调度注意 |
| --- | --- | --- |
| `CONFIGURATION` | 恢复未确认的两侧配置发布 | 高频轻量检查 |
| `MANUAL` | 提交/查询人工计算并正式落库 | `processed`表示本次扫描完成；根据待处理情况在后续调度继续，不代表任务完成 |
| `AUTOMATIC` | 推进已有自动任务，再检查配置中的周触发时机 | 返回`retry_required`时宿主应记录需重试，不报业务成功 |
| `HOTSPOT` | 检查北京时间明天的热点空槽 | 每日触发，无空槽立即结束；同次分页使用同一业务时点，第二天游标重置 |
| `MARKETING` | 自动营销槽位引用 | 按返回游标分页 |
| `MARKETING_PLACEMENT` | 人工营销过审内容确定日期、形成正式策划 | 未得到内容事实时保持等待，不伪造完成 |
| `CONTENT_STATUS` | 普通/热点内容状态对账 | 按返回游标分页 |
| `CONTENT_FLOW` | 到达T−x生产日期后，将已定题、待生产的账号策划结果写入现有内容流水 | 每天由宿主触发3次；需先提供`ContentFlowWriter`并启用`planning.content-flow.enabled`，未接入时返回503 |
| `MARKETING_STATUS` | 营销需求生产/分配进度对账 | 按返回游标分页 |
| `ALGORITHM` | 唤醒Python的`planning`与`manual_compute`角色 | `accepted`仅代表受理信号，业务完成必须查持久化任务 |

分页扫描的`has_more=true`配合`next_after_id`继续，游标由宿主Job上下文维护；失败不推进游标。普通人工的排队/运行状态通过`needs_next_tick`提示后续再检查，不能立即无间隔循环轮询。按宿主要求设置单次调度的页数/时长预算。配置、人工、自动等持久化任务可在后续调用恢复，进程内游标不作为业务完成凭据。

外部不可用会抛出异常或返回明确的`retry_required`，宿主Job需据此记录失败/待重试。`processed`、HTTP202及唤醒回执不能当作整个业务完成。生产与审核状态仍以内容侧实际结果为准。

自动正式结果每次提交推进最多500条明细，事务内另有少量游标/状态写入；`write_cursor`与该页明细一起提交，失败只回滚当前页。批次在`staging`期间对页面、导出、换题、使用次数和内容扫描不可见；最后一页校验数量后只更新一条批次为`ready`，与Java提交凭证一起提交，然后才能向Python确认。`needs_next_tick=true`表示仍需宿主后续推进，无忙循环或新定时器。相同提案指纹可在进程重启后恢复，变化指纹明确拒绝；不自动删除未完成批次。宿主自行查询策划表时也必须使用read视图或显式过滤批次`write_state='ready'`。

`ContentFlowWriter.transactionMode()`明确选择事务边界：默认`INDEPENDENT`适用于远程或独立提交，调用时不持有策划事务/行锁；写后重新锁定并核对策划版本和待生产状态，回执丢失依靠目标唯一键及原始回执恢复。`SAME_TRANSACTION`仅用于同一DataSource/事务管理器且加入当前REQUIRED事务的写入；流水和策划回执共同提交或回滚，禁止在该模式发HTTP或开启独立事务。目标端仍须实现幂等、版本单调和已生产内容不可更新，方法名upsert本身不代表这些约束已实现。

## 5. 驻场前验收入口

```bash
# 在java-backend目录；仅H2和Python HTTP响应桩，不读开发MySQL或调用模型
mvn test -Dtest=InsideThreePagesAcceptanceTest,PythonClientTest,PlanningTaskServiceTest
```

验收加载真实宿主装配、Controller、Service、Repository、六套Mapper和查询视图。测试夹具先以DBA身份建库，再以仅SELECT/INSERT/UPDATE/DELETE权限的非管理员账号装配应用，明确断言CREATE/ALTER被拒绝。覆盖配置保存/恢复、标签版本冲突与操作人、防重人工任务、正式结果、换题、列表、导出、全部任务阶段、内部鉴权和依赖故障；断言不存在旧代理、模拟资料和本地调度Bean。此为隔离H2权限验证，真实Venus/MySQL的授权和视图访问仍由现场验证。

新增结果发布/流水事务/DBA SQL演练入口：`mvn test -Dtest=AutoScheduleServiceTest,ContentFlowDispatchServiceTest,DatabaseReleaseTest,PlanningTaskServiceTest`。DBA脚本在H2做新库、V8升级和回退演练，JSON函数及MySQL多列ALTER使用明确的方言兼容；不能代替现场MySQL执行评审。使用`python tools/build_db_release.py --output godp-planning-services/src/main/resources/db/release/20261107-v9 --check`核对发布包和权威源码，工具不连接数据库。

可选实际Vue浏览器验收：先`frontend/npm run build`，安装Playwright与Chrome后设置`PLANNING_BROWSER_ACCEPTANCE=1`，再运行`InsideThreePagesAcceptanceTest`。`PLANNING_PLAYWRIGHT_MODULE`可指定已有Playwright模块位置，`PLANNING_CHROME_PATH`指定浏览器。浏览器只连接测试JVM的回环MVC桥及临时静态代理；这两个桥不进入正式工程。证据保存在忽略的`run/inside-host-browser/`。

测试通过仅证明模块、页面和契约可装配。真实SSO、权限SQL、内容系统、调度SDK和实际数据库性能仍须驻场联调。数据库脚本、视图及JSON函数兼容性通过宿主发布流程单独确认。
