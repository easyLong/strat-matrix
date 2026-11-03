"""Shared results use cases; no HTTP routing."""
import json
import pymysql
from ..core.actor import current_actor
from ..db import connection
from ..planning_progress import COMPLETED_ACCOUNT_COUNT_SQL, PRODUCTION_STATUS_SQL, planning_status_label
from ..models import ReplaceTopicInput
from .errors import ApplicationError, database_error
from ..core.planning_items import enrich_plan_item, infer_content_role, replacement_block_reason
from .catalog import available_replacement_topics
from .periods import is_execution_error

def read_batches(cursor, plan_type=None, limit=5000, batch_ids=None):
    query = (
        "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
        "account_count, content_count, note, create_time AS created_at, "
        "update_time AS updated_at, EXISTS(SELECT 1 FROM godp_auto_plan_run r "
        "WHERE r.batch_id=godp_planning_batch.id AND r.plan_mode='ai_matching' AND r.del_flag='N') AS ai_committed "
        "FROM godp_planning_batch WHERE del_flag='N' "
    )
    params: tuple = ()
    if batch_ids is not None:
        query += "AND id IN ("+",".join(["%s"]*len(batch_ids))+") " if batch_ids else "AND 0=1 "
        params = tuple(batch_ids)
    if plan_type:
        query += "AND plan_type=%s "
        params += (plan_type,)
    query += "ORDER BY create_time DESC, id DESC LIMIT %s"
    cursor.execute(query, (*params, limit))
    rows = cursor.fetchall()
    if not rows:
        return []

    ids = [row["id"] for row in rows]
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(
        "SELECT batch_id, MAX(task_name) AS task_name, "
        "SUBSTRING_INDEX(GROUP_CONCAT(status ORDER BY id DESC), ',', 1) AS task_status, "
        "SUM(result_count) AS task_completed_count, SUM(failure_count) AS task_failed_count, "
        "SUM(topic_count) AS task_topic_count, MAX(update_time) AS task_updated_at "
        "FROM godp_manual_task WHERE del_flag='N' AND batch_id IN (" + placeholders + ") "
        "GROUP BY batch_id",
        ids,
    )
    tasks = {row["batch_id"]: row for row in cursor.fetchall()}
    cursor.execute(
        "SELECT i.batch_id, COUNT(*) AS item_count, "
        "COUNT(DISTINCT i.account_id) AS account_item_count, "
        "COUNT(DISTINCT CASE WHEN (i.status LIKE '%%失败%%' OR i.status LIKE '%%异常%%' "
        "OR i.status LIKE '%%错误%%') AND COALESCE(s.production_status, '') <> 'failed' "
        "AND i.status NOT IN ('生成失败','生产失败','生产异常') THEN i.account_id END) AS planning_failed_count, "
        "COUNT(DISTINCT NULLIF(i.topic_id,'')) AS selected_topic_count, "
        f"{COMPLETED_ACCOUNT_COUNT_SQL} AS completed_account_count, "
        f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL} IN ('generated','published') THEN 1 ELSE 0 END) AS production_completed_count, "
        f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='ready' THEN 1 ELSE 0 END) AS ready_count, "
        f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='failed' THEN 1 ELSE 0 END) AS failed_count "
        "FROM godp_planning_item i LEFT JOIN godp_slot_state s "
        "ON s.item_id=i.id AND s.del_flag='N' "
        "WHERE i.del_flag='N' AND i.batch_id IN (" + placeholders + ") "
        "GROUP BY i.batch_id",
        ids,
    )
    counts = {row["batch_id"]: row for row in cursor.fetchall()}
    for row in rows:
        task = tasks.get(row["id"], {})
        counts_for_batch = counts.get(row["id"], {})
        slot_count = counts_for_batch.get("item_count", 0)
        production_completed_count = counts_for_batch.get("production_completed_count", 0)
        ready_count = counts_for_batch.get("ready_count", 0)
        production_failed_count = counts_for_batch.get("failed_count", 0)
        planning_failed_count = counts_for_batch.get("planning_failed_count", 0)
        row["task_name"] = task.get("task_name") or (
            f"{'Auto-' if row['plan_type'] == 'auto' else 'Manual-'}{row['cycle_start'].strftime('%Y%m%d')}"
        )
        row["updated_at"] = task.get("task_updated_at") or row["updated_at"]
        row["planning_status"] = task.get("task_status") or (
            "\u5df2\u5b8c\u6210" if row["plan_type"] == "manual" or row.get('ai_committed') else row["status"]
        )
        row["content_status"] = (
            "\u751f\u6210\u5931\u8d25" if production_failed_count else
            "\u5df2\u5b8c\u6210" if slot_count and production_completed_count == slot_count else
            "\u751f\u6210\u4e2d" if ready_count or production_completed_count else
            "\u5f85\u751f\u4ea7"
        )
        row["result_count"] = slot_count
        row["content_failed_count"] = production_failed_count
        row["content_completed_count"] = production_completed_count
        row["content_total_count"] = slot_count
        row["content_completed_account_count"] = counts_for_batch.get("completed_account_count", 0)
        if row["plan_type"] == "manual" and task:
            row["completed_count"] = task.get("task_completed_count") or 0
            row["failed_count"] = task.get("task_failed_count") or 0
            row["topic_count"] = task.get("task_topic_count") or 0
        else:
            failed_accounts = planning_failed_count
            if not counts_for_batch and is_execution_error(row["status"]):
                failed_accounts = row["account_count"]
            row["failed_count"] = failed_accounts
            row["completed_count"] = max(
                0, min(row["account_count"], counts_for_batch.get("account_item_count", 0) - failed_accounts)
            )
            row["topic_count"] = counts_for_batch.get("selected_topic_count", 0)
        # Content callbacks can mark a batch as unfinished without a planning failure.
        if (row["planning_status"] in ("未完成", "生成失败", "生产失败", "生产异常")
                and production_failed_count and not row["failed_count"]):
            row["planning_status"] = "已完成"
        row["planning_status"] = planning_status_label(row["planning_status"], row["failed_count"])
    return rows


