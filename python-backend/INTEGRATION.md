# content_planning 接入说明（0.3.0）

依据《strat-matrix Python 模块化改造方案》v1.1，运行代码统一封装到 `app/content_planning/`。独立运行和嵌入 FastAPI 使用同一份算法实现；本轮不调整 V19 权重、策略、配额、输入/提案哈希，也不迁移 Java 业务职责。

## 1. 两种运行方式

### 当前项目独立运行

在 `python-backend` 目录，使用 Python **3.10.11**：

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 6930
```

原 `/api/...` 路径与请求方法保留。`app/main.py` 只负责显式加载独立配置、创建应用及兼容函数导出；没有第二套算法。独立模式启动失败会退出。

### 嵌入已有 FastAPI

复制模块、资源并合并依赖后，在宿主创建应用处安装一次，须在宿主开始服务前执行：

```python
from fastapi import FastAPI
from app.content_planning import install_content_planning
from app.content_planning.config import PlanningConfig

app = FastAPI()  # 保留宿主原来的 lifespan、路由和异常处理
planning = install_content_planning(
    app,
    config_provider=lambda: PlanningConfig.from_mapping(host_config_snapshot()),
    prefix='/planning',
)
```

`host_config_snapshot()` 由接入方从自己的配置中心/密钥服务返回字典。它是示意函数，模块不强依赖特定 Apollo、宿主包名或私有 SDK。直接传 `config=PlanningConfig(...)` 也可以，与 `config_provider` 二选一。

**可运行示例**：`examples/minimal_host.py`。默认关闭，不需数据库即可验证宿主接入：

```bash
python -m uvicorn examples.minimal_host:app --host 127.0.0.1 --port 8000
# /health → 200；/planning/api/health → 503 planning_disabled
# /openapi.json 同时包含宿主与策划模块的接口定义
```

宿主自身只启动一个端口；转发使用 `httpx.ASGITransport`，不另启策划进程或回环 HTTP 端口。必须使用安装入口组合生命周期，不能只把子应用交给 ASGITransport 而省略启停。

Java 的 Python 基础地址改为 `http://<宿主>:<端口>/planning`，其余 `/api/...` 后缀保持原样。例如最终地址为 `/planning/api/internal/manual-computations`。真实 `PythonClient` 的契约测试已覆盖该拼接、令牌、请求体和 202 返回值。

## 2. 配置来源与优先级

| 内容 | 独立模式 | 宿主模式 |
| --- | --- | --- |
| 数据库账号 | `load_config()` 显式读取：传入/进程环境 > 根 `.env` > `docs/.env` | `PlanningConfig.database` 或 `PLANNING_MYSQL_*` |
| 连接地址、令牌、模型名 | MySQL `godp_system_config` | `config.settings` 显式值 > 注入的 `settings_provider()` 或 MySQL；连接配置可由宿主管理 |
| 生命周期条件、标签字典、映射、策略及版本 | 原 MySQL 表 | 原 MySQL 表，不变成宿主环境变量 |
| 冻结业务配置 | Java 下发带版本快照 | 同左，原校验语义保留 |
| 测试 override | 只由测试显式使用 | 不作为生产配置注入方式 |

没有模块导入时读取 `.env`、写 `os.environ` 的行为。配置过期后读取失败不继续使用旧密钥。各应用缓存独立，默认 5 秒；显式配置快照在创建应用时确定，修改该快照需重建应用，不能宣称已实现宿主动态热更新。

`examples/content-planning-config.example.json` 提供无真实凭据的示例。主要配置：

