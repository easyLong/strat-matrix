"""Initialize only planner-owned extensions and result tables, never source copies."""

from pathlib import Path
from .db import connection
from .retired_tables import RETIRED_TABLES, retired_statement


def statements(source):
    import re
    # CREATE blocks have no stored procedures; semicolons inside comments are retained.
    return re.findall(r'CREATE TABLE IF NOT EXISTS\s+\w+\s*\([\s\S]*?\) ENGINE=[^;]+;', source)


def main():
    from .init_db import sync_table_comments, sync_column_comments
    root = Path(__file__).resolve().parents[1]
    tables = 0
    with connection() as db, db.cursor() as cursor:
        for name in ('schema.sql', 'pipeline_schema.sql', 'manual_marketing_schema.sql', 'content_production_schema.sql', 'matching_quality_schema.sql'):
            source = (root / name).read_text(encoding='utf-8')
            for statement in statements(source):
                if retired_statement(statement):
                    continue
                cursor.execute(statement)
                tables += 1
            if name=='schema.sql':
                from .init_manual_tasks_db import ensure_schema as ensure_manual_tasks
                ensure_manual_tasks(cursor)
            sync_table_comments(cursor, source)
            sync_column_comments(cursor, source)
        from .init_system_config import seed_config
        from .init_shared_workflow_db import ensure_schema
        ensure_schema(cursor)
        seed_config(cursor, migrate_legacy=False)
        from .init_account_mapping import seed_rules
        seed_rules(cursor)
        db.commit()
        cursor.execute('SHOW TABLES')
        available = {next(iter(row.values())) for row in cursor.fetchall()}
    print(f'Planner schema ready: {tables} definitions; retired tables present: {len(available & set(RETIRED_TABLES))}')


if __name__ == '__main__':
    main()
