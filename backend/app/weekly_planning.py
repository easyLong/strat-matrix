"""Plan hotspot placeholders, marketing slots and ordinary-topic fallback."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
import random

from .db import connection
from .account_profile import save_batch_account_profiles
from .models import StrategyConfig
from .ordinary_planning import PlanningError, current_next_monday, load_accounts, load_topics


def load_marketing(cursor, accounts: list[dict]) -> tuple[list[dict], str | None]:
    if not any(account["marketing_eligible"] for account in accounts):
        return [], None
    cursor.execute(
        "SELECT source_batch_id FROM godp_marketing_sync_run WHERE del_flag='N' "
        "ORDER BY source_snapshot_at DESC, id DESC LIMIT 1"
    )
    latest = cursor.fetchone()
    if not latest:
        raise PlanningError("营销账号存在，但 IF-03 营销选题尚未成功同步")
    cursor.execute(
        "SELECT topic_id, account_id, approval_status, approved_at, valid_from, valid_to, "
        "source_snapshot_at, payload_json FROM godp_marketing_topic_source "
        "WHERE del_flag='N' AND active_in_snapshot=1 AND enabled=1 "
        "ORDER BY account_id, approved_at, topic_id"
    )
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    marketing = []
    for row in cursor.fetchall():
        source = json.loads(row["payload_json"])
        valid = (
            row["approval_status"] == "approved" and row["approved_at"] is not None
            and (row["valid_from"] is None or row["valid_from"] <= now_utc)
            and (row["valid_to"] is None or row["valid_to"] >= now_utc)
        )
        marketing.append({
            "topic_id": row["topic_id"], "account_id": row["account_id"],
            "title": source["title"], "outline": source.get("outline") or "",
            "content_type": source.get("content_type") or "",
            "approved_at": row["approved_at"].isoformat() if row["approved_at"] else None,
            "source_snapshot_at": row["source_snapshot_at"].isoformat(),
            "valid": valid,
        })
    return marketing, latest["source_batch_id"]


def round_hotspot_slots(slot_count: int, ratio: int) -> int:
    return int((Decimal(slot_count) * Decimal(ratio) / Decimal(100)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP,
    ))


def run_weekly_planning(cycle_start: date | None = None) -> dict:
    start = cycle_start or current_next_monday()
    if start.weekday() != 0:
        raise PlanningError("目标策划周期必须从周一开始")
    end = start + timedelta(days=6)
    batch_code = f"AUTO-RULE-{start:%Y%m%d}"
    lock_name = f"godp:ordinary:live:{start:%Y%m%d}"

    with connection() as db, db.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (lock_name,))
        if cursor.fetchone()["acquired"] != 1:
            raise PlanningError("同周期自动策划正在执行，请稍后重试")
        try:
            cursor.execute(
                "SELECT r.batch_id, r.account_count, r.slot_count, b.batch_code, b.cycle_end "
                "FROM godp_auto_plan_run r JOIN godp_planning_batch b "
                "ON b.id=r.batch_id AND b.del_flag='N' "
                "WHERE r.data_scope='live' AND r.cycle_start=%s AND r.del_flag='N' "
                "ORDER BY r.id DESC LIMIT 1", (start,),
            )
            existing = cursor.fetchone()
            if existing:
                db.rollback()
                return {"batch_id": existing["batch_id"], "batch_code": existing["batch_code"],
                        "account_count": existing["account_count"], "slot_count": existing["slot_count"],
                        "cycle_start": start.isoformat(), "cycle_end": end.isoformat(), "reused": True}
            if start < current_next_monday():
                raise PlanningError("只能为下周或更晚的周期提前策划")
            cursor.execute(
                "SELECT id FROM godp_planning_batch WHERE plan_type='auto' AND cycle_start=%s "
                "AND batch_code NOT LIKE 'DEMO-%%' AND del_flag='N' LIMIT 1", (start,),
            )
            if cursor.fetchone():
                raise PlanningError("该周期已有正式自动策划批次，不能重复生成")
            cursor.execute(
                "SELECT version, config_json FROM godp_strategy_config "
                "WHERE config_key='operations' AND del_flag='N' FOR UPDATE"
            )
            config_row = cursor.fetchone()
            config = StrategyConfig.model_validate_json(config_row["config_json"]) if config_row else StrategyConfig()
            config_version = config_row["version"] if config_row else 0
            accounts = load_accounts(cursor, "live", config)
            ordinary = load_topics(cursor, "live")
            marketing, marketing_sync_batch = load_marketing(cursor, accounts)
            by_account: dict[str, list[dict]] = {}
            for topic in marketing:
                by_account.setdefault(topic["account_id"], []).append(topic)
            for topics in by_account.values():
                topics.sort(key=lambda topic: (topic["approved_at"] or "9999", topic["topic_id"]))

            positions = [(account, day) for account in accounts for day in config.planning_days]
            slot_count = len(positions)
            hotspot_count = round_hotspot_slots(slot_count, config.hotspot_ratio)
            seed = int.from_bytes(sha256(f"{start}:{config_version}:live".encode()).digest()[:8], "big")
            rng = random.Random(seed)
            hotspots = set(rng.sample(range(slot_count), hotspot_count))
            marketing_slots: dict[int, dict | None] = {}
            for account_index, account in enumerate(accounts):
                if not account["marketing_eligible"]:
                    continue
                base = account_index * len(config.planning_days)
                non_hotspot = [base + offset for offset in range(len(config.planning_days))
                               if base + offset not in hotspots]
                candidates = by_account.get(account["account_id"], [])
                count = min(len(candidates), config.marketing_max, len(non_hotspot))
                selected = sorted(rng.sample(non_hotspot, count)) if count else []
                legal = [topic for topic in candidates if topic["valid"]]
                for index, position in enumerate(selected):
                    marketing_slots[position] = legal[index] if index < len(legal) else None

            marketing_count = len(marketing_slots)
            note = (f"热点空槽{hotspot_count}；营销槽位{marketing_count}；"
                    f"其余普通选题按热度兜底；未执行AI匹配；配置V{config_version}")
            cursor.execute(
                "INSERT INTO godp_planning_batch "
                "(batch_code, plan_type, status, cycle_start, cycle_end, account_count, "
                "content_count, note, create_by, update_by) "
                "VALUES (%s, 'auto', '已规划', %s, %s, %s, %s, %s, "
                "'weekly-plan-cli', 'weekly-plan-cli')",
                (batch_code, start, end, len(accounts), slot_count, note),
            )
            batch_id = cursor.lastrowid
            used_ordinary: dict[str, set[str]] = {}
            fallback_marketing_count = 0
            for position, (account, day) in enumerate(positions):
                if position in hotspots:
                    slot_type, topic, topic_type, status, role = "hotspot", None, None, "待热点触发", None
                else:
                    slot_type = "marketing_priority" if position in marketing_slots else "regular"
                    topic = marketing_slots.get(position)
                    if topic is None:
                        used = used_ordinary.setdefault(account["account_id"], set())
                        topic = next((candidate for candidate in ordinary
                                      if candidate["topic_id"] not in used), ordinary[0])
                        used.add(topic["topic_id"])
                        topic_type = "普通"
                        role = topic["content_role"]
                        if slot_type == "marketing_priority":
                            fallback_marketing_count += 1
                    else:
                        topic_type, role = "营销", "转化"
                    status = "已规划"
                publish_date = start + timedelta(days=day - 1)
                cursor.execute(
                    "INSERT INTO godp_planning_item "
                    "(batch_id, account_id, account_name, publish_date, slot_type, "
                    "topic_id, topic_title, topic_type, outline, content_type, status, "
                    "lifecycle_stage, content_role, create_by, update_by) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "'weekly-plan-cli', 'weekly-plan-cli')",
                    (batch_id, account["account_id"], account["account_name"], publish_date,
                     slot_type, topic["topic_id"] if topic else "", topic["title"] if topic else "待热点触发",
                     topic_type, topic["outline"] if topic else None,
                     topic["content_type"] if topic else None, status,
                     account["lifecycle_stage"], role),
                )
                item_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO godp_slot_state "
                    "(item_id, slot_id, version, topic_id, create_by, update_by) "
                    "VALUES (%s, %s, 1, %s, 'weekly-plan-cli', 'weekly-plan-cli')",
                    (item_id, f"SLOT-{item_id}", topic["topic_id"] if topic else ""),
                )
            snapshot = {"ordinary": ordinary, "marketing": marketing,
                        "marketing_sync_batch_id": marketing_sync_batch,
                        "hotspot_positions": sorted(hotspots), "random_seed": seed}
            cursor.execute(
                "INSERT INTO godp_auto_plan_run "
                "(cycle_start, cycle_end, data_scope, plan_mode, batch_id, config_version, "
                "config_json, account_snapshot_json, topic_snapshot_json, account_count, "
                "slot_count, status, create_by, update_by) "
                "VALUES (%s, %s, 'live', 'rule_fallback', %s, %s, %s, %s, %s, %s, %s, "
                "'已规划', 'weekly-plan-cli', 'weekly-plan-cli')",
                (start, end, batch_id, config_version, config.model_dump_json(),
                 json.dumps(accounts, ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False),
                 len(accounts), slot_count),
            )
            save_batch_account_profiles(cursor, batch_id, accounts, config_version, "weekly-plan-cli")
            db.commit()
            return {"batch_id": batch_id, "batch_code": batch_code,
                    "cycle_start": start.isoformat(), "cycle_end": end.isoformat(),
                    "account_count": len(accounts), "slot_count": slot_count,
                    "hotspot_slots": hotspot_count, "marketing_slots": marketing_count,
                    "marketing_ordinary_fallback_slots": fallback_marketing_count,
                    "reused": False}
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))


def main() -> None:
    parser = argparse.ArgumentParser(description="生成下周热点空槽、营销和普通兜底策划")
    parser.add_argument("--cycle-start", type=date.fromisoformat, help="目标周周一；默认下周一")
    args = parser.parse_args()
    try:
        print(json.dumps(run_weekly_planning(args.cycle_start), ensure_ascii=False))
    except PlanningError as exc:
        parser.exit(2, f"周策划未生成：{exc}\n")


if __name__ == "__main__":
    main()
