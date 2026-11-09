# 普通人工策划首轮迁移

本页记录首轮6张业务表的验收状态。后续新增第7张人工营销任务表及多槽位结果升级，见[人工营销业务迁移](人工营销策划业务迁移_V0.1.md)和[策划结果改造](策划结果三工程改造_V0.1.md)；远端业务库尚未发布这两项变更。

日期：2026-11-02。范围：新建非营销人工任务 → Python计算 → Java正式结果 → 原页面查询。

当前本地已切换：Java业务库为`strat_matrix_bus`，Python算法库仍为`strat_matrix`。数据库账号取自根目录`.env`，通过`JAVA_MYSQL_DATABASE=strat_matrix_bus`指定Java库。业务库已初始化本轮6张表，并通过真实MySQL及前端入口闭环验收。表名不带语言标识；两个库即使存在同名表，也由各自连接和数据归属隔离。历史Python业务数据继续保留。

## 本轮边界

```text
Vue（接口及页面样式保持）
  → Java：校验选择、冻结输入、保存任务、账号日期占用
  → Python：幂等受理计算、受控后台执行、返回分配建议
  → Java：校验返回账号/选题/版本，事务保存批次及明细
  → Vue：原任务列表、查看策划、账号/时间列表、换题和导出
```

人工选题分配延续原有“从已选合格选题中随机分配”的语义；现在用任务编号固定随机种子，使重试不改变结果。没有借本轮迁移切换成自动策划V2或新增模型调用。

营销、自动策划、热点和综合配置页仍走既有实现。生命周期、标签、画像、向量、匹配策略仍归Python。策划日、调度时间、营销上限、热点占比已另建Java业务配置表和接口，但综合页面尚未切换；详见[配置改造 V0.1](AI策划配置三工程改造_V0.1.md)。

## 数据归属

Java负责创建并维护Java业务表；Python负责创建并维护新增算法计算表。Java仅连接Java业务库；Python计算接口仅连接Python算法库。没有跨库SQL、同库复制正式结果或双写。未迁移的旧Python业务表暂时保留，随对应业务闭环迁移逐步退出。

| 表 | 所属 | 内容 |
| --- | --- | --- |
| godp_manual_preview | Java | 30分钟有效的选择及输入快照 |
| godp_manual_task | Java | 业务状态、创建人、冻结计算输入、失败原因 |
| godp_manual_reservation | Java | 账号＋投放日期唯一占用，失败释放 |
| godp_planning_batch | Java | 正式批次 |
| godp_planning_item | Java | 正式明细、内容状态、乐观锁版本及展示快照 |
| godp_planning_adjustment | Java | 换题操作记录 |
| godp_manual_compute | Python | 技术计算任务、输入摘要、租约及建议结果 |

已有业务库从旧表名升级时，先停止业务服务，再对`strat_matrix_bus`执行
`java-backend/godp-planning-services/src/main/resources/db/migrations/V2__rename_business_tables.sql`，随后启动新版本。
该脚本只用于已有`godp_java_*`表的库；新库直接使用`manual-business.sql`建表。
更名保留原数据、主键和字段注释，不能先运行新版本再改表，以免创建一组空的新表。

新Java任务及明细ID从10^12起步，避免迁移期与旧Python数字ID冲突，并保持JavaScript安全整数兼容。驻场须保留该范围或统一改造外部ID协议，不能重置为1。所有新表及字段均有中文注释。

展示扩展字段保存在JSON快照中；任务状态、账号日期唯一键和结果版本使用独立字段。业务读写已迁至MyBatis `ManualMapper` 和 `mapper/xiangliang/ManualMapper.xml`，Repository只封装有业务含义的操作和事务；未引入行内私有SDK。

报表导出由`ManualExportService`构造同一套选题级字段：默认CSV兼容旧调用，`format=xlsx`由宿主已有的Apache POI输出Excel。前端优先请求XLSX；若迁移期旧接口返回CSV，按响应媒体类型保存为CSV。XLSX使用POI流式工作簿并清理临时文件，驻场要确认容器临时目录权限。

## 接口与执行

前端沿用 `/manual-plans/previews`、`/previews/{code}/submit` 和 `/query/*`；Java入口统一加 `/api/plan`。新增Java预览编号以 `JPREV-` 开头，计算幂等编号以 `JMAN-` 开头。

新预览仅冻结选择，返回的items为空数组；当前Vue只使用preview_id继续提交，不依赖该数组。正式分配在提交后的计算阶段完成，不能把预览响应当作最终结果。

