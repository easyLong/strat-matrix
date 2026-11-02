"""Shared periods use cases; no HTTP routing."""
from datetime import date, datetime, timedelta, timezone
import json
import pymysql
from ..db import connection
from ..models import StrategyConfig
from .errors import ApplicationError, database_error
from ..core.planning_items import enrich_plan_item

def cycle_records() -> tuple[list[dict], list[dict]]:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                "account_count, content_count, note, update_time, create_time "
                "FROM godp_planning_batch WHERE del_flag='N' "
                "ORDER BY create_time DESC, id DESC LIMIT 5000"
            )
            batches = cursor.fetchall()
            if not batches:
                return [], []
            from ..adapters.bank.catalog import hydrate
            placeholders = ','.join(['%s'] * len(batches))
            cursor.execute(
                'SELECT i.batch_id,i.account_id,i.account_name,i.slot_type,i.topic_id,i.topic_type,i.status,'
                's.production_status FROM godp_planning_item i '
                "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
                "WHERE i.del_flag='N' AND i.batch_id IN (" + placeholders + ')',
                [batch['id'] for batch in batches])
            return batches, hydrate(cursor, cursor.fetchall())
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())

def is_execution_error(status: str | None) -> bool:
    return bool(status and any(marker in status for marker in ("失败", "异常", "错误")))

def planning_topic_type(item: dict) -> str:
    value = item.get("topic_type")
    aliases = {
        "normal": "普通", "regular": "普通", "普通": "普通",
        "marketing": "营销", "marketing_priority": "营销", "营销": "营销",
        "hotspot": "热点", "热点": "热点",
    }
    if value in aliases:
        return aliases[value]
    if item.get("slot_type") == "hotspot":
        return "热点"
    if item.get("slot_type") == "marketing_priority" or item.get("source_is_marketing"):
        return "营销"
    return "普通"

def hotspot_is_pending(item: dict) -> bool:
    return item["slot_type"] == "hotspot" and (
        not item["topic_id"] or
        (item["account_id"].startswith("DEMO-") and item.get("production_status") in (None, "planned"))
    )

def failure_account_um(item: dict) -> str | None:
    payload = item.get("account_source_payload")
    if not payload:
        return None
    try:
        source = json.loads(payload) if isinstance(payload, str) else payload
    except (TypeError, ValueError):
        return None
    if not isinstance(source, dict):
        return None
    value = source.get("um_no") or source.get("owner_um")
    return str(value).strip() or None if value is not None else None

def cycle_failure_rows(relevant: list[dict], items: list[dict]) -> list[dict]:
    by_batch: dict[int, list[dict]] = {}
    for item in items:
        by_batch.setdefault(item["batch_id"], []).append(item)
    failures = []
    for batch in relevant:
        rows = by_batch.get(batch["id"], [])
        item_failures = [item for item in rows if is_execution_error(item["status"])]
        for item in item_failures:
            failures.append({"batch_code": batch["batch_code"],
                             "account_id": item["account_id"],
                             "account_name": item["account_name"],
                             "um_no": failure_account_um(item),
                             "reason": item["status"]})
        if is_execution_error(batch["status"]) and not item_failures:
            reason = f"批次状态：{batch['status']}"
            if batch["note"]:
                reason += f"；批次备注：{batch['note']}"
            failures.append({"batch_code": batch["batch_code"], "account_id": None,
                             "account_name": "批次级异常", "um_no": None,
                             "reason": reason})
    return failures

