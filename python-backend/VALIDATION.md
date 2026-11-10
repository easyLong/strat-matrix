# Python 模块化改造验收记录

日期：2026-11-10；模块版本：0.3.0；验证基于基础提交 `00c94fe4dd21a62b95e62a541e5dd1954cbf5ea2` 加当时工作区，随后随本轮代码提交固化。完整仓库的变更范围记录于 `docs/发布记录_2026-11-10.md`；本文件描述验证发生时的状态，不代表已完成行内生产验收。

## 实现对应表

| 项目 | 已完成内容 |
| --- | --- |
| M01 命名空间 | 运行模块迁入 app/content_planning，相对导入保留；测试、动态 patch、工具命令和核心回归定位同步迁移 |
| M02 应用工厂 | create_app(config, dependencies=...)；app.main:app 独立入口继续复用 |
| M03 宿主安装 | install_content_planning，HTTPX ASGITransport，共用端口，显式组合原宿主 lifespan |
| M04 配置 | 连接配置显式注入、CONTENT_PLANNING_ENABLED/PLANNING_* 映射、无导入时环境写入；算法字典和策略仍存 MySQL |
| M05 资源 | 每应用连接池、配置缓存、模型容量及适配器；线程显式传播 runtime/操作人；关闭等待执行器再释放池 |
| M06 接口隔离 | 白名单、前缀、独立鉴权与异常、请求/二进制响应保留、OpenAPI 命名空间、Java 前缀客户端契约测试 |
| M07 外置资源 | database/content_planning、内置标签字典、显式资源路径、离线工具和可从其他目录使用的交付包 |
| M08 依赖说明 | 25 表与旧业务依赖分开登记，保留正式批次防重复校验；启动不执行 DDL |
| M09 验证交付 | 最小宿主、配置示例、专测、独立与宿主真实启动、SQL、依赖清单和逐文件 SHA-256 |

## 实测结果

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| Python 完整回归 | 563 通过，149 子断言通过，0 失败 | run/python-module-python-tests.log、python-module-python.junit.xml |
| 宿主与交付专测 | 32 项，另有独立入口配置专测 1 项，均包含在完整回归中通过 | tests/content_planning、tests/test_standalone_config_loading.py |
| 根级 testing 框架 | 53 通过 | run/python-module-harness-tests.log |
| Java 完整回归 | 155 项：150 通过、5 跳过，0 失败/错误；包括新增 /planning 客户端测试 | run/python-module-java-tests.log；隔离构建 surefire XML |
| V19 small/scale 固定回放 | 两套通过；与改造前冻结评测的差异仅执行耗时 | run/python-module-v19-small、python-module-v19-scale、python-module-v19-comparison.json |
| 独立接口清单对照 | 改造前后均为 111 个路径/方法组合，无新增或删除 | run/python-module-standalone-route-comparison.json |
| SQL 离线核对 | 25 表 DDL 与来源一致，0 数据库写入 | tools.content_planning.schema check |
| Uvicorn 独立启动 | /api/health 200，算法库可只读检查 | run/python-module-network-smoke.json |
| 最小宿主关闭 | /health 200；策划健康 503 disabled；OpenAPI 200 | 同上，真实临时端口 |
| 最小宿主启用 | 宿主/策划健康均 200；无令牌访问执行器 401；OpenAPI 200 | 同上，真实算法库只读检查，无任务提交 |
| 交付包独立复测 | 复制到新目录后 32 项模块测试通过，不依赖本项目独立入口 | run/python-module-exported-tests.log、python-module-exported-tests.junit.xml |

验收使用项目 Python 3.10.11；Java 使用 JDK8，在隔离目录构建，没有覆盖运行 JAR。首轮 Java 测试 JVM 因机器默认堆过大未启动，改用 `-Xmx768m -XX:ParallelGCThreads=2` 后完整通过，无业务代码调整。

可随 Git 获取的脱敏汇总为 [validation-results.json](validation-results.json)，其中 `uncommitted_worktree` 表示运行测试时尚未提交，不是对读者当前检出的 Git 状态作判断。原始运行日志、构建目录和本地 ZIP 保留在忽略目录，不随代码提交。

专测覆盖默认关闭零资源、启动失败释放资源且宿主继续运行、原 lifespan 状态和启动/关闭钩子、鉴权及错误格式隔离、两个启用模块不串配置/令牌、容量隔离、后台线程上下文、关闭顺序、资源关闭异常、外部 root_path、UTF-8 路径/重复 query/原始字节、gzip/重复响应头/429 Retry-After、请求体上限、验证错误、OpenAPI 同名模型、跨目录模块导入、SQL 核对和交付哈希。

V19 的召回、模型精判、分配、选题结果、数据指纹和缓存/策略校验未因目录变化而改变。固定回放使用受控模型响应，不把模拟测试称为真实模型质量评估。

## 未验收及待接入事项

- 未调用真实大模型：0 模型调用、0 Token 费用；未提交真实策划任务或写入业务数据。真实模型网关协议、网络、凭据与质量还需联调。
- 未执行数据库 DDL/迁移；当前真实库仅用于启动就绪只读检查。目标宿主的依赖版本、DML 权限与建表发布须现场验证。
- **仅有 25 张算法表的环境仍不能保证全部旧路径通过。** 准备阶段的 godp_planning_batch 校验及旧自动调度/提交分支依赖已列入数据库说明；没有删除校验，也没有声称已完成纯算法库全链收敛。
- 没有对本轮新代码重新生成三页面截图报告；此前验收包对应此前冻结源码。
- 当前本地旧进程检查到 planning/manual_compute 待执行信号，本轮没有中断该服务强制重启。新代码已在临时独立端口完成上述启动验证；正式切换前按运维流程停止触发、排空后重启。
- 不宣称已通过行内架构评审、安全扫描或生产验收。旧版本的扫描和黄金集确认状态不因本轮重构自动改变。

## 交付与回退

`tools.content_planning.export_module` 生成无真实凭据的模块 ZIP、逐文件清单和 ZIP SHA-256。包包含运行模块、外置 SQL、工具、专测、最小宿主、配置示例及依赖，排除本机环境、日志、私有适配及当前项目独立入口；宿主自行装配，不覆盖宿主 app.main。

回退先停止新任务受理、等待当前轮次结束，恢复此前源码包、依赖和独立/宿主入口；保留任务、租约、快照与提案。此轮无数据库结构变更，不以删表回退。旧版本依赖和新版本依赖不可在同一宿主进程混装。