| 内部接口 | 输入 | 输出 |
| --- | --- | --- |
| POST /api/internal/manual-computations | request_id、accounts、topics、algorithm_version | HTTP 202，request_id、status、result、error |
| GET /api/internal/manual-computations/{request_id} | 计算任务编号 | 同上；不存在返回404 |

计算状态为pending/running/succeeded/failed。Java业务状态为pending/computing/completed/failed，映射到现有页面文案。202只代表受理，Java正式结果事务提交成功后才是业务完成。

同一request_id和同一输入重复提交返回原计算任务；输入摘要不同返回409。Java每次调度可重复提交同一任务并获取最新状态，以此兼顾受理回包丢失和Python进程重启后的唤醒恢复。

计算租约2分钟，每次执行至多10个轻量人工计算任务；没有新增常驻轮询。Java本地Job调用 `ManualPlanningService.advance()`，驻场由宿主Job调用该方法，不复制standalone调度类。多个Java实例并发推进时依靠Python幂等受理和Java结果事务行锁避免重复批次。

网络异常保留业务任务等待后续调度，错误原因可查询；计算明确失败或结果越出所选范围时业务失败并释放日期占用。没有“网络异常就标已完成”的降级。

## 迁移期读取

新任务不写旧Python业务表；历史任务和其他策划类型通过HTTP只读查询。Java合并后排序、分页，使原页面入口能够同时查看新旧数据。账号/周期统计按账号和选题去重。

`ManualPorts.Source` 是行内资料边界，包含冻结快照、账号资料补全、换题候选以及已策划资格。当前 `LocalPythonAdapter` 调用只读的资料接口复用已有适配器；它不会创建Python预览、业务任务或正式结果。驻场替换为客户Java账号/选题查询方法，算法调用保留。

历史聚合是过渡方案：会读取所选范围内的历史分页后在Java合并，最多500页，超限明确提示缩小范围。适合首轮验证，不作为大规模报表最终架构；后续逐步迁移历史读取能力或改为稳定游标合并。未迁移的旧列表兼容接口仍不能视为完整Java业务接口。

换题仅允许待生产、版本相符、非营销且在投放有效期内的选题。正式记录、版本及操作日志在Java同一事务更新。

## 内容状态读取边界

普通人工策划的正式明细由Java业务库保存。内容方负责生产，宿主Java实现
`ManualPorts.ContentStatusSource`，按候选明细的`itemId`、`slotId`、`version`、`topicId`
读取内容方的当前状态，返回`待生产`、`生产中`、`已完成`或`生产失败`，以及状态更新时间；
已完成时还须返回内容ID。策划模块不提交生产任务，也不接收内容方直接回调。

宿主调度调用`ManualContentStatusService.reconcile(limit, afterId)`，服务再通过上述来源接口查询内容方。
单次最多200条，返回`next_after_id`与`has_more`，后续页继续传入游标；下一轮从0开始。
Java在事务内核对明细版本及选题，忽略过期状态，更新明细、批次及任务列表进度。
行外目前没有内容方查询接口，因此本地服务不主动执行对账；该能力已用隔离测试验证，
驻场只需接入内容方查询方法与宿主Job。普通人工的新明细在完成对账前显示待生产。

## 本地数据库准备及启动

MySQL连接仍放根目录 `.env`。当前已设置`JAVA_MYSQL_DATABASE=strat_matrix_bus`，其余连接项复用既有MYSQL配置。也可独立指定Java连接；未配置Java库名时，通用启动器仍默认Python库名加`_business`，部署时应显式填写实际业务库：

```dotenv
JAVA_MYSQL_HOST=127.0.0.1
JAVA_MYSQL_PORT=3306
JAVA_MYSQL_DATABASE=strat_matrix_bus
JAVA_MYSQL_USER=your_business_user
JAVA_MYSQL_PASSWORD=your_business_password
```

同一个本地MySQL实例中的两个schema仅用于行外验证；行内按已确认要求使用隔离的数据库连接和账号。禁止把Java库配置成Python同一库。数据库配置生成文件含密码和内部令牌，位于已忽略的run目录，不提交或交付。

```bash
# python-backend目录
python -m app.init_planner_db
python -m app.java_development --output ../run/java-backend.properties

# java-backend目录
mvn verify
java -jar godp-planning-server/target/planning-business.jar --spring.config.additional-location=file:../run/java-backend.properties
```

Java在已存在的业务数据库中执行 `java-backend/godp-planning-services/src/main/resources/db/manual-business.sql`，使用CREATE TABLE IF NOT EXISTS创建本模块6张业务表，重复启动不会删除已有数据。开关为 `planning.manual.initialize-schema`，本地默认true；如宿主统一执行数据库发布，可置为false，由发布流程执行同一SQL。后续表结构变更需增加明确的迁移脚本，CREATE TABLE IF NOT EXISTS不负责升级已有字段。