def list_cycle_items(cycle_id: date, limit: int = 1000) -> list[dict]:
    if cycle_id.weekday() != 0:
        raise ApplicationError(status_code=422, detail="策划周期应使用周一日期")
    limit = max(1, min(limit, 5000))
    try:
        with connection() as db, db.cursor() as cursor:
            from ..adapters.mysql.planning_queries import items as source_items
            rows = source_items(cursor, 'b.cycle_start>=%s AND b.cycle_start<%s',
                                [cycle_id, cycle_id + timedelta(days=7)],
                                'i.account_name,b.create_time DESC,i.publish_date,i.id', limit)
            return [enrich_plan_item(row, row['plan_type']) for row in rows]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def list_planning_cycles() -> list[dict]:
    batches, items = cycle_records()
    by_batch: dict[int, list[dict]] = {}
    for item in items:
        by_batch.setdefault(item["batch_id"], []).append(item)
    grouped: dict[date, list[dict]] = {}
    for batch in batches:
        grouped.setdefault(monday(batch["cycle_start"]), []).append(batch)
    result = []
    for start, group in sorted(grouped.items(), reverse=True):
        rows = [item for batch in group for item in by_batch.get(batch["id"], [])]
        auto_rows = [item for batch in group if batch["plan_type"] == "auto"
                     for item in by_batch.get(batch["id"], [])]
        all_accounts = {item["account_id"] for item in rows}
        failed_batches = [batch for batch in group if is_execution_error(batch["status"])]
        failed_ids = {item["account_id"] for item in rows if is_execution_error(item["status"])}
        for batch in failed_batches:
            failed_ids.update(item["account_id"] for item in by_batch.get(batch["id"], []))
        pending_hotspot_accounts = {
            item["account_id"] for item in auto_rows if hotspot_is_pending(item)
        }
        missing_failed = sum(batch["account_count"] for batch in failed_batches
                             if not by_batch.get(batch["id"]))
        assigned = [item for item in rows
                    if item["topic_id"] and not is_execution_error(item["status"])]
        planning_failed_accounts = len(failed_ids) + missing_failed
        completed_accounts = len(all_accounts - failed_ids - pending_hotspot_accounts)
        execution_started = start <= datetime.now(timezone(timedelta(hours=8))).date()
        if planning_failed_accounts:
            planning_status = "\u6267\u884c\u5f02\u5e38"
        elif not execution_started:
            planning_status = "\u5df2\u89c4\u5212"
        elif pending_hotspot_accounts:
            planning_status = "\u70ed\u70b9\u7a7a\u69fd\u5f85\u586b\u5145"
        else:
            planning_status = "\u5df2\u5b8c\u6210"
        production_states = [item.get("production_status") for item in rows]
        production_failed = sum(state == "failed" for state in production_states)
        production_completed = sum(state in ("generated", "published") for state in production_states)
        production_ready = sum(state == "ready" for state in production_states)
        if production_failed:
            content_status = "\u751f\u4ea7\u5f02\u5e38"
        elif production_states and production_completed == len(production_states):
            content_status = "\u5df2\u5b8c\u6210"
        elif production_ready or production_completed:
            content_status = "\u751f\u4ea7\u4e2d"
        else:
            content_status = "\u5f85\u751f\u4ea7"
        result.append({
            "cycle_id": start.isoformat(), "cycle_start": start,
            "cycle_end": start + timedelta(days=6), "batch_count": len(group),
            "account_count": len(all_accounts) + missing_failed,
            "auto_item_count": sum(len(by_batch.get(batch["id"], [])) for batch in group
                                    if batch["plan_type"] == "auto"),
            "manual_item_count": sum(len(by_batch.get(batch["id"], [])) for batch in group
                                      if batch["plan_type"] == "manual"),
            "content_count": len(rows),
            "regular_slots": sum(item["slot_type"] == "regular" for item in auto_rows),
            "marketing_slots": sum(item["slot_type"] == "marketing_priority" for item in auto_rows),
            "hotspot_slots": sum(item["slot_type"] == "hotspot" for item in auto_rows),
            "topic_uses": len(assigned),
            "unique_topics": len({(planning_topic_type(item), item["topic_id"])
                                   for item in assigned}),
            "success_accounts": completed_accounts,
            "failed_accounts": planning_failed_accounts,
            "planning_status": planning_status,
            "content_status": content_status,
            "updated_at": max(batch["update_time"] for batch in group),
        })
    return result

