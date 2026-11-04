"""Explicit algorithm-only bootstrap; never execute legacy business migrations."""
import argparse
import json

from .algorithm_schema import TABLE_GROUPS, definitions, inspect_schema


def initialize():
    from .db import connection
    from .init_system_config import seed_config
    blocks = definitions()
    # MySQL DDL autocommits. Validate all source definitions before the first DDL;
    # a partially failed install is resumable, not transactionally rolled back.
    from .algorithm_schema import build_sql
    build_sql()
    with connection() as db, db.cursor() as cursor:
        for tables in TABLE_GROUPS.values():
            for table in tables:
                cursor.execute(blocks[table])
        schema = inspect_schema(cursor)
        if schema['status'] != 'passed':
            return {**schema,'configuration_seeded':False}
        # No legacy key rename/deletion, demo content, mapping approval or policy
        # promotion. Existing values and versions retain precedence.
        inserted = seed_config(cursor,migrate_legacy=False)
        db.commit()
    return {**schema,'configuration_seeded':True,'configuration_inserted':inserted}


def main(argv=None):
    parser = argparse.ArgumentParser(description='首次创建Python自有算法表及缺失配置键；不建Java业务表')
    parser.add_argument('--apply',action='store_true',help='显式执行建表及缺失配置键初始化')
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error('建表须显式使用--apply；离线查看请用app.algorithm_schema export/check')
    try:
        result = initialize()
    except Exception:
        result = dict(status='not_ready',reason='算法库初始化失败，请核对权限和既有表结构；DDL可能已部分生效')
    print(json.dumps(result,ensure_ascii=True))
    return 0 if result['status']=='passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
