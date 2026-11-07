# strat-matrix 服务器部署说明

**当前阿里云部署优先阅读[复用现有两库部署步骤](ALIYUN_DEPLOYMENT.md)**。下方包含历史升级说明，不能作为新版本从头顺序执行的命令清单；当前两库已升级时不要重复建库、迁历史或运行演示种子。

环境名称现统一为`outside`和`inside`，由MySQL中的`PLANNING_ENV`选择。先阅读[双环境切换](双环境切换_V0.1.md)；下文旧`local_development`／`bank`名称作为兼容说明，不能在显式设置统一模式后继续作为独立开关。

日常outside与完整验收已[统一到Java资料入口](统一资料链路_2026-11-03.md)。升级需同时构建Java、更新Python并重新生成本地Java配置，不能只替换其中一个服务。`run/bank-source-fixture.json`及私有配置不随Git交付，新环境须准备自己的模拟资料文件；缺失时明确返回503，不创建假成功数据。升级后在仓库根目录运行`python -m testing.source_verify`只读核查，真实模型验收使用`python -m testing.live --execute`并遵守暂停调度要求。

后续营销/热点增量不新增表或字段，需重新构建Java以更新MyBatis查询及业务服务。热点现在由宿主每日触发“明日空槽检查”，不再配置Python热点定时器或22:00门槛；行外已有脉冲按日模拟。真实验收可按[增量记录](营销热点与模拟内容衔接验收_2026-11-03.md)运行，测试数据仍只保留在本地。

**2026-11-03三工程更新：** 仓库包含[Vue](../frontend/README.md)、[Java](../java-backend/README.md)、[Python](../python-backend/README.md)三个独立子项目，未来分别嵌入客户已有工程。本地页面经Java6931访问业务库，Java委派Python执行算法。配置发布、正式结果、热点/营销业务、历史查询与报表已完成本轮迁移，真实内容方、身份和宿主调度待接。发布顺序与实测证据以[双库迁移记录](双库业务迁移与验收_2026-11-03.md)为准。本地一键启动需要JDK及Maven；bank模式不启动本地Java，改用客户已有Java服务。

存量部署必须先停止旧版本业务写入并备份两库，再按上述记录发布业务库 V3/V4/V5、算法库 Pipeline 迁移、配置及历史导入。只执行下方历史的 `app.init_db` 不足以升级Java业务库。确认迁移后再启用 `planning.history.mode=business_only`、`planning.config-release.enabled=true`、`planning.auto-schedule.enabled=true` 及 `AUTO_SCHEDULE_OWNER=java`；新生成的本地配置已使用这些开关。新环境仍需自行初始化数据源与已批准的算法策略，不能直接使用本地验收账号和策略编号。

当前启动脚本只运行Vue、Java和Python三个服务。后台执行已并入Python，Java本地开发壳模拟宿主触发；驻场不复制该本地调度配置，由客户调度平台调用内部唤醒客户端。详见[服务内后台执行](BACKGROUND_EXECUTION.md)。

2026-10-28 升级新增营销任务总分配数量字段。已有部署应先在 `python-backend` 目录执行 `python -m app.init_manual_marketing_db`，再构建前端并重启后端；具体命令与兼容边界见[近期修改汇总](近期修改汇总_2026-10-28.md)。营销创建请求已改为单个选题和总分配数量，前后端须同时更新。

单账号普通选题闭环使用已有持久化任务表，迁移命令为`cd python-backend && python -m app.init_workflow_db`。流程处理函数已由服务内执行器调用；内容生产默认关闭，本地模拟须显式配置。

本文档适用于一台 Linux 服务器，采用以下进程结构：

目录迁移说明：Python子项目现为`python-backend/`。更新旧部署前先停止旧服务；如果原来使用`backend`目录下的虚拟环境，需在新目录重新创建环境并安装依赖，不能直接搬用包含旧绝对路径的虚拟环境。使用系统pip的部署无需重建虚拟环境。现有`logs/backend.log`及`run/backend.pid`名称保留兼容，不代表源码仍位于旧目录。

- FastAPI 后端：`127.0.0.1:6930`
- Java本地开发壳：`127.0.0.1:6931`
- Vite Preview 前端：`127.0.0.1:930`
- Nginx：对外提供80/443，将`/api/`映射到Java的`/api/plan/`
- MySQL：使用项目根目录 `.env` 中的数据库配置

生产环境建议使用域名和 HTTPS。项目脚本负责启动、停止和查看前后端进程，Nginx 建议交给系统服务管理。

## 1. 服务器准备

以 Ubuntu/Debian 为例：

```bash
sudo apt update
sudo apt install -y git curl nginx python3 python3-venv python3-pip nodejs npm
```

当前项目兼容基线为Node.js 16.13.0、npm 8.1.0、Python 3.10.11及JDK 8；按该基线准备环境，不再沿用早期Node20/Python3.11的建议。

