# Python 子项目

原`backend`目录已统一改为`python-backend/`，Python包名仍为`app`。本工程负责算法配置、标签、画像、向量、输入准备和匹配计算；Java负责业务任务与正式结果。旧Python业务代码保留兼容和追溯，当前页面已退出历史联合查询。当前边界和验收见[双库迁移记录](../docs/双库业务迁移与验收_2026-11-03.md)。

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m uvicorn app.main:app --host 127.0.0.1 --port 6930
```

测试不要求启动Java。访问真实业务接口需要根目录`.env`中的MySQL连接及已初始化的系统配置；真实打标／向量化还需要库内模型配置。

后台执行已整合进FastAPI，不再另开Worker终端。启动API只初始化受控执行器，不扫描业务、不启动Python定时器。Java持久化业务任务后委派计算，经内部唤醒接口推进算法及重试恢复。`AUTO_SCHEDULE_OWNER=java`时，旧Python周策划、热点和人工业务执行不再竞争写入，算法推进不处理旧内容业务状态。

执行器最多两个角色同时运行，每种角色最多一个运行或排队请求；同角色重复唤醒合并。业务任务仍由原数据库租约、重试和断点保护，运行信号及进程监控不冒充业务完成。正常启动不再使用`python -m app.jobs.worker`；其默认命令会拒绝启动，只保留`--once`单次诊断。

接口、恢复及行内调度边界见[后台执行说明](../docs/BACKGROUND_EXECUTION.md)。

算法配置由Python维护；Java综合配置发布时调用受保护的算法配置命令，Python保存幂等回执。自动任务收到带版本的Java业务配置后冻结，正式提案交由Java落库并确认。运行时Python不连接Java业务库。

数据库初始化与一次性历史迁移命令见[发布说明](../docs/双库业务迁移与验收_2026-11-03.md#数据库发布)。`tools/migrate_business_boundary.py`和`tools/migrate_planning_history.py`仅用于行外发布，不导入运行服务或驻场数据适配层。

`app.java_development`仅是现有本地一键脚本的配置桥接：从MySQL生成Java启动配置，文件位于忽略的`run/`，不输出密钥；它不是Java能力接口或目标架构的一部分。

共用接口约定见[三工程契约](../docs/contracts/README.md)。
