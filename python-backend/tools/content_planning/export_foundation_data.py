"""Export existing foundation rows for DBA review, without changing either database."""
import argparse
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import pymysql


# Explicit whitelist: no credentials, outside fixtures, addresses, schedules or
# accounts may leak into the portable system configuration subset.
PORTABLE_KEYS = (
    'MODEL_NAME', 'EMBEDDING_MODEL_NAME', 'AUTO_PLANNING_POLICY_ID',
    'AI_API_MAX_CONCURRENT_REQUESTS', 'MODEL_MAX_CONCURRENT_REQUESTS',
    'EMBEDDING_MAX_CONCURRENT_REQUESTS', 'AI_PENDING_TASK_LIMIT', 'AI_LIMIT_SCOPE',
)


def literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, (bool, int, float, Decimal)):
        return str(int(value)) if isinstance(value, bool) else str(value)
    if isinstance(value, bytes):
        return "X'" + value.hex() + "'"
    if isinstance(value, (date, datetime)):
        value = value.isoformat(sep=' ') if isinstance(value, datetime) else value.isoformat()
    # Avoid SQL-mode-dependent string escaping, preserving every source character.
    return "CONVERT(X'" + str(value).encode('utf-8').hex() + "' USING utf8mb4)"


def read_rows(cursor, sql, args=()):
    cursor.execute(sql, args)
    return cursor.fetchall()


def collect(algorithm_options, business_options):
    # Each database has its own consistent snapshot. Stop configuration edits
    # while exporting to obtain a coordinated cross-database baseline.
    with pymysql.connect(**algorithm_options) as algorithm, pymysql.connect(**business_options) as business:
        with algorithm.cursor() as a, business.cursor() as b:
            for cursor in (a, b):
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            runtime = read_rows(a, 'SELECT * FROM godp_system_config WHERE config_key IN ('
                                + ','.join(['%s'] * len(PORTABLE_KEYS)) + ') ORDER BY config_key', PORTABLE_KEYS)
            bound = next((r['config_value'] for r in runtime
                          if r['config_key'] == 'AUTO_PLANNING_POLICY_ID' and r['del_flag'] == 'N'), None)
            policies = read_rows(a, 'SELECT * FROM godp_matching_policy WHERE id=%s', (int(bound),)) if bound and int(bound)>0 else []
            algorithm_rows = {
                'godp_strategy_config': read_rows(a, "SELECT * FROM godp_strategy_config WHERE config_key IN ('operations','tag_taxonomy') ORDER BY id"),
                'godp_strategy_config_version': read_rows(a, "SELECT * FROM godp_strategy_config_version WHERE config_key IN ('operations','tag_taxonomy') ORDER BY id"),
                'godp_account_mapping_rule': read_rows(a, 'SELECT * FROM godp_account_mapping_rule ORDER BY id'),
                'godp_matching_policy': policies,
            }
            business_rows = {table: read_rows(b, f'SELECT * FROM {table} ORDER BY id') for table in (
                'godp_business_planning_config', 'godp_business_planning_config_version', 'godp_planning_config_release')}
    return algorithm_rows, business_rows, runtime


def insert_sql(tables):
    lines = ['-- 当前数据库配置快照：保留原字段、ID、版本、状态及历史',
             '-- 仅用于对应空表首次导入，存量环境须单独比较，禁止覆盖执行',
             '-- 客户端须遇错停止并ROLLBACK，禁止使用mysql --force',
             'SET NAMES utf8mb4;', 'START TRANSACTION;']
    for table, rows in tables.items():
        lines.append(f'-- {table}: {len(rows)} rows')
        for row in rows:
            columns = ','.join('`' + key + '`' for key in row)
            lines.append(f'INSERT INTO `{table}` ({columns}) VALUES ('
                         + ','.join(literal(value) for value in row.values()) + ');')
    lines.append('COMMIT;')
    return '\n'.join(lines) + '\n'


def checks(tables):
    return '\n'.join(f"SELECT '{table}' AS table_name, COUNT(*) AS actual_rows, {len(rows)} AS exported_rows FROM `{table}`;"
                     for table, rows in tables.items()) + '\n'


def write_package(output, algorithm_rows, business_rows, runtime):
    if output.exists() and any(output.iterdir()):
        raise ValueError('输出目录非空，请另选新目录，避免覆盖已审阅的数据包')
    output.mkdir(parents=True, exist_ok=True)
    files = {
        '01-algorithm-foundation.sql': insert_sql(algorithm_rows),
        '02-business-foundation.sql': insert_sql(business_rows),
        '03-system-config-portable.sql': insert_sql({'godp_system_config': runtime}),
        '04-algorithm-check.sql': checks(algorithm_rows),
        '05-business-check.sql': checks(business_rows),
        'algorithm-data.json': json.dumps(algorithm_rows, ensure_ascii=False, indent=2, default=str) + '\n',
        'business-data.json': json.dumps(business_rows, ensure_ascii=False, indent=2, default=str) + '\n',
    }
    for name, content in files.items():
        (output / name).write_bytes(content.encode('utf-8'))
    config = {r['config_key']: r for r in algorithm_rows['godp_strategy_config']}
    current = config.get('tag_taxonomy')
    mappings = algorithm_rows['godp_account_mapping_rule']
    warnings = []
    if any(r['status'] == 'draft' and r['del_flag'] == 'N' for r in mappings):
        warnings.append('现有映射含draft，原样保留；导入不代表已经生效，正式匹配前需确认。')
    if current and any(r['taxonomy_version'] != current['version'] and r['del_flag'] == 'N' for r in mappings):
        warnings.append('映射绑定词表历史版本，已一并导出词表历史；不能擅自改为当前版本。')
    if any(r['status'] == 'pending' for r in business_rows['godp_planning_config_release']):
        warnings.append('存在pending配置发布记录，先完成发布或排查后再作为行内初始化基线。')
    if not algorithm_rows['godp_matching_policy']:
        warnings.append('没有绑定策略，未导出其它测试策略；需另行确认V19策略。')
    manifest = dict(source='current-database-snapshot',
                    counts={k: len(v) for k,v in {**algorithm_rows, **business_rows, 'godp_system_config': runtime}.items()},
                    config_versions={k:r['version'] for k,r in config.items()},
                    warnings=warnings,
                    environment_settings='密钥、地址、环境模式及调度开关在行内重新配置，未导出。',
                    sha256={name:sha256(value.encode('utf-8')).hexdigest() for name,value in files.items()})
    (output / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description='只读导出当前双库的基础配置数据，不生成示例、不执行导入')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('输出目录非空，请另选新目录')
    from app.standalone_config import load_config
    from app.content_planning.java_development import java_database_settings
    algorithm, business, runtime = collect(load_config().database.connection_options(), java_database_settings())
    manifest = write_package(args.output, algorithm, business, runtime)
    print(json.dumps(dict(status='exported', output=str(args.output), counts=manifest['counts'],
                          warnings=manifest['warnings']),ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
