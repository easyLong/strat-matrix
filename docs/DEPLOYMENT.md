# strat-matrix 服务器部署说明

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
INTEGRATION_TOKEN=请替换成随机长字符串
BACKEND_HOST=127.0.0.1
BACKEND_PORT=6930
FRONTEND_HOST=127.0.0.1
FRONTEND_PORT=930
ORDINARY_SCHEDULER_ENABLED=1
```

For direct public access on Alibaba Cloud, set BACKEND_HOST and FRONTEND_HOST to 0.0.0.0 and allow TCP 930 in the security group. With Nginx, expose only ports 80/443 and keep backend port 6930 private.

确认数据库账号已经拥有 `strat_matrix` 数据库及项目表的读写权限。初始化或补齐表结构：

```bash
cd /opt/strat-matrix
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python -m app.init_db
```

如果需要初始化演示数据，再执行：

```bash
backend/.venv/bin/python -m app.seed_prototype
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

1. 检查 `backend/.venv`。
2. 启动 FastAPI 后端。
3. 执行前端生产构建；依赖不存在时执行 `npm ci`。
4. 启动普通内容周策划调度进程（默认开启，按服务端配置的北京时间执行）。
5. 启动 Vite Preview 前端。
6. 将 PID 写入 `run/`，日志写入 `logs/`。

默认端口：

```text
后端：6930
前端：930
```

首次只构建一次时可以：

```bash
BUILD_FRONTEND=1 ./start.sh
```

如果只重启服务、不重新构建前端：

```bash
BUILD_FRONTEND=0 ./start.sh
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

## 7. 常用环境变量

脚本支持通过环境变量调整路径和端口：

```bash
APP_ROOT=/opt/strat-matrix \
BACKEND_PORT=6930 \
FRONTEND_PORT=930 \
BUILD_FRONTEND=0 \
./start.sh
```

可用变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ROOT` | 脚本所在目录 | 项目根目录 |
| `PYTHON_BIN` | 自动选择 `.venv/bin/python`，否则使用 `python3` | 后端 Python |
| `NPM_BIN` | `npm` | Node 包管理器 |
| `BACKEND_HOST` | `127.0.0.1` | 后端监听地址 |
| `BACKEND_PORT` | `6930` | 后端端口 |
| `FRONTEND_HOST` | `127.0.0.1` | 前端监听地址 |
| `FRONTEND_PORT` | `930` | 前端端口 |
| `CHECK_HOST` | `127.0.0.1` | Local health-check address when services bind to `0.0.0.0` |
| `BUILD_FRONTEND` | `1` | 是否在启动前构建前端 |
| `RUN_DIR` | `run` | PID 文件目录 |
| `LOG_DIR` | `logs` | 日志目录 |
| `ORDINARY_SCHEDULER_ENABLED` | `1` | 是否启动普通内容周策划调度进程；设为 `0` 后重启服务停用 |

## 8. 发布更新流程

```bash
cd /opt/strat-matrix
./stop.sh
git pull
backend/.venv/bin/pip install -r backend/requirements.txt
BUILD_FRONTEND=1 ./start.sh
./status.sh
sudo nginx -t && sudo systemctl reload nginx
```

如果更新涉及数据库结构，先备份数据库，再执行 `backend/.venv/bin/python -m app.init_db`。

## 9. 故障排查

### 后端启动失败

```bash
cat logs/backend.log
backend/.venv/bin/python -m app.init_db
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

可以通过 `BACKEND_PORT` 和 `FRONTEND_PORT` 修改端口，并同步修改 Nginx 配置。
