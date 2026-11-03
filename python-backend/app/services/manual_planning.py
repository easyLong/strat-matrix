"""Shared manual planning use cases; no HTTP routing."""
from datetime import date, datetime, timedelta, timezone
import json
import secrets
from uuid import uuid4
import pymysql
from ..core.actor import current_actor
from ..db import connection
from ..ordinary_planning import PlanningError, load_accounts
from ..manual_availability import ensure_manual_accounts_available, planned_manual_accounts
from ..planning_progress import COMPLETED_ACCOUNT_COUNT_SQL, PRODUCTION_STATUS_SQL, planning_status_label
from ..models import ManualPlanCreate, ManualItem, ManualPreviewInput, StrategyConfig
from .errors import ApplicationError, database_error
from .planning_slots import queue_manual_slot
from .catalog import available_topics, list_accounts
from .results import get_batch

def create_manual_batch(payload: ManualPlanCreate) -> dict:
    operator = current_actor()
    try:
        from ..bank_bridge.input_snapshot import freeze_inputs
        from ..bank_bridge.factory import use_adapters
        source = freeze_inputs([i.account_id for i in payload.items], [i.topic_id for i in payload.items])
        with use_adapters(source), connection() as db, db.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            batch_id = insert_manual_batch(cursor, payload, operator=operator)
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return get_batch(batch_id)

def insert_manual_batch(cursor, payload: ManualPlanCreate, operator: str = "system",
                        exclude_task_id: int | None = None) -> int:
    ensure_manual_accounts_available(cursor, payload.publish_date,
                                     [item.account_id for item in payload.items], exclude_task_id)
    is_demo = any(
        item.account_id.startswith("DEMO-") or item.topic_id.startswith("DEMO-")
        for item in payload.items
    )
    batch_code = ("DEMO-MAN-" if is_demo else "MAN-") + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + uuid4().hex[:6].upper()
    note = (("演示数据｜" if is_demo else "") + payload.note)[:500]
    lifecycle_by_account: dict[str, str] = {}
    cursor.execute(
        "SELECT config_json FROM godp_strategy_config WHERE config_key='operations' AND del_flag='N'"
    )
    config_row = cursor.fetchone()
    config = StrategyConfig.model_validate_json(config_row["config_json"]) if config_row else StrategyConfig()
    for scope in ("production", "demo"):
        try:
            lifecycle_by_account.update({
                account["account_id"]: account["lifecycle_stage"]
                for account in load_accounts(cursor, scope, config,account_ids=[item.account_id for item in payload.items])
            })
        except PlanningError:
            continue
    cursor.execute(
        "INSERT INTO godp_planning_batch "
        "(batch_code, plan_type, status, cycle_start, cycle_end, account_count, "
        "content_count, note, create_by, update_by) "
        "VALUES (%s, 'manual', '待生成', %s, %s, %s, 0, %s, %s, %s)",
        (batch_code, payload.publish_date, payload.publish_date, len(payload.items), note,
         operator, operator),
    )
    batch_id = cursor.lastrowid
    topics=available_topics(cursor,list({item.topic_id for item in payload.items}))
    for item in payload.items:
        topic=topics[item.topic_id]
        snapshot=json.loads(topic['topic_payload'])
        cursor.execute(
            "INSERT INTO godp_planning_item "
            "(batch_id, account_id, account_name, publish_date, slot_type, "
            "topic_id, topic_title, outline,content_type,topic_type,status, lifecycle_stage, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, 'manual_extra', %s, %s, %s,%s,%s,'待生成', %s, %s, %s)",
            (batch_id, item.account_id, item.account_name, payload.publish_date,
             item.topic_id, item.topic_title,snapshot.get('outline') or '',topic.get('content_type') or snapshot.get('content_type') or '',
             topic['topic_type'],lifecycle_by_account.get(item.account_id),
             operator, operator),
        )
        queue_manual_slot(
            cursor, cursor.lastrowid, batch_id, batch_code,
            item.account_id, item.topic_id, payload.publish_date.isoformat(), operator=operator,
        )
    return batch_id

