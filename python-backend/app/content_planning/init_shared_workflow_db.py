"""Upgrade planner status projection and durable planning-task execution fields."""

from .db import connection

SCANNER_COLUMNS = {
    'production_task_id': "VARCHAR(64) NULL COMMENT '从Java读取的当前版本内容生产任务标识'",
    'production_lease_expires_at': "DATETIME(6) NULL COMMENT '历史本地模拟领取租约，生产对接不使用'",
    'production_attempt_count': "INT NOT NULL DEFAULT 0 COMMENT '历史本地模拟累计领取次数，生产对接不使用'",
    'production_error': "VARCHAR(500) NOT NULL DEFAULT '' COMMENT '当前版本内容生产失败原因'",
    'production_reported_at': "DATETIME(6) NULL COMMENT '最近采纳的内容生产结果时间，按UTC保存'",
}

MARKETING_STATUS_COLUMNS = {
    'content_completed_count': "INT NOT NULL DEFAULT 0 COMMENT '从Java查询并确认的营销内容生产完成数'",
    'content_failed_count': "INT NOT NULL DEFAULT 0 COMMENT '从Java查询并确认的营销内容生产失败数'",
    'production_reported_at': "DATETIME(6) NULL COMMENT '最近采纳的行内营销生产状态时间，按UTC保存'",
}


def ensure_schema(cursor):
    from .init_manual_tasks_db import ensure_schema as ensure_manual_tasks
    ensure_manual_tasks(cursor)
    cursor.execute('SHOW COLUMNS FROM godp_manual_marketing_task')
    marketing_columns = {row['Field'] for row in cursor.fetchall()}
    for name, definition in MARKETING_STATUS_COLUMNS.items():
        if name not in marketing_columns:
            cursor.execute(f'ALTER TABLE godp_manual_marketing_task ADD COLUMN {name} {definition}')
    cursor.execute('SHOW COLUMNS FROM godp_slot_state')
    columns = {row['Field'] for row in cursor.fetchall()}
    for name, definition in SCANNER_COLUMNS.items():
        if name not in columns:
            cursor.execute(f'ALTER TABLE godp_slot_state ADD COLUMN {name} {definition}')
    cursor.execute('SHOW INDEX FROM godp_slot_state')
    indexes = {row['Key_name'] for row in cursor.fetchall()}
    if 'uk_slot_production_task' not in indexes:
        cursor.execute('ALTER TABLE godp_slot_state ADD UNIQUE KEY uk_slot_production_task (production_task_id)')
    if 'idx_slot_production_scan' not in indexes:
        cursor.execute('ALTER TABLE godp_slot_state ADD KEY idx_slot_production_scan (production_status,production_lease_expires_at,id)')


def main():
    with connection() as db, db.cursor() as cursor:
        ensure_schema(cursor)
        from .init_system_config import seed_config
        seed_config(cursor, migrate_legacy=False)
        db.commit()
    print('Shared workflow schema ready; existing source and result data retained.')


if __name__ == '__main__':
    main()
