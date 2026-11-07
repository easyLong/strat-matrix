# 阿里云部署：复用当前两库

更新日期：2026-11-05。适用于将当前版本部署到一台Linux ECS，继续使用现有`strat_matrix`算法库和`strat_matrix_bus`业务库。当前两库已完成公共字段升级，不再重建、清库、导入历史或执行演示种子。

```text
浏览器 → ECS Nginx:80/443 → Vue页面:930
                         → /api/ → Java:6931 → Python:6930
                                      ↓              ↓
                                strat_matrix_bus  strat_matrix
```

这是行外部署，继续使用`outside`模拟资料接入。`inside`用于实际嵌入客户工程，不应仅因部署到服务器而切换。

## 1. 准备运行环境

服务器操作系统尚未确认，软件安装命令需按实际发行版选择。运行版本与当前项目保持一致：

| 工具 | 本项目版本/要求 |
| --- | --- |
| Python | 3.10.11，需可创建venv |
| Node.js / npm | 16.13.0 / 8.1.0，含构建用开发依赖 |
| Java | JDK 8 |
| Maven | 本地验证使用3.9.9，可构建Java项目 |
| 其他 | Git、curl、Nginx |

安装后核对`python3.10 --version`、`node -v`、`npm -v`、`java -version`和`mvn -v`。若Python路径不同，下文用实际3.10.11解释器替换`python3.10`。Windows的`.venv`、`node_modules`及`.tmp-tools`不可直接复制到Linux运行。

## 2. 获取代码与安装依赖

以下使用已有部署目录`/data/strat-matrix`。首次部署先在其父目录执行`git clone https://github.com/easyLong/strat-matrix.git strat-matrix`；已有仓库先查看`git status --short`，保留服务器上的未提交改动，不用强制重置覆盖。

```bash
cd /data/strat-matrix
git pull --ff-only origin main
python3.10 -m venv python-backend/.venv
python-backend/.venv/bin/python -m pip install -r python-backend/requirements.txt
cd frontend
npm ci --include=dev
cd ..
```

若是更新已有服务器，先按第5节停止服务器旧进程，并确认退出后再拉取、构建Java。GitHub只能取得已提交并推送的代码；本地未提交修复不在其中。本次“替换选题”修复尚未提交，发布该修复前需先提交并推送，或受控上传对应修改。

## 3. 单独准备连接配置和模拟资料

根目录`.env`填写现有数据库连接，包含两库的参数。服务器已有正确文件时直接保留，不用示例覆盖。

```dotenv
MYSQL_HOST=现有数据库地址
MYSQL_PORT=3306
MYSQL_USER=算法库账号
MYSQL_PASSWORD=算法库密码
MYSQL_DATABASE=strat_matrix
JAVA_MYSQL_HOST=现有业务数据库地址
JAVA_MYSQL_PORT=3306
JAVA_MYSQL_USER=业务库账号
JAVA_MYSQL_PASSWORD=业务库密码
JAVA_MYSQL_DATABASE=strat_matrix_bus
```

显式填写`JAVA_MYSQL_DATABASE`，否则代码默认使用`MYSQL_DATABASE`加`_business`，与当前业务库名称不同。端口、模型、令牌和部署模式继续读取算法库`godp_system_config`，不重复写进`.env`。这些配置与本地共享，修改会影响本地；当前同机三服务地址应为Java回环6931及Python回环6930，不能保留仅本地电脑可用的局域网地址。

通过安全文件传输，把本地`run/bank-source-fixture.json`放到服务器同一相对位置：

```text
/data/strat-matrix/run/bank-source-fixture.json
```

该文件提供账号、选题等行外模拟资料，不在数据库或Git仓库内。只复制文件，不上传整个`run`目录，避免带入Windows进程PID、旧配置、日志和含密钥的备份。`run/java-backend.properties`由服务器启动时重新生成，不复制本地版本。

