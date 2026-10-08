"""Determine planned hotspot slots at T-1 22:00 Asia/Shanghai."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import random
import time as clock
from zoneinfo import ZoneInfo

from .db import connection
from .ordinary_planning import PlanningError, load_topics


BUSINESS_ZONE = ZoneInfo("Asia/Shanghai")
POLL_SECONDS = 60
RETRY_INTERVAL = timedelta(minutes=5)
SYNC_LOCK = "godp:hotspot-topic-sync"


def due_publish_date(now: datetime) -> date:
    local = now.astimezone(BUSINESS_ZONE)
    return local.date() + timedelta(days=local.time() >= time(22, 0))


def reconcile_batches(cursor, today: date) -> int:
    cursor.execute(
        "SELECT b.id, b.cycle_start, b.status, r.id AS run_id, r.status AS run_status "
        "FROM godp_planning_batch b JOIN godp_auto_plan_run r ON r.batch_id=b.id "
        "WHERE b.del_flag='N' AND r.del_flag='N' AND r.data_scope='live' "
        "AND r.plan_mode='rule_fallback' AND b.cycle_start<=%s "
        "AND b.status IN ('已规划', '热点空槽待填充') FOR UPDATE",
        (today,),
    )
    batches = cursor.fetchall()
    changed = 0
    for batch in batches:
        cursor.execute(
            "SELECT COUNT(*) AS pending FROM godp_planning_item "
            "WHERE batch_id=%s AND slot_type='hotspot' AND topic_id='' AND del_flag='N'",
            (batch["id"],),
        )
        pending = cursor.fetchone()["pending"]
        target = "热点空槽待填充" if pending else "已完成"
        if batch["status"] != target:
            cursor.execute(
                "UPDATE godp_planning_batch SET status=%s, update_by='hotspot-scheduler' WHERE id=%s",
                (target, batch["id"]),
            )
            changed += 1
        if not pending and batch["run_status"] != "已完成":
            cursor.execute(
                "UPDATE godp_auto_plan_run SET status='已完成', update_by='hotspot-scheduler' WHERE id=%s",
                (batch["run_id"],),
            )
    return changed


def run_due(now: datetime | None = None) -> dict:
    instant = now or datetime.now(BUSINESS_ZONE)
    local = instant.astimezone(BUSINESS_ZONE)
    cutoff = due_publish_date(local)
    utc_now = instant.astimezone(timezone.utc).replace(tzinfo=None)
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (SYNC_LOCK,))
        if cursor.fetchone()["acquired"] != 1:
            raise PlanningError("热点选题同步或触发正在执行，请稍后重试")
        try:
            status_updates = reconcile_batches(cursor, local.date())
            db.commit()
            cursor.execute(
                "SELECT i.id, i.batch_id, i.account_id, i.topic_title, i.publish_date, "
                "s.version, s.slot_id FROM godp_planning_item i "
                "JOIN godp_planning_batch b ON b.id=i.batch_id "
                "JOIN godp_auto_plan_run r ON r.batch_id=b.id "
                "JOIN godp_slot_state s ON s.item_id=i.id "
                "WHERE i.del_flag='N' AND b.del_flag='N' AND r.del_flag='N' AND s.del_flag='N' "
                "AND r.data_scope='live' AND r.plan_mode='rule_fallback' "
                "AND i.slot_type='hotspot' AND i.topic_id='' AND s.topic_id='' "
                "AND s.published_at IS NULL AND i.status<>'已发布' "
                "AND i.publish_date<=%s ORDER BY i.publish_date, i.id FOR UPDATE",
                (cutoff,),
            )
            pending = cursor.fetchall()
            if not pending:
                return {"due_slots": 0, "hotspot_topics": 0, "ordinary_fallback": 0,
                        "status_updates": status_updates, "cutoff_date": cutoff.isoformat()}

            cursor.execute(
                "SELECT source_batch_id FROM godp_hotspot_sync_run WHERE del_flag='N' "
                "ORDER BY source_snapshot_at DESC, id DESC LIMIT 1"
            )
            latest = cursor.fetchone()
            if not latest:
                raise PlanningError("已到热点确定时间，但 IF-04 热点选题尚未成功同步")
            cursor.execute(
                "SELECT topic_id, payload_json FROM godp_hotspot_topic_source "
                "WHERE del_flag='N' AND active_in_snapshot=1 AND enabled=1 "
                "AND source_batch_id=%s "
                "AND (valid_from IS NULL OR valid_from<=%s) "
                "AND (valid_to IS NULL OR valid_to>=%s) ORDER BY topic_id",
                (latest["source_batch_id"], utc_now, utc_now),
            )
            hotspots = []
            for row in cursor.fetchall():
                source = json.loads(row["payload_json"])
                hotspots.append({"topic_id": row["topic_id"], "title": source["title"],
                                 "outline": source.get("outline") or "",
                                 "content_type": source.get("content_type") or ""})

            by_date: dict[date, list[dict]] = {}
            for item in pending:
                by_date.setdefault(item["publish_date"], []).append(item)
            placeholders = ",".join(["%s"] * len(by_date))
            cursor.execute(
                "SELECT i.publish_date, i.topic_id FROM godp_planning_item i "
                "JOIN godp_auto_plan_run r ON r.batch_id=i.batch_id "
                "WHERE i.del_flag='N' AND r.del_flag='N' AND r.data_scope='live' "
                "AND r.plan_mode='rule_fallback' AND i.slot_type='hotspot' "
                "AND i.topic_type='热点' AND i.topic_id<>'' "
                f"AND i.publish_date IN ({placeholders})",
                tuple(by_date),
            )
            used_by_date: dict[date, set[str]] = {}
            for row in cursor.fetchall():
                used_by_date.setdefault(row["publish_date"], set()).add(row["topic_id"])
            ordinary: list[dict] | None = None
            hotspot_count = 0
            fallback_count = 0
            touched_batches: set[int] = set()
            for publish_date, items in sorted(by_date.items()):
                seed = int.from_bytes(sha256(
                    f"{publish_date}:{latest['source_batch_id']}".encode()
                ).digest()[:8], "big")
                rng = random.Random(seed)
                rng.shuffle(items)
                choices = [topic for topic in hotspots
                           if topic["topic_id"] not in used_by_date.get(publish_date, set())]
                rng.shuffle(choices)
                for index, item in enumerate(items):
                    if index < len(choices):
                        topic = choices[index]
                        topic_type = "热点"
                        role = "流量"
                        reason = f"热点触发随机分配；IF-04批次{latest['source_batch_id']}"
                        hotspot_count += 1
                    else:
                        if ordinary is None:
                            ordinary = load_topics(cursor, "live")
                        topic = ordinary[0]
                        topic_type = "普通"
                        role = topic["content_role"]
                        reason = f"合法热点不足，普通选题热度兜底；IF-04批次{latest['source_batch_id']}"
                        fallback_count += 1
                    next_version = item["version"] + 1
                    cursor.execute(
                        "UPDATE godp_planning_item SET topic_id=%s, topic_title=%s, topic_type=%s, "
                        "outline=%s, content_type=%s, content_role=%s, status='已规划', "
                        "update_by='hotspot-scheduler' WHERE id=%s AND topic_id=''",
                        (topic["topic_id"], topic["title"], topic_type, topic["outline"],
                         topic["content_type"], role, item["id"]),
                    )
                    cursor.execute(
                        "UPDATE godp_slot_state SET version=%s, topic_id=%s, "
                        "production_status='planned', update_by='hotspot-scheduler' "
                        "WHERE item_id=%s AND topic_id='' AND published_at IS NULL",
                        (next_version, topic["topic_id"], item["id"]),
                    )
                    cursor.execute(
                        "INSERT INTO godp_planning_adjustment "
                        "(item_id, result_version, adjustment_source, old_topic_id, old_topic_title, "
                        "new_topic_id, new_topic_title, reason, create_by, update_by) "
                        "VALUES (%s, %s, '热点触发', '', %s, %s, %s, %s, "
                        "'hotspot-scheduler', 'hotspot-scheduler')",
                        (item["id"], next_version, item["topic_title"], topic["topic_id"],
                         topic["title"], reason),
                    )
                    touched_batches.add(item["batch_id"])
            status_updates += reconcile_batches(cursor, local.date())
            db.commit()
            return {"due_slots": len(pending), "hotspot_topics": hotspot_count,
                    "ordinary_fallback": fallback_count, "status_updates": status_updates,
                    "updated_batches": len(touched_batches), "source_batch_id": latest["source_batch_id"],
                    "cutoff_date": cutoff.isoformat()}
        except Exception:
            db.rollback()
            raise
        finally:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (SYNC_LOCK,))


def log(event: dict) -> None:
    print(json.dumps({"at": datetime.now(BUSINESS_ZONE).isoformat(), **event}, ensure_ascii=False), flush=True)


def serve() -> None:
    retry_after: datetime | None = None
    log({"status": "started", "timezone": "Asia/Shanghai"})
    while True:
        now = datetime.now(BUSINESS_ZONE)
        if retry_after is None or now >= retry_after:
            try:
                result = run_due(now)
                retry_after = None
                if result["due_slots"] or result["status_updates"]:
                    log({"status": "applied", **result})
            except Exception as exc:
                retry_after = now + RETRY_INTERVAL
                log({"status": "failed", "error_type": type(exc).__name__,
                     "message": str(exc) if isinstance(exc, PlanningError) else "",
                     "retry_after": retry_after.isoformat()})
        clock.sleep(POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="按北京时间在T-1 22:00确定已规划热点槽位")
    parser.add_argument("--once", action="store_true", help="仅处理已到时间且尚未确定的热点空槽")
    args = parser.parse_args()
    if args.once:
        try:
            print(json.dumps(run_due(), ensure_ascii=False))
        except (PlanningError, RuntimeError, ValueError) as exc:
            parser.exit(2, f"热点选题未确定：{exc}\n")
        return
    try:
        serve()
    except KeyboardInterrupt:
        log({"status": "stopped"})


if __name__ == "__main__":
    main()
