"""Prepare batch-specific account embeddings through a configured service."""

import argparse
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
import time
from urllib.parse import quote, urlsplit

from dotenv import load_dotenv

from .vector_utils import normalized_vector
from .worker_http import StaleResult, WorkerError, json_request


load_dotenv(Path(__file__).resolve().parents[2] / "docs" / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
LOG = logging.getLogger("account-vector-worker")
JobKey = tuple[int, str, str]


class ConfigurationError(WorkerError):
    pass


@dataclass(frozen=True)
class WorkerConfig:
    api_url: str
    api_token: str
    model_url: str
    model_token: str
    model_timeout: int
    poll_seconds: int
    retry_seconds: int


def http_url(value: str, name: str) -> str:
    try:
        parsed = urlsplit(value)
        valid = parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.fragment
        parsed.port  # Also reject an invalid port without logging the URL.
    except ValueError as exc:
        raise ConfigurationError(f"{name} 必须是有效的 HTTP(S) 地址") from exc
    if not valid or any(character.isspace() for character in value):
        raise ConfigurationError(f"{name} 必须是有效的 HTTP(S) 地址")
    return value


def seconds(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} 必须是整数秒数") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} 必须在 {minimum}–{maximum} 秒之间")
    return value


def read_config() -> WorkerConfig:
    model_url = os.getenv("ACCOUNT_VECTOR_MODEL_URL", "").strip()
    api_token = os.getenv("INTEGRATION_TOKEN", "").strip()
    if not model_url or not api_token:
        raise ConfigurationError("需要配置 ACCOUNT_VECTOR_MODEL_URL 和 INTEGRATION_TOKEN；未处理任何任务")
    api_url = os.getenv("ACCOUNT_VECTOR_API_URL", "").strip().rstrip("/")
    if not api_url:
        api_url = f"http://127.0.0.1:{os.getenv('BACKEND_PORT', '6930')}"
    return WorkerConfig(
        api_url=http_url(api_url, "ACCOUNT_VECTOR_API_URL"), api_token=api_token,
        model_url=http_url(model_url, "ACCOUNT_VECTOR_MODEL_URL"),
        model_token=os.getenv("ACCOUNT_VECTOR_MODEL_TOKEN", "").strip(),
        model_timeout=seconds("ACCOUNT_VECTOR_MODEL_TIMEOUT_SECONDS", 120, 1, 600),
        poll_seconds=seconds("ACCOUNT_VECTOR_POLL_SECONDS", 30, 5, 3600),
        retry_seconds=seconds("ACCOUNT_VECTOR_RETRY_SECONDS", 600, 60, 86400),
    )


def job_key(job: object) -> JobKey:
    if not isinstance(job, dict):
        raise WorkerError("账号向量任务必须是 JSON 对象")
    batch_id, account_id, fingerprint = (job.get(key) for key in ("batch_id", "account_id", "profile_hash"))
    if type(batch_id) is not int or batch_id < 1:
        raise WorkerError("账号向量任务缺少有效批次 ID")
    if not isinstance(account_id, str) or not account_id.strip() or len(account_id) > 64:
        raise WorkerError("账号向量任务缺少有效账号 ID")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise WorkerError("账号向量任务缺少有效画像指纹")
    if type(job.get("config_version")) is not int or job["config_version"] < 0 \
            or not isinstance(job.get("profile"), dict):
        raise WorkerError("账号向量任务缺少配置版本或画像")
    return batch_id, account_id, fingerprint


def submit_result(endpoint: str, cfg: WorkerConfig, key: JobKey, payload: dict) -> None:
    response = json_request(endpoint, "PUT", body=payload,
                            headers={"X-Integration-Token": cfg.api_token}, stale_conflict=True)
    if response.get("batch_id") != key[0] or response.get("account_id") != key[1] \
            or response.get("profile_hash") != key[2] or response.get("status") != payload["status"]:
        raise WorkerError("账号向量回写响应与任务不一致")


