# Python驻场接入与预检

2026-11-10：同进程 FastAPI 接入请先阅读 [content_planning 接入说明](INTEGRATION.md) 与 [本轮验收](VALIDATION.md)。运行目录为 `app/content_planning/`，SQL 为 `database/content_planning/`。下文的 25 表检查只证明算法自有结构就绪，旧准备/提交路径的额外业务表依赖须按 [数据库边界](database/content_planning/README.md) 核对。

2026-11-04确认行内Python为**3.10.11**，以此为本项目适配目标。目标服务器操作系统、CPU架构和离线包来源仍需现场确认；Windows测试环境不能代替目标Linux离线安装验证。

2026-11-05已统一六公共字段。存量库升级、备份、断点恢复及只读验收见[表结构发布说明](../docs/表结构公共字段规范与升级_2026-11-05.md)；现场可用`--owner algorithm`独立发布算法库，不要求Python运行服务获得Java业务库权限。DDM建模与实际DDL发布由现场流程完成。

本工程接收Java委派的计算，经Java HTTP查询原始资料，只写策划算法库。Java维护业务任务及正式批次、明细、内容状态；宿主调度触发Python受控执行，无需另启动Worker或Python定时器。

2026-11-09：Java正式调用的算法配置、标签及流水线状态只提供POST路径，已删除对应旧GET/PUT；人工计算状态只提供/{request_id}/query。健康仍为GET，不提供失败回退或协议协商。部署需同时升级三工程；字段与验收见[POST最终契约](../docs/业务接口POST收口_2026-11-09.md)。

## 已在行外准备好的内容

| 部分 | 可直接复用 | 驻场处理 |
| --- | --- | --- |
| 算法接口与执行 | FastAPI、持久化任务、租约、冻结输入、V19、提案确认 | 并入宿主ASGI工程，绑定日志/鉴权及内部地址；宿主统一触发 |
| 行内资料读取 | `app/content_planning/bank_bridge/java_http.py`的7项查询及固定实体 | Java实现真实查询，填写地址和令牌；有统一包装时集中适配`site_java_private.py`，不改算法 |
| 模型出口 | 文本、标签、画像、向量及精判共用模型地址和凭据 | 填模型网关前缀与两个模型名称，准备网络及系统信任证书；核对协议 |
| 算法库发布 | `database/content_planning/algorithm_schema.sql`的25张表、中文注释和独立初始化命令 | DBA创建独立库及授权；首次安装或按预检结果审核增量变更 |
| 接入预检 | `python -m app.content_planning.onsite_check` | 查看实际缺项，补真实资料样本与网络联调证据 |
| 交接包 | `python -m app.content_planning.bank_bridge.package`包含算法DDL、预检、Java Mapper及装配模板 | 按行内实际Python/OS准备离线wheels及宿主依赖，不搬Windows环境目录到Linux |

当前模型适配仍采用方舟协议：`/chat/completions`和文本输入的`/embeddings/multimodal`，Bearer鉴权。更换兼容网关只改配置；若行内模型平台的请求/响应或鉴权协议不同，应集中修改`app/doubao_labeling.py`适配器及测试，不改打标、画像和V19业务调用。不能把“可改地址”等同于已支持任意模型协议。

## 模型入口并发与任务准入（2026-11-06）

模型打标、共享向量化、OP-04效果测试、自动策划/准备/匹配任务创建与重试，以及后台唤醒均在Python入口检查并发容量。鉴权优先；已满立即返回429及`Retry-After`，不排队等待模型名额。查询、配置查看和健康检查不占模型入口额度。人工非营销随机分配不调用模型，不纳入模型额度。

HTTP入口名额与实际模型名额分开。后台打标、T6向量、账号/选题向量、V19映射/主关联标注/精判都经共用模型适配器取得文本或向量名额；一个HTTP请求返回202不等于其后台任务结束。现有后台池仍最多2个执行线程，重复唤醒按任务角色合并，不新增独立Worker或定时器。

| `godp_system_config`配置键 | 初始值 | 作用 |
| --- | --- | --- |
| `AI_API_MAX_CONCURRENT_REQUESTS` | 4 | 每个Python进程同时受理的模型/任务入口请求数 |
| `MODEL_MAX_CONCURRENT_REQUESTS` | 2 | 所有文本模型实际调用共享上限 |
| `EMBEDDING_MAX_CONCURRENT_REQUESTS` | 2 | 账号、选题及T6共用向量调用上限 |
| `AI_PENDING_TASK_LIMIT` | 32 | 每类外部创建/重新入队的任务准入阈值；检查未完成流水线、待准备或待执行匹配任务 |
| `AI_LIMIT_SCOPE` | process | process为进程内；mysql为同一算法库的跨进程模型共享额度 |

