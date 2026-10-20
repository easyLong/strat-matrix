"""Install metadata needed by the atomic Planning result commit adapter."""

from .db import connection


COLUMNS = {
    "production_batch_id": (
        "BIGINT NULL COMMENT 'Pipeline正式提交后关联的策划批次ID；仅记录下游提交关系'"
    ),
    "operations_committed_at": (
        "DATETIME(6) NULL COMMENT '匹配提案被正式策划Pipeline原子提交的UTC时间'"
    ),
}


def main() -> None:
    with connection() as db, db.cursor() as cursor:
        added = 0
        for name, definition in COLUMNS.items():
            cursor.execute(
                "SELECT COUNT(*) AS column_count FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_matching_task' AND COLUMN_NAME=%s",
                (name,),
            )
            if cursor.fetchone()["column_count"] == 0:
                cursor.execute(f"ALTER TABLE godp_matching_task ADD COLUMN `{name}` {definition}")
                added += 1
        cursor.execute(
            "SELECT COUNT(*) AS index_count FROM INFORMATION_SCHEMA.STATISTICS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='godp_matching_task' "
            "AND INDEX_NAME='idx_matching_task_production_batch'"
        )
        if cursor.fetchone()["index_count"] == 0:
            cursor.execute("ALTER TABLE godp_matching_task ADD KEY idx_matching_task_production_batch "
                           "(production_batch_id)")
        db.commit()
    print(f"Result commit schema ready; matching task columns added: {added}")


if __name__ == "__main__":
    main()
