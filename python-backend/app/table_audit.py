"""Bank public-column contract; pure DDL helpers, never connect or migrate at import."""
import re

PUBLIC_COLUMNS = {
    'id': "BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '主键ID'",
    'del_flag': "VARCHAR(1) NOT NULL DEFAULT 'N' COMMENT '删除标志：N正常、Y删除'",
    'created_by': "VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '创建人'",
    'updated_by': "VARCHAR(50) NOT NULL DEFAULT 'system' COMMENT '修改人'",
    'created_time': "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'",
    'updated_time': "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '修改时间'",
}


def columns(ddl):
    result = {}
    for line in ddl.splitlines()[1:]:
        match = re.match(r'\s*([a-z][a-z0-9_]*)\s+((?:BIGINT|INT|TINYINT|VARCHAR|CHAR|DATETIME|TIMESTAMP|DATE|LONGTEXT|MEDIUMTEXT|TEXT|DOUBLE|DECIMAL|JSON)\b.*)', line, re.I)
        if match:
            result[match.group(1)] = match.group(2).rstrip(',')
    return result


def validate_ddl(ddl):
    found = columns(ddl)
    for name, expected in PUBLIC_COLUMNS.items():
        actual = re.sub(r"\s+COMMENT\s+'[^']*'.*", '', found.get(name, ''), flags=re.I)
        target = expected.split(' COMMENT ')[0]
        if actual.upper() != target.upper():
            raise ValueError('公共字段不符合行内规范：' + name)
    return True


def normalize_ddl(ddl):
    """Add a surrogate id while retaining every natural key as a unique constraint."""
    table = re.search(r'CREATE TABLE IF NOT EXISTS (\w+)', ddl).group(1)
    found = columns(ddl)
    legacy_pk = []
    if 'id' not in found:
        for line in ddl.splitlines()[1:]:
            match = re.search(r'PRIMARY KEY\s*\(([^)]+)\)', line, re.I)
            if match:
                legacy_pk = [part.strip().strip('`') for part in match.group(1).split(',')]
            match = re.match(r'\s*(\w+)\s+.*\bPRIMARY KEY\b', line, re.I)
            if match and match.group(1) in found:
                legacy_pk = [match.group(1)]
        if not legacy_pk:
            raise ValueError('缺少可保留的旧主键：' + table)
    body = ddl[ddl.index('(') + 1:ddl.rindex(') ENGINE=')]
    if legacy_pk:
        body = re.sub(r'PRIMARY KEY\s*\([^)]+\)\s*,?', '', body, flags=re.I)
    lines = []
    for line in body.splitlines():
        if not line.strip():
            continue
        match = re.match(r'\s*(\w+)\s+', line)
        name = match.group(1) if match else None
        if name in PUBLIC_COLUMNS:
            continue
        if legacy_pk and name in legacy_pk and re.search(r'PRIMARY KEY', line, re.I):
            line = re.sub(r'\s+PRIMARY KEY', '', line, flags=re.I)
            if 'NOT NULL' not in line.upper():
                line = re.sub(r'\s+COMMENT', ' NOT NULL COMMENT', line, flags=re.I)
        lines.append(line.strip().rstrip(','))
    if legacy_pk:
        lines.append('UNIQUE KEY uk_audit_legacy_' + table + ' (' + ','.join(legacy_pk) + ')')
    public = [name + ' ' + definition for name, definition in PUBLIC_COLUMNS.items()]
    prefix = ddl[:ddl.index('(') + 1]
    suffix = ddl[ddl.rindex(') ENGINE='):]
    return prefix + '\n    ' + ',\n    '.join(public + lines) + '\n' + suffix


def metadata_errors(column_rows, primary_columns, primary_type='BTREE'):
    """Validate actual MySQL metadata, not merely the presence of six column names."""
    by_name = {row['COLUMN_NAME']: row for row in column_rows}
    errors = []
    for name in PUBLIC_COLUMNS:
        row = by_name.get(name)
        if not row:
            errors.append(name + ':missing')
            continue
        typ = row['COLUMN_TYPE'].lower()
        expected = 'bigint' if name == 'id' else 'varchar(1)' if name == 'del_flag' else 'varchar(50)' if name.endswith('_by') else 'datetime'
        if typ != expected and not (name == 'id' and re.fullmatch(r'bigint\(\d+\)', typ)):
            errors.append(name + ':type')
        if row['IS_NULLABLE'] != 'NO':
            errors.append(name + ':nullable')
        default = str(row['COLUMN_DEFAULT'] or '')
        if name == 'del_flag' and default != 'N' or name.endswith('_by') and default != 'system':
            errors.append(name + ':default')
        if name.endswith('_time') and not re.fullmatch(r'CURRENT_TIMESTAMP(?:\(\))?', default, re.I):
            errors.append(name + ':default')
        extra = row['EXTRA'].lower()
        if name == 'id' and 'auto_increment' not in extra:
            errors.append(name + ':auto_increment')
        if name == 'updated_time' and not re.search(r'on update current_timestamp(?:\(\))?', extra):
            errors.append(name + ':on_update')
        if not re.search(r'[\u4e00-\u9fff]', row['COLUMN_COMMENT'] or ''):
            errors.append(name + ':comment')
    if primary_columns != ['id'] or primary_type.upper() != 'BTREE':
        errors.append('id:primary_key')
    return errors
