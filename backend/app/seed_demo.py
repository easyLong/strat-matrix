"""Insert clearly marked, repeatable demo catalog and planning records.

Only fixed DEMO-* records are created. Legacy demo hotspot placeholders are
converted into ordinary demo content; real business rows are never changed.
"""

from datetime import date, datetime, timedelta, timezone
import json

from .db import connection
from .models import StrategyConfig


ACCOUNTS = [
    ("DEMO-A001", "郑州演示账号·理财顾问"),
    ("DEMO-A002", "洛阳演示账号·生活向导"),
    ("DEMO-A003", "开封演示账号·职场伙伴"),
    ("DEMO-A004", "南阳演示账号·家庭管家"),
    ("DEMO-A005", "新乡演示账号·金融科普"),
    ("DEMO-A006", "许昌演示账号·城市观察"),
    ("DEMO-A007", "商丘演示账号·生活向导"),
    ("DEMO-A008", "焦作演示账号·职场伙伴"),
    ("DEMO-A009", "周口演示账号·家庭管家"),
    ("DEMO-A010", "平顶山演示账号·金融科普"),
    ("DEMO-A011", "信阳演示账号·城市观察"),
    ("DEMO-A012", "濮阳演示账号·理财顾问"),
]

TOPICS = [
    ("DEMO-T001", "演示选题：月度预算怎么做更清晰"),
    ("DEMO-T002", "演示选题：识别常见短信诈骗"),
    ("DEMO-T003", "演示选题：家庭备用金的准备思路"),
    ("DEMO-T004", "演示选题：手机银行转账前核对哪些信息"),
    ("DEMO-T005", "演示选题：外出旅行时的账户安全提醒"),
    ("DEMO-T006", "演示选题：新市民常用账户服务介绍"),
    ("DEMO-T007", "演示选题：银行卡遗失后的处理步骤"),
    ("DEMO-T008", "演示选题：日常消费记录整理方法"),
    ("DEMO-T009", "演示选题：长辈使用移动支付的注意事项"),
    ("DEMO-T010", "演示选题：毕业后第一份工资的收支管理"),
    ("DEMO-T011", "演示选题：周末城市生活服务盘点"),
    ("DEMO-T012", "演示选题：常见金融术语的通俗解释"),
]

MARKETING_TOPIC = ("DEMO-M001", "演示营销选题：线上服务入口介绍")
TOPIC_CATEGORIES = ("生活", "安全", "家庭", "服务", "安全", "服务", "安全", "生活", "家庭", "职场", "生活", "科普")


def automatic_items(
    monday: date,
    account_count: int,
    days: tuple[int, ...],
    marketing_accounts: set[int] | None = None,
    hotspot_accounts: set[int] | None = None,
) -> list[tuple]:
    marketing_accounts = marketing_accounts or set()
    hotspot_accounts = hotspot_accounts or set()
    rows = []
    for index, (account_id, account_name) in enumerate(ACCOUNTS[:account_count]):
        for position, day_offset in enumerate(days):
            publish_date = monday + timedelta(days=day_offset)
            if position == 1 and index in marketing_accounts:
                slot_type = "marketing_priority"
                topic_id, topic_title = MARKETING_TOPIC
                status = "已分配"
            else:
                slot_type = "regular"
                topic_id, topic_title = TOPICS[(index * len(days) + position) % len(TOPICS)]
                status = "已分配"
            rows.append((account_id, account_name, publish_date, slot_type, topic_id, topic_title, status))
    return rows


def manual_items(publish_date: date, account_indexes: tuple[int, ...], topic_index: int) -> list[tuple]:
    topic_id, topic_title = TOPICS[topic_index]
    return [
        (ACCOUNTS[index][0], ACCOUNTS[index][1], publish_date, "manual_extra", topic_id, topic_title, "待生成")
        for index in account_indexes
    ]


