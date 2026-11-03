"""Create a persisted ordinary-only V2 pipeline at the configured business time."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
import json
import time as clock
from zoneinfo import ZoneInfo

from .db import connection
from .models import StrategyConfig
from .ordinary_planning import PlanningError, monday
from .planning_pipeline import create_pipeline
from .matching_policy import intact_document, implementation_approval_errors
from .system_config import SystemConfigError, get_setting


BUSINESS_ZONE = ZoneInfo("Asia/Shanghai")
RETRY_INTERVAL = timedelta(hours=1)
POLL_SECONDS = 60


def schedule_owner() -> str:
    try:
        return get_setting('AUTO_SCHEDULE_OWNER', 'python')
    except SystemConfigError as error:
        # An existing installation can upgrade code before the new config row is seeded.
        if str(error) == '系统配置 AUTO_SCHEDULE_OWNER 尚未初始化':
            return 'python'
        raise


def due_cycle(now: datetime) -> date | None:
    """Return next Monday only after this week's configured trigger time."""
    with connection() as db, db.cursor() as cursor:
        cursor.execute(
            "SELECT config_json FROM godp_strategy_config "
            "WHERE config_key='operations' AND del_flag='N'"
        )
        row = cursor.fetchone()
    config = StrategyConfig.model_validate_json(row["config_json"]) if row else StrategyConfig()
    local_now = now.astimezone(BUSINESS_ZONE)
    week_start = monday(local_now.date())
    trigger_date = week_start + timedelta(days=config.schedule_day - 1)
    trigger_time = time.fromisoformat(config.schedule_time)
    trigger_at = datetime.combine(trigger_date, trigger_time, tzinfo=BUSINESS_ZONE)
    return week_start + timedelta(days=7) if local_now >= trigger_at else None


def start_v2_pipeline(cycle_start: date, *, commit_owner: str = 'python',
                      business_config_version=None, business_config=None) -> dict:
    try:
        policy_id = int(get_setting('AUTO_PLANNING_POLICY_ID', '0'))
        selection = json.loads(get_setting('AUTO_PLANNING_ACCOUNT_IDS', '[]'))
    except (ValueError, TypeError) as exc:
        raise PlanningError('自动策划策略或账号范围配置无效') from exc
    if not isinstance(selection, list) or len(selection) > 2000 or any(
            not isinstance(x, str) or not x.strip() or x != x.strip() for x in selection) or len(set(selection)) != len(selection):
        raise PlanningError('自动策划账号范围必须是不重复的账号ID数组')
    if policy_id <= 0:
        raise PlanningError('请先在系统配置中绑定已批准的V2自动策划策略')
    with connection() as db, db.cursor() as cursor:
        cursor.execute("SELECT * FROM godp_matching_policy WHERE id=%s AND del_flag='N'", (policy_id,))
        policy = cursor.fetchone()
        if not policy or policy['status'] != 'approved':
            raise PlanningError('自动策划绑定的策略不存在或尚未批准')
        document = intact_document(policy)
        if document.implementation_key != 'builtin-cosine-portfolio-v2' or document.approval_errors() or implementation_approval_errors(document):
            raise PlanningError('自动策划仅支持完整且已批准的V2组合策略')
        if document.vector_space.vector_model != get_setting('EMBEDDING_MODEL_NAME', ''):
            raise PlanningError('自动策划策略的向量模型与当前公共向量模型不一致')
        cursor.execute("SELECT batch_id,plan_mode FROM godp_auto_plan_run "
                       "WHERE data_scope='live' AND cycle_start=%s AND del_flag='N' ORDER BY id DESC LIMIT 1",
                       (cycle_start,))
        existing = cursor.fetchone()
        if existing:
            return {'status': 'reused', 'batch_id': existing['batch_id'], 'plan_mode': existing['plan_mode']}
    options = dict(planning_scope='ordinary_only', production_provider='disabled', commit_owner=commit_owner)
    if business_config is not None:
        options.update(business_config_version=business_config_version, business_config=business_config)
    pipeline = create_pipeline(cycle_start, selection or None, policy_id, **options)
    return {**pipeline, 'pipeline_status': pipeline['status'],
            'status': 'reused' if pipeline['reused'] else 'created'}


def run_due(now: datetime) -> dict:
    if schedule_owner() == 'java':
        return {'status': 'delegated_to_java'}
    cycle_start = due_cycle(now)
    if cycle_start is None:
        return {"status": "waiting"}
    return start_v2_pipeline(cycle_start)


def log(event: dict) -> None:
    print(json.dumps({"at": datetime.now(BUSINESS_ZONE).isoformat(), **event}, ensure_ascii=False, default=str), flush=True)


def serve() -> None:
    completed_cycle: date | None = None
    retry_after: datetime | None = None
    log({"status": "started", "scope": "live", "timezone": "Asia/Shanghai"})
    while True:
        now = datetime.now(BUSINESS_ZONE)
        try:
            if schedule_owner() == 'java':
                if completed_cycle is not None:
                    log({'status': 'delegated_to_java'})
                completed_cycle = None
                clock.sleep(POLL_SECONDS)
                continue
            cycle_start = due_cycle(now)
            if cycle_start and cycle_start != completed_cycle and (retry_after is None or now >= retry_after):
                result = start_v2_pipeline(cycle_start)
                completed_cycle = cycle_start
                retry_after = None
                log(result)
        except PlanningError as exc:
            retry_after = now + RETRY_INTERVAL
            log({"status": "failed", "message": str(exc), "retry_after": retry_after.isoformat()})
        except Exception as exc:
            retry_after = now + RETRY_INTERVAL
            log({"status": "failed", "error_type": type(exc).__name__,
                 "retry_after": retry_after.isoformat()})
        clock.sleep(POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="按服务端配置创建普通选题V2周策划流程")
    parser.add_argument("--once", action="store_true", help="只检查一次配置并在到期时执行")
    args = parser.parse_args()
    if args.once:
        try:
            print(json.dumps(run_due(datetime.now(BUSINESS_ZONE)), ensure_ascii=False, default=str))
        except (PlanningError, RuntimeError, ValueError) as exc:
            parser.exit(2, f"自动策划未完成：{exc}\n")
        return
    try:
        serve()
    except KeyboardInterrupt:
        log({"status": "stopped"})


if __name__ == "__main__":
    main()