def list_batches(plan_type: str | None = None, limit: int = 200) -> list[dict]:
    if plan_type not in (None,'manual','auto'):
        raise ApplicationError(422,'Invalid planning type')
    try:
        with connection() as db, db.cursor() as cursor:
            return read_batches(cursor,plan_type,max(1,min(limit,5000)))
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc


def get_batch(batch_id: int) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, batch_code, plan_type, status, cycle_start, cycle_end, "
                "account_count, content_count, note, create_time AS created_at "
                "FROM godp_planning_batch WHERE id=%s AND del_flag='N'",
                (batch_id,),
            )
            batch = cursor.fetchone()
            if not batch:
                raise ApplicationError(status_code=404, detail="策划批次不存在")
            from ..adapters.mysql.planning_queries import items as source_items
            items = [enrich_plan_item(item, batch['plan_type']) for item in source_items(
                cursor, 'i.batch_id=%s', [batch_id], 'i.account_name,i.publish_date,i.id')]
            return {**batch, 'result_count': len(items), 'items': items}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def search_items(account: str, limit: int = 1000) -> list[dict]:
    account = account.strip()
    if not account:
        return []
    limit = max(1, min(limit, 5000))
    try:
        with connection() as db, db.cursor() as cursor:
            from ..adapters.mysql.planning_queries import items as source_items
            rows = source_items(cursor, '(i.account_id LIKE %s OR i.account_name LIKE %s)',
                                [f'%{account}%', f'%{account}%'],
                                'b.cycle_start DESC,b.create_time DESC,i.publish_date,i.id', limit)
            return [enrich_plan_item(row, row['plan_type']) for row in rows]
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def list_planning_accounts(limit: int = 5000) -> list[dict]:
    limit = max(1, min(limit, 10000))
    try:
        with connection() as db, db.cursor() as cursor:
            from ..adapters.mysql.planning_queries import planning_accounts
            return planning_accounts(cursor, limit)
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

REPLACEMENT_QUERY = (
    "SELECT i.id, i.account_id, i.account_name, i.publish_date, i.slot_type, "
    "i.topic_id, i.topic_title, i.topic_type, i.status, i.lifecycle_stage, i.content_role, "
    "b.id AS batch_id, b.plan_type, b.batch_code, b.create_time AS batch_created_at, "
    "b.cycle_start, b.cycle_end, "
    "s.slot_id, s.version, s.topic_id AS slot_topic_id, s.production_status, s.published_at "
    "FROM godp_planning_item i JOIN godp_planning_batch b ON b.id=i.batch_id "
    "LEFT JOIN godp_slot_state s ON s.item_id=i.id AND s.del_flag='N' "
    "WHERE i.id=%s AND i.del_flag='N' AND b.del_flag='N'")


