"""Seed one 18-account failure batch for the results time-list demo."""

from datetime import date

from .db import connection


def main() -> None:
    batch_code = "DEMO-FAIL-20261026-18"
    with connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM godp_planning_batch WHERE batch_code=%s",
            (batch_code,),
        )
        existing = cursor.fetchone()
        if existing:
            print({"created": False, "batch_id": existing["id"], "items": 0})
            return

        cursor.execute(
            "SELECT account_code, account_name FROM godp_account "
            "WHERE account_code LIKE %s AND del_flag='N' ORDER BY id LIMIT 18",
            ("DEMO-P-%",),
        )
        accounts = cursor.fetchall()
        if len(accounts) < 18:
            raise RuntimeError(f"测试账号不足 18 个，当前只有 {len(accounts)} 个")

        cursor.execute(
            "SELECT topic_code, title FROM godp_topic "
            "WHERE del_flag='N' ORDER BY id LIMIT 1"
        )
        topic = cursor.fetchone()
        if not topic:
            raise RuntimeError("没有可复用的测试选题")

        cursor.execute(
            "INSERT INTO godp_planning_batch "
            "(batch_code, plan_type, status, cycle_start, cycle_end, account_count, "
            "content_count, note, create_by, update_by) "
            "VALUES (%s, 'auto', %s, %s, %s, %s, 0, %s, 'demo-seed', 'demo-seed')",
            (
                batch_code,
                "执行失败",
                date(2026, 10, 26),
                date(2026, 11, 1),
                len(accounts),
                "用于时间列表失败详情展示",
            ),
        )
        batch_id = cursor.lastrowid
        cursor.executemany(
            "INSERT INTO godp_planning_item "
            "(batch_id, account_id, account_name, publish_date, slot_type, topic_id, "
            "topic_title, status, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, 'regular', %s, %s, %s, 'demo-seed', 'demo-seed')",
            [
                (
                    batch_id,
                    account["account_code"],
                    account["account_name"],
                    date(2026, 10, 27),
                    topic["topic_code"],
                    topic["title"],
                    "匹配失败：测试失败数据",
                )
                for account in accounts
            ],
        )
        db.commit()
        print({"created": True, "batch_id": batch_id, "items": len(accounts)})


if __name__ == "__main__":
    main()
