# strat-matrix 服务器部署说明

单账号普通选题闭环新增流程Worker及持久化任务表，迁移命令为 `cd backend && python -m app.init_workflow_db`。现有启动脚本已接入迁移和Worker管理，运行及验收说明见 [ORDINARY_WORKFLOW.md](ORDINARY_WORKFLOW.md)。内容生产默认关闭；本地模拟模式须显式配置。

本文档适用于一台 Linux 服务器，采用以下进程结构：

- FastAPI 后端：`127.0.0.1:6930`
- Vite Preview 前端：`127.0.0.1:930`
- Nginx：对外提供 80/443 端口，并将 `/api/` 转发到后端
- MySQL：使用项目根目录 `.env` 中的数据库配置

生产环境建议使用域名和 HTTPS。项目脚本负责启动、停止和查看前后端进程，Nginx 建议交给系统服务管理。

## 1. 服务器准备

以 Ubuntu/Debian 为例：

```bash
sudo apt update
sudo apt install -y git curl nginx python3 python3-venv python3-pip nodejs npm
```

建议 Node.js 使用 20 LTS 或更高版本，Python 使用 3.11 或更高版本。

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

MySQL `godp_system_config` 保存前后端监听地址/端口、模型标识和鉴权密钥，见[系统配置说明](SYSTEM_CONFIG.md)。安装后端依赖后，在 `backend` 执行 `python -m app.init_system_config --migrate-env --clean-env` 初始化当前配置并物理删除其余旧参数。需要跨系统接口时，再设置 `INTEGRATION_TOKEN`。

页面作为整体业务模块嵌入客户系统，直接进入策划配置、AI自动策划、手动策划和策划结果。登录、用户账号和角色由宿主系统负责。当前人工操作审计统一标记为“运营人员”，自动任务标记为 `system`。

`/api/integrations/` 和 `/api/internal/` 下的系统接口使用 `X-Integration-Token` 机器令牌。

服务默认监听 `0.0.0.0:6930` 和 `0.0.0.0:930`。阿里云安全组需开放对应端口；经 Nginx 访问时只需对外开放 80/443。

确认数据库账号已经拥有 `strat_matrix` 数据库及项目表的读写权限。初始化或补齐表结构：

```bash
cd /opt/strat-matrix
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
(cd backend && .venv/bin/python -m app.init_db)
```

如果需要初始化演示数据，再执行：

```bash
(cd backend && .venv/bin/python -m app.seed_prototype)
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

1. 选择Python：显式`PYTHON_BIN`优先，其次项目`backend/.venv/bin/python`，再尝试系统`python3`/`python`；检查已启用模型进程的必要配置。
2. 启动尚未运行的FastAPI后端。
3. 启动周度规则策划与热点调度进程（默认开启，按服务端配置的北京时间执行）。
4. 标签、选题向量、账号向量及 AI 准备 Worker 默认不随服务启动；需要时手动启动对应 Worker。
5. 默认执行前端生产构建；前端依赖缺失或 `node_modules/@types/node` 不存在时执行 `npm ci --include=dev`，确保 TypeScript、Vite 和 Node 类型依赖完整。前端构建在前端启动前、后端启动后进行。
6. 启动尚未运行的Vite Preview前端，将PID写入`run/`、日志写入`logs/`。

Matching Executor Worker 默认关闭。完成匹配策略审批后，如需处理 V1/V2 匹配任务，可通过进程环境变量启动：`MATCHING_EXECUTOR_WORKER_ENABLED=1 ./start.sh`；查看状态时使用 `MATCHING_EXECUTOR_WORKER_ENABLED=1 ./status.sh`。默认启动不会消费匹配队列。

`start.sh` 检测到 PID 对应进程已运行时会跳过该服务。更新代码后，按第 8 节停止旧进程再启动。前端构建和进程目录采用项目默认值，监听地址与端口从配置表读取。

默认端口：

```text
后端：6930
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
tail -f logs/ordinary-scheduler.log
tail -f logs/hotspot-scheduler.log
tail -f logs/account-vector-worker.log
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

- `/api/` 转发到 `127.0.0.1:6930`
- 页面请求转发到 `127.0.0.1:930`

如果使用 HTTPS，可通过 Certbot 配置证书：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.example.com
```

## 7. 常用系统配置

MySQL `godp_system_config` 保存服务监听地址/端口、模型标识和鉴权密钥；Worker 开关及其它运行参数使用项目默认值。定位项目及解释器的启动选项可在命令行指定：

```bash
APP_ROOT=/opt/strat-matrix \
PYTHON_BIN=/opt/strat-matrix/backend/.venv/bin/python \
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
backend/.venv/bin/pip install -r backend/requirements.txt
(cd backend && .venv/bin/python -m app.init_system_config --migrate-env --clean-env)
(cd backend && .venv/bin/python -m app.init_db)
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
(cd backend && .venv/bin/python -m app.init_db)
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
