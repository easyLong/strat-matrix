"""Refresh DEMO automatic planning fixtures against an explicit Shanghai clock.

Never calls models, publishes events or changes customer source/usage facts.
Keeps existing batch/item IDs and backs up affected rows before any changes.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json
import random

from .db import ROOT, connection
from .models import StrategyConfig
from .ordinary_planning import PlanningError, load_accounts
from .weekly_planning import round_hotspot_slots

ZONE = timezone(timedelta(hours=8))
OPERATOR = "auto-demo-refresh"


def local_at(day: date, hour: int = 22, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), ZONE)


def sql_time(instant: datetime) -> datetime:
    # Existing business batch/item audit timestamps are displayed as local time.
    return instant.astimezone(ZONE).replace(tzinfo=None)


def trigger_for(start: date, config: StrategyConfig) -> datetime:
    hour, minute = map(int, config.schedule_time.split(":"))
    return local_at(start - timedelta(days=7) + timedelta(days=config.schedule_day - 1), hour, minute)


def read_rows(cursor, table: str, field: str, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    cursor.execute(f"SELECT * FROM {table} WHERE {field} IN ({','.join(['%s'] * len(ids))})", ids)
    return cursor.fetchall()


def refresh(instant: datetime) -> dict:
    local = instant.astimezone(ZONE)
    start = local.date() - timedelta(days=local.weekday())
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK('godp:auto-demo-refresh', 5) AS acquired")
        if cursor.fetchone()["acquired"] != 1:
            raise PlanningError("展示数据正在更新，请稍后重试")
        try:
            cursor.execute("SELECT config_json FROM godp_strategy_config WHERE config_key='operations' AND del_flag='N'")
            config_row = cursor.fetchone()
            config = StrategyConfig.model_validate_json(config_row["config_json"]) if config_row else StrategyConfig()
            cursor.execute(
                "SELECT * FROM godp_planning_batch WHERE plan_type='auto' AND del_flag='N' "
                "AND batch_code LIKE 'DEMO-%%' AND cycle_start<=%s ORDER BY cycle_start,id FOR UPDATE", (start,),
            )
            batches = cursor.fetchall()
            current = [batch for batch in batches if batch["cycle_start"] == start]
            if len(current) > 1:
                raise PlanningError("本周有多个展示批次，请先明确需要更新的批次")
            cursor.execute(
                "SELECT id FROM godp_planning_batch WHERE plan_type='auto' AND del_flag='N' "
                "AND batch_code NOT LIKE 'DEMO-%%' AND cycle_start=%s", (start,),
            )
            if cursor.fetchone():
                raise PlanningError("本周已有正式策划，不再创建或改写展示批次")
            batch_ids = [batch["id"] for batch in batches]
            items = read_rows(cursor, "godp_planning_item", "batch_id", batch_ids)
            if any(not row["account_id"].startswith("DEMO-") or
                   (row["topic_id"] and not row["topic_id"].startswith("DEMO-")) for row in items):
                raise PlanningError("展示批次存在正式账号或选题引用，已停止更新")
            item_ids = [row["id"] for row in items]
            states = read_rows(cursor, "godp_slot_state", "item_id", item_ids)
            slot_ids = [row["slot_id"] for row in states]
            obsolete_events = []
            if slot_ids:
                marks = ",".join(["%s"] * len(slot_ids))
                for table in ("godp_content_receipt", "godp_publication_receipt"):
                    field = "slot_id" if table == "godp_content_receipt" else "planning_result_id"
                    references = slot_ids if table == "godp_content_receipt" else item_ids
                    reference_marks = ",".join(["%s"] * len(references))
                    cursor.execute(f"SELECT id FROM {table} WHERE {field} IN ({reference_marks}) AND del_flag='N' LIMIT 1", references)
                    if cursor.fetchone():
                        raise PlanningError("展示槽位已有客户回执，已停止更新")
                cursor.execute(
                    f"SELECT * FROM godp_integration_outbox WHERE del_flag='N' "
                    f"AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.slot_id')) IN ({marks}) FOR UPDATE", slot_ids,
                )
                current_item_ids = {row["id"] for row in items if current and row["batch_id"] == current[0]["id"]}
                obsolete_events = [event for event in cursor.fetchall()
                                   if json.loads(event["payload_json"]).get("item_id") in current_item_ids]
                if any(event["delivery_status"] != "pending" or event["attempts"] != 0
                       or not json.loads(event["payload_json"]).get("account_id", "").startswith("DEMO-")
                       for event in obsolete_events):
                    raise PlanningError("展示槽位已有被投递或正式数据事件，已停止更新")
            if item_ids:
                cursor.execute(
                    "SELECT a.id FROM godp_planning_adjustment a JOIN godp_planning_item i ON i.id=a.item_id "
                    "WHERE i.batch_id=%s AND a.del_flag='N' LIMIT 1", (current[0]["id"] if current else 0,),
                )
                if cursor.fetchone():
                    raise PlanningError("展示槽位已有调整记录，已停止更新")
            backup = {"as_of": local.isoformat(), "batches": batches, "items": items, "states": states,
                      "obsolete_pending_events": obsolete_events,
                      "runs": read_rows(cursor, "godp_auto_plan_run", "batch_id", batch_ids)}
            if any(run["data_scope"] != "demo" for run in backup["runs"]):
                raise PlanningError("展示批次关联正式运行记录，已停止更新")
            backup_path = ROOT / "logs" / f"auto-demo-before-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
            backup_path.parent.mkdir(exist_ok=True)
            backup_path.write_text(json.dumps(backup, default=str, ensure_ascii=False, indent=2), encoding="utf-8")

            cursor.execute(
                "SELECT t.topic_code,t.title,t.is_marketing,s.payload_json FROM godp_topic t "
                "LEFT JOIN godp_topic_source s ON s.topic_id=t.topic_code AND s.del_flag='N' "
                "WHERE t.topic_code LIKE 'DEMO-%%' AND t.del_flag='N' AND t.status='可用' ORDER BY t.topic_code"
            )
            topics = cursor.fetchall()
            ordinary = [row for row in topics if not row["is_marketing"]]
            marketing = [row for row in topics if row["is_marketing"]]
            hotspots = [row for row in ordinary if "热点" in json.loads(row["payload_json"] or "{}").get("content_type", "")]
            if not ordinary:
                raise PlanningError("没有可用的展示普通选题")
            accounts = load_accounts(cursor, "demo", config)
            accounts_by_id = {account["account_id"]: account for account in accounts}
            if not current:
                created = sql_time(trigger_for(start, config) + timedelta(minutes=3))
                cursor.execute(
                    "INSERT INTO godp_planning_batch (batch_code,plan_type,status,cycle_start,cycle_end,"
                    "create_by,update_by,create_time,update_time) VALUES (%s,'auto','已规划',%s,%s,%s,%s,%s,%s)",
                    (f"DEMO-P-AI-{start:%Y%m%d}", start, start + timedelta(days=6), OPERATOR, OPERATOR, created, created),
                )
                current = [{"id": cursor.lastrowid, "cycle_start": start}]
                batches.extend(current)
            current_id = current[0]["id"]
            by_batch: dict[int, list[dict]] = defaultdict(list)
            for row in items:
                if row["del_flag"] == "N":
                    by_batch[row["batch_id"]].append(row)
            output = []
            for batch in batches:
                batch_id = batch["id"]
                cycle = batch["cycle_start"]
                is_current = batch_id == current_id
                grouped: dict[str, list[dict]] = defaultdict(list)
                for row in by_batch[batch_id]:
                    grouped[row["account_id"]].append(row)
                selected = sorted(accounts_by_id) if is_current else sorted(grouped)
                if not selected:
                    raise PlanningError("历史展示批次缺少账号明细，不能标记完成")
                positions = [(account_id, day) for account_id in selected for day in config.planning_days]
                rng = random.Random(f"auto-demo:{cycle}:{config.planning_days}")
                hot_positions: set[tuple[str, int]] = set()
                marketing_positions: set[tuple[str, int]] = set()
                if is_current:
                    count = round_hotspot_slots(len(positions), config.hotspot_ratio)
                    for index, day in enumerate(config.planning_days):
                        take = count // len(config.planning_days) + int(index < count % len(config.planning_days))
                        hot_positions.update((account, day) for account in rng.sample(selected, take))
                    for account_id in selected:
                        if accounts_by_id[account_id]["marketing_eligible"] and marketing:
                            available = [(account_id, day) for day in config.planning_days if (account_id, day) not in hot_positions]
                            marketing_positions.update(rng.sample(available, min(config.marketing_max, len(available))))
                created_at = trigger_for(cycle, config) + timedelta(minutes=3)
                updates = [created_at]
                total = pending = filled = 0
                for account_index, account_id in enumerate(selected):
                    existing = sorted(grouped[account_id], key=lambda row: (row["publish_date"], row["id"]))
                    if len(existing) > len(config.planning_days):
                        raise PlanningError("一个展示账号有重复或额外周槽位，已停止更新")
                    account = accounts_by_id.get(account_id)
                    if account is None:
                        raise PlanningError("展示批次的账号来源已缺失，已停止更新")
                    for index, day in enumerate(config.planning_days):
                        row = existing[index] if index < len(existing) else None
                        publish = cycle + timedelta(days=day - 1)
                        slot_type = ("hotspot" if (account_id, day) in hot_positions else
                                     "marketing_priority" if (account_id, day) in marketing_positions else "regular") if is_current else (row["slot_type"] if row else "regular")
                        due = local_at(publish - timedelta(days=1))
                        waiting = slot_type == "hotspot" and due > local
                        pool = marketing if slot_type == "marketing_priority" and marketing else hotspots if slot_type == "hotspot" and hotspots else ordinary
                        topic = None if waiting else pool[(account_index * len(config.planning_days) + index) % len(pool)]
                        if not is_current and row and row["topic_id"]:
                            # Keep manually adjusted historical topic references and versions.
                            topic = next((candidate for candidate in topics if candidate["topic_code"] == row["topic_id"]), None)
                            if topic is None:
                                raise PlanningError("历史展示选题已缺失，已停止更新")
                        source = json.loads(topic["payload_json"] or "{}") if topic else {}
                        topic_id = topic["topic_code"] if topic else ""
                        topic_type = None if waiting else "营销" if topic["is_marketing"] else "热点" if slot_type == "hotspot" and hotspots else "普通"
                        role = None if waiting else "转化" if topic_type == "营销" else "流量"
                        stage = (row.get("lifecycle_stage") if row else None) or account["lifecycle_stage"]
                        changed_at = due + timedelta(minutes=3) if slot_type == "hotspot" and not waiting else created_at
                        updates.append(changed_at)
                        values = (account["account_name"], publish, slot_type, topic_id,
                                  topic["title"] if topic else "待热点触发", topic_type,
                                  source.get("outline") or source.get("summary") or None,
                                  source.get("content_type") or None, "待热点触发" if waiting else "已分配", stage, role,
                                  OPERATOR, sql_time(created_at), sql_time(changed_at))
                        if row:
                            item_id = row["id"]
                            cursor.execute(
                                "UPDATE godp_planning_item SET account_name=%s,publish_date=%s,slot_type=%s,topic_id=%s,"
                                "topic_title=%s,topic_type=%s,outline=%s,content_type=%s,status=%s,lifecycle_stage=%s,"
                                "content_role=%s,update_by=%s,create_time=%s,update_time=%s WHERE id=%s", (*values, item_id),
                            )
                        else:
                            cursor.execute(
                                "INSERT INTO godp_planning_item (account_name,publish_date,slot_type,topic_id,topic_title,"
                                "topic_type,outline,content_type,status,lifecycle_stage,content_role,update_by,create_time,"
                                "update_time,batch_id,account_id,create_by) VALUES (" + ",".join(["%s"] * 17) + ")",
                                (*values, batch_id, account_id, OPERATOR),
                            )
                            item_id = cursor.lastrowid
                        # Completion concerns topic determination, not fictional publication.
                        cursor.execute(
                            "INSERT INTO godp_slot_state (item_id,slot_id,topic_id,production_status,create_by,update_by,create_time,update_time) "
                            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE topic_id=VALUES(topic_id),"
                            "production_status=VALUES(production_status),content_id=NULL,generated_at=NULL,published_at=NULL,"
                            "update_by=VALUES(update_by),create_time=VALUES(create_time),update_time=VALUES(update_time),del_flag='N'",
                            (item_id, f"DEMO-AUTO-SLOT-{item_id}", topic_id, "planned" if waiting else "ready",
                             OPERATOR, OPERATOR, sql_time(created_at), sql_time(changed_at)),
                        )
                        total += 1
                        pending += int(waiting)
                        filled += int(slot_type == "hotspot" and not waiting)
                status = "热点空槽待填充" if pending else "已完成"
                cursor.execute(
                    "UPDATE godp_planning_batch SET status=%s,account_count=%s,content_count=%s,"
                    "note=%s,create_time=%s,update_time=%s,update_by=%s WHERE id=%s",
                    (status, len(selected), total, "DEMO 展示数据；按上海时间逐槽确定选题；没有执行 AI 或内容生产", sql_time(created_at),
                     sql_time(max(updates)), OPERATOR, batch_id),
                )
                # Retain original input snapshots for audit; they no longer describe refreshed fixtures.
                cursor.execute("UPDATE godp_auto_plan_run SET del_flag='Y',update_by=%s WHERE batch_id=%s AND data_scope='demo' AND del_flag='N'", (OPERATOR, batch_id))
                output.append({"cycle_start": cycle.isoformat(), "accounts": len(selected), "slots": total,
                               "hotspot_submitted": filled, "hotspot_pending": pending, "status": status})
            for event in obsolete_events:
                cursor.execute("UPDATE godp_integration_outbox SET del_flag='Y',update_by=%s WHERE id=%s", (OPERATOR, event["id"]))
            db.commit()
            return {"as_of": local.isoformat(), "backup": str(backup_path), "cycles": output,
                    "next_week_created": False}
        finally:
            cursor.execute("SELECT RELEASE_LOCK('godp:auto-demo-refresh')")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", help="ISO timestamp with timezone; defaults to current Asia/Shanghai time")
    args = parser.parse_args()
    instant = datetime.fromisoformat(args.as_of) if args.as_of else datetime.now(ZONE)
    if instant.tzinfo is None:
        parser.error("--as-of 必须包含时区，例如 2026-10-13T09:00:00+08:00")
    try:
        print(json.dumps(refresh(instant), ensure_ascii=False, indent=2))
    except Exception as exc:
        # Do not expose database credentials/SQL through connection exceptions.
        message = str(exc) if isinstance(exc, PlanningError) else type(exc).__name__
        parser.exit(1, f"展示数据更新失败：{message}\n")


if __name__ == "__main__":
    main()