Java开发壳按Java8兼容开发；安装客户兼容的JDK及Maven，确认`java -version`和`mvn -version`可执行。`start.sh`默认构建Java；已离线准备好jar时可用`BUILD_JAVA=0`，工具路径可通过`JAVA_BIN`、`MVN_BIN`指定。不要复制内部框架依赖作为行外启动前提。

## 2. 上传项目

```bash
sudo mkdir -p /opt/strat-matrix
sudo chown -R "$USER":"$USER" /opt/strat-matrix
cd /opt/strat-matrix

# 任选一种方式
git clone <你的仓库地址> .
# 或将本地项目文件上传到 /opt/strat-matrix
```

不要上传本地的 `frontend/node_modules`、`frontend/dist`、`.tmp-*` 和本地数据库密码文件副本。

## 3. 配置数据库

在项目根目录创建 `.env`：

```bash
cp .env.example .env
vi .env
```

至少配置：

```dotenv
MYSQL_HOST=数据库地址
MYSQL_PORT=3306
MYSQL_USER=数据库账号
MYSQL_PASSWORD=数据库密码
MYSQL_DATABASE=strat_matrix
```

MySQL `godp_system_config` 保存前后端监听地址/端口、模型标识和鉴权密钥，见[系统配置说明](SYSTEM_CONFIG.md)。安装后端依赖后，在 `python-backend` 执行 `python -m app.init_system_config --migrate-env --clean-env` 初始化当前配置并物理删除其余旧参数。需要跨系统接口时，再设置 `INTEGRATION_TOKEN`。

页面作为整体业务模块嵌入客户系统，一级页面为 AI策划配置、人工策划和策划结果。登录、用户账号和角色由宿主系统负责。当前人工操作审计统一标记为“运营人员”，自动任务标记为 `system`。

`/api/integrations/` 和 `/api/internal/` 下的系统接口使用 `X-Integration-Token` 机器令牌。

已有Python和前端默认监听`0.0.0.0:6930`、`0.0.0.0:930`；Java本地壳只监听回环地址6931，经前端或Nginx访问。生产外部入口应收口网关，不将Python内部管理接口作为浏览器入口。

确认数据库账号已经拥有 `strat_matrix` 数据库及项目表的读写权限。初始化或补齐表结构：

```bash
cd /opt/strat-matrix
python3 -m venv python-backend/.venv
python-backend/.venv/bin/pip install -r python-backend/requirements.txt
(cd python-backend && .venv/bin/python -m app.init_db)
```

如果需要初始化演示数据，再执行：

```bash
(cd python-backend && .venv/bin/python -m app.seed_prototype)
```

生产环境不要执行演示数据脚本。

## 4. 启动服务

给脚本增加执行权限：

```bash
chmod +x start.sh stop.sh status.sh
```

启动：

```bash
./start.sh
```

`start.sh` 会完成以下工作：

1. 选择Python：显式`PYTHON_BIN`优先，其次项目`python-backend/.venv/bin/python`，再尝试系统`python3`/`python`；检查已启用模型进程的必要配置。
2. local模式构建并启动Java开发壳，从库内配置生成本地启动文件；bank模式使用客户已有Java。
3. 启动尚未运行的FastAPI后端。
4. FastAPI初始化服务内执行器，Java local profile发出带令牌的执行信号；不启动独立Worker。若旧Worker仍运行则要求先stop，避免升级时重复执行。
5. 默认执行前端生产构建；前端依赖缺失或 `node_modules/@types/node` 不存在时执行 `npm ci --include=dev`，确保 TypeScript、Vite 和 Node 类型依赖完整。前端构建在前端启动前、后端启动后进行。
6. 启动尚未运行的Vite Preview前端，将PID写入`run/`、日志写入`logs/`。

不再使用Worker开关或额外终端启动后台进程。Java内部令牌需由库内配置生成；bank模式由客户Job负责周期触发和恢复扫描。

`start.sh` 检测到 PID 对应进程已运行时会跳过该服务。更新代码后，按第 8 节停止旧进程再启动。前端构建和进程目录采用项目默认值，监听地址与端口从配置表读取。

默认端口：

```text
后端：6930
Java：6931（本地开发壳，JAVA_GATEWAY_URL可指定回环地址及端口）
前端：930
```

## 5. 查看和停止

查看进程及接口健康状态：

```bash
./status.sh
```

停止：

```bash
./stop.sh
```

日志：

```bash
tail -f logs/backend.log
tail -f logs/frontend.log
tail -f logs/java-backend.log
```

后端健康检查：

```bash
curl http://127.0.0.1:6930/api/health
```

## 6. 配置 Nginx

