"""Run the ordinary-topic weekly fallback at the configured business time."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
import json
import time as clock
from zoneinfo import ZoneInfo

from .db import connection
from .models import StrategyConfig
from .ordinary_planning import PlanningError, monday, run_ordinary_planning


BUSINESS_ZONE = ZoneInfo("Asia/Shanghai")
RETRY_INTERVAL = timedelta(hours=1)
POLL_SECONDS = 60


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


def run_due(now: datetime) -> dict:
    cycle_start = due_cycle(now)
    if cycle_start is None:
        return {"status": "waiting"}
    result = run_ordinary_planning(cycle_start=cycle_start, scope="live")
    return {"status": "reused" if result["reused"] else "created", **result}


def log(event: dict) -> None:
    print(json.dumps({"at": datetime.now(BUSINESS_ZONE).isoformat(), **event}, ensure_ascii=False), flush=True)


def serve() -> None:
    completed_cycle: date | None = None
    retry_after: datetime | None = None
    log({"status": "started", "scope": "live", "timezone": "Asia/Shanghai"})
    while True:
        now = datetime.now(BUSINESS_ZONE)
        try:
            cycle_start = due_cycle(now)
            if cycle_start and cycle_start != completed_cycle and (retry_after is None or now >= retry_after):
                result = run_ordinary_planning(cycle_start=cycle_start, scope="live")
                completed_cycle = cycle_start
                retry_after = None
                log({"status": "reused" if result["reused"] else "created", **result})
        except PlanningError as exc:
            retry_after = now + RETRY_INTERVAL
            log({"status": "failed", "message": str(exc), "retry_after": retry_after.isoformat()})
        except Exception as exc:
            retry_after = now + RETRY_INTERVAL
            log({"status": "failed", "error_type": type(exc).__name__,
                 "retry_after": retry_after.isoformat()})
        clock.sleep(POLL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="按服务端配置执行正式普通内容周策划")
    parser.add_argument("--once", action="store_true", help="只检查一次配置并在到期时执行")
    args = parser.parse_args()
    if args.once:
        try:
            print(json.dumps(run_due(datetime.now(BUSINESS_ZONE)), ensure_ascii=False))
        except (PlanningError, RuntimeError, ValueError) as exc:
            parser.exit(2, f"自动策划未完成：{exc}\n")
        return
    try:
        serve()
    except KeyboardInterrupt:
        log({"status": "stopped"})


if __name__ == "__main__":
    main()
