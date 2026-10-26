"""Install the additive, unscheduled manual marketing request table."""

from pathlib import Path
from .db import connection


def main():
    source = (Path(__file__).resolve().parents[1] / 'manual_marketing_schema.sql').read_text(encoding='utf-8')
    with connection() as db, db.cursor() as cursor:
        for statement in source.split(';'):
            if statement.strip():
                cursor.execute(statement)
        cursor.execute("SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_manual_preview'")
        if cursor.fetchone()['n']:
            cursor.execute("SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_manual_preview' AND COLUMN_NAME='content_mode'")
            if not cursor.fetchone()['n']:
                cursor.execute("ALTER TABLE godp_manual_preview ADD COLUMN content_mode VARCHAR(24) NOT NULL DEFAULT 'legacy' COMMENT '人工策划内容模式：non_marketing非营销，legacy历史混合选题流程'")
        db.commit()
    print('Manual marketing request schema ready')


if __name__ == '__main__':
    main()