复制示例配置并修改域名：

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/strat-matrix
sudo vi /etc/nginx/sites-available/strat-matrix
sudo ln -s /etc/nginx/sites-available/strat-matrix /etc/nginx/sites-enabled/strat-matrix
sudo nginx -t
sudo systemctl reload nginx
```

配置文件将：

- `/api/`转发到Java；示例使用本地6931，行内改为客户Java服务实际地址
- 页面请求转发到 `127.0.0.1:930`

如果使用 HTTPS，可通过 Certbot 配置证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.com
```

## 7. 常用系统配置

MySQL `godp_system_config`保存服务监听地址／端口、模型标识和鉴权密钥；后台并发采用代码默认值，不再通过Worker开关启动独立进程。定位项目及解释器的启动选项可在命令行指定：

```bash
APP_ROOT=/opt/strat-matrix \
PYTHON_BIN=/opt/strat-matrix/python-backend/.venv/bin/python \
./start.sh
```

以下是启动引导选项，不写入配置表：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ROOT` | 脚本所在目录 | 项目根目录 |
| `PYTHON_BIN` | 自动选择 `.venv/bin/python`，否则使用 `python3` | 后端 Python |
| `NPM_BIN` | `npm` | Node 包管理器 |

服务端口默认是后端 `6930`、前端 `930`，可在 `godp_system_config` 配置。模型 ID 与密钥的设置方式见[系统配置说明](SYSTEM_CONFIG.md)。

## 8. 发布更新流程

```bash
cd /opt/strat-matrix
./stop.sh
git pull --ff-only origin main
python-backend/.venv/bin/pip install -r python-backend/requirements.txt
(cd python-backend && .venv/bin/python -m app.init_system_config --migrate-env --clean-env)
(cd python-backend && .venv/bin/python -m app.init_db)
./start.sh
./status.sh
sudo nginx -t && sudo systemctl reload nginx
```

若更新涉及数据库结构，执行初始化前先备份数据库；`app.init_db` 会按建表脚本补齐新表、字段及中文注释，并保留已有业务记录。

更新后核对`/api/tag-taxonomy`：新版`tags.T1`为启用标签名称数组，`items.T1`为包含`id/name/enabled`的对象数组。若仍只有对象形式的`tags`而没有`items`，应检查后端是否仍为旧进程、代理目标是否正确；前后端必须部署对应版本。确认资源更新后再强制刷新浏览器。接口兼容细节见[标签字典契约](TAG_TAXONOMY.md)。

批次账号画像版本新增 `godp_account_profile`，更新代码后须先执行上面的初始化命令，再启动策划调度器。新正式批次会同时保存账号画像与向量准备状态；旧批次不使用当前账号数据补造历史画像。内部接口和账号向量进程配置见[批次账号画像与向量准备](ACCOUNT_PROFILE_VECTOR.md)。账号向量进程默认关闭；启用后启动脚本检查全局模型凭据和内部接口令牌。

正式AI准备版本新增 `godp_ai_preparation`、`godp_ai_preparation_account`、`godp_ai_preparation_topic`，也须先运行初始化命令。规则策划会检查该周期的AI准备占用，取消准备后恢复规则调度的周期生成资格。新增推进进程默认关闭；账号和选题向量统一使用系统配置中的全局向量模型。账号向量进程已兼容运营批次和准备记录两种身份；接口、命令和新进程运维见[正式AI输入准备流程](AI_PREPARATION.md)。

匹配执行基础版本新增 `godp_matching_policy`、`godp_matching_task`、`godp_matching_attempt`，更新后先初始化数据库并重启后端。策略版本和租约任务接口见[算法策略及执行任务](MATCHING_EXECUTION.md)。本轮无新增常驻匹配执行器，不会自动创建策略、调用模型或提交运营策划结果。

补充输入版本新增 `godp_matching_input_snapshot` 及任务表的 `contract_version`、`supplemental_hash`，仍先运行初始化命令再重启后端。旧任务默认保留第一版，不回填补充事实或改变指纹。第二版策略与历史 `topic_type` 可选扩展见[补充输入快照](MATCHING_SUPPLEMENTAL_INPUTS.md)，本轮没有新增环境变量或常驻进程。

## 9. 故障排查

### 后端启动失败

```bash
cat logs/backend.log
(cd python-backend && .venv/bin/python -m app.init_db)
```

重点检查 `.env`、数据库网络访问、数据库授权和 Python 依赖。

### 前端页面能打开但接口失败

```bash
curl http://127.0.0.1:6930/api/health
sudo nginx -t
tail -f logs/backend.log
```

重点检查 Nginx 的 `/api/` 转发规则，确认没有把 `/api` 改写成错误路径。

### 端口被占用

```bash
ss -lntp | grep -E ':6930|:930'
```

当前服务端口默认是后端 `6930`、前端 `930`，可在 MySQL 配置中调整；若经 Nginx 对外提供服务，还需同步调整 Nginx 配置。
