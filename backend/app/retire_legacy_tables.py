"""Back up a fixed whitelist and optionally drop retired source/sync tables.

Only --apply drops tables. The backup is completed and hashed before any DDL.
Fixtures are developer data, never shipped in the on-site code bundle.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from .db import connection, ROOT
from .retired_tables import RETIRED_TABLES


def backup(directory: Path):
    directory.mkdir(parents=True, exist_ok=False)
    destination = directory / 'restore.sql'
    metadata = {'tables': {}, 'created_at': datetime.now(timezone.utc).isoformat()}
    with connection() as db, db.cursor() as cursor, destination.open('w', encoding='utf-8', newline='\n') as stream:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
        cursor.execute('SELECT DATABASE() AS database_name')
        metadata['database'] = cursor.fetchone()['database_name']
        metadata['row_hashes'] = {}
        cursor.execute('SHOW TABLES')
        available = {next(iter(row.values())) for row in cursor.fetchall()}
        cursor.execute('SELECT TABLE_NAME,REFERENCED_TABLE_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE '
                       'WHERE REFERENCED_TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL')
        if any(row['REFERENCED_TABLE_NAME'] in RETIRED_TABLES for row in cursor.fetchall()):
            raise RuntimeError('待删表仍被外键引用，停止删除')
        stream.write('-- Local recovery backup. Contains test data; keep outside Git.\nSET NAMES utf8mb4;\n')
        for table in RETIRED_TABLES:
            if table not in available:
                continue
            cursor.execute(f'SHOW CREATE TABLE `{table}`')
            create = cursor.fetchone()['Create Table']
            stream.write(f'\nDROP TABLE IF EXISTS `{table}`;\n{create};\n')
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY id')
            rows = cursor.fetchall()
            digest = sha256()
            for row in rows:
                columns = ','.join('`' + name + '`' for name in row)
                insert = f'INSERT INTO `{table}` ({columns}) VALUES (' + ','.join(['%s'] * len(row)) + ')'
                rendered = cursor.mogrify(insert, tuple(row.values())) + ';\n'
                stream.write(rendered)
                digest.update(rendered.encode('utf-8'))
            metadata['tables'][table] = len(rows)
            metadata['row_hashes'][table] = digest.hexdigest()
        stream.flush()
        os.fsync(stream.fileno())
        db.rollback()
    metadata['sha256'] = sha256(destination.read_bytes()).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    return metadata


def export_local_fixture():
    from .bank_bridge.local_sql import LocalSQLSource
    from .bank_bridge.bridge import collect
    from .bank_bridge.contracts import AccountQuery, TopicQuery
    from .bank_bridge.local_fixture import FIXTURE_PATH
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        source = LocalSQLSource(cursor)
        accounts = list(collect(source, 'accounts', AccountQuery()))
        topics = list(collect(source, 'topics', TopicQuery()))
        db.rollback()
    def item(row):
        return {'data': row.model_dump(mode='json'), 'local_payload': row._local_payload}
    content = {'accounts': [item(a) for a in accounts], 'topics': [item(t) for t in topics]}
    FIXTURE_PATH.parent.mkdir(exist_ok=True)
    temporary = FIXTURE_PATH.with_suffix('.tmp')
    temporary.write_text(json.dumps(content, ensure_ascii=False, default=str), encoding='utf-8')
    temporary.replace(FIXTURE_PATH)
    return {'accounts': len(accounts), 'topics': len(topics)}


def apply(directory: Path):
    metadata = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if sha256((directory / 'restore.sql').read_bytes()).hexdigest() != metadata['sha256']:
        raise RuntimeError('备份校验不通过，停止删除')
    tables = tuple(metadata['tables'])
    if set(tables) - set(RETIRED_TABLES):
        raise RuntimeError('备份表不在删除白名单')
    with connection() as db, db.cursor() as cursor:
        cursor.execute('SELECT DATABASE() AS database_name')
        if cursor.fetchone()['database_name'] != metadata.get('database') or not metadata.get('row_hashes'):
            raise RuntimeError('当前数据库与备份不一致或备份缺少校验信息，停止删除')
        for table in tables:
            cursor.execute(f'SELECT COUNT(*) AS n FROM `{table}`')
            if cursor.fetchone()['n'] != metadata['tables'][table]:
                raise RuntimeError('备份后数据数量已变化，停止删除并重新备份')
            cursor.execute(f'SELECT * FROM `{table}` ORDER BY id')
            digest = sha256()
            for row in cursor.fetchall():
                columns = ','.join('`' + name + '`' for name in row)
                insert = f'INSERT INTO `{table}` ({columns}) VALUES (' + ','.join(['%s'] * len(row)) + ')'
                digest.update((cursor.mogrify(insert, tuple(row.values())) + ';\n').encode('utf-8'))
            if digest.hexdigest() != metadata['row_hashes'][table]:
                raise RuntimeError('备份后数据内容已变化，停止删除并重新备份')
        if tables:
            cursor.execute('DROP TABLE ' + ','.join('`' + table + '`' for table in tables))
        db.commit()
        cursor.execute('SHOW TABLES')
        remaining = {next(iter(row.values())) for row in cursor.fetchall()}
        if set(tables) & remaining:
            raise RuntimeError('部分旧表仍存在')
    return list(tables)


def main():
    parser = argparse.ArgumentParser(description='备份并清理已取消的本地基础副本、同步和主动投递表')
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--export-fixture', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    directory = args.backup_dir or ROOT / 'run/backups' / ('retired-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    if not directory.exists():
        metadata = backup(directory)
    else:
        metadata = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    result = {'backup': str(directory), 'tables': metadata['tables']}
    if args.export_fixture:
        result['fixture'] = export_local_fixture()
    if args.apply:
        result['dropped'] = apply(directory)
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
