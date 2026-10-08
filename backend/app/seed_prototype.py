"""Seed the prototype's complete local demo dataset.

The reset is limited to records using the reserved DEMO- prefix. Customer
records and integration facts are never deleted or changed.
"""

from datetime import date, datetime, timedelta, timezone
import json

from .db import connection
from .taxonomy import normalize_taxonomy


TAGS = {
    "T1": ["非营销", "营销"],
    "T2": ["流量", "转化"],
    "T3": ["金融理财", "本地生活", "数码科技", "职场成长", "健康生活", "亲子家庭"],
    "T4": ["年轻客群", "职场人群", "家庭客群", "宝妈客群", "银发客群"],
    "T5": ["通勤", "周末休闲", "家庭消费", "餐饮", "出行", "居家"],
}

PROTOTYPE_ACCOUNTS = [
    ("A", "美食小日记", "郑州", "生活向导", "@food_diary", True, 126000, "上升", 38000),
    ("B", "旅行玩家", "洛阳", "城市观察", "@travel_go", True, 87000, "平稳", 29000),
    ("C", "数码前沿", "开封", "数码顾问", "@digital_now", False, 32000, "上升", 18000),
    ("D", "职场进阶指南", "南阳", "职场伙伴", "@career_up", True, 64000, "平稳", 22000),
    ("E", "本地生活研究所", "新乡", "生活向导", "@city_life", True, 189000, "上升", 51000),
    ("F", "年轻人理财课", "许昌", "理财顾问", "@money_young", False, 26000, "下滑", 9000),
    ("G", "妈妈生活志", "商丘", "家庭管家", "@mom_life", True, 221000, "平稳", 44000),
    ("H", "城市观察员", "焦作", "城市观察", "@city_watch", False, 13000, "上升", 11000),
]

TOPICS = [
    ("T001", "属地推荐", "周末城市轻徒步路线，半日松弛攻略", "围绕城市近郊轻徒步路线，提供交通、路线长度、装备和餐饮建议。", "本地生活", False),
    ("T002", "产品营销", "信用卡周末权益清单：吃喝玩乐怎么选", "梳理周末高频权益场景，用清单化方式说明适用人群与使用条件。", "信用卡权益", True),
    ("T003", "热点解读", "降息之后，普通家庭如何安排闲置资金", "结合热点背景解释家庭现金管理思路，突出风险分层与流动性安排。", "家庭理财", False),
    ("T004", "财商教育", "工资到账后应该先做哪三件事", "从现金流、应急金与长期储蓄三个步骤帮助用户建立资金安排顺序。", "资金管理", False),
    ("T005", "客群兴趣内容", "秋季养生食谱：增强免疫力的家常搭配", "围绕秋季饮食场景给出易执行的家常搭配与注意事项。", "健康生活", False),
    ("T006", "一句话讨论", "手机换新季：预算不同怎么选", "围绕预算档位快速给出换机思路，引导评论区讨论。", "数码消费", False),
    ("T007", "产品权益种草", "周末餐饮权益怎么用更划算", "聚焦餐饮场景，解释权益使用门槛和组合方式。", "餐饮权益", True),
    ("T008", "热点解读", "假期出行新规落地后需要注意什么", "用问答形式拆解近期出行相关热点规则变化。", "出行热点", False),
]


def reset_demo_planning(cursor) -> None:
    cursor.execute("SELECT id FROM godp_planning_batch WHERE batch_code LIKE 'DEMO-%'")
    batch_ids = [row["id"] for row in cursor.fetchall()]
    if batch_ids:
        placeholders = ",".join(["%s"] * len(batch_ids))
        cursor.execute(f"SELECT id FROM godp_planning_item WHERE batch_id IN ({placeholders})", batch_ids)
        item_ids = [row["id"] for row in cursor.fetchall()]
        if item_ids:
            item_marks = ",".join(["%s"] * len(item_ids))
            cursor.execute(f"UPDATE godp_planning_adjustment SET del_flag='Y' WHERE item_id IN ({item_marks})", item_ids)
            cursor.execute(f"UPDATE godp_slot_state SET del_flag='Y' WHERE item_id IN ({item_marks})", item_ids)
            cursor.execute(f"UPDATE godp_planning_item SET del_flag='Y' WHERE id IN ({item_marks})", item_ids)
        cursor.execute(f"UPDATE godp_manual_task SET del_flag='Y' WHERE batch_id IN ({placeholders})", batch_ids)
        cursor.execute(f"UPDATE godp_planning_batch SET del_flag='Y' WHERE id IN ({placeholders})", batch_ids)
    cursor.execute("UPDATE godp_manual_task SET del_flag='Y' WHERE task_code LIKE 'MAN-TASK-%'")
    cursor.execute("UPDATE godp_manual_preview SET del_flag='Y' WHERE preview_code LIKE 'PREV-%'")
    cursor.execute("UPDATE godp_integration_outbox SET del_flag='Y' WHERE payload_json LIKE '%DEMO-%'")