def list_auto_cycles() -> list[dict]:
    batches, items = cycle_records()
    auto_ids = [batch["id"] for batch in batches if batch["plan_type"] == "auto"]
    run_by_batch: dict[int, dict] = {}
    if auto_ids:
        try:
            with connection() as db, db.cursor() as cursor:
                cursor.execute(
                    "SELECT batch_id, config_version, config_json, plan_mode "
                    "FROM godp_auto_plan_run WHERE del_flag='N' AND batch_id IN (" +
                    ",".join(["%s"] * len(auto_ids)) + ")", auto_ids,
                )
                run_by_batch = {row["batch_id"]: row for row in cursor.fetchall()}
        except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
            raise database_error() from exc
    by_batch: dict[int, list[dict]] = {}
    for item in items:
        by_batch.setdefault(item["batch_id"], []).append(item)
    grouped: dict[date, list[dict]] = {}
    for batch in batches:
        if batch["plan_type"] == "auto":
            grouped.setdefault(monday(batch["cycle_start"]), []).append(batch)
    result = []
    for start, group in sorted(grouped.items(), reverse=True):
        run = next((run_by_batch[batch["id"]] for batch in group if batch["id"] in run_by_batch), None)
        run_config = StrategyConfig.model_validate_json(run["config_json"]) if run else None
        rows = [item for batch in group for item in by_batch.get(batch["id"], [])]
        accounts = {item["account_id"] for item in rows}
        failed_ids = {item["account_id"] for item in rows if is_execution_error(item["status"])}
        failed_batches = [batch for batch in group if is_execution_error(batch["status"])]
        missing_failed = sum(batch["account_count"] for batch in group
                             if is_execution_error(batch["status"]) and not by_batch.get(batch["id"]))
        failed = len(failed_ids) + missing_failed
        regular_slots = sum(1 for item in rows if item["slot_type"] == "regular")
        marketing_slots = sum(1 for item in rows if item["slot_type"] == "marketing_priority")
        hotspot_rows = [item for item in rows if item["slot_type"] == "hotspot"]
        hotspot_slots = len(hotspot_rows)
        hotspot_pending = sum(1 for item in hotspot_rows if hotspot_is_pending(item))
        hotspot_submitted = hotspot_slots - hotspot_pending
        pending_hotspot_accounts = {
            item["account_id"] for item in hotspot_rows
            if hotspot_is_pending(item)
        }
        has_execution_exception = bool(failed_ids or failed_batches)
        execution_started = start <= datetime.now(timezone(timedelta(hours=8))).date()
        if has_execution_exception:
            cycle_status = None
        elif not execution_started:
            cycle_status = "已规划"
        elif hotspot_pending > 0:
            cycle_status = "热点空槽待填充"
        else:
            cycle_status = "已完成"
        base_planning_complete_accounts = len(accounts - failed_ids)
        all_topics_determined_accounts = len(
            accounts - failed_ids - pending_hotspot_accounts
        )
        result.append({
            "cycle_id": start.isoformat(), "cycle_start": start,
            "cycle_end": start + timedelta(days=6), "batch_count": len(group),
            "account_count": len(accounts) + missing_failed,
            "base_planning_complete_accounts": base_planning_complete_accounts,
            "all_topics_determined_accounts": all_topics_determined_accounts,
            "planning_failed_accounts": failed,
            "has_execution_exception": has_execution_exception,
            # Keep the previous response fields for existing consumers. Their precise
            # meanings are exposed above under explicit names.
            "success_accounts": all_topics_determined_accounts,
            "failed_accounts": failed,
            "regular_slots": regular_slots,
            "marketing_slots": marketing_slots,
            "hotspot_slots": hotspot_slots,
            "hotspot_submitted": hotspot_submitted,
            "hotspot_pending": hotspot_pending,
            "status": cycle_status,
            "updated_at": max(batch["update_time"] for batch in group),
            "config_version": run["config_version"] if run else None,
            "planning_days": run_config.planning_days if run_config else None,
            "schedule_day": run_config.schedule_day if run_config else None,
            "schedule_time": run_config.schedule_time if run_config else None,
            "allocation_method": run["plan_mode"] if run else None,
        })
    return result

def list_auto_failures(cycle_id: date) -> list[dict]:
    batches, items = cycle_records()
    relevant = [batch for batch in batches if batch["plan_type"] == "auto"
                and monday(batch["cycle_start"]) == cycle_id]
    if not relevant:
        raise ApplicationError(status_code=404, detail="自动策划周期不存在")
    return cycle_failure_rows(relevant, items)

def list_cycle_failures(cycle_id: date) -> list[dict]:
    """Return account-level planning failures for every batch in a cycle."""
    batches, items = cycle_records()
    relevant = [batch for batch in batches if monday(batch["cycle_start"]) == cycle_id]
    if not relevant:
        raise ApplicationError(status_code=404, detail="策划周期不存在")
    return cycle_failure_rows(relevant, items)
