"""Account eligibility for one manual planning publication date."""

from datetime import date
import json

from fastapi import HTTPException


def planned_manual_accounts(cursor, publish_date: date) -> set[str]:
    """Return accounts with committed manual planning results for this date."""
    cursor.execute(
        "SELECT DISTINCT i.account_id FROM godp_planning_item i "
        "JOIN godp_planning_batch b ON b.id=i.batch_id "
        "WHERE i.publish_date=%s AND i.del_flag='N' AND b.del_flag='N' "
        "AND b.plan_type='manual'", (publish_date,),
    )
    return {row["account_id"] for row in cursor.fetchall()}


def pending_manual_accounts(cursor, publish_date: date,
                            exclude_task_id: int | None = None) -> set[str]:
    """Return in-flight allocations for submission concurrency protection only."""
    exclusion = " AND t.id<>%s" if exclude_task_id is not None else ""
    params = (publish_date, exclude_task_id) if exclude_task_id is not None else (publish_date,)
    cursor.execute(
        "SELECT p.allocations_json FROM godp_manual_task t "
        "JOIN godp_manual_preview p ON p.preview_code=t.preview_code "
        "WHERE t.publish_date=%s AND t.del_flag='N' AND p.del_flag='N' "
        "AND t.status IN ('执行中','进行中')" + exclusion, params,
    )
    pending = set()
    for row in cursor.fetchall():
        items = json.loads(row["allocations_json"])
        if not isinstance(items, list) or any(not isinstance(item, dict) or not item.get("account_id") for item in items):
            raise ValueError("进行中的手动策划账号数据不完整")
        pending.update(item["account_id"] for item in items)
    return pending


def ensure_manual_accounts_available(cursor, publish_date: date, account_ids: list[str],
                                     exclude_task_id: int | None = None) -> None:
    """Serialize overlapping submissions using account row locks.

    Call in a READ COMMITTED transaction. After waiting for an account lock,
    the availability query must see tasks committed by the previous holder.
    """
    wanted = sorted(set(account_ids))
    if not wanted:
        raise HTTPException(status_code=422, detail="请先选择账号")
    cursor.execute(
        "SELECT account_code FROM godp_account WHERE account_code IN (" +
        ",".join(["%s"] * len(wanted)) + ") AND del_flag='N' AND status='启用' "
        "ORDER BY account_code FOR UPDATE", wanted,
    )
    if {row["account_code"] for row in cursor.fetchall()} != set(wanted):
        raise HTTPException(status_code=409, detail="所选账号已停用或不存在，请重新选择")
    blocked = set(wanted) & (
        planned_manual_accounts(cursor, publish_date) |
        pending_manual_accounts(cursor, publish_date, exclude_task_id)
    )
    if blocked:
        raise HTTPException(status_code=409,
                            detail=f"所选账号中有 {len(blocked)} 个在 {publish_date} 已手动策划，请重新选择")