def seed_config(cursor, now: datetime) -> None:
    config = {
        "marketing_max": 1,
        "rolling_posts": 10,
        "stage_targets": [
            {"name": "冷启验证期", "traffic": 80, "conversion": 20},
            {"name": "流量增长期", "traffic": 70, "conversion": 30},
            {"name": "转化试探期", "traffic": 50, "conversion": 50},
            {"name": "转化放大期", "traffic": 30, "conversion": 70},
            {"name": "稳定经营期", "traffic": 50, "conversion": 50},
        ],
    }
    config_json = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    cursor.execute(
        "INSERT INTO godp_strategy_config (config_key, config_json, version, create_by, update_by) "
        "VALUES ('operations', %s, 3, 'demo-seed', 'demo-seed') "
        "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), version=3, "
        "create_by='demo-seed', update_by='demo-seed', del_flag='N'",
        (config_json,),
    )
    for module in ("marketing", "strategy"):
        for version, action, operator in ((1, "迁移基线", "运营小王"), (2, "保存", "运营小冰"), (3, "保存", "运营小冰")):
            cursor.execute(
                "INSERT INTO godp_strategy_config_version "
                "(config_key, version, config_json, action, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, 'demo-seed') "
                "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), action=VALUES(action), "
                "create_by=VALUES(create_by), update_by='demo-seed', del_flag='N'",
                (module, version, config_json, action, operator),
            )
    cursor.execute(
        "INSERT INTO godp_strategy_config_version "
        "(config_key, version, config_json, action, create_by, update_by) "
        "VALUES ('operations', 3, %s, '保存', 'demo-seed', 'demo-seed') "
        "ON DUPLICATE KEY UPDATE config_json=VALUES(config_json), action='保存', del_flag='N'",
        (config_json,),
    )
    tags_json = json.dumps(normalize_taxonomy(TAGS), ensure_ascii=False, separators=(",", ":"))
    cursor.execute(
        "INSERT IGNORE INTO godp_strategy_config "
        "(config_key, config_json, version, create_by, update_by) "
        "VALUES ('tag_taxonomy', %s, 1, 'demo-seed', 'demo-seed')",
        (tags_json,),
    )