```bash
cd /data/strat-matrix
mkdir -p run
chmod 600 .env run/bank-source-fixture.json
```

数据库需允许ECS实际连接出口地址，账号需具备对应库权限。若`.env`中的地址是本地网络地址，ECS必须有可达链路；仅复制同样的地址不能保证云端能连接。

## 4. 数据库只读核查

```bash
cd /data/strat-matrix
python-backend/.venv/bin/python python-backend/tools/migrate_table_audit.py \
  --check --output run/ecs-audit-check
cd python-backend
.venv/bin/python -m app.deployment_environment check
cd ..
```

当前两库已经升级，以上只核查，不加`--apply`。不要执行历史`seed_*`、重复迁移历史或把`app.init_db`当作部署必需命令。若核查提示缺表或缺字段，先核对是否连错库或服务器代码版本过旧。

## 5. 启动三个服务

**先停止本地电脑服务及服务器旧实例，避免两边同时推进同一数据库任务；正在计算的任务应先等待退出。** 当前启动器的Java outside开发壳会发出调度信号，不是只提供页面查询。

```bash
cd /data/strat-matrix
bash stop.sh
bash start.sh
bash status.sh
```

`start.sh`会构建Java、生成Linux运行配置、启动Java与Python、构建前端并启动930预览服务。它不是重启命令，已运行进程会跳过。使用`bash`执行即可，不必为启动脚本修改Git文件权限。启动脚本的进程启动提示不代表已就绪，等待后检查状态和日志。

```bash
curl -f http://127.0.0.1:6930/api/health
curl -f http://127.0.0.1:6931/api/plan/service-health
curl -f http://127.0.0.1:930/
tail -n 80 logs/backend.log
tail -n 80 logs/java-backend.log
tail -n 80 logs/frontend.log
```

Java健康接口只代表Java服务存活，还需在页面核查配置历史、账号和任务列表。启动可能推进既有任务并触发模型调用；模型账户未恢复时，不能将页面可访问视为算法验收通过。无需单独启动Worker。

## 6. 对外访问

临时评审可在阿里云ECS安全组和操作系统防火墙中，仅对评审者IP开放TCP930，访问`http://服务器公网IP:930/`。6930和6931作为内部通信端口，不作为页面入口。当前outside使用测试身份，限制评审来源IP；不要按已接入真实登录权限的系统对公网开放。

稳定入口使用Nginx80/443，示例见[nginx.conf.example](../deploy/nginx.conf.example)。修改`server_name`为实际域名或服务器地址，将文件放入服务器Nginx实际的配置include目录，执行：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

阿里云安全组与系统防火墙也需允许对应入口端口。示例核心转发为：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:6931/api/plan/;
}
location / {
    proxy_pass http://127.0.0.1:930;
}
```

保留`/api/plan/`及结尾斜杠，浏览器`/api/query/plans`须到Java`/api/plan/query/plans`。Vue不直接调用Python。正式长期部署时可由Nginx直接托管构建产物`frontend/dist`，并使用systemd管理Java/Python；当前根目录脚本采用前端预览进程，未配置开机自启。

安全组操作参考[阿里云官方说明](https://www.alibabacloud.com/help/en/ecs/user-guide/security-group-rules)。

## 7. 验收与后续更新

页面检查：AI策划配置与历史配置、策划任务列表、账号/时间列表、策划详情及替换选题。先只读核查，确认数据来自同一两库、模拟资料ID相符，再提交测试任务。

后续正常更新：停止旧服务 → `git pull --ff-only origin main` → 更新Python依赖 → 按当次发布说明处理必要迁移 → `bash start.sh` → `bash status.sh`。本地调试服务不要同时恢复同库调度。数据库密码、内部令牌、模拟资料和备份不提交GitHub。

本说明基于当前仓库实现核对，尚未登录ECS执行安装、发布或外网验收。首次空库部署需另按两侧建表与配置初始化流程，不适用本文复用现有数据库的前提。