这是并发和队列准入控制，不代表已经实现按分钟的RPM/TPM。每次批量打标仍最多100个选题。32是每类准入阈值；同任务重复提交复用原记录，已受理流水线的子阶段不受外部创建限额阻断。准入计数和业务创建之间使用MySQL命名锁串行保护；不新增容量表。

新环境随算法库初始化补齐上述配置。已有环境只新增这五项、不覆盖已有值、不改模型密钥或其他配置：

```bash
python -m app.content_planning.model_capacity --init-config
python -m app.content_planning.system_config list --group model_limits
```

调整用既有`app.content_planning.system_config set`，数值并发范围1—64、任务阈值1—1000，不能用0关闭保护；旧库未补键前按上表保守默认值运行，已停用或非法配置拒绝执行。配置缓存约5秒生效，改变上限保留原运行计数，不重建信号量。缩小上限不会中断在途模型调用，已有调用结束前不再超额进入。

单进程保留process即可。多Uvicorn worker、多实例或独立模型Worker共享同一模型配额时，设置`AI_LIMIT_SCOPE=mysql`，所有实例须连接同一算法MySQL并使用一致配置；入口请求额度仍按进程计算。mysql模式使用独立数据库连接持有模型槽位命名锁至网络调用结束，进程退出释放；需要结合连接池预算和行内模型网关配额设置，不能简单把案例中的8复制到每台实例。现场用有限模拟请求核对MySQL命名锁权限和实际网关额度，不以测试桩代替集群验收。

限流与模型服务返回429均视为可重试：打标仅退回自己持有的租约、不写失败标签；向量不写失败结果；匹配保存已完成缓存并归还租约等待后续宿主推进，不把繁忙写成业务生产失败。Java保留429、提示及经过校验的`Retry-After`；不自动忙循环重试。既有数据、指纹、模型参数和V19阈值保持原有规则。

离线验证使用统一回归入口，新增并发/重入/异常释放、动态缩限、MySQL共享槽位、队列拒绝及幂等复用、后台延后和Java429适配测试，不调用真实模型。

## 1. 离线核对与首次建表

下述命令在`python-backend/`运行。仅MySQL连接放`.env`或由宿主注入；其它配置保存在算法库`godp_system_config`。

```bash
python -m app.content_planning.algorithm_schema check
python -m app.content_planning.bank_bridge.selfcheck
```

这两个命令不连接真实模型、不写数据库。生成文件从四份现有DDL中按固定算法表清单抽取，测试防止混入Java业务表；需要重新生成时：

```bash
python -m app.content_planning.algorithm_schema export --output algorithm_schema.sql
```

新算法库的显式安装入口：

```bash
python -m app.content_planning.init_algorithm_db --apply
```

仅创建25张算法表并补充缺失的系统配置键，保留已有配置值及版本。不创建Java批次/明细/人工任务表，不复制行内主数据，不导入演示数据，不初始化或批准匹配策略，不自动生成标签词表。词表、生命周期/经营规则及策略需按经确认版本单独发布。

DDL在MySQL中会自动提交；失败可能已有部分表生效，排除权限等原因后可以重跑。`CREATE IF NOT EXISTS`不升级旧表字段，已有结构不兼容时停止配置初始化并报告缺项，需由DBA审核增量迁移。不要以再次执行旧`app.content_planning.init_db`、`app.content_planning.init_planner_db`或`app.content_planning.init_shared_workflow_db`补齐业务表的方式处理。

已有环境只新增模型地址配置时，使用`migrations/20261103_add_model_endpoint.sql`，它不会覆盖已有值。不要为添加这个键运行会清理其它配置的历史迁移命令。

## 2. 配置接入

| 配置 | 含义 |
| --- | --- |
| `PLANNING_ENV` | `outside`开发模拟；`inside`行内接入 |
| `JAVA_GATEWAY_URL` | Java业务服务根地址 |
| `JAVA_API_BASE_URL` | Java内部资料查询前缀 |
| `JAVA_API_TOKEN` | Python访问Java的内部令牌 |
| `INTEGRATION_TOKEN` | Java访问Python的内部令牌 |
| `MODEL_BASE_URL` | `chat_completions` 为网关前缀；`doubao_native` 为行内完整文本接口地址，见 `BANK_MODEL_GATEWAY.md` |
| `MODEL_PROTOCOL` | 默认 `chat_completions`；行内 `doubaoNative` 设为 `doubao_native` |
| `EMBEDDING_BASE_URL` | 原生文本模式下单独确认的向量服务前缀；为空时阻止向量调用 |
| `ARK_API_KEY` | 当前模型适配器的Bearer密钥，保持原键名 |
| `MODEL_NAME` / `EMBEDDING_MODEL_NAME` | 共用文本及向量模型名称/接入点 |
| `AUTO_PLANNING_POLICY_ID` | 已批准、可正式执行的V19策略ID，声明向量空间 |

