"""Generate a weekly batch using the documented ordinary-topic fallback.

This operator-triggered first slice does not claim to run vector matching or AI.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

from .db import connection
from .account_metrics import account_metrics
from .account_profile import interaction_snapshot, save_batch_account_profiles
from .models import LifecycleCondition, StrategyConfig


class PlanningError(Exception):
    pass


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def current_next_monday() -> date:
    return monday(datetime.now(ZoneInfo("Asia/Shanghai")).date()) + timedelta(days=7)


def matches(condition: LifecycleCondition, metrics: dict[str, int | float]) -> bool:
    actual = metrics[condition.field]
    expected = condition.value
    return {
        "lt": actual < expected,
        "lte": actual <= expected,
        "gte": actual >= expected,
        "gt": actual > expected,
        "eq": actual == expected,
    }[condition.operator]


def lifecycle_stage(config: StrategyConfig, metrics: dict[str, int | float]) -> str:
    for rule in config.lifecycle_rules:
        if rule.catchAll:
            return rule.name
        passed = matches(rule.conditions[0], metrics)
        for condition in rule.conditions[1:]:
            result = matches(condition, metrics)
            passed = passed and result if condition.join == "AND" else passed or result
        if passed:
            return rule.name
    raise PlanningError("生命周期配置缺少兜底阶段")


def load_accounts(cursor, scope: str, config: StrategyConfig) -> list[dict]:
    cursor.execute(
        "SELECT a.account_code, a.account_name, a.persona, a.marketing_eligible, s.source_updated_at, "
        "s.payload_json FROM godp_account a JOIN godp_account_source s "
        "ON s.account_id=a.account_code WHERE a.del_flag='N' AND s.del_flag='N' "
        "AND s.active_in_snapshot=1 "
        "AND a.status='启用' ORDER BY a.account_code"
    )
    accounts = []
    direct_metrics: set[str] = set()
    now_utc = datetime.now(timezone.utc)
    for row in cursor.fetchall():
        if row["account_code"].startswith("DEMO-") != (scope == "demo"):
            continue
        source = json.loads(row["payload_json"])
        account_status = source.get("account_status")
        enabled = account_status if account_status is not None else source.get("enabled", True)
        persona = source.get("account_persona")
        if persona is None:
            persona = source.get("persona") or row["persona"]
        if not enabled or not row["account_name"].strip() or not persona.strip():
            continue
        account = {
            "account_id": row["account_code"],
            "account_name": row["account_name"],
            "persona": persona,
            "marketing_eligible": bool(row["marketing_eligible"]),
            "followers_count": int(source.get("follower_count") if source.get("follower_count") is not None
                                   else source.get("followers") or 0),
            "source_updated_at": row["source_updated_at"].isoformat(),
            "valid_content_count": 0,
            "rolling_interaction_count": 0,
            "source_payload": source,
            "metrics_as_of": now_utc.isoformat(),
            "rolling_posts": config.rolling_posts,
        }
        if source.get("interaction_data") is not None:
            account["interaction_data"] = interaction_snapshot(source["interaction_data"], now_utc)
            account["interaction_source"] = "if01"
            account.update(account_metrics(account["interaction_data"], config.rolling_posts, now_utc))
            direct_metrics.add(account["account_id"])
        accounts.append(account)
    if not accounts:
        raise PlanningError(f"{scope} 范围内没有已同步且启用的账号")

    by_id = {account["account_id"]: account for account in accounts}
    cursor.execute(
        "SELECT account_id, published_at, payload_json FROM godp_content_history "
        "WHERE del_flag='N' AND published_at IS NOT NULL "
        "AND published_at>=DATE_SUB(%s, INTERVAL 3 MONTH) "
        "AND published_at<=%s "
        "ORDER BY account_id, published_at DESC, id DESC",
        (now_utc.replace(tzinfo=None), now_utc.replace(tzinfo=None)),
    )
    legacy_posts: dict[str, list[dict]] = {}
    for row in cursor.fetchall():
        account = by_id.get(row["account_id"])
        if account is None or account["account_id"] in direct_metrics:
            continue
        content = json.loads(row["payload_json"])
        content["published_at"] = row["published_at"].isoformat()
        legacy_posts.setdefault(row["account_id"], []).append(content)
    for account in accounts:
        if account["account_id"] not in direct_metrics:
            account["interaction_data"] = interaction_snapshot(legacy_posts.get(account["account_id"], []), now_utc)
            account["interaction_source"] = "legacy_content_history"
            account.update(account_metrics(account["interaction_data"], config.rolling_posts, now_utc))
        account["lifecycle_stage"] = lifecycle_stage(config, account)
        target = next(target for target in config.stage_targets if target.name == account["lifecycle_stage"])
        account["business_goal"] = {"traffic": target.traffic, "conversion": target.conversion}
    return accounts


def load_topics(cursor, scope: str) -> list[dict]:
    cursor.execute(
        "SELECT t.topic_code, t.title, s.source_updated_at, s.payload_json, "
        "tag.tags_json FROM godp_topic t JOIN godp_topic_source s "
        "ON s.topic_id=t.topic_code LEFT JOIN godp_topic_tag tag "
        "ON tag.topic_id=t.topic_code AND tag.del_flag='N' "
        "WHERE t.del_flag='N' AND s.del_flag='N' AND s.active_in_snapshot=1 "
        "AND t.status='可用' "
        "AND t.is_marketing=0 "
        "AND (s.valid_from IS NULL OR s.valid_from<=UTC_TIMESTAMP(6)) "
        "AND (s.valid_to IS NULL OR s.valid_to>=UTC_TIMESTAMP(6)) "
        "ORDER BY t.topic_code"
    )
    topics = []
    for row in cursor.fetchall():
        if row["topic_code"].startswith("DEMO-") != (scope == "demo"):
            continue
        source = json.loads(row["payload_json"])
        topic_status = source.get("status")
        enabled = topic_status if topic_status is not None else source.get("enabled", True)
        if not row["title"].strip() or not enabled or source.get("is_marketing", False):
            continue
        if source.get("topic_type", "normal") not in ("normal", "ordinary", "普通"):
            continue
        tags = json.loads(row["tags_json"]) if row["tags_json"] else {}
        role_value = tags.get("T2", [])
        role = role_value[0] if isinstance(role_value, list) and role_value else role_value
        topics.append({
            "topic_id": row["topic_code"],
            "title": row["title"],
            "outline": source.get("outline") or source.get("summary") or "",
            "content_type": source.get("content_type") or "",
            "topic_heat": float(source.get("topic_heat", source.get("heat", 0)) or 0),
            "content_role": role if role in ("流量", "转化") else "流量",
            "source_updated_at": row["source_updated_at"].isoformat(),
        })
    if not topics:
        raise PlanningError(f"{scope} 范围内没有已同步且有效的普通选题")
    return sorted(topics, key=lambda topic: (-topic["topic_heat"], topic["topic_id"]))


def run_ordinary_planning(cycle_start: date | None = None, scope: str = "live") -> dict:
    if scope not in ("demo", "live"):
        raise PlanningError("数据范围只能为 demo 或 live")
    start = cycle_start or current_next_monday()
    if start.weekday() != 0:
        raise PlanningError("目标策划周期必须从周一开始")
    end = start + timedelta(days=6)
    batch_code = f"{'DEMO-' if scope == 'demo' else ''}AUTO-REG-{start:%Y%m%d}"
    lock_name = f"godp:ordinary:{scope}:{start:%Y%m%d}"

    with connection() as db, db.cursor() as cursor:
        # Keep every source read on one database snapshot, including the
        # legacy interaction fallback, regardless of the server default.
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (lock_name,))
        if cursor.fetchone()["acquired"] != 1:
            raise PlanningError("同周期普通策划正在执行，请稍后重试")
        try:
            cursor.execute(
                "SELECT r.batch_id, r.account_count, r.slot_count FROM godp_auto_plan_run r "
                "JOIN godp_planning_batch b ON b.id=r.batch_id AND b.del_flag='N' "
                "WHERE r.data_scope=%s AND r.cycle_start=%s "
                "AND r.plan_mode='ordinary_fallback' AND r.del_flag='N'",
                (scope, start),
            )
            existing = cursor.fetchone()
            if existing:
                db.rollback()
                return {"batch_id": existing["batch_id"], "batch_code": batch_code,
                        "account_count": existing["account_count"], "slot_count": existing["slot_count"],
                        "cycle_start": start.isoformat(), "cycle_end": end.isoformat(), "reused": True}
            if start < current_next_monday():
                raise PlanningError("只能为下周或更晚的周期提前策划")

            cursor.execute(
                "SELECT id FROM godp_planning_batch WHERE plan_type='auto' AND cycle_start=%s "
                "AND del_flag='N' AND " + ("batch_code LIKE %s" if scope == "demo" else "batch_code NOT LIKE %s"),
                (start, "DEMO-%"),
            )
            if cursor.fetchone():
                raise PlanningError("该周期已有自动策划批次，不能叠加生成普通内容批次")

            cursor.execute(
                "SELECT version, config_json FROM godp_strategy_config "
                "WHERE config_key='operations' AND del_flag='N' FOR UPDATE"
            )
            config_row = cursor.fetchone()
            config = StrategyConfig.model_validate_json(config_row["config_json"]) if config_row else StrategyConfig()
            config_version = config_row["version"] if config_row else 0
            accounts = load_accounts(cursor, scope, config)
            topics = load_topics(cursor, scope)
            slot_count = len(accounts) * len(config.planning_days)
            note = f"普通选题热度兜底；未执行AI匹配；配置V{config_version}"
            cursor.execute(
                "INSERT INTO godp_planning_batch "
                "(batch_code, plan_type, status, cycle_start, cycle_end, account_count, "
                "content_count, note, create_by, update_by) "
                "VALUES (%s, 'auto', '已规划', %s, %s, %s, %s, %s, 'ordinary-plan-cli', 'ordinary-plan-cli')",
                (batch_code, start, end, len(accounts), slot_count, note),
            )
            batch_id = cursor.lastrowid
            for account in accounts:
                for index, day in enumerate(config.planning_days):
                    topic = topics[index % len(topics)]
                    publish_date = start + timedelta(days=day - 1)
                    cursor.execute(
                        "INSERT INTO godp_planning_item "
                        "(batch_id, account_id, account_name, publish_date, slot_type, "
                        "topic_id, topic_title, topic_type, outline, content_type, "
                        "status, lifecycle_stage, content_role, "
                        "create_by, update_by) "
                        "VALUES (%s, %s, %s, %s, 'regular', %s, %s, '普通', %s, %s, '已规划', %s, %s, "
                        "'ordinary-plan-cli', 'ordinary-plan-cli')",
                        (batch_id, account["account_id"], account["account_name"], publish_date,
                         topic["topic_id"], topic["title"], topic["outline"], topic["content_type"],
                         account["lifecycle_stage"], topic["content_role"]),
                    )
                    item_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO godp_slot_state (item_id, slot_id, version, topic_id, "
                        "create_by, update_by) VALUES (%s, %s, 1, %s, 'ordinary-plan-cli', 'ordinary-plan-cli')",
                        (item_id, f"SLOT-{item_id}", topic["topic_id"]),
                    )

            cursor.execute(
                "INSERT INTO godp_auto_plan_run "
                "(cycle_start, cycle_end, data_scope, plan_mode, batch_id, config_version, "
                "config_json, account_snapshot_json, topic_snapshot_json, account_count, "
                "slot_count, status, create_by, update_by) "
                "VALUES (%s, %s, %s, 'ordinary_fallback', %s, %s, %s, %s, %s, %s, %s, "
                "'已规划', 'ordinary-plan-cli', 'ordinary-plan-cli')",
                (start, end, scope, batch_id, config_version, config.model_dump_json(),
                 json.dumps(accounts, ensure_ascii=False), json.dumps(topics, ensure_ascii=False),
                 len(accounts), slot_count),
            )
            if scope == "live":
                save_batch_account_profiles(cursor, batch_id, accounts, config_version, "ordinary-plan-cli")
            db.commit()
            return {"batch_id": batch_id, "batch_code": batch_code,
                    "account_count": len(accounts), "slot_count": slot_count,
                    "cycle_start": start.isoformat(), "cycle_end": end.isoformat(), "reused": False}
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


def main() -> None:
    parser = argparse.ArgumentParser(description="为下一自然周生成普通内容兜底策划批次")
    parser.add_argument("--cycle-start", type=date.fromisoformat,
                        help="目标周的周一日期；默认下周一")
    parser.add_argument("--scope", choices=("demo", "live"), default="live",
                        help="demo 使用演示数据，live 使用正式同步数据")
    args = parser.parse_args()
    try:
        result = run_ordinary_planning(args.cycle_start, args.scope)
    except PlanningError as exc:
        parser.exit(2, f"普通内容策划未生成：{exc}\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
