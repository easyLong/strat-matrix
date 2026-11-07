"""Build/review a DBA release from authoritative SQL. Standard library, no DB access."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'src/main/resources/db'
BASE = ('manual-business.sql', 'business-planning-config.sql',
        'auto-planning-business.sql', 'slot-completion.sql')
VERSION = '20261107-v9'
HEADER = '-- godp-strat-matrix Java业务库发布；由DBA在已确认的目标schema执行。\n'
PUBLIC = ('id', 'del_flag', 'created_by', 'updated_by', 'created_time', 'updated_time')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build():
    sources = {name: (DB / name).read_text(encoding='utf-8') for name in BASE}
    views = (DB / 'planning-query-views.sql').read_text(encoding='utf-8')
    upgrade = (DB / 'migrations/V9__staged_result_publication.sql').read_text(encoding='utf-8')
    tables = {}
    for source in sources.values():
        for name, body in re.findall(
                r'CREATE TABLE IF NOT EXISTS (godp_\w+)\s*\(([\s\S]*?)\) ENGINE=[^;]+;', source):
            if name in tables:
                raise ValueError('duplicate table: ' + name)
            columns = re.findall(r'^\s+(\w+)\s+([^\n]+)', body, re.M)
            actual = {name for name, _ in columns}
            if not set(PUBLIC) <= actual:
                raise ValueError('missing public fields: ' + name)
            for column, definition in columns:
                if column.upper() in ('UNIQUE', 'KEY', 'CONSTRAINT', 'PRIMARY'):
                    continue
                if 'COMMENT' not in definition:
                    raise ValueError('missing field comment: ' + name + '.' + column)
            tables[name] = body
    if len(tables) != 14:
        raise ValueError('review business table inventory before changing 14-table baseline')
    quoted = ','.join("'" + name + "'" for name in sorted(tables))
    basecheck = HEADER + f'''SELECT DATABASE() AS target_schema, CURRENT_USER() AS release_user, VERSION() AS mysql_version;
SELECT TABLE_NAME,ENGINE,TABLE_COLLATION,TABLE_COMMENT FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ({quoted}) ORDER BY TABLE_NAME;
'''
    rollback_views = views.replace(" AND b.write_state='ready'", '').replace(" AND write_state='ready'", '')
    files = {
        'ddl/01-new-install.sql': HEADER + '-- 仅用于全新库；先检查14张业务表均不存在。不得用IF NOT EXISTS替代存量升级。\n'
            + '\n'.join(sources.values()) + '\n' + views,
        'ddl/02-upgrade-v8-to-v9.sql': HEADER + '-- 仅适用于已完成V8且尚无V9字段的库；新库不要执行。\n'
            + upgrade + '\n' + views,
        'dml/01-initial-data-review.sql': HEADER + '''-- 没有可擅自覆盖的通用初始配置；不包含测试账号、测试选题、密钥或批准策略。
-- 新库由业务负责人通过正式配置发布流程建立当前版本和历史，不能伪造已确认的两侧配置。
-- 存量库保持全部现有配置，本脚本只核查。
SELECT config_key,version FROM godp_business_planning_config;
SELECT COUNT(*) AS history_versions FROM godp_business_planning_config_version;
''',
        'checks/01-new-install-precheck.sql': basecheck + f'''
-- existing_tables必须为0；不满足则停止，改用匹配基线的升级包。
SELECT COUNT(*) AS existing_tables FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ({quoted});
''',
        'checks/02-upgrade-v8-precheck.sql': basecheck + f'''
-- existing_tables必须为14，public_columns必须为84，v9_columns必须为0。
SELECT COUNT(*) AS existing_tables FROM information_schema.TABLES
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ({quoted});
SELECT COUNT(*) AS public_columns FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ({quoted})
 AND COLUMN_NAME IN ('id','del_flag','created_by','updated_by','created_time','updated_time');
SELECT COUNT(*) AS v9_columns FROM information_schema.COLUMNS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_planning_batch'
 AND COLUMN_NAME IN ('write_state','write_cursor');
-- 以下V7/V8基线结果分别必须为2、1；少任一项不得跳版本。
SELECT COUNT(*) AS v7_columns FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME IN ('godp_business_planning_config','godp_business_planning_config_version')
 AND COLUMN_NAME='content_production_lead_days_json';
SELECT COUNT(DISTINCT INDEX_NAME) AS v8_indexes FROM information_schema.STATISTICS
 WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_planning_item' AND INDEX_NAME='idx_result_content_flow_scan';
-- 查看已有自动任务，停止调度并确认没有执行中的写入后再发布。
SELECT status,COUNT(*) AS task_count FROM godp_auto_planning_task WHERE del_flag='N' GROUP BY status;
''',
        'checks/03-postcheck.sql': basecheck + f'''
-- 三个视图必须全部存在，新增字段类型、默认值、中文说明需与DDL一致。
SELECT TABLE_NAME,COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,COLUMN_COMMENT
 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME='godp_planning_batch' AND COLUMN_NAME IN ('write_state','write_cursor');
SELECT TABLE_NAME,VIEW_DEFINITION FROM information_schema.VIEWS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME IN ('godp_planning_item_read','godp_planning_batch_read','godp_planning_task_read');
SELECT write_state,COUNT(*) AS batch_count FROM godp_planning_batch GROUP BY write_state;
SELECT COUNT(*) AS invalid_write_states FROM godp_planning_batch
 WHERE write_state NOT IN ('ready','staging') OR write_cursor<0;
SELECT COUNT(*) AS leaked_staging_items FROM godp_planning_item_read i
 JOIN godp_planning_batch b ON b.id=i.batch_id WHERE b.write_state<>'ready';
-- 应用账号应独立验证：具有必要DML和视图SELECT，无需CREATE/ALTER/DROP。
SHOW GRANTS;
''',
        'checks/04-index-review.sql': HEADER + f'''-- 只读；真实EXPLAIN和容量结论由现场实际数据验证。
SELECT TABLE_NAME,INDEX_NAME,NON_UNIQUE,SEQ_IN_INDEX,COLUMN_NAME,SUB_PART
 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE()
 AND TABLE_NAME IN ({quoted}) ORDER BY TABLE_NAME,INDEX_NAME,SEQ_IN_INDEX;
EXPLAIN SELECT i.id FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id
 WHERE i.del_flag='N' AND b.del_flag='N' AND b.write_state='ready'
 AND i.content_status='planned' AND i.id>0 ORDER BY i.id LIMIT 500;
EXPLAIN SELECT id FROM godp_planning_item WHERE account_id='REPLACE_WITH_SAMPLE_ACCOUNT'
 AND publish_date BETWEEN '2026-11-02' AND '2026-11-08' AND del_flag='N';
''',
        'rollback/01-precheck.sql': HEADER + '''-- 兼容回退前停止调度/写入；blocking_batches必须为0，否则先用新版继续推进至完整发布。
-- 检查SQL不会自动中止后续脚本，由DBA审核结果并签认后才可继续。
SELECT COUNT(*) AS blocking_batches FROM godp_planning_batch WHERE write_state<>'ready';
SELECT id,write_state,write_cursor FROM godp_planning_batch WHERE write_state<>'ready';
SELECT status,COUNT(*) AS task_count FROM godp_auto_planning_task WHERE del_flag='N' GROUP BY status;
''',
        'rollback/02-compatible-rollback.sql': HEADER
            + '-- 仅在01-precheck的blocking_batches为0后执行，再回退应用。\n'
            + '-- 恢复V8视图；保留兼容列和全部业务数据，不自动DROP表/列，不删除分批结果。\n'
            + rollback_views,
    }
    inventory = ['# Java业务表与索引评审清单', '',
        '生成自当前DDL；仅包含本模块14张业务表，不包含Python算法表和行内内容流水表。', '',
        '所有表采用InnoDB/utf8mb4；排序规则尚未固定，需按目标schema现有规范确认后发布。', '',
        '现有id均为BIGINT自增；业务编号/槽位编号另设唯一约束，保留现有业务ID范围。', '',
        '| 表名 | 唯一约束与索引 |', '| --- | --- |']
    for name, body in sorted(tables.items()):
        indexes = [line.strip().rstrip(',') for line in body.splitlines()
                   if re.match(r'\s*(UNIQUE KEY|KEY)\b', line)]
        indexes += [line.strip().rstrip(',') for line in body.splitlines()
                    if ' UNIQUE ' in line and not line.strip().startswith('UNIQUE')]
        inventory.append(f'| `{name}` | ' + '<br>'.join(indexes).replace('|', '\\|') + ' |')
    inventory += ['', '## 业务动作与防重复边界', '',
        '| 动作 | 数据库与服务共同约束 |', '| --- | --- |',
        '| 周自动策划 | cycle_start唯一；锁定同一自动任务；恢复时校验proposal_hash |',
        '| 正式明细 | (batch_id,slot_id)唯一；每页明细与游标同事务提交 |',
        '| 人工提交 | preview_code/task_code唯一；营销request_id唯一并核对request_hash |',
        '| 账号日期占用 | (publish_date,account_id)唯一；释放后原行逻辑复用 |',
        '| 热点/过审内容引用 | (resource_kind,resource_key)唯一；重复占用拒绝 |',
        '| 配置发布 | command_id唯一、版本校验；配置历史(config_key,version)唯一 |',
        '| 内容流水 | 行内目标实现提供planningItemId唯一、版本单调及原始回执；本模块不替目标建表 |', '',
        '容量评估：自动明细约为账号数×每周策划日数×保留周数，另加人工明细；'
        '账号/选题快照LONGTEXT需按真实平均字节和索引占用估算。归档保留期、分区需求由DBA和业务方确认。', '',
        '高频JSON筛选、模糊名称查询可能无法利用普通索引；现场EXPLAIN及规模压测后决定结构化投影，不能凭样例判断性能已达标。', '',
        '自动结果：每次推进最多写500条明细，事务还包含少量游标/状态记录；'
        '若宿主将500定义为所有DML影响行数上限，应进一步下调明细批量。', '',
        '人工结果仍按单任务原子写入，规模化分批是后续专项；本轮未声称全部写入路径均已拆分。', '']
    files['TABLE_DESIGN.md'] = '\n'.join(inventory)
    files['README.md'] = '''# godp-strat-matrix Java业务库 DBA发布包

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
'''
    source_paths = [DB / n for n in BASE] + [DB / 'planning-query-views.sql', DB / 'migrations/V9__staged_result_publication.sql', Path(__file__).resolve()]
    manifest = {'release': VERSION, 'hash_format': 'UTF-8 text with LF line endings',
        'sources': {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p.read_text(encoding='utf-8').encode('utf-8')) for p in source_paths},
        'files': {name: digest(value.encode('utf-8')) for name, value in sorted(files.items())}}
    files['manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    files = build()
    if args.check:
        actual = {str(p.relative_to(args.output)).replace('\\', '/') for p in args.output.rglob('*') if p.is_file()}
        drift = sorted(set(files) ^ actual)
        drift += [name for name, value in files.items() if (args.output / name).is_file()
                  and (args.output / name).read_text(encoding='utf-8') != value]
        if drift:
            raise SystemExit('release drift: ' + ', '.join(drift))
        print('DBA release verified: 14 tables, ' + str(len(files)) + ' files')
    else:
        for name, value in files.items():
            target = args.output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value.encode('utf-8'))
        print('DBA release generated: ' + str(len(files)) + ' files; no database accessed')


if __name__ == '__main__':
    main()
