"""Poll existing AI preparations until their inputs can be frozen."""

import argparse
import logging
import time

from fastapi import HTTPException

from .ai_preparation import advance_preparation, today
from .db import connection
from .system_config import get_setting


LOG = logging.getLogger("ai-preparation-worker")


def poll_seconds() -> int:
    try:
        interval = int(get_setting("AI_PREPARATION_POLL_SECONDS", "60"))
    except ValueError as exc:
        raise ValueError("AI_PREPARATION_POLL_SECONDS 必须是整数") from exc
    if not 5 <= interval <= 3600:
        raise ValueError("AI_PREPARATION_POLL_SECONDS 必须在5至3600秒之间")
    return interval


def run_once() -> int:
    after_id = 0
    failures = 0
    while True:
        with connection() as db, db.cursor() as cursor:
            cursor.execute(
                "SELECT id, version FROM godp_ai_preparation WHERE del_flag='N' AND id>%s "
                "AND (status IN ('waiting_inputs','blocked') "
                "OR (status='inputs_frozen' AND cycle_end<%s)) ORDER BY id LIMIT 100",
                (after_id, today()),
            )
            rows = cursor.fetchall()
        if not rows:
            return failures
        for row in rows:
            try:
                result = advance_preparation(row["id"], row["version"])
                LOG.info("准备记录 %s 状态 %s，版本 %s", row["id"], result["status"], result["version"])
            except HTTPException as exc:
                if exc.status_code not in (404, 409):
                    failures += 1
                LOG.info("准备记录 %s 本轮未推进，HTTP %s", row["id"], exc.status_code)
            except Exception as exc:
                failures += 1
                LOG.error("准备记录 %s 推进异常：%s", row["id"], type(exc).__name__)
        after_id = rows[-1]["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description="推进已创建的正式AI输入准备，不创建运营结果")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        interval = poll_seconds()
    except ValueError as exc:
        LOG.error("%s", exc)
        return 2
    if args.check_config:
        LOG.info("准备推进进程配置有效；未访问数据库或模型")
        return 0
    while True:
        try:
            failures = run_once()
        except Exception as exc:
            failures = 1
            LOG.error("准备队列读取异常：%s", type(exc).__name__)
        if args.once:
            return 1 if failures else 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
