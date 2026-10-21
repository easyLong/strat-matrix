"""Poll matching tasks assigned to the built-in deterministic engine."""

import argparse
import logging
import time

from fastapi import HTTPException
from pydantic import ValidationError

from .matching_contracts import ClaimTask, MatchingFailure
from .matching_executor import (IMPLEMENTATION_KEY, ExecutorInputError,
                                ExecutorPolicyError, execute_job)
from .matching_tasks import claim_task, fail_task, save_evaluation
from .system_config import get_setting


LOG = logging.getLogger("matching-executor-worker")


def _integer_env(name: str, default: int, low: int, high: int) -> int:
    raw = get_setting(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数") from exc
    if not low <= value <= high:
        raise ValueError(f"{name} 必须在{low}至{high}之间")
    return value


def poll_seconds() -> int:
    return _integer_env("MATCHING_EXECUTOR_POLL_SECONDS", 10, 5, 3600)


def lease_seconds() -> int:
    # The built-in engine makes no model/network call, but large matrices can
    # still take time. Keep the default comfortably above the API's old 300s.
    return _integer_env("MATCHING_EXECUTOR_LEASE_SECONDS", 1800, 30, 3600)


def _failure_payload(job: dict, code: str) -> MatchingFailure:
    return MatchingFailure.model_validate({
        "lease_id": job["lease_id"],
        "input_hash": job["input_hash"],
        "policy_hash": job["policy_hash"],
        "error_code": code,
    })


def _record_failure(job: dict, code: str) -> None:
    try:
        fail_task(job["task_id"], _failure_payload(job, code))
    except HTTPException as exc:
        LOG.info("匹配任务 %s 失败状态未回写，HTTP %s", job.get("task_id"), exc.status_code)
    except Exception as exc:
        LOG.error("匹配任务 %s 失败状态回写异常：%s", job.get("task_id"), type(exc).__name__)


def run_once() -> int:
    after_id = 0
    failures = 0
    while True:
        response = claim_task(
            ClaimTask(after_id=after_id, lease_seconds=lease_seconds()),
            implementation_key=IMPLEMENTATION_KEY,
        )
        next_after_id = response.get("next_after_id", after_id)
        job = response.get("job")
        if job is None:
            if next_after_id > after_id:
                after_id = next_after_id
                continue
            return failures
        after_id = next_after_id
        try:
            proposal = execute_job(job)
        except (ExecutorPolicyError, ExecutorInputError, ValidationError, ValueError, TypeError, KeyError):
            failures += 1
            LOG.error("匹配任务 %s 的执行策略或冻结输入不符合内置执行器契约", job["task_id"])
            _record_failure(job, "invalid_response")
            continue
        except Exception as exc:
            failures += 1
            LOG.error("匹配任务 %s 执行异常：%s", job["task_id"], type(exc).__name__)
            _record_failure(job, "execution_failed")
            continue

        try:
            result = save_evaluation(job["task_id"], proposal)
            LOG.info("匹配任务 %s 已完成，状态 %s，版本 %s",
                     job["task_id"], result["status"], result["version"])
        except HTTPException as exc:
            failures += 1
            LOG.info("匹配任务 %s 结果未保存，HTTP %s", job["task_id"], exc.status_code)
        except Exception as exc:
            failures += 1
            LOG.error("匹配任务 %s 结果保存异常：%s", job["task_id"], type(exc).__name__)
            _record_failure(job, "execution_failed")


def main() -> int:
    parser = argparse.ArgumentParser(description="执行已批准策略绑定的普通内容匹配任务")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        interval = poll_seconds()
        lease = lease_seconds()
    except ValueError as exc:
        LOG.error("%s", exc)
        return 2
    if args.check_config:
        LOG.info("Matching Executor 配置有效；poll=%ss lease=%ss；未访问数据库", interval, lease)
        return 0
    while True:
        try:
            failures = run_once()
        except Exception as exc:
            failures = 1
            LOG.error("Matching Executor 队列读取异常：%s", type(exc).__name__)
        if args.once:
            return 1 if failures else 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
