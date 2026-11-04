"""Allowlisted algorithm-only DDL. Export/check do not import DB or call services."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('schema.sql', 'pipeline_schema.sql', 'matching_quality_schema.sql', 'manual_compute_schema.sql')
TABLE_GROUPS = {
    'configuration': ('godp_system_config', 'godp_strategy_config', 'godp_strategy_config_version',
                      'godp_algorithm_config_command'),
    'features': ('godp_topic_tag', 'godp_topic_tag_history', 'godp_t6_tag', 'godp_topic_profile',
                 'godp_account_profile', 'godp_topic_label_job', 'godp_account_mapping_rule'),
    'preparation': ('godp_ai_preparation', 'godp_ai_preparation_account',
                    'godp_ai_preparation_topic', 'godp_ai_preparation_progress'),
    'matching': ('godp_matching_policy', 'godp_matching_task', 'godp_matching_input_snapshot',
                 'godp_matching_attempt', 'godp_matching_ai_cache', 'godp_matching_quality_run'),
    'execution': ('godp_planning_pipeline_run', 'godp_planning_stage_run', 'godp_algorithm_proposal',
                  'godp_manual_compute'),
}
REQUIRED_TABLES = frozenset(t for group in TABLE_GROUPS.values() for t in group)


def definitions(root=ROOT):
    result = {}
    for filename in SOURCES:
        source = (root / filename).read_text(encoding='utf-8')
        for statement, table in re.findall(r'(CREATE TABLE IF NOT EXISTS (godp_\w+)\s*\([\s\S]*?\) ENGINE=[^;]+;)', source):
            if table not in REQUIRED_TABLES:
                continue
            if table in result:
                raise ValueError('算法DDL出现重复定义')
            result[table] = statement
    if set(result) != REQUIRED_TABLES:
        raise ValueError('算法DDL与表归属清单不一致')
    return result


def column_specs(ddl):
    columns = {}
    for line in ddl.splitlines()[1:]:
        found = re.match(r'\s*([a-z][a-z0-9_]*)\s+', line)
        if not found:
            continue
        comment = re.search(r"\bCOMMENT '([^']+)'", line)
        if not comment or not re.search(r'[\u4e00-\u9fff]', comment.group(1)):
            raise ValueError('算法DDL字段缺少中文注释')
        columns[found.group(1)] = comment.group(1)
    if not columns or not re.search(r"COMMENT='[^']*[\u4e00-\u9fff][^']*'", ddl):
        raise ValueError('算法DDL缺少表注释或字段')
    return columns


def build_sql(root=ROOT):
    blocks = definitions(root)
    lines = ['-- Python算法库首次安装：25张算法自有表，无Java业务表、原始资料表或演示数据。',
             '-- 自动生成：python -m app.algorithm_schema export --output algorithm_schema.sql',
             '-- 仅CREATE IF NOT EXISTS；不升级已有表字段，不删除表，不初始化/批准算法策略。', '']
    for group, tables in TABLE_GROUPS.items():
        lines.append('-- ' + group)
        for table in tables:
            column_specs(blocks[table])
            lines.extend([blocks[table], ''])
    return '\n'.join(lines)


def inspect_schema(cursor):
    expected = {t:column_specs(ddl) for t,ddl in definitions().items()}
    names = sorted(expected)
    cursor.execute('SELECT TABLE_NAME,COLUMN_NAME,COLUMN_COMMENT FROM INFORMATION_SCHEMA.COLUMNS '
                   'WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (' + ','.join(['%s']*len(names)) + ')', names)
    actual = {t:{} for t in names}
    for row in cursor.fetchall():
        if row['TABLE_NAME'] in actual:
            actual[row['TABLE_NAME']][row['COLUMN_NAME']] = row['COLUMN_COMMENT']
    missing_tables = [t for t in names if not actual[t]]
    missing_columns = [t+'.'+c for t in names if actual[t] for c in expected[t] if c not in actual[t]]
    missing_comments = [t+'.'+c for t in names for c in expected[t] if c in actual[t]
                        and not re.search(r'[\u4e00-\u9fff]', actual[t][c] or '')]
    return dict(status='passed' if not (missing_tables or missing_columns or missing_comments) else 'not_ready',
                required_tables=len(names), missing_tables=missing_tables, missing_columns=missing_columns,
                missing_comments=missing_comments)


def main(argv=None):
    parser = argparse.ArgumentParser(description='离线生成或核对Python算法库DDL，不连接数据库')
    parser.add_argument('action', choices=('export','check'))
    parser.add_argument('--output', type=Path, default=ROOT/'algorithm_schema.sql')
    args = parser.parse_args(argv)
    sql = build_sql()
    if args.action == 'export':
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(sql, encoding='utf-8')
    valid = args.output.is_file() and args.output.read_text(encoding='utf-8') == sql
    print(json.dumps(dict(status='passed' if valid else 'not_ready',tables=len(REQUIRED_TABLES),
                          sha256=sha256(sql.encode()).hexdigest(),database_writes=0),ensure_ascii=True))
    return 0 if valid else 2


if __name__ == '__main__':
    raise SystemExit(main())
