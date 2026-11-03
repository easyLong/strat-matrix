# 三工程接口契约与迁移边界 V0.2

日期：2026-11-03。目标：一个仓库内的三个子项目独立开发，最终分别嵌入客户现有的Vue、Java、Python工程。

当前开发环境已发布Java业务库`strat_matrix_bus`及Python算法库`strat_matrix`迁移，配置冻结、普通自动正式闭环、Java热点/营销业务、SQL分页及历史导入见[双库业务迁移与验收](../双库业务迁移与验收_2026-11-03.md)。真实行内资料、内容状态、权限和调度尚待现场接入。

目录已统一为`frontend/`、`java-backend/`、`python-backend/`。Python原目录已重命名；`app`包名、数据库及接口地址保持不变。启动脚本和驻场代码包均使用新目录。

## 当前与目标

| 链路 | 当前实现 | 宿主接入目标 |
| --- | --- | --- |
| Vue → Java | Vite把`/api/**`映射到Java的`/api/plan/**` | 客户网关／请求封装承担映射，页面只调用Java |
| Java页面业务 | 配置发布、人工任务、自动任务、正式结果及内容业务由Java维护；当前页面SQL查询业务库 | 迁入宿主业务包和Mapper，替换身份、事实来源及装配 |
| Java → Python | 普通人工异步计算、自动Pipeline启动/提案/确认、算法配置幂等命令 | 绑定宿主内网地址、鉴权及HTTP客户端，不重写算法 |
| Python → Java | 日常与验收共用Java资料查询；outside由Java读模拟文件 | 替换Java `SourceFacts`为行内SQL/服务实现，保留实体及分页语义 |
| 数据库 | Java保存业务与已导入历史；Python保存算法资产和计算任务，旧业务数据保留追溯 | 两库独立发布，运行服务不跨库连接 |
| 调度 | Python服务内受控执行；Java local profile模拟宿主触发，无独立Worker | 客户调度触发Java；不迁移本地模拟调度 |

旧架构备忘中的“本仓库不建设Java、Python永久保留全部业务”已被三工程决定替代。本地迁移与测试不代表已完成行内认证、内容联调或生产发布。

最新取数及算法投影以[统一资料链路](../统一资料链路_2026-11-03.md)为准：原始资料由Java提供，生命周期和选题标签由Python对Java传入实体计算。旧Python资料POST已停用，不继续维护第二套日常取数方向。

## 页面契约先保持稳定

请求及响应以`frontend/src/api.ts`、`frontend/src/api/queries.ts`、`frontend/src/types.ts`和现有Python页面路由为迁移前基线，不在增加Java入口时改字段、分页结构和业务含义。

- JSON接口错误继续返回原HTTP状态及`detail`；受理返回不当作业务完成。
- 重复查询参数及已编码的中文／ID不得重新编码或丢失。
- 导出保留原始字节、Content-Type、Content-Disposition，不包装成JSON。
- 账号模板导入目前仍由浏览器解析CSV；策划明细XLSX导出已在Java使用宿主已有的Apache POI。
- 内部任务和模型管理不经页面入口开放；OP作为服务接口另行接入授权，当前不经本地页面白名单转接。
- 具体白名单集中在Java `PageRoutes`，新增页面API时必须同步更新和测试。

## 业务和计算对象

| 对象 | 权威方 | 主要内容 |
| --- | --- | --- |
| 人工策划业务请求 | Java | 非营销：名称、日期、账号、选题；营销：名称、单个选题、总生成数量 |
| 基础资料 | 客户业务系统，经Java读取 | 账号ID、选题ID、原始属性及互动；营销内容ID与选题ID分开 |
| 业务规则 | Java | 策划日、自动调度日期时间、营销上限和热点选题占比 |
| 算法规则／资产 | Python | 生命周期条件组、阶段目标、标签字典、映射、向量及匹配权重 |
| 输入快照 | Java固定业务版本，Python保存完整冻结输入 | 已选账号/选题、业务规则快照及算法准备版本 |
| 技术计算请求／结果 | Python | 请求编号、输入版本、计算任务编号、进度、提案、评分、未匹配原因 |
| 正式策划与状态 | Java | 业务任务、批次、账号、日期、选题、生产状态及操作记录 |

Java先事务写正式结果及确认凭据，再向Python确认；Python不直接落Java正式结果。配置页的一次保存由持久化发布命令衔接两库，不以一次HTTP成功冒充跨库事务。内容侧已有内容的生成、审核和分配仍由客户内容系统负责，策划侧只读取事实并完成引用和排期。

## 每次业务迁移的检查项

1. 先为选定用例固定现有请求响应样例和业务校验，不改变页面行为。
2. 在Java实现该用例的业务逻辑、事务和查询，明确要迁移的表及数据。
3. Python只保留该用例需要的计算能力；明确异步任务受理、查询和结果。
4. 完成业务数据迁移及验证，再将页面路由切换到Java真实实现。
5. 停用对应Python业务写入；同一业务不能两边同时写，回退前同样检查写入归属。

建议顺序：基础只读查询 → 配置管理 → 人工非营销策划闭环 → 自动编排 → 营销与内容衔接 → 剩余报表。算法改进和业务迁移不同时大范围展开。

## 独立验证

| 子项目 | 命令 | 是否依赖其他服务 |
| --- | --- | --- |
| frontend | `npm test`、`npm run build` | 否 |
| java-backend | `mvn verify` | 否，测试使用本地HTTP夹具，不访问MySQL或真实模型 |
| python-backend | 安装开发依赖后，在仓库根目录运行`python -m testing --suite python` | 否，提供独立系统配置，阻断真实MySQL和公网，配置专项使用替身 |

默认联调端口：Vue930 → Java6931 → Python6930。独立命令见三个子项目README。无需第四个Worker进程。根目录start／stop／status脚本用于Linux联调部署；bank模式使用客户已有Java服务和调度，须接内部唤醒，详见[后台执行说明](../BACKGROUND_EXECUTION.md)。

## 第一阶段历史验收记录（2026-11-02，普通人工迁移前）

- 重构前基线`36280c5`已推送GitHub main，之后的三工程改动单独保留。
- Java在真实JDK8运行`mvn verify`，10项测试通过并生成可运行jar；首次下载公开依赖后，离线`mvn -o verify`也通过。
- Python全量362项测试通过；本地配置生成相关检查再次通过，未执行真实业务创建或模型调用。
- 前端16项测试及生产构建通过。
- 经实际Vite → Java → Python验证：配置、标签、账号分页、人工任务分页、时间分页、CSV字节及文件名、422错误响应正确；页面入口拒绝内部任务及OP请求。
- Linux三个管理脚本通过Bash语法检查；当前Windows本地三个服务已运行并验证930页面入口，经Java访问Python。尚未在Linux完整执行启动／停止脚本。
- Java尚未拥有业务表、正式任务或行内权限实现；数据库归属和真实算法能力契约仍待逐项迁移。

Java公开兼容基线依据：[Spring Boot2.7.18要求](https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/getting-started.html)、[Spring5.3 RestTemplate](https://docs.spring.io/spring-framework/docs/5.3.39/javadoc-api/org/springframework/web/client/RestTemplate.html)。该开发壳不替代客户实际BOM和生产补丁线。