def seed_batches() -> list[tuple]:
    return [
        (
            "DEMO-AI-20260907-01", "auto", "策划完成", date(2026, 9, 7), date(2026, 9, 13),
            6, "演示数据｜较早周期的自动策划样例",
            automatic_items(date(2026, 9, 7), 6, (0, 2, 4), {1}),
        ),
        (
            "DEMO-AI-20260914-01", "auto", "策划完成", date(2026, 9, 14), date(2026, 9, 20),
            1, "演示数据｜账号资料缺失，等待补齐后重试", [],
        ),
        (
            "DEMO-AI-20260921-01", "auto", "策划完成", date(2026, 9, 21), date(2026, 9, 27),
            8, "演示数据｜上一周期自动策划样例",
            automatic_items(date(2026, 9, 21), 8, (0, 2, 4), {0, 5}),
        ),
        (
            "DEMO-MAN-20260924-01", "manual", "待生成", date(2026, 9, 24), date(2026, 9, 24),
            3, "演示数据｜临时定向追加，尚未调用内容 Agent",
            manual_items(date(2026, 9, 24), (0, 2, 4), 7),
        ),
        (
            "DEMO-AI-20260928-01", "auto", "策划完成", date(2026, 9, 28), date(2026, 10, 4),
            12, "演示数据｜当前周期：常规内容和已就绪营销内容",
            automatic_items(date(2026, 9, 28), 12, (0, 2, 4), {0, 4, 8}, {1, 3, 6, 9}),
        ),
        (
            "DEMO-MAN-20260930-01", "manual", "待生成", date(2026, 9, 30), date(2026, 9, 30),
            4, "演示数据｜当前周期的手动追加草稿",
            manual_items(date(2026, 9, 30), (1, 3, 5, 7), 2),
        ),
    ]


