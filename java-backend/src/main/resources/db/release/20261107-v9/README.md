# godp-strat-matrix Java业务库 DBA发布包

版本：20261107-v9。工具只读取源码、生成文件，不连接数据库、不修改任何环境。

## 目标与权限

目标schema由行内确认，通过数据库客户端连接选择；不硬编码operations、strat_matrix_bus。
Java业务表和Python算法表分别发布；本包不建行内既有内容流水表。
应用只需业务表SELECT/INSERT/UPDATE/DELETE及视图SELECT；发布账号由DBA掌管DDL权限。
不在应用启动执行建表，不启用Flyway/Liquibase自动迁移，不提供内置GRANT或生产账户口令。

## 执行路线（只能选择一条）

1. 新库：停止调度，备份/审批 → checks/01-new-install-precheck.sql（existing_tables=0）
   → ddl/01-new-install.sql → dml/01-initial-data-review.sql → checks/03-postcheck.sql。
2. V8存量库：核实已完成V6/V7/V8、先备份 → checks/02-upgrade-v8-precheck.sql
   → ddl/02-upgrade-v8-to-v9.sql → checks/03-postcheck.sql → 部署V9应用 → 恢复调度。
   V2～V7旧基线须先按原迁移链升级，不能直接执行本增量。部分执行中断时先核对元数据，不能直接重放ALTER。
3. 运行账户由DBA单独验证，不能用管理员启动成功代替DML-only验收。

检查脚本只返回结果，不自动阻断；任何不符合项由DBA处理并确认后才可执行下一步。
MySQL DDL可能已自动提交，SQL事务回滚不能替代备份和恢复；执行失败时停止并记录已完成语句。
本包没有通用初始业务配置，首次配置通过正式配置发布流程建立，不能默认批准算法策略。

## 回退

停止调度与写入 → rollback/01-precheck.sql → blocking_batches必须为0
→ rollback/02-compatible-rollback.sql恢复旧视图 → 回退旧应用 → 只读复核后恢复调度。
若有staging批次，先由新版继续推进，或由DBA制定保留数据的恢复方案，禁止直接暴露半成品。
兼容回退保留新增列和全部业务数据，旧应用写入使用ready默认值。
首次建库回退也不自动DROP14张表；是否撤销空表由DBA在确认无业务数据后另行审批。

## 索引、容量与完整性

TABLE_DESIGN.md为表/索引及容量评审入口；checks/04-index-review.sql只读获取索引和典型EXPLAIN。
真实行内MySQL版本、排序规则、JSON/视图支持、执行权限、数据范围和压测仍需现场确认。
manifest.json记录权威源码和产物SHA256；下列命令验证发布包未偏离当前源码：

```bash
python tools/build_db_release.py --output src/main/resources/db/release/20261107-v9 --check
```