def process_job(job: dict, cfg: WorkerConfig, ready_results: dict[JobKey, dict]) -> bool:
    key = job_key(job)
    batch_id, account_id, fingerprint = key
    endpoint = f"{cfg.api_url}/api/internal/account-vectors/{batch_id}/{quote(account_id, safe='')}"
    if key not in ready_results:
        try:
            response = json_request(cfg.model_url, "POST", body={
                "task": "account_profile_embedding", "batch_id": batch_id,
                "account_id": account_id, "profile_hash": fingerprint,
                "config_version": job["config_version"], "profile": job["profile"],
            }, headers={"Authorization": f"Bearer {cfg.model_token}"} if cfg.model_token else {},
                timeout=cfg.model_timeout)
            try:
                normalized_vector(response["vector"], response["vector_model"], "账号")
            except (KeyError, ValueError, TypeError, OverflowError) as exc:
                raise WorkerError("模型返回的账号向量无效") from exc
            # The backend normalizes the vector. Keep the original response
            # for identical retries if its acknowledgement is lost.
            ready_results[key] = {"profile_hash": fingerprint, "status": "ready",
                                  "vector": response["vector"], "vector_model": response["vector_model"].strip()}
        except WorkerError as exc:
            reason = str(exc)[:500]
            try:
                submit_result(endpoint, cfg, key, {"profile_hash": fingerprint,
                                                  "status": "failed", "error": reason})
            except StaleResult:
                LOG.info("批次 %s 账号 %s 已不需要本次结果", batch_id, account_id)
                return True
            except WorkerError as report_error:
                LOG.error("批次 %s 账号 %s 失败状态回写异常：%s", batch_id, account_id, report_error)
            LOG.warning("批次 %s 账号 %s 向量生成失败：%s", batch_id, account_id, reason)
            return False
    try:
        submit_result(endpoint, cfg, key, ready_results[key])
    except StaleResult:
        ready_results.pop(key, None)
        LOG.info("批次 %s 账号 %s 已结束、版本不匹配或已由其他进程提交", batch_id, account_id)
    except WorkerError as exc:
        LOG.warning("批次 %s 账号 %s 向量回写异常，保留结果等待重试：%s", batch_id, account_id, exc)
        return False
    else:
        ready_results.pop(key, None)
        LOG.info("批次 %s 账号 %s 画像向量已就绪", batch_id, account_id)
    return True


def run(cfg: WorkerConfig, once: bool, batch_id: int | None = None) -> int:
    cooldowns: dict[JobKey, float] = {}
    ready_results: dict[JobKey, dict] = {}
    while True:
        failures = 0
        seen: set[JobKey] = set()
        try:
            after_id = 0
            while True:
                batch_filter = f"&batch_id={batch_id}" if batch_id is not None else ""
                listed = json_request(
                    f"{cfg.api_url}/api/internal/account-vector-jobs?limit=100&after_id={after_id}{batch_filter}",
                    "GET", headers={"X-Integration-Token": cfg.api_token})
                jobs, next_after_id = listed.get("jobs"), listed.get("next_after_id")
                if not isinstance(jobs, list) or type(next_after_id) is not int \
                        or next_after_id < after_id or (jobs and next_after_id == after_id):
                    raise WorkerError("账号向量任务列表或分页游标格式错误")
                for job in jobs:
                    try:
                        key = job_key(job)
                        if batch_id is not None and key[0] != batch_id:
                            raise WorkerError("账号向量任务不属于指定批次")
                        seen.add(key)
                        if cooldowns.get(key, 0) > time.monotonic():
                            continue
                        if not process_job(job, cfg, ready_results):
                            failures += 1
                        cooldowns[key] = time.monotonic() + cfg.retry_seconds
                    except WorkerError as exc:
                        LOG.error("账号向量任务处理异常：%s", exc)
                        failures += 1
                if next_after_id == after_id:
                    break
                # Advance even when a page was filtered to an empty jobs list.
                after_id = next_after_id
            ready_results = {key: result for key, result in ready_results.items() if key in seen}
        except WorkerError as exc:
            LOG.error("读取账号向量任务失败：%s", exc)
            failures += 1
        if once:
            return 1 if failures else 0
        cooldowns = {key: until for key, until in cooldowns.items() if until > time.monotonic()}
        time.sleep(cfg.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="策划批次账号画像向量生成进程")
    parser.add_argument("--once", action="store_true", help="扫描一次任务队列后退出")
    parser.add_argument("--batch-id", type=int, help="只处理指定正式策划批次")
    parser.add_argument("--check-config", action="store_true", help="检查配置后退出，不读取任务或调用模型")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.batch_id is not None and args.batch_id < 1:
        parser.error("--batch-id 必须是正整数")
    try:
        cfg = read_config()
    except ConfigurationError as exc:
        LOG.error("账号向量进程配置无效：%s", exc)
        return 2
    if args.check_config:
        LOG.info("账号向量进程配置有效；未读取任务或调用模型")
        return 0
    return run(cfg, args.once, args.batch_id)


if __name__ == "__main__":
    raise SystemExit(main())