def manual_account_availability(publish_date: date) -> dict:
    try:
        with connection() as db, db.cursor() as cursor:
            planned = planned_manual_accounts(cursor, publish_date)
        return {"publish_date": publish_date, "planned_account_ids": sorted(planned)}
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def preview_manual_plan(payload: ManualPreviewInput) -> dict:
    operator = current_actor()
    if payload.followers_min is not None and payload.followers_max is not None \
            and payload.followers_min > payload.followers_max:
        raise ApplicationError(status_code=422, detail="粉丝量下限不能大于上限")
    catalog = list_accounts(limit=1000)
    filtered = [account for account in catalog if
                  (not payload.keyword or payload.keyword.lower() in
                   f"{account['account_id']} {account['account_name']} {account['account_alias']}".lower()) and
                  (not payload.city or account["city"] == payload.city) and
                  (not payload.persona or account["persona"] == payload.persona) and
                  (not payload.traffic_trend or account["traffic_trend"] == payload.traffic_trend) and
                  (payload.certified is None or account["certified"] == payload.certified) and
                  (payload.followers_min is None or (account["followers"] is not None and
                   account["followers"] >= payload.followers_min)) and
                  (payload.followers_max is None or (account["followers"] is not None and
                   account["followers"] <= payload.followers_max))]
    if payload.account_ids:
        wanted = set(payload.account_ids)
        candidates = [account for account in filtered if account["account_id"] in wanted]
        if len(candidates) != len(wanted):
            raise ApplicationError(status_code=409, detail="抽中账号状态或筛选条件已变化，请重新查询并抽取")
    else:
        candidates = filtered
    blocked = set(manual_account_availability(payload.publish_date)["planned_account_ids"])
    if payload.account_ids and blocked.intersection(payload.account_ids):
        raise ApplicationError(status_code=409, detail="所选账号包含当日已手动策划的账号，请重新选择")
    candidates = [account for account in candidates if account["account_id"] not in blocked]
    target = payload.target_count or len(candidates)
    if not target or target > len(candidates):
        raise ApplicationError(status_code=422, detail="符合条件的账号不足，无法完成本次抽取")
    if payload.target_count is not None:
        candidates = secrets.SystemRandom().sample(candidates, target)
    try:
        with connection() as db, db.cursor() as cursor:
            unique_topic_ids = list(dict.fromkeys(payload.topic_ids))
            topics = available_topics(cursor, unique_topic_ids)
            if len(topics) != len(unique_topic_ids):
                raise ApplicationError(status_code=422, detail="所选选题包含不可用、未审核或已过期的选题")
            if payload.content_mode == 'non_marketing' and any(topic['is_marketing'] for topic in topics.values()):
                raise ApplicationError(status_code=422, detail='非营销策划只能选择非营销选题')
            items = []
            for account in candidates:
                compatible = [topics[topic_id] for topic_id in payload.topic_ids
                              if not topics[topic_id]["is_marketing"] or account["marketing_eligible"]]
                if not compatible:
                    raise ApplicationError(status_code=422, detail=f"账号 {account['account_name']} 不具备所选营销选题资格")
                topic = secrets.choice(compatible)
                items.append(ManualItem(
                    account_id=account["account_id"], account_name=account["account_name"],
                    topic_id=topic["topic_id"], topic_title=topic["topic_title"],
                ))
            preview_id = "PREV-" + uuid4().hex.upper()
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
            cursor.execute(
                "INSERT INTO godp_manual_preview "
                "(preview_code, task_name, content_mode, publish_date, allocations_json, note, expires_at, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (preview_id, payload.task_name, payload.content_mode or 'legacy', payload.publish_date,
                 json.dumps([item.model_dump() for item in items], ensure_ascii=False),
                 payload.note, expires_at.replace(tzinfo=None), operator, operator),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
    return {"preview_id": preview_id, "task_name": payload.task_name, "publish_date": payload.publish_date,
            "expires_at": expires_at, "items": items, "note": payload.note}

def mark_manual_task_failed(task_id: int, reason: str, last_error: str, operator: str) -> None:
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "UPDATE godp_manual_task SET status='执行失败', "
                "failure_count=planned_account_count, failure_reason=%s, last_error=%s, "
                "update_by=%s WHERE id=%s AND status='执行中'",
                (reason, last_error[:500], operator, task_id),
            )
            db.commit()
    except (pymysql.MySQLError, RuntimeError, ValueError):
        pass

def execute_manual_preview(preview_id: str, task_id: int, operator: str) -> None:
    """Compatibility entrypoint; execution is always claimed from the durable queue."""
    from .manual_tasks import run_once
    return run_once(task_id,limit=1)