已移除Python代建Java表的工具。配置生成器仅读取连接参数并写本地启动文件，不连接Java数据库；数据库连接和业务表初始化失败由Java启动直接报错，不会静默回落到Python库。数据库本身需预先创建并授权，建库权限与建表权限分开处理。此前1044表示当前账号无权访问/创建新业务库，不表示Java不能建表。

切换前应先让旧Python已经受理的普通人工任务执行完毕。旧预览再提交会提示重新提交，不允许旧新入口同时创建业务任务。

需要由数据库管理员授权时，可按实际账号执行（账号及来源主机请替换，不要新建同名账号）：

```sql
CREATE DATABASE IF NOT EXISTS strat_matrix_bus CHARACTER SET utf8mb4;
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX
ON strat_matrix_bus.* TO '实际Java数据库账号'@'实际来源主机';
```

启动后查看 `/api/plan/service-health` 的 `manual_business_enabled`，必须为true才表示已切换Java普通人工路径。存活检查不代替业务验收。

## 验证与当前限制

- Java隔离H2（MySQL模式）验证：任务受理、重复提交、并发占用、重建服务后恢复、断连重试、非法结果回滚、失败释放、换题状态及版本、查询分页、带时区与旧无时区时间排序。
- 单独启动Python测试API，以真实HTTP完成Java提交→Python自有库异步计算→Java独立测试库落库→原页面查询契约及导出验证。测试使用既有E2E账号/选题，不触发内容生产。
- 此前Python全量374项测试、Java真实HTTP验收及前端16项测试通过。本轮MyBatis、Excel及过渡接口收口后，Java常规27项测试通过，另1项需显式开启的HTTP验收跳过；前端生产构建通过。本地Java重启后，经前端代理请求的XLSX导出返回HTTP 200、正确媒体类型和Excel文件签名。
- 之前尝试的`strat_matrix_business`无权限，现已按实际授权库`strat_matrix_bus`完成切换，无需再申请前一个库。业务库初始化6表，所有表/字段注释完整；不同数据库中的同名表互不影响。
- 正常端口Vue930→Java6931→Python6930真实闭环验收通过：测试账号`E2E-ORD-ACCOUNT-001`、选题`E2E-ORD-TOPIC-001`、投放日期2026-11-24，Java任务/批次ID为1000000000000，1条正式明细。重复提交返回同一任务；查询、周期入口、导出和账号可用性验证通过。旧Python业务任务/批次数均未增加，未触发内容生产。
- 本地报告保存在忽略的`run/java-business-db-acceptance.json`；不含账号密码或内部令牌。
- 首轮终点是“策划结果可查”。Java内容状态对账服务已具备，内容方查询适配尚待行内接入；内容使用次数、业务配置迁移、自动/营销链路、行内身份与数据权限仍待后续处理。新明细初始为待生产。
- 旧Python历史任务的停用/归档及旧表删除需要后续统一迁移，本轮不删除历史记录。

## 驻场适配点

按客户工程技术栈逐项替换的代码位置、版本差异和需确认信息见[Java 驻场替换点清单](JAVA_HOST_REPLACEMENT_POINTS.md)。

1. 由宿主数据库发布流程执行业务schema；在宿主MyBatis配置中加载`ManualMapper`和`mapper/xiangliang/ManualMapper.xml`，用绑定业务库的Mapper与同库事务管理器构造`ManualDatabase` Bean。不复制本地Hikari装配或运行期建表配置。Repository迁移是独立完成的工作，不能归为仅修改连接配置。
2. 实现`ManualPorts.Source`，调用客户账号、选题和历史参与资格查询。
3. 实现`ManualPorts.Actor`，从可信会话取得创建人，并在Controller外接入权限和数据范围。
4. 实现`ManualPorts.Computer`，用宿主HTTP客户端适配Python计算契约；内部令牌由宿主注入。
5. 实现`ManualPorts.ContentStatusSource`，由宿主Job触发内容状态读取；宿主Job另调用`ManualPlanningService.advance`推进人工计算，不复制`LocalJobPulse`。
6. 有历史策划数据时实现`ManualPorts.Transition`的旧任务、结果、批次和旧换题语义方法；旧Python URL仅由行外`LocalPythonAdapter`持有。明确无历史数据的新安装可显式注册`ManualNewInstallTransition`，不可用于遮蔽应保留的历史结果。历史迁完并替换其余旧业务后移除过渡实现。
7. 以上接口由`ManualModuleConfiguration`统一装配，不重写业务Service的构造代码。
