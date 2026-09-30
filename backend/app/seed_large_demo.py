"""Create a larger local demo catalog: 100 accounts and 600 topics.

Only the reserved DEMO-L* identifiers are written. The script is idempotent and
also refreshes the source payloads used by the account and topic APIs.
"""

from datetime import datetime, timezone
import json

from .db import connection


CITY_PERSONAS = [
    ("郑州", "理财顾问"), ("洛阳", "生活向导"), ("开封", "职场伙伴"),
    ("南阳", "家庭管家"), ("新乡", "金融科普"), ("许昌", "城市观察"),
    ("商丘", "生活向导"), ("焦作", "职场伙伴"), ("周口", "家庭管家"),
    ("平顶山", "金融科普"), ("信阳", "城市观察"), ("濮阳", "理财顾问"),
    ("安阳", "消费规划师"), ("漯河", "本地生活"), ("三门峡", "家庭管家"),
    ("驻马店", "职场伙伴"), ("鹤壁", "城市观察"), ("济源", "理财顾问"),
    ("商丘", "安全提醒官"), ("郑州", "新市民服务"),
]

SUBJECTS = [
    "家庭预算", "备用金准备", "日常消费", "账户安全", "移动支付", "银行卡使用",
    "反诈识别", "出行规划", "城市服务", "亲子教育", "长辈数字生活", "毕业求职",
    "职场沟通", "副业规划", "租房生活", "小微经营", "节日消费", "健康管理",
    "本地活动", "线上服务", "贷款常识", "保险保障", "信用管理", "养老金准备",
    "年轻家庭", "新市民生活", "商户经营", "女性成长", "银发生活", "社区互助",
]

ACTIONS = [
    "怎么做更清晰", "常见误区有哪些", "需要提前准备什么", "如何用三步完成",
    "一张清单讲明白", "适合新手的做法", "哪些细节容易忽略", "如何判断是否适合自己",
    "遇到变化时怎么调整", "怎样安排更稳妥", "从一个案例看懂", "如何降低操作风险",
    "周末可以做哪些准备", "给忙碌人群的建议", "如何和家人一起规划",
    "低成本实践方法", "高频问题集中答疑", "不同阶段怎么安排", "怎样避免重复花费",
    "一周复盘可以怎么做",
]

CATEGORY_TYPES = [
    ("生活", "生活服务"), ("安全", "安全提醒"), ("家庭", "家庭经营"),
    ("服务", "服务介绍"), ("职场", "职场成长"), ("科普", "知识科普"),
    ("城市", "属地推荐"), ("消费", "消费指南"), ("经营", "经营方法"),
    ("营销", "营销内容"),
]


def account_rows(now: datetime) -> tuple[list[tuple], list[tuple]]:
    records: list[tuple] = []
    sources: list[tuple] = []
    for index in range(1, 101):
        city, persona = CITY_PERSONAS[(index - 1) % len(CITY_PERSONAS)]
        account_id = f"DEMO-LA{index:03d}"
        account_name = f"{city}批量演示账号{index:03d}·{persona}"
        marketing_eligible = index % 4 == 0
        certified = index % 3 != 0
        followers = 5000 + index * 137
        records.append((account_id, account_name, city, persona, int(marketing_eligible)))
        sources.append((
            account_id, now, json.dumps({
                "account_id": account_id,
                "account_name": account_name,
                "platform": "演示平台",
                "organization": f"演示机构{(index - 1) % 8 + 1}",
                "city": city,
                "marketing_eligible": marketing_eligible,
                "persona": persona,
                "target_audience": ["本地用户", "家庭客群"],
                "interests": ["生活服务", "实用知识"],
                "certified": certified,
                "followers": followers,
                "enabled": True,
                "updated_at": now.replace(tzinfo=timezone.utc).isoformat(),
            }, ensure_ascii=False),
        ))
    return records, sources


def topic_rows(now: datetime) -> tuple[list[tuple], list[tuple]]:
    records: list[tuple] = []
    sources: list[tuple] = []
    for index in range(600):
        subject = SUBJECTS[index % len(SUBJECTS)]
        action = ACTIONS[index // len(SUBJECTS)]
        category, content_type = CATEGORY_TYPES[index % len(CATEGORY_TYPES)]
        topic_id = f"DEMO-LT{index + 1:03d}"
        title = f"批量演示选题：{subject}{action}"
        is_marketing = category == "营销"
        records.append((topic_id, title, category, int(is_marketing)))
        sources.append((
            topic_id, now, json.dumps({
                "topic_id": topic_id,
                "title": title,
                "summary": f"围绕{subject}，说明{action}时的关键判断和执行步骤。",
                "outline": f"先说明{subject}的使用场景，再拆解{action}的具体方法，最后补充风险提醒。",
                "source": "seed-large-demo",
                "category": category,
                "content_type": content_type,
                "applicable_cities": [],
                "is_marketing": is_marketing,
                "product_or_activity": "批量演示活动" if is_marketing else "",
                "approval_status": "approved",
                "enabled": True,
                "updated_at": now.replace(tzinfo=timezone.utc).isoformat(),
            }, ensure_ascii=False),
        ))
    return records, sources


def main() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    accounts, account_sources = account_rows(now)
    topics, topic_sources = topic_rows(now)
    with connection() as db, db.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO godp_account "
            "(account_code, account_name, city, persona, marketing_eligible, status, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, %s, '启用', 'demo-large-seed', 'demo-large-seed') "
            "ON DUPLICATE KEY UPDATE account_name=VALUES(account_name), city=VALUES(city), "
            "persona=VALUES(persona), marketing_eligible=VALUES(marketing_eligible), "
            "status='启用', update_by='demo-large-seed', del_flag='N'",
            accounts,
        )
        cursor.executemany(
            "INSERT INTO godp_account_source "
            "(account_id, source_updated_at, payload_json, create_by, update_by) "
            "VALUES (%s, %s, %s, 'demo-large-seed', 'demo-large-seed') "
            "ON DUPLICATE KEY UPDATE source_updated_at=VALUES(source_updated_at), "
            "payload_json=VALUES(payload_json), update_by='demo-large-seed', del_flag='N'",
            account_sources,
        )
        cursor.executemany(
            "INSERT INTO godp_topic "
            "(topic_code, title, category, is_marketing, status, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, '可用', 'demo-large-seed', 'demo-large-seed') "
            "ON DUPLICATE KEY UPDATE title=VALUES(title), category=VALUES(category), "
            "is_marketing=VALUES(is_marketing), status='可用', update_by='demo-large-seed', del_flag='N'",
            topics,
        )
        cursor.executemany(
            "INSERT INTO godp_topic_source "
            "(topic_id, source_updated_at, approval_status, payload_json, create_by, update_by) "
            "VALUES (%s, %s, 'approved', %s, 'demo-large-seed', 'demo-large-seed') "
            "ON DUPLICATE KEY UPDATE source_updated_at=VALUES(source_updated_at), "
            "approval_status='approved', payload_json=VALUES(payload_json), "
            "update_by='demo-large-seed', del_flag='N'",
            topic_sources,
        )
        db.commit()
    print(f"Seeded {len(accounts)} accounts and {len(topics)} topics with DEMO-L prefixes")


if __name__ == "__main__":
    main()
