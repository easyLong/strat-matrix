# 阿里云查看部署：系统Python与共享数据库

更新日期：2026-11-09。云端直接使用系统python，不创建虚拟环境；继续连接本地相同的strat_matrix和strat_matrix_bus。云端只用于远程查看，关闭云端调度，本地任务继续正常运行。不重新建库、导入历史或初始化演示数据。

浏览器→前端930→Java回环6931→Python回环6930。前端只访问Java。当前三工程已删除旧HTTP兼容入口，必须发布同一版本。

## 1. 运行环境与代码

Python3.10.11、Node16.13.0/npm8.1.0、JDK8、Maven。安装方式按服务器实际Linux发行版选择；不复制Windows解释器、node_modules或工具目录。

服务器已存在仓库时先查看git status，保留服务器上的未提交修改。当前最新代码在feature/planning-v2，不能拉main后误认为取得该分支更新。

```bash
cd /data/strat-matrix
git switch feature/planning-v2
git pull --ff-only origin feature/planning-v2
python --version
node -v
java -version
python -m pip install -r python-backend/requirements.txt
mvn -f java-backend/pom.xml -Pdev -DskipTests package
cd frontend
npm ci --include=dev
npm run build
cd ..
mkdir -p run logs
```

更新已有运行服务时，先按第5节停止旧服务再拉取、构建和启动；只运行start.sh不会替换已运行PID。

## 2. 配置与资料

根.env沿用现有MySQL连接，包含MYSQL_*及JAVA_MYSQL_*，明确JAVA_MYSQL_DATABASE=strat_matrix_bus；服务器必须能连接数据库。端口、令牌和部署模式仍读取godp_system_config，不把密钥写进命令或Git。

行外模式保持outside；同机Java/Python通信使用回环地址和6931/6930。共享的JAVA_GATEWAY_URL、JAVA_API_BASE_URL不能指向仅公司电脑可访问的局域网地址。修改库内配置会同时影响本地，优先让两边都使用相同回环端口。

单独复制本地run/bank-source-fixture.json到服务器相同相对路径。当前账号、选题的行外基础资料由Java读取该文件；只共用数据库不等于该文件自动同步。不要上传整个run目录、Windows PID或旧Java配置。

```bash
chmod 600 .env run/bank-source-fixture.json
```

共享业务库已于2026-11-09补齐V8扫描索引、V9两字段及三视图；同一个库不要重复执行ALTER或初始化。不同数据库先核对版本，再走DBA发布流程。修复及数据校验见[运行记录](页面POST接口404修复_2026-11-09.md)。

## 3. 启动Python和Java

```bash
cd /data/strat-matrix/python-backend
python -m app.deployment_environment check
python -m app.java_development --output ../run/java-backend.properties
nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 6930 \
  > ../logs/backend.log 2>&1 < /dev/null &
echo $! > ../run/backend.pid
```

确认Python健康后启动Java；生成的properties包含凭据，不提交Git。

```bash
curl -f http://127.0.0.1:6930/api/health
cd /data/strat-matrix/java-backend
nohup java -jar godp-planning-server/target/planning-business.jar \
  --spring.config.additional-location=file:../run/java-backend.properties \
  --planning.manual.initialize-schema=false \
  --planning.local-pulse.enabled=false \
  > ../logs/java-backend.log 2>&1 < /dev/null &
echo $! > ../run/java-backend.pid
```

必须使用godp-planning-server/target下的当前JAR；旧java-backend/target/planning-business.jar不是新代码。关闭initialize-schema避免启动改表；关闭local-pulse避免云端扫描和推进共享任务。无需单独启动Worker。

## 4. 启动前端与外网访问

```bash
cd /data/strat-matrix/frontend
PLANNING_ENV=outside JAVA_GATEWAY_URL=http://127.0.0.1:6931 \
nohup node node_modules/vite/bin/vite.js preview --host 0.0.0.0 --port 930 \
  > ../logs/frontend.log 2>&1 < /dev/null &
echo $! > ../run/frontend.pid
```

ECS安全组和系统防火墙只需向你的公网IP开放TCP930；6930/6931不对公网开放。访问http://服务器公网IP:930/。长期使用可按deploy/nginx.conf.example统一80/443入口；当前outside使用测试身份，页面并非强制只读，编辑会直接修改共享数据。

## 5. 检查、停止和故障定位

```bash
cd /data/strat-matrix
PYTHON_BIN="$(command -v python)" bash status.sh
curl -f http://127.0.0.1:6931/api/plan/service-health
curl -f -X POST -H 'Content-Type: application/json' \
  -d '{}' http://127.0.0.1:930/api/config/query
tail -n 80 logs/backend.log
tail -n 80 logs/java-backend.log
tail -n 80 logs/frontend.log
# 停止云端三个服务，不影响公司电脑的服务
PYTHON_BIN="$(command -v python)" bash stop.sh
```

当前先不用根start.sh，它仍包含旧数据库初始化。没有额外Python环境时status/stop也显式传系统python路径。

如果health正常但POST /api/config/query返回404，先检查Java进程实际运行JAR位置与版本；不要恢复旧GET接口。缺write_state/write_cursor则说明连到了未升级的另一个业务库，先核对.env，不用初始化数据来处理。

本记录根据本机真实修复整理，尚未登录阿里云执行远程部署或外网验收。