def submit_manual_preview(preview_id: str, background_tasks=None) -> dict:
    operator = current_actor()
    task_code = "MAN-TASK-" + uuid4().hex.upper()
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            cursor.execute(
                "SELECT task_name, publish_date, allocations_json, status, batch_id, expires_at "
                "FROM godp_manual_preview WHERE preview_code=%s AND del_flag='N' FOR UPDATE",
                (preview_id,),
            )
            preview = cursor.fetchone()
            if not preview:
                raise ApplicationError(status_code=404, detail="策划预览不存在")
            cursor.execute(
                "SELECT id, task_code, preview_code, task_name, publish_date, planned_account_count, "
                "result_count, failure_count, topic_count, status, failure_reason, batch_id, "
                "last_error, create_time AS created_at, create_by AS created_by, "
                "update_time AS updated_at FROM godp_manual_task "
                "WHERE preview_code=%s AND del_flag='N' AND status IN ('执行中','进行中','已完成') "
                "ORDER BY id DESC LIMIT 1",
                (preview_id,),
            )
            existing_task = cursor.fetchone()
            if existing_task:
                return existing_task
            if preview["status"] == "submitted" and preview["batch_id"]:
                raise ApplicationError(status_code=409, detail="该策划已提交")
            if preview["expires_at"] < datetime.now(timezone.utc).replace(tzinfo=None):
                raise ApplicationError(status_code=409, detail="策划预览已过期，请重新提交")
            items = [ManualItem.model_validate(item) for item in json.loads(preview["allocations_json"])]
            ensure_manual_accounts_available(cursor, preview["publish_date"],
                                             [item.account_id for item in items])
            topic_count = len({item.topic_id for item in items})
            cursor.execute(
                "INSERT INTO godp_manual_task "
                "(task_code, preview_code, task_name, publish_date, planned_account_count, topic_count, status, create_by, update_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, '执行中', %s, %s)",
                (task_code, preview_id, preview["task_name"], preview["publish_date"], len(items), topic_count,
                 operator, operator),
            )
            task_id = cursor.lastrowid
            db.commit()
            cursor.execute(
                "SELECT id, task_code, preview_code, task_name, publish_date, planned_account_count, "
                "result_count, failure_count, topic_count, status, failure_reason, batch_id, "
                "last_error, create_time AS created_at, create_by AS created_by, "
                "update_time AS updated_at FROM godp_manual_task WHERE id=%s",
                (task_id,),
            )
            task = cursor.fetchone()
            return task
    except ApplicationError:
        raise
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc

def list_manual_tasks(limit: int = 20, offset: int = 0) -> list[dict]:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    try:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, task_code, preview_code, task_name, publish_date, planned_account_count, "
                "result_count, failure_count, topic_count, status, failure_reason, t.batch_id, "
                "COALESCE((SELECT p.content_mode FROM godp_manual_preview p WHERE p.preview_code=t.preview_code LIMIT 1),'legacy') AS content_mode, "
                "CASE WHEN status IN ('执行中','进行中') THEN '待生产' "
                "WHEN status <> '已完成' THEN '待生产' "
                "WHEN t.batch_id IS NULL OR COALESCE(cs.slot_count, 0)=0 THEN '待生产' "
                "WHEN cs.failed_count > 0 THEN '生成失败' "
                "WHEN cs.completed_count=cs.slot_count THEN '已完成' "
                "WHEN cs.ready_count > 0 OR cs.completed_count > 0 THEN '生成中' "
                "ELSE '待生产' END AS content_status, "
                "COALESCE(cs.failed_count, 0) AS content_failed_count, "
                "COALESCE(cs.completed_count, 0) AS content_completed_count, "
                "COALESCE(cs.slot_count, 0) AS content_total_count, "
                "COALESCE(cs.completed_account_count, 0) AS content_completed_account_count, "
                "COALESCE((SELECT batch_code FROM godp_planning_batch WHERE id=t.batch_id AND del_flag='N'), '') AS batch_code, "
                "last_error, create_time AS created_at, create_by AS created_by, "
                "update_time AS updated_at "
                "FROM godp_manual_task t "
                "LEFT JOIN (SELECT i.batch_id, COUNT(*) AS slot_count, "
                f"{COMPLETED_ACCOUNT_COUNT_SQL} AS completed_account_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL} IN ('generated','published') THEN 1 ELSE 0 END) AS completed_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='ready' THEN 1 ELSE 0 END) AS ready_count, "
                f"SUM(CASE WHEN {PRODUCTION_STATUS_SQL}='failed' THEN 1 ELSE 0 END) AS failed_count "
                "FROM godp_planning_item i LEFT JOIN godp_slot_state s "
                "ON s.item_id=i.id AND s.del_flag='N' "
                "WHERE i.del_flag='N' GROUP BY i.batch_id) cs ON cs.batch_id=t.batch_id "
                "WHERE t.del_flag='N' ORDER BY t.id DESC LIMIT %s OFFSET %s", (limit, offset),
            )
            rows = cursor.fetchall()
            for row in rows:
                row["planning_status"] = planning_status_label(row["status"], row["failure_count"])
            return rows
    except (pymysql.MySQLError, RuntimeError, ValueError) as exc:
        raise database_error() from exc
