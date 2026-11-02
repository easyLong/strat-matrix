"""Idempotent persistent manual-task execution metadata migration."""
from .db import connection

COLUMNS = {
    'execution_token': "VARCHAR(32) NULL COMMENT '当前执行领取令牌，用于拒绝过期执行结果'",
    'lease_expires_at': "DATETIME(6) NULL COMMENT '当前执行领取到期时间，按UTC保存'",
    'attempt_count': "INT NOT NULL DEFAULT 0 COMMENT '累计执行领取次数，达到上限后终止重试'",
    'next_attempt_at': "DATETIME(6) NULL COMMENT '下次允许重试时间，按UTC保存'",
}

def ensure_schema(cursor):
    cursor.execute('SHOW COLUMNS FROM godp_manual_task')
    existing = {row['Field'] for row in cursor.fetchall()}
    for name, definition in COLUMNS.items():
        if name not in existing:
            cursor.execute(f'ALTER TABLE godp_manual_task ADD COLUMN `{name}` {definition}')
    cursor.execute('SHOW INDEX FROM godp_manual_task')
    if not any(row['Key_name'] == 'idx_manual_task_queue' for row in cursor.fetchall()):
        cursor.execute('ALTER TABLE godp_manual_task ADD INDEX idx_manual_task_queue '
                       '(status,next_attempt_at,lease_expires_at,id)')

def main():
    with connection() as db, db.cursor() as cursor:
        ensure_schema(cursor)
        db.commit()
    print('Persistent manual-task schema ready.')

if __name__ == '__main__':
    main()