def replace_topic(item_id: int, payload: ReplaceTopicInput) -> dict:
    operator = current_actor()
    try:
        from ..bank_bridge.input_snapshot import freeze_inputs
        from ..bank_bridge.factory import use_adapters, source_mode
        from .content_status import refresh_item_status
        if source_mode() == 'java_http':
            refresh_item_status(item_id)
        with connection() as db, db.cursor() as cursor:
            cursor.execute(REPLACEMENT_QUERY, (item_id,))
            source_item = cursor.fetchone()
        if not source_item:
            raise ApplicationError(404, '策划结果不存在')
        reason = replacement_block_reason(source_item, source_item['plan_type'])
        if reason:
            raise ApplicationError(409, reason)
        if source_item['version'] != payload.expected_version:
            raise ApplicationError(409, '结果版本已变化，请重新查询')
        source = freeze_inputs([source_item['account_id']], [payload.new_topic_id])
        with use_adapters(source), connection() as db, db.cursor() as cursor:
            cursor.execute(REPLACEMENT_QUERY + ' FOR UPDATE', (item_id,))
            item = cursor.fetchone()
            if not item:
                raise ApplicationError(status_code=404, detail="策划结果不存在")
            if item['account_id'] != source_item['account_id']:
                raise ApplicationError(409, '策划账号已变化，请重新查询')
            block_reason = replacement_block_reason(item, item["plan_type"])
            if block_reason:
                raise ApplicationError(status_code=409, detail=block_reason)
            if item["version"] != payload.expected_version:
                raise ApplicationError(status_code=409, detail="结果版本已变化或状态无法确认，请刷新后重试")
            if payload.new_topic_id == item["topic_id"]:
                raise ApplicationError(status_code=409, detail="新选题与当前选题相同")
            topics = available_replacement_topics(cursor, item["account_id"], payload.new_topic_id)
            topic = topics[0] if topics else None
            if topic is None:
                raise ApplicationError(status_code=409, detail="新选题不可用、未审核或已过期，请重新选择")
            next_version = item["version"] + 1
            topic_payload = topic["topic_payload"]
            cursor.execute(
                "SELECT tags_json FROM godp_topic_tag WHERE topic_id=%s AND del_flag='N'",
                (topic["topic_id"],),
            )
            tag_row = cursor.fetchone()
            tag_values = json.loads(tag_row["tags_json"]) if tag_row else {}
            role_value = tag_values.get("T2", [])
            next_role = role_value[0] if isinstance(role_value, list) and role_value else role_value
            if next_role not in ("流量", "转化"):
                role_slot_type = (
                    "marketing_priority" if topic["topic_type"] == "营销" else
                    "hotspot" if topic["topic_type"] == "热点" else "regular"
                )
                next_role = infer_content_role({**item, "slot_type": role_slot_type}, topic_payload)
            cursor.execute(
                "UPDATE godp_planning_item SET topic_id=%s, topic_title=%s, topic_type=%s, "
                "outline=%s, content_type=%s, content_role=%s, "
                "status='已规划', update_by=%s WHERE id=%s",
                (topic["topic_id"], topic["topic_title"],
                 topic["topic_type"],
                 topic_payload.get("outline") or topic_payload.get("summary") or "",
                 topic_payload.get("content_type") or "", next_role, operator, item_id),
            )
            cursor.execute(
                "UPDATE godp_slot_state SET version=%s, topic_id=%s, "
                "production_status='planned', content_id=NULL, generated_at=NULL, "
                "update_by=%s WHERE item_id=%s",
                (next_version, topic["topic_id"], operator, item_id),
            )
            cursor.execute(
                "INSERT INTO godp_planning_adjustment "
                "(item_id, result_version, adjustment_source, old_topic_id, old_topic_title, "
                "new_topic_id, new_topic_title, reason, create_by, update_by) "
                "VALUES (%s, %s, '人工替换', %s, %s, %s, %s, %s, %s, %s)",
                (item_id, next_version, item["topic_id"], item["topic_title"],
                 topic["topic_id"], topic["topic_title"], payload.reason, operator, operator),
            )
            adjustment_id = cursor.lastrowid
            cursor.execute(
                "SELECT id, create_time AS created_at, create_by AS created_by, item_id, result_version, "
                "adjustment_source, old_topic_id, old_topic_title, new_topic_id, new_topic_title, reason "
                "FROM godp_planning_adjustment WHERE id=%s", (adjustment_id,),
            )
            adjustment = cursor.fetchone()
            db.commit()
    except ApplicationError:
        raise
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    updated = {
        "id": item_id, "account_id": item["account_id"], "account_name": item["account_name"],
        "publish_date": item["publish_date"], "slot_type": item["slot_type"],
        "topic_id": topic["topic_id"], "topic_title": topic["topic_title"], "status": "已规划",
        "slot_id": item["slot_id"], "production_status": "planned",
        "batch_id": item["batch_id"], "batch_code": item["batch_code"],
        "batch_created_at": item["batch_created_at"], "plan_type": item["plan_type"],
        "cycle_start": item["cycle_start"], "cycle_end": item["cycle_end"],
        "publish_status": "未发布", "allow_replace": True,
        "replace_block_reason": "", "result_version": next_version,
        "content_type": topic_payload.get("content_type", ""),
        "outline": topic_payload.get("outline", "") or topic_payload.get("summary", ""),
        "topic_type": topic["topic_type"],
        "lifecycle_stage": item.get("lifecycle_stage"),
        "content_role": next_role,
    }
    return {"item": updated, "adjustment": adjustment}

def list_adjustments(item_id: int, limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 100))
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, item_id, result_version, adjustment_source, old_topic_id, old_topic_title, "
                "new_topic_id, new_topic_title, reason, create_time AS created_at, create_by AS created_by "
                "FROM godp_planning_adjustment WHERE item_id=%s AND del_flag='N' "
                "ORDER BY id DESC LIMIT %s", (item_id, limit),
            )
            return cursor.fetchall()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