def seed_accounts_topics(cursor, now: datetime) -> list[str]:
    # 原型验收模式只展示 DEMO-P 目录，之前的大目录演示记录保留在库中但不参与接口查询。
    cursor.execute("UPDATE godp_account SET del_flag='Y' WHERE account_code LIKE 'DEMO-%' AND account_code NOT LIKE 'DEMO-P-%'")
    cursor.execute("UPDATE godp_account_source SET del_flag='Y' WHERE account_id LIKE 'DEMO-%' AND account_id NOT LIKE 'DEMO-P-%'")
    cursor.execute("UPDATE godp_topic SET del_flag='Y' WHERE topic_code LIKE 'DEMO-%' AND topic_code NOT LIKE 'DEMO-P-%'")
    cursor.execute("UPDATE godp_topic_source SET del_flag='Y' WHERE topic_id LIKE 'DEMO-%' AND topic_id NOT LIKE 'DEMO-P-%'")
    cursor.execute("UPDATE godp_topic_tag SET del_flag='Y' WHERE topic_id LIKE 'DEMO-%' AND topic_id NOT LIKE 'DEMO-P-%'")
    account_ids: list[str] = []
    account_rows = []
    source_rows = []
    for code, name, city, persona, handle, marketing, followers, trend, average in PROTOTYPE_ACCOUNTS:
        account_id = f"DEMO-P-{code}"
        account_ids.append(account_id)
        account_rows.append((account_id, name, city, persona, int(marketing)))
        source_rows.append((account_id, now, json.dumps({
            "account_id": account_id, "account_name": name, "platform": "演示平台",
            "organization": "原型演示机构", "city": city, "marketing_eligible": marketing,
            "persona": persona, "handle": handle, "certified": code in {"A", "B", "D", "E", "G"},
            "followers": followers, "traffic_trend": trend, "traffic_average": average,
            "enabled": True, "updated_at": now.replace(tzinfo=timezone.utc).isoformat(),
        }, ensure_ascii=False)))
    for index in range(9, 69):
        code = f"M{index:02d}"
        account_id = f"DEMO-P-{code}"
        city = ["郑州", "洛阳", "开封", "南阳", "新乡", "许昌", "商丘", "焦作"][index % 8]
        persona = ["生活向导", "理财顾问", "职场伙伴", "家庭管家"][index % 4]
        name = f"测试账号{index:02d}"
        marketing = index % 5 == 0
        followers = 6000 + index * 3700
        account_ids.append(account_id)
        account_rows.append((account_id, name, city, persona, int(marketing)))
        source_rows.append((account_id, now, json.dumps({
            "account_id": account_id, "account_name": name, "platform": "演示平台",
            "organization": "原型测试机构", "city": city, "marketing_eligible": marketing,
            "persona": persona, "handle": f"@demo_{index}", "certified": index % 3 != 0,
            "followers": followers, "traffic_trend": "下滑" if index % 4 == 0 else "上升",
            "traffic_average": 7000 + index * 800, "enabled": True,
            "updated_at": now.replace(tzinfo=timezone.utc).isoformat(),
        }, ensure_ascii=False)))
    cursor.executemany(
        "INSERT INTO godp_account (account_code, account_name, city, persona, marketing_eligible, status, create_by, update_by) "
        "VALUES (%s, %s, %s, %s, %s, '启用', 'demo-seed', 'demo-seed') "
        "ON DUPLICATE KEY UPDATE account_name=VALUES(account_name), city=VALUES(city), persona=VALUES(persona), "
        "marketing_eligible=VALUES(marketing_eligible), status='启用', update_by='demo-seed', del_flag='N'",
        account_rows,
    )
    cursor.executemany(
        "INSERT INTO godp_account_source (account_id, source_updated_at, payload_json, create_by, update_by) "
        "VALUES (%s, %s, %s, 'demo-seed', 'demo-seed') "
        "ON DUPLICATE KEY UPDATE source_updated_at=VALUES(source_updated_at), payload_json=VALUES(payload_json), "
        "update_by='demo-seed', del_flag='N'",
        source_rows,
    )
    topic_ids: list[str] = []
    topic_rows = []
    topic_sources = []
    content_types = {"T001": "属地推荐", "T002": "产品营销", "T003": "热点解读", "T004": "财商教育", "T005": "客群兴趣内容", "T006": "一句话讨论", "T007": "产品权益种草", "T008": "热点解读"}
    for code, category, title, outline, theme, marketing in TOPICS:
        topic_id = f"DEMO-P-{code}"
        topic_ids.append(topic_id)
        topic_rows.append((topic_id, title, category, int(marketing)))
        topic_sources.append((topic_id, now, json.dumps({
            "topic_id": topic_id, "title": title, "summary": outline, "outline": outline,
            "source": "prototype-seed", "category": category, "content_type": content_types[code],
            "theme": theme, "is_marketing": marketing, "approval_status": "approved", "enabled": True,
            "updated_at": now.replace(tzinfo=timezone.utc).isoformat(),
        }, ensure_ascii=False)))
    cursor.executemany(
        "INSERT INTO godp_topic (topic_code, title, category, is_marketing, status, create_by, update_by) "
        "VALUES (%s, %s, %s, %s, '可用', 'demo-seed', 'demo-seed') "
        "ON DUPLICATE KEY UPDATE title=VALUES(title), category=VALUES(category), is_marketing=VALUES(is_marketing), "
        "status='可用', update_by='demo-seed', del_flag='N'",
        topic_rows,
    )
    cursor.executemany(
        "INSERT INTO godp_topic_source (topic_id, source_updated_at, approval_status, payload_json, create_by, update_by) "
        "VALUES (%s, %s, 'approved', %s, 'demo-seed', 'demo-seed') "
        "ON DUPLICATE KEY UPDATE source_updated_at=VALUES(source_updated_at), approval_status='approved', "
        "payload_json=VALUES(payload_json), update_by='demo-seed', del_flag='N'",
        topic_sources,
    )
    for topic_id, tags in zip(topic_ids, (["非营销", "流量", "本地生活", "年轻客群", "周末休闲"], ["营销", "转化", "金融理财", "年轻客群", "餐饮"], ["非营销", "转化", "金融理财", "家庭客群", "居家"], ["非营销", "流量", "金融理财", "职场人群", "通勤"], ["非营销", "流量", "健康生活", "宝妈客群", "家庭消费"], ["非营销", "流量", "数码科技", "年轻客群", "通勤"], ["营销", "转化", "本地生活", "家庭客群", "餐饮"], ["非营销", "流量", "本地生活", "年轻客群", "出行"])):
        cursor.execute(
            "INSERT INTO godp_topic_tag (topic_id, version, tags_json, create_by, update_by) VALUES (%s, 1, %s, 'demo-seed', 'demo-seed') "
            "ON DUPLICATE KEY UPDATE tags_json=VALUES(tags_json), update_by='demo-seed', del_flag='N'",
            (topic_id, json.dumps({f"T{i + 1}": [tag] for i, tag in enumerate(tags)}, ensure_ascii=False)),
        )
    return account_ids, topic_ids


