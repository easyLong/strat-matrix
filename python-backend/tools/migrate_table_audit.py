"""Explicit, backed-up six-column migration; never imported by either runtime."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

import pymysql

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'python-backend'))
from app.algorithm_schema import definitions
from app.db import settings
from app.java_development import java_database_settings
from app.table_audit import PUBLIC_COLUMNS, metadata_errors


def business_definitions():
    result = {}
    for path in (ROOT / 'java-backend/godp-planning-services/src/main/resources/db').glob('*.sql'):
        for sql, name in re.findall(r'(CREATE TABLE IF NOT EXISTS (godp_\w+)\s*\([\s\S]*?\) ENGINE=[^;]+;)', path.read_text(encoding='utf-8')):
            result[name] = sql
    return result


def inspect(cursor, table):
    cursor.execute('SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,COLUMN_COMMENT '
                   'FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION', (table,))
    rows = cursor.fetchall()
    cursor.execute('SELECT COLUMN_NAME,INDEX_TYPE FROM INFORMATION_SCHEMA.STATISTICS WHERE TABLE_SCHEMA=DATABASE() '
                   'AND TABLE_NAME=%s AND INDEX_NAME=\'PRIMARY\' ORDER BY SEQ_IN_INDEX', (table,))
    primary = cursor.fetchall()
    return rows, [row['COLUMN_NAME'] for row in primary], primary[0]['INDEX_TYPE'] if primary else ''


def source_time(cols, names, fallback):
    for name in names:
        if name not in cols:
            continue
        typ = cols[name]['COLUMN_TYPE'].lower()
        if 'bigint' in typ:
            return f'COALESCE(FROM_UNIXTIME(`{name}` / 1000),{fallback})'
        if 'varchar' in typ:
            return f"COALESCE(CAST(REPLACE(LEFT(`{name}`,19),'T',' ') AS DATETIME),{fallback})"
        return f'COALESCE(`{name}`,{fallback})'
    return fallback


def source_actor(cols, name):
    legacy = 'create_by' if name == 'created_by' else 'update_by'
    expressions = [f"NULLIF(`{legacy}`,'')"] if legacy in cols else []
    if 'payload' in cols:
        key = 'created_by' if name == 'created_by' else 'updated_by'
        expressions.append(f"CASE WHEN JSON_VALID(payload) THEN NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(payload,'$.{key}')),'null'),'') END")
    if name == 'updated_by' and 'created_by' in cols:
        expressions.append("NULLIF(created_by,'')")
    return 'COALESCE(' + ','.join(expressions + ["'system'"]) + ')' if expressions else "'system'"


def plan(table, rows, primary, primary_type):
    if not re.fullmatch(r'godp_[a-z0-9_]+', table):
        raise ValueError('表名不在允许范围')
    cols = {row['COLUMN_NAME']: row for row in rows}
    if not cols or not primary:
        raise ValueError('目标表或原主键缺失：' + table)
    errors = metadata_errors(rows, primary, primary_type)
    if not errors:
        return [], [], {}
    ddl = []
    if 'id' not in cols:
        keys = ','.join('`' + name + '`' for name in primary)
        ddl.append(f'ALTER TABLE `{table}` DROP PRIMARY KEY, ADD COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT \'主键ID\', '
                   f'ADD PRIMARY KEY USING BTREE (id), ADD UNIQUE KEY uk_audit_legacy_{table} ({keys})')
    elif primary != ['id']:
        raise ValueError('已有id与原主键冲突，禁止自动重编号：' + table)
    elif any(error.startswith('id:') for error in errors):
        ddl.append(f"ALTER TABLE `{table}` MODIFY COLUMN id BIGINT NOT NULL AUTO_INCREMENT COMMENT '主键ID'")
    added = []
    for name, definition in PUBLIC_COLUMNS.items():
        if name == 'id':
            continue
        if name not in cols:
            ddl.append(f'ALTER TABLE `{table}` ADD COLUMN {name} {definition}')
            added.append(name)
        elif any(error.startswith(name + ':') for error in errors):
            ddl.append(f'ALTER TABLE `{table}` MODIFY COLUMN {name} {definition}')
    backfill = {}
    for name in added:
        if name.endswith('_by'):
            backfill[name] = source_actor(cols, name)
        elif name == 'created_time':
            backfill[name] = source_time(cols, ('create_time', 'created_at'), 'created_time')
        elif name == 'updated_time':
            backfill[name] = source_time(cols, ('update_time', 'updated_at', 'create_time', 'created_at'), 'created_time')
    # Updating added fields must not advance the legacy business/lease timestamps.
    preserve = [name for name, row in cols.items() if 'on update' in row['EXTRA'].lower() and name not in backfill]
    dml = []
    if backfill:
        values = [f'`{name}`={expression}' for name, expression in backfill.items()]
        values += [f'`{name}`=`{name}`' for name in preserve]
        dml.append(f'UPDATE `{table}` SET ' + ','.join(values))
    return ddl, dml, {name: source_actor(cols, name) if name not in cols else f'`{name}`' for name in ('created_by', 'updated_by')}


def fingerprint(rows, names):
    values = [sha256(json.dumps({name: row[name] for name in names}, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest() for row in rows]
    return sha256(''.join(sorted(values)).encode()).hexdigest()


def pending_ddl(statements, rows, primary, primary_type):
    """Resume ALTERs after a crash without replaying an already added column/key."""
    cols = {row['COLUMN_NAME'] for row in rows}
    errors = metadata_errors(rows, primary, primary_type)
    remaining = []
    for sql in statements:
        if 'DROP PRIMARY KEY' in sql and 'id' in cols and primary == ['id']:
            continue
        added = re.search(r'ADD COLUMN (\w+)', sql)
        if added and added.group(1) in cols:
            continue
        modified = re.search(r'MODIFY COLUMN (\w+)', sql)
        if modified and not any(error.startswith(modified.group(1) + ':') for error in errors):
            continue
        remaining.append(sql)
    return remaining


def run(owner, output, apply, resume=False):
    target = definitions() if owner == 'algorithm' else business_definitions()
    cfg = settings() if owner == 'algorithm' else java_database_settings()
    cfg = {**cfg, 'init_command': "SET time_zone='+00:00'"}
    output.mkdir(parents=True, exist_ok=True)
    report = {'owner': owner, 'apply': apply, 'tables': {}, 'status': 'not_ready'}
    with pymysql.connect(**cfg) as db, db.cursor() as cursor:
        lock = 'strat-matrix:public-columns:' + owner
        cursor.execute('SELECT GET_LOCK(%s,5) acquired', (lock,))
        if cursor.fetchone()['acquired'] != 1:
            raise ValueError('数据库升级锁被占用')
        try:
            plans = {}
            for table in sorted(target):
                rows, pk, pk_type = inspect(cursor, table)
                backup = output / (owner + '-' + table + '-before.json')
                saved = json.loads(backup.read_text(encoding='utf-8')) if resume and backup.exists() else None
                if backup.exists() and apply and not resume:
                    raise ValueError('备份已存在，请指定--resume或使用新的输出目录')
                original_rows = saved['columns'] if saved else rows
                original_pk = saved['primary'] if saved else pk
                original_type = saved['primary_type'] if saved else pk_type
                ddl, dml, actors = plan(table, original_rows, original_pk, original_type)
                ddl = pending_ddl(ddl, rows, pk, pk_type)
                # Validate every table before the first DDL; never silently truncate an UM.
                for expression in actors.values():
                    cursor.execute(f'SELECT COUNT(*) amount FROM `{table}` WHERE CHAR_LENGTH({expression})>50')
                    if cursor.fetchone()['amount']:
                        raise ValueError('操作人长度超过50，需先确认映射：' + table)
                if any(row['COLUMN_NAME'] == 'del_flag' for row in rows):
                    cursor.execute(f"SELECT COUNT(*) amount FROM `{table}` WHERE del_flag IS NULL OR del_flag NOT IN ('N','Y')")
                    if cursor.fetchone()['amount']:
                        raise ValueError('存在未知删除标志：' + table)
                plans[table] = (original_rows, ddl, dml, pk, pk_type, saved)
                report['tables'][table] = {'ddl': len(ddl), 'backfill': len(dml)}
            script = '\n\n'.join('-- ' + table + '\n' + ';\n'.join(ddl + dml) + (';' if ddl or dml else '-- already compliant')
                                    for table, (_, ddl, dml, _, _, _) in plans.items()) + '\n'
            (output / (owner + '-migration.sql')).write_text(script, encoding='utf-8')
            db.rollback()  # release preflight metadata locks before ALTER
            if apply:
                for table, (rows, ddl, dml, pk, pk_type, saved) in plans.items():
                    if not ddl and not dml:
                        continue
                    backup = output / (owner + '-' + table + '-before.json')
                    if saved:
                        before = saved['rows']
                    else:
                        cursor.execute(f'SHOW CREATE TABLE `{table}`')
                        schema = cursor.fetchone()['Create Table']
                        cursor.execute(f'SELECT * FROM `{table}`')
                        before = cursor.fetchall()
                        backup.write_text(json.dumps({'ddl': schema, 'columns': rows, 'rows': before,
                                                      'primary': pk, 'primary_type': pk_type}, ensure_ascii=False, default=str), encoding='utf-8')
                    names = [row['COLUMN_NAME'] for row in rows]
                    original = fingerprint(before, names)
                    db.rollback()
                    for sql in ddl + dml:
                        cursor.execute(sql)
                    db.commit()
                    actual, pk, typ = inspect(cursor, table)
                    errors = metadata_errors(actual, pk, typ)
                    if errors:
                        raise ValueError('升级后的公共字段校验失败：' + table)
                    cursor.execute(f'SELECT * FROM `{table}`')
                    after = cursor.fetchall()
                    if fingerprint(after, names) != original:
                        raise ValueError('原业务字段指纹变化：' + table)
                    report['tables'][table].update(rows=len(after), original_fields_preserved=True)
                if owner == 'business':
                    from app.init_planner_db import statements
                    source = (ROOT / 'java-backend/godp-planning-services/src/main/resources/db/planning-query-views.sql').read_text(encoding='utf-8')
                    for sql in statements(source):
                        cursor.execute(sql)
                    db.commit()
                    report['views_refreshed'] = 3
            report['status'] = 'passed' if apply else 'planned'
        finally:
            db.rollback()
            cursor.execute('SELECT RELEASE_LOCK(%s)', (lock,))
    (output / (owner + '-report.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description='两侧自有表六公共字段升级；停服务、预检、备份、回填和业务数据指纹检查')
    parser.add_argument('--owner', choices=('algorithm', 'business', 'both'), default='both')
    parser.add_argument('--output', type=Path, default=ROOT / 'run/table-audit-migration' / datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--check', action='store_true', help='只读校验39张正式表的六字段规范，不执行升级')
    parser.add_argument('--resume', action='store_true', help='使用同一输出目录的原始备份恢复中断升级，不覆盖备份')
    args = parser.parse_args()
    owners = ('algorithm', 'business') if args.owner == 'both' else (args.owner,)
    try:
        if args.resume and not args.apply:
            raise ValueError('--resume须与--apply一起使用')
        if args.check and args.apply:
            raise ValueError('--check与--apply不可同时使用')
        if args.apply:
            # Both owners must pass preflight before changing either schema.
            for owner in owners:
                run(owner, args.output, False, args.resume)
        reports = [run(owner, args.output, args.apply, args.resume) for owner in owners]
    except Exception as exc:
        # Backups may contain configuration secrets; never dump rows/settings/driver messages.
        print(json.dumps({'status': 'not_ready', 'error': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}, ensure_ascii=False))
        return 2
    changes = sum(t['ddl'] + t['backfill'] for r in reports for t in r['tables'].values())
    status = ('passed' if changes == 0 else 'not_ready') if args.check else ('passed' if args.apply else 'planned')
    print(json.dumps({'status': status, 'tables': sum(len(r['tables']) for r in reports), 'pending_changes': changes if not args.apply else 0}, ensure_ascii=False))
    return 2 if args.check and changes else 0


if __name__ == '__main__':
    raise SystemExit(main())