| 键 | 说明 |
| --- | --- |
| `CONTENT_PLANNING_ENABLED` | 默认 false；关闭不访问策划数据库/模型，不创建执行器 |
| `PLANNING_MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | 策划自有数据库，生产用 DML 账号 |
| `PLANNING_ENV` | inside/outside；沿用既有部署选择器，资料均按 Java HTTP 适配约定读取 |
| `PLANNING_JAVA_API_BASE_URL`、`PLANNING_JAVA_GATEWAY_URL`、`PLANNING_JAVA_API_TOKEN` | Java 资料能力与业务入口 |
| `PLANNING_INTEGRATION_TOKEN` | 调用策划内部接口的服务令牌；转发层不自动补令牌 |
| `PLANNING_MODEL_BASE_URL`、`PLANNING_ARK_API_KEY`、`PLANNING_MODEL_NAME`、`PLANNING_EMBEDDING_MODEL_NAME` | 模型网关及两类模型；其他已支持连接键可按 `PLANNING_` + 现有 catalog 键传入 |
| `PLANNING_MODEL_PROTOCOL` | `chat_completions` 或 `custom`；默认实现兼容 Chat Completions 和文本 Embeddings，未声称兼容 Responses |
| `PLANNING_MODEL_AUTHORIZATION_SCHEME`、`PLANNING_MODEL_HEADERS` | 默认 Bearer；附加头为字符串字典，不允许覆盖 Authorization、Host 或传输头 |
| `PLANNING_MAX_WORKERS`、`PLANNING_POOL_SIZE`、`PLANNING_POOL_TIMEOUT` | 默认 2、16、5 秒，均有范围校验 |
| `PLANNING_CACHE_SECONDS`、`PLANNING_MAX_FORWARD_BODY_BYTES` | 默认 5 秒、16MiB；请求大小上限可调整 |
| `PLANNING_RESOURCE_DIRECTORY` | 外置 SQL 资源的绝对目录，工具需要；运行健康检查不读取 SQL 文件 |
| `PLANNING_FIXTURE_PATH` | 仅显式选择 fixture 适配器时需要的绝对路径；正式资料来源仍是 Java |
| `PLANNING_WORKSPACE_DIRECTORY` | 只用于本工程开发/打包工具的绝对目录，生产运行无需提供 |

模型协议不同不能只改 URL。`custom` 必须通过 `PlanningDependencies(model_adapters={'text': ..., 'embedding': ...})` 提供两个适配器，每个实现 `post(model_config, path, payload) -> dict`，将结果归一到现有模型响应结构。默认适配器仍经过模型入口容量控制；宿主适配器默认由宿主管理，只有 `model_adapters_owned=True` 才在模块关闭时关闭。自定义适配器需负责其 HTTP 超时和协议转换。

可选 `PlanningDependencies` 还包含 `database_pool_factory(config)`、`settings_provider()`、`executor_factory(runtime)`、`source_adapter`、`production_adapter`。连接池须实现 `connection()` 上下文及 `close()`；工厂交出的池归模块所有，不要直接返回宿主其他业务共用的可关闭连接池。`settings_provider` 返回现有系统配置 catalog 的完整连接配置快照；不替代算法策略存储。

## 3. 资源与任务生命周期

1. 导入包/创建应用：只登记路由和依赖，不建立数据库连接、不调用模型、不启动后台任务。
2. 宿主启动：先进入原宿主 lifespan，再按开关启动策划配置校验、算法表就绪检查及受控执行器。
3. 宿主或 Java 发起唤醒：沿用原角色清单和受控线程池推进持久化任务。启动本身不扫描业务，不设 Python 定时器；定时调度仍归行内。
4. 后台线程显式继承 runtime 和操作人上下文；数据库池、系统配置缓存、模型容量预算及适配器按应用隔离。
5. 关闭：停止受理唤醒，等待当前执行轮次完成，再释放连接池和自有模型适配器，最后退出原宿主 lifespan。线程不能被强制安全中断；部署须给足优雅退出时间，异常退出依靠原租约/检查点恢复。

启动错误仅记录异常类型，不输出连接串或密钥；清理已创建资源后策划接口返回 **503 planning_not_ready**，宿主正常提供其余接口。关闭模块返回 **503 planning_disabled**。独立模式启动异常退出。单个 runtime 只启动一次，重启测试或应用须创建新实例。

同进程仍共享 CPU、内存和进程故障范围，容量控制是每个应用实例的限制，不是全机房分布式限流。多实例仍依赖原数据库租约、锁和幂等语义。

## 4. 接口、鉴权及 OpenAPI

默认宿主交付清单：健康接口、`/api/internal/*` 算法能力、标签词表 query/save 和标签查询/测试 OP。完整路径/方法记录在 `database/content_planning/routes.json`；运行后以宿主 `/openapi.json` 为准。

旧 Python 业务页面接口只保留独立运行兼容，默认不注册到宿主；当前三页面仍通过 Java 业务服务。可显式用 `allowed_routes=[...]` 缩小或扩展交付路径，但只能选择真实存在的路径，需单独审查兼容功能依赖。重复前缀、无效前缀、同路径方法冲突会拒绝安装。

策划中间件、服务令牌与异常处理仅在子应用生效。转发保留方法、原始查询参数/请求体、已有鉴权/审计头、有效状态码、二进制响应及 `Retry-After`；逐跳头会剔除。没有任意 URL 代理，没有自动提权。请求体最多 16MiB，响应当前按字节缓冲，超大导出需先评估内存。

OpenAPI 模型、所有 component 引用和 operationId 按安装前缀命名空间隔离；宿主模型、原路由标签及异常格式不变。HTTP 内部令牌安全声明会写入模块文档。接口文档不会因为共享端口而自动放开服务权限。

## 5. 数据库和交付工具

**25 张算法表不代表所有旧路径依赖满足。** 准备阶段仍有正式业务批次防重复查询，兼容自动调度和 Python 提交分支仍读写旧业务结构。具体表、分支及后续 Java 替换工作见 [数据库依赖说明](database/content_planning/README.md)。本轮保留这些校验，没有用删校验、建视图或跨库 SQL 掩盖问题。

```bash
# 离线核对 / 导出，不连接数据库
python -m tools.content_planning.schema check --resource-directory <SQL绝对目录>
python -m tools.content_planning.schema export --resource-directory <SQL绝对目录> --output <DDL输出文件>
python -m tools.content_planning.inspect_dependencies --output <依赖清单JSON>

# 无密钥的模块交付包：源码、SQL、最小宿主、测试、依赖、哈希清单
python -m tools.content_planning.export_module --output <交付ZIP绝对路径>
```

从其他工作目录调用时，用宿主安装的包或显式 `PYTHONPATH=<python-backend绝对目录>`。SQL 路径通过参数指定。运行模块无需保留本仓库前端目录，初始标签树已经放入模块 `assets/`。

`tools/content_planning/initialize.py` 是显式初始化入口，必须传 `--apply` 和 SQL 目录。其他旧迁移/诊断工具随命名空间调整为 `python -m app.content_planning.<工具>`；涉及行外 Java 配置桥、全项目打包、演示数据的工具需要当前开发工程或显式 workspace，不作为仅复制模块后可直接使用的生产能力。模块交付不含当前项目 `app/main.py`、standalone 配置、真实 `.env`、私有适配器、日志、虚拟环境或生成内容。

## 6. 验证入口与边界

在仓库根目录，以应用 Python 3.10.11 环境运行：

```bash
python -m testing --suite python
python -m testing --suite algorithm --dataset small --output <新目录>
```

宿主专测可在 `python-backend` 执行：

```bash
python -m pytest -q tests/content_planning
```

测试使用注入的池/配置/模型响应验证模块生命周期、转发、鉴权、并发容量和包迁移，不会访问真实 MySQL 或公网模型。测试包含真实 HTTPX 进程内 ASGI 请求，但不能代替行内现有宿主依赖版本和真实模型网关联调。

依赖基线：Python 3.10.11、FastAPI 0.136.1、Starlette 1.3.1、Uvicorn 0.46.0、Pydantic 2.13.3、PyMySQL 1.1.1、DBUtils 3.2.0，新增 HTTPX 0.28.1 用于进程内转发。全部以 `requirements.txt` 为准；与宿主同进程必须共同解析/验证版本，不能在同一环境同时装两套不兼容 FastAPI。Starlette 当前测试客户端依赖的 httpx2 不等同于本模块 HTTPX ASGITransport。

本轮的实测结果、交付方式和未验证事项见 [模块改造验收记录](VALIDATION.md)，具体文件哈希在交付 ZIP 的 `module-manifest.json` 及旁侧 `.sha256` 文件。此前三页面验收包属于此前冻结版本，不能当成本轮代码的截图验收证据。