def main() -> None:
    created_config = 0
    created_accounts = 0
    created_topics = 0
    created_batches = 0
    created_items = 0
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT id FROM godp_strategy_config WHERE config_key='operations'")
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO godp_strategy_config "
                "(config_key, config_json, version, create_by, update_by) "
                "VALUES ('operations', %s, 1, 'demo-seed', 'demo-seed')",
                (StrategyConfig().model_dump_json(),),
            )
            created_config = 1

        for index, (account_code, account_name) in enumerate(ACCOUNTS):
            city = account_name.split("演示账号", 1)[0]
            persona = account_name.split("·", 1)[-1]
            cursor.execute(
                "INSERT INTO godp_account "
                "(account_code, account_name, city, persona, marketing_eligible, status, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, '启用', 'demo-seed', 'demo-seed') "
                "ON DUPLICATE KEY UPDATE id=id",
                (account_code, account_name, city, persona, int(index % 3 == 0)),
            )
            created_accounts += int(cursor.rowcount == 1)
            account_payload = json.dumps({
                "account_id": account_code,
                "account_name": account_name,
                "city": city,
                "persona": persona,
                "marketing_eligible": index % 3 == 0,
                "certified": index % 2 == 0,
                "followers": 12000 + index * 1750,
                "enabled": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False)
            cursor.execute(
                "INSERT INTO godp_account_source (account_id, source_updated_at, payload_json, create_by, update_by) "
                "VALUES (%s, %s, %s, 'demo-seed', 'demo-seed') "
                "ON DUPLICATE KEY UPDATE source_updated_at=VALUES(source_updated_at), "
                "payload_json=VALUES(payload_json), update_by='demo-seed', del_flag='N'",
                (account_code, datetime.now(timezone.utc).replace(tzinfo=None), account_payload),
            )

        for (topic_code, title), category in [*zip(TOPICS, TOPIC_CATEGORIES), (MARKETING_TOPIC, "营销")]:
            cursor.execute(
                "INSERT INTO godp_topic "
                "(topic_code, title, category, is_marketing, status, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, '可用', 'demo-seed', 'demo-seed') "
                "ON DUPLICATE KEY UPDATE id=id",
                (topic_code, title, category, int(category == "营销")),
            )
            created_topics += int(cursor.rowcount == 1)
            topic_payload = json.dumps({
                "topic_id": topic_code,
                "title": title,
                "summary": f"围绕“{title}”整理可直接执行的内容要点。",
                "outline": f"从用户场景、关键步骤和风险提示三个部分展开“{title}”。",
                "content_type": "营销内容" if category == "营销" else "知识科普",
                "source": "demo-seed",
                "category": category,
                "is_marketing": category == "营销",
                "approval_status": "approved",
                "enabled": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False)
            cursor.execute(
                "INSERT INTO godp_topic_source "
                "(topic_id, source_updated_at, approval_status, payload_json, create_by, update_by) "
                "VALUES (%s, %s, 'approved', %s, 'demo-seed', 'demo-seed') "
                "ON DUPLICATE KEY UPDATE source_updated_at=VALUES(source_updated_at), "
                "approval_status='approved', payload_json=VALUES(payload_json), "
                "update_by='demo-seed', del_flag='N'",
                (topic_code, datetime.now(timezone.utc).replace(tzinfo=None), topic_payload),
            )

        for code, plan_type, status, start, end, account_count, note, items in seed_batches():
            cursor.execute("SELECT id FROM godp_planning_batch WHERE batch_code=%s", (code,))
            if cursor.fetchone():
                continue
            content_count = sum(1 for item in items if item[6] == "已分配")
            cursor.execute(
                "INSERT INTO godp_planning_batch "
                "(batch_code, plan_type, status, cycle_start, cycle_end, account_count, "
                "content_count, note, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'demo-seed', 'demo-seed')",
                (code, plan_type, status, start, end, account_count, content_count, note),
            )
            batch_id = cursor.lastrowid
            if items:
                cursor.executemany(
                    "INSERT INTO godp_planning_item "
                    "(batch_id, account_id, account_name, publish_date, slot_type, topic_id, "
                    "topic_title, status, create_by, update_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'demo-seed', 'demo-seed')",
                    [(batch_id, *item) for item in items],
                )
                if plan_type == "auto":
                    cursor.execute(
                        "SELECT id, topic_id FROM godp_planning_item WHERE batch_id=%s",
                        (batch_id,),
                    )
                    cursor.executemany(
                        "INSERT IGNORE INTO godp_slot_state "
                        "(item_id, slot_id, version, topic_id, production_status, create_by, update_by) "
                        "VALUES (%s, %s, 1, %s, 'planned', 'demo-seed', 'demo-seed')",
                        [(row["id"], f"DEMO-SLOT-{row['id']}", row["topic_id"])
                         for row in cursor.fetchall()],
                    )
            created_batches += 1
            created_items += len(items)
        cursor.execute(
            "SELECT i.id, i.topic_id FROM godp_planning_item i "
            "JOIN godp_planning_batch b ON b.id=i.batch_id "
            "LEFT JOIN godp_slot_state s ON s.item_id=i.id "
            "WHERE b.batch_code LIKE 'DEMO-%%' AND b.plan_type='auto' "
            "AND i.del_flag='N' AND s.id IS NULL",
        )
        cursor.executemany(
            "INSERT IGNORE INTO godp_slot_state "
            "(item_id, slot_id, version, topic_id, production_status, create_by, update_by) "
            "VALUES (%s, %s, 1, %s, 'planned', 'demo-seed', 'demo-seed')",
            [(row["id"], f"DEMO-SLOT-{row['id']}", row["topic_id"])
             for row in cursor.fetchall()],
        )
        cursor.execute(
            "UPDATE godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
            "SET i.slot_type='regular', i.topic_id=%s, i.topic_title=%s, "
            "i.status='已分配', i.update_by='demo-seed' "
            "WHERE b.batch_code LIKE 'DEMO-%%' AND b.create_by='demo-seed' "
            "AND i.create_by='demo-seed' AND i.slot_type='hotspot_reserved'",
            TOPICS[0],
        )
        db.commit()
    print(
        f"Created {created_config} demo config, {created_accounts} accounts, "
        f"{created_topics} topics, {created_batches} batches and {created_items} items"
    )


if __name__ == "__main__":
    main()

