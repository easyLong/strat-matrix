# Python 子项目

行内运行版本已确认：**Python 3.10.11**。仓库根目录及本目录的`.python-version`记录目标版本；生产依赖以`requirements.txt`为准，开发测试使用`requirements-dev.txt`。请在该版本的独立虚拟环境安装，不沿用电脑全局Python的依赖。

3.10.11独立环境已通过完整回归，版本表、安装步骤及驻场限制见[适配验收记录](../docs/Python310驻场适配_2026-11-04.md)。

首轮[算法执行优化](../docs/算法执行优化记录_2026-11-03.md)已加入DBUtils连接池、冻结角色覆盖检查、不可变缓存批读及任务范围内2路打标；需更新`requirements.txt`依赖。配置/模型401或403会阻断准备任务，修复后显式重试，不会自动持续重放。

驻场前已补齐[Python接入与预检](ONSITE.md)：可配置模型网关、25张算法自有表的[独立DDL](algorithm_schema.sql)、不依赖Java业务表的健康检查、显式只读预检及有限模型连通测试。新算法库使用`python -m app.init_algorithm_db --apply`；已有环境不要用旧业务初始化器补表。

三工程驻场的实际流程、交互、数据归属及待补开发见[功能流程清单](../docs/三工程驻场功能流程适配清单_V1.0_2026-11-03.md)及[Excel跟踪表](../docs/三工程驻场功能流程适配清单_V1.0_2026-11-03.xlsx)，重点核对模型出口、原始资料HTTP、最小算法DDL及旧OP收口。

普通选题匹配仅保留V19，执行入口为`matching_quality_executor.py`；旧算法策略仅供历史查询。已有环境通过`python -m app.consolidate_v19 --apply`迁移策略绑定，详见[V19统一说明](../docs/V19算法统一说明_2026-11-03.md)。

部署环境使用库内`PLANNING_ENV=outside/inside`。`python -m app.deployment_environment show/check/select`提供查看、预检和选择；inside强制Java资料来源并在启动前校验配置。详见[双环境切换](../docs/双环境切换_V0.1.md)。

outside同样使用Java HTTP资料入口，默认`http://127.0.0.1:6931/api/plan/internal/source`，令牌默认复用内部令牌；显式Java资料地址/令牌优先。Java读取模拟文件，Python运行时不再直接读夹具。页面需要的生命周期/标签通过`POST /api/internal/catalog-projection`对Java传入实体计算，无额外资料查询。旧`POST /api/internal/manual-source`已停用。

原`backend`目录已统一改为`python-backend/`，Python包名仍为`app`。本工程负责算法配置、标签、画像、向量、输入准备和匹配计算；Java负责业务任务与正式结果。旧Python业务代码保留兼容和追溯，当前页面已退出历史联合查询。当前边界和验收见[双库迁移记录](../docs/双库业务迁移与验收_2026-11-03.md)。

```bash
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 6930
```

测试不要求启动Java。访问真实业务接口需要根目录`.env`中的MySQL连接及已初始化的系统配置；真实打标／向量化还需要库内模型配置。

开发回归推荐在**仓库根目录**运行`python -m testing --suite python`。该入口为旧单测补充独立系统配置并阻断真实MySQL和公网访问；直接运行原始pytest不等于完成这种隔离。固定算法回放和对比报告见[测试工具](../testing/README.md)。

后台执行已整合进FastAPI，不再另开Worker终端。启动API只初始化受控执行器，不扫描业务、不启动Python定时器。Java持久化业务任务后委派计算，经内部唤醒接口推进算法及重试恢复。`AUTO_SCHEDULE_OWNER=java`时，旧Python周策划、热点和人工业务执行不再竞争写入，算法推进不处理旧内容业务状态。

执行器最多两个角色同时运行，每种角色最多一个运行或排队请求；同角色重复唤醒合并。业务任务仍由原数据库租约、重试和断点保护，运行信号及进程监控不冒充业务完成。正常启动不再使用`python -m app.jobs.worker`；其默认命令会拒绝启动，只保留`--once`单次诊断。

接口、恢复及行内调度边界见[后台执行说明](../docs/BACKGROUND_EXECUTION.md)。

算法配置由Python维护；Java综合配置发布时调用受保护的算法配置命令，Python保存幂等回执。自动任务收到带版本的Java业务配置后冻结，正式提案交由Java落库并确认。运行时Python不连接Java业务库。

数据库初始化与一次性历史迁移命令见[发布说明](../docs/双库业务迁移与验收_2026-11-03.md#数据库发布)。`tools/migrate_business_boundary.py`和`tools/migrate_planning_history.py`仅用于行外发布，不导入运行服务或驻场数据适配层。

`app.java_development`仅是现有本地一键脚本的配置桥接：从MySQL生成Java启动配置，文件位于忽略的`run/`，不输出密钥；它不是Java能力接口或目标架构的一部分。

共用接口约定见[三工程契约](../docs/contracts/README.md)。