`outside`的模型地址留空时兼容现有公网方舟地址；`inside`缺模型地址则拒绝模型调用，不自动退回公网。地址禁止携带用户名、密码、查询参数或片段；不关闭TLS证书校验，不自动跟随重定向。网络代理、证书及出网策略以宿主提供的受控环境为准。

通过配置CLI修改密钥会出现在终端历史时，应改用现场受控配置方式，不将真实密钥写入文档、命令样例、工单或交接包。

## 3. 统一只读预检

```bash
python -m app.content_planning.onsite_check --target inside --output /受控目录/python-preflight.json
```

只按inside校验，不保存切换、不写库、不新建任务、不触发Java或模型。检查Java配置、内部令牌、模型配置、25张算法表及字段/中文注释、启用标签词表、算法配置、V19策略及向量模型一致性。

| 结果 | 含义 | 退出码 |
| --- | --- | --- |
| `local_checks_passed` | 本地配置/结构检查通过；不是行内功能验收结论 | 0 |
| `needs_confirmation` | 存在待人工确认的算法规则口径，如没有已审核映射规则 | 2 |
| `not_ready` | 必需配置、表字段、算法资产或显式样本检查未通过 | 2 |

无已审核映射且策略允许受限模型映射时，预检明确列为待确认；若策略禁止模型补足，则报未就绪。工具不自动批准草稿、不修改匹配阈值，也不认为模型兜底必然适合所有账号。

只读检查一页Java账号和选题，显式增加`--java`：

```bash
python -m app.content_planning.onsite_check --target inside --java
```

样本数量为0不能算字段验收通过。此检查仅覆盖账号及选题样本，完整7项查询、账号/选题过滤、营销审核及生产状态须继续使用仓库的`testing.bank_source`资料适配工具，并由现场准备真实脱敏样本。

需要实际验证模型时，显式增加以下参数；会产生最多两次模型调用，只发送固定测试文本，不读取账号/选题、不保存标签/向量、不创建策划：

```bash
python -m app.content_planning.onsite_check --target inside --probe-models
```

文本输出、向量返回及已批准策略的模型标识/维度需要一致。某一调用失败会停止样本测试并报错，不保存上游原始响应或密钥。模型连通不等于真实业务数据的脱敏口径已获批准。

补齐并确认配置后再用既有环境选择命令切换，重启宿主部署的Python服务：

```bash
python -m app.content_planning.deployment_environment select inside
```

## 4. 验收与仍需现场完成的部分

`/api/health`只检查Python算法表存在性，不再要求Java业务表；字段和算法资产的完整检查使用上面的预检。健康检查成功不表示Java、模型网络或正式策划成功。

本轮行外只读检查：25张表及字段中文注释、标签版本4、V19策略9/2048维、Java一页账号及选题通过；已审核映射规则0条，明确待确认。inside目标检查正确报告Java地址/接入配置、模型网关尚未填写；没有切换环境或自动批准规则。

本轮新增26项Python测试，完整回归Python455项及148个子测试、工具36项、Java、前端21项及构建和V19固定回放全部通过，证据在`run/regression/20261103-214315-135219/`。交接包已校验清单指纹、排除私有运行文件，并在解压目录中阻断数据库/网络后成功导入Python应用和核对DDL。包内未准备目标环境wheels，不能视为已完成行内离线安装验收。

当前开发库已存在这25张表，因此本轮未重新建表或删表；仅幂等增加空值的`MODEL_BASE_URL`配置，其它配置值未变化。Python已重启加载新代码；原3条真实模型验收记录的账号/周期/批次查询、导出及使用次数仍通过只读复核，没有新增模型调用或业务数据。

仍需现场：实际运行版本与离线依赖、网关协议/证书/鉴权、真实资料映射和分页、数据权限、算法规则确认、宿主调度、内容系统及双库正式结果联调。Python旧业务/OP路径尚未全部删除，正常入口必须继续走Java，不能把旧路径当作已迁入的新业务能力。

后续[执行优化](../docs/算法执行优化记录_2026-11-03.md)新增公开依赖`DBUtils==3.2.0`，离线包需包含该wheel；连接池每进程最多16条、借用等待5秒，无启动预连接或定时器，先关闭执行器再关闭池。需结合宿主副本数及算法在途任务确认数据库连接配额。准备批次内2路打标尚不等于全局QPS控制，真实网关配额需另验。

Python失败任务已有持久化重试；Java失败任务的恢复仍需补业务入口，上轮真实模型验收包含人工恢复。上述预检不修复该业务状态，也不把失败任务改成成功。