def seed_batches(cursor, account_ids: list[str], topic_ids: list[str]) -> None:
    weeks = [
        ("DEMO-P-AI-20260907", date(2026, 9, 7), 39, 91, 7, 19, 9, "\u7b56\u5212\u5b8c\u6210"),
        ("DEMO-P-AI-20260914", date(2026, 9, 14), 40, 90, 8, 22, 12, "\u7b56\u5212\u5b8c\u6210"),
        ("DEMO-P-AI-20260921", date(2026, 9, 21), 42, 91, 10, 25, 18, "\u7b56\u5212\u5b8c\u6210"),
        ("DEMO-P-AI-20260928", date(2026, 9, 28), 54, 110, 16, 20, 20, "\u70ed\u70b9\u7a7a\u69fd\u5f85\u586b\u5145"),
        ("DEMO-P-AI-20261005", date(2026, 10, 5), 60, 120, 20, 40, 24, "\u5df2\u89c4\u5212"),
    ]
    for week_index, (batch_code, start, account_count, regular_count, marketing_count, hotspot_count, manual_count, status) in enumerate(weeks):
        end = start + timedelta(days=6)
        auto_content_count = regular_count + marketing_count + hotspot_count
        cursor.execute(
            "INSERT INTO godp_planning_batch (batch_code, plan_type, status, cycle_start, cycle_end, account_count, content_count, note, create_by, update_by) "
            "VALUES (%s, 'auto', %s, %s, %s, %s, %s, %s, 'demo-seed', 'demo-seed') "
            "ON DUPLICATE KEY UPDATE plan_type='auto', status=VALUES(status), cycle_start=VALUES(cycle_start), "
            "cycle_end=VALUES(cycle_end), account_count=VALUES(account_count), content_count=VALUES(content_count), "
            "note=VALUES(note), update_by='demo-seed', del_flag='N'",
            (batch_code, status, start, end, account_count, auto_content_count, "prototype auto planning"),
        )
        cursor.execute("SELECT id FROM godp_planning_batch WHERE batch_code=%s", (batch_code,))
        batch_id = cursor.fetchone()["id"]
        slot_types = ["regular"] * regular_count + ["marketing_priority"] * marketing_count + ["hotspot"] * hotspot_count
        account_slot_positions: dict[str, int] = {}
        for index, slot_type in enumerate(slot_types):
            account_index = index % account_count
            account_id = account_ids[account_index]
            slot_position = account_slot_positions.get(account_id, 0)
            account_slot_positions[account_id] = slot_position + 1
            topic_id = topic_ids[(index * 3 + week_index * 2) % len(topic_ids)]
            if slot_type == "marketing_priority":
                topic_id = topic_ids[1]
            elif slot_type == "hotspot":
                topic_id = topic_ids[2 if index % 2 == 0 else 7]
            status_value = "\u5df2\u5206\u914d"
            publish_date = start + timedelta(days=(slot_position % 3) * 2)
            cursor.execute(
                "INSERT INTO godp_planning_item (batch_id, account_id, account_name, publish_date, slot_type, topic_id, topic_title, status, create_by, update_by) "
                "SELECT %s, a.account_code, a.account_name, %s, %s, t.topic_code, t.title, %s, 'demo-seed', 'demo-seed' "
                "FROM godp_account a JOIN godp_topic t ON t.topic_code=%s WHERE a.account_code=%s",
                (batch_id, publish_date, slot_type, status_value, topic_id, account_id),
            )
            item_id = cursor.lastrowid
            if slot_type == "hotspot" and week_index == 3:
                production_status = "ready" if index < regular_count + marketing_count + 4 else "planned"
            elif slot_type == "hotspot" and week_index == 4:
                production_status = "planned"
            elif slot_type == "hotspot":
                production_status = "ready"
            else:
                production_status = "published" if index % 29 == 0 else ("generated" if index % 11 == 0 else "planned")
            published_at = datetime(2026, 9, 23, 8, 0) if production_status == "published" else None
            cursor.execute(
                "INSERT INTO godp_slot_state (item_id, slot_id, version, topic_id, production_status, content_id, generated_at, published_at, create_by, update_by) "
                "VALUES (%s, %s, 1, %s, %s, %s, %s, %s, 'demo-seed', 'demo-seed')",
                (item_id, f"DEMO-P-SLOT-{item_id}", topic_id, production_status,
                 f"DEMO-P-CONTENT-{item_id}" if production_status in ("generated", "published") else None,
                 datetime(2026, 9, 22, 8, 0) if production_status in ("generated", "published") else None,
                 published_at),
            )

        manual_code = f"DEMO-P-MAN-{start.strftime('%Y%m%d')}"
        manual_status = "\u5f85\u5ba1\u6838" if week_index == 2 else "\u5df2\u5b8c\u6210"
        cursor.execute(
            "INSERT INTO godp_planning_batch (batch_code, plan_type, status, cycle_start, cycle_end, account_count, content_count, note, create_by, update_by) "
            "VALUES (%s, 'manual', %s, %s, %s, %s, %s, %s, 'demo-seed', 'demo-seed') "
            "ON DUPLICATE KEY UPDATE plan_type='manual', status=VALUES(status), cycle_start=VALUES(cycle_start), "
            "cycle_end=VALUES(cycle_end), account_count=VALUES(account_count), content_count=VALUES(content_count), "
            "note=VALUES(note), update_by='demo-seed', del_flag='N'",
            (manual_code, manual_status, start, end, manual_count, manual_count, "prototype manual planning"),
        )
        cursor.execute("SELECT id FROM godp_planning_batch WHERE batch_code=%s", (manual_code,))
        manual_batch_id = cursor.fetchone()["id"]
        for offset in range(manual_count):
            account_id = account_ids[(account_count + offset) % len(account_ids)]
            topic_id = topic_ids[(offset + 3) % len(topic_ids)]
            publish_date = start + timedelta(days=5 + offset % 2)
            cursor.execute(
                "INSERT INTO godp_planning_item (batch_id, account_id, account_name, publish_date, slot_type, topic_id, topic_title, status, create_by, update_by) "
                "SELECT %s, a.account_code, a.account_name, %s, 'manual_extra', t.topic_code, t.title, %s, 'demo-seed', 'demo-seed' "
                "FROM godp_account a JOIN godp_topic t ON t.topic_code=%s WHERE a.account_code=%s",
                (manual_batch_id, publish_date, "\u5f85\u5ba1\u6838" if week_index == 2 else "\u5df2\u751f\u6210", topic_id, account_id),
            )
        task_code = f"MAN-TASK-DEMO-P-{start.strftime('%Y%m%d')}"
        preview_code = f"PREV-DEMO-P-{start.strftime('%Y%m%d')}"
        task_status = "\u6267\u884c\u4e2d" if week_index == 2 else "\u5df2\u5b8c\u6210"
        result_count = 0 if week_index == 2 else manual_count
        failure_count = manual_count if week_index == 2 else 0
        cursor.execute(
            "INSERT INTO godp_manual_task (task_code, preview_code, publish_date, planned_account_count, result_count, failure_count, topic_count, status, failure_reason, batch_id, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '', %s, 'demo-seed', 'demo-seed') "
            "ON DUPLICATE KEY UPDATE preview_code=VALUES(preview_code), publish_date=VALUES(publish_date), "
            "planned_account_count=VALUES(planned_account_count), result_count=VALUES(result_count), failure_count=VALUES(failure_count), "
            "topic_count=VALUES(topic_count), status=VALUES(status), failure_reason='', batch_id=VALUES(batch_id), "
            "update_by='demo-seed', del_flag='N'",
            (task_code, preview_code, start, manual_count, result_count, failure_count, min(manual_count, len(topic_ids)), task_status, manual_batch_id),
        )


def main() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with connection() as db, db.cursor() as cursor:
        reset_demo_planning(cursor)
        seed_config(cursor, now)
        account_ids, topic_ids = seed_accounts_topics(cursor, now)
        seed_batches(cursor, account_ids, topic_ids)
        db.commit()
    print("Prototype demo data initialized: 68 accounts, 8 topics, 5 auto cycles, taxonomy T1-T5")


if __name__ == "__main__":
    main()
