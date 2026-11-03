"""Prepare batch-specific account embeddings through a configured service."""

import argparse
from dataclasses import dataclass
import logging
import re
import time
from urllib.parse import quote

from .vector_utils import normalized_vector
from .system_config import get_setting
from .worker_http import StaleResult, WorkerError, json_request
from .doubao_labeling import DoubaoConfigurationError, read_embedding_config


LOG = logging.getLogger("account-vector-worker")
JobKey = tuple[str, int, str, str]


class ConfigurationError(WorkerError):
    pass


@dataclass(frozen=True)
class WorkerConfig:
    api_url: str
    api_token: str
    model_timeout: int
    poll_seconds: int
    retry_seconds: int


def seconds(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(get_setting(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} 必须是整数秒数") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} 必须在 {minimum}–{maximum} 秒之间")
    return value


def read_config() -> WorkerConfig:
    api_token = get_setting("INTEGRATION_TOKEN", "").strip()
    if not api_token:
        raise ConfigurationError("需要配置 INTEGRATION_TOKEN；未处理任何任务")
    try:
        read_embedding_config()
    except DoubaoConfigurationError as exc:
        raise ConfigurationError(str(exc)) from exc
    api_url = get_setting("ACCOUNT_VECTOR_API_URL", "").strip().rstrip("/")
    if not api_url:
        api_url = f"http://127.0.0.1:{get_setting('BACKEND_PORT', '6930')}"
    return WorkerConfig(
        api_url=api_url, api_token=api_token,
        model_timeout=seconds("ACCOUNT_VECTOR_MODEL_TIMEOUT_SECONDS", 120, 1, 600),
        poll_seconds=seconds("ACCOUNT_VECTOR_POLL_SECONDS", 30, 5, 3600),
        retry_seconds=seconds("ACCOUNT_VECTOR_RETRY_SECONDS", 600, 60, 86400),
    )


def job_key(job: object) -> JobKey:
    if not isinstance(job, dict):
        raise WorkerError("账号向量任务必须是 JSON 对象")
    identity = "preparation_id" if "preparation_id" in job else "batch_id"
    if "preparation_id" in job and "batch_id" in job:
        raise WorkerError("账号向量任务不能同时包含运营批次与准备记录ID")
    batch_id, account_id, fingerprint = (job.get(key) for key in (identity, "account_id", "profile_hash"))
    if type(batch_id) is not int or batch_id < 1:
        raise WorkerError("账号向量任务缺少有效批次 ID")
    if not isinstance(account_id, str) or not account_id.strip() or len(account_id) > 64:
        raise WorkerError("账号向量任务缺少有效账号 ID")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise WorkerError("账号向量任务缺少有效画像指纹")
    if type(job.get("config_version")) is not int or job["config_version"] < 0 \
            or not isinstance(job.get("profile"), dict):
        raise WorkerError("账号向量任务缺少配置版本或画像")
    return identity, batch_id, account_id, fingerprint


def submit_result(endpoint: str, cfg: WorkerConfig, key: JobKey, payload: dict) -> None:
    response = json_request(endpoint, "PUT", body=payload,
                            headers={"X-Integration-Token": cfg.api_token}, stale_conflict=True)
    if response.get(key[0]) != key[1] or response.get("account_id") != key[2] \
            or response.get("profile_hash") != key[3] or response.get("status") != payload["status"]:
        raise WorkerError("账号向量回写响应与任务不一致")


def process_job(job: dict, cfg: WorkerConfig, ready_results: dict[JobKey, dict]) -> bool:
    key = job_key(job)
    identity, batch_id, account_id, fingerprint = key
    route = "preparation-account-vectors" if identity == "preparation_id" else "account-vectors"
    endpoint = f"{cfg.api_url}/api/internal/{route}/{batch_id}/{quote(account_id, safe='')}"
    if key not in ready_results:
        try:
            response = json_request(f"{cfg.api_url}/api/internal/embedding-model", "POST", body={
                "task": "account_profile_embedding", identity: batch_id,
                "account_id": account_id, "profile_hash": fingerprint,
                "config_version": job["config_version"], "profile": job["profile"],
            }, headers={"X-Integration-Token": cfg.api_token},
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


def run(cfg: WorkerConfig, once: bool, batch_id: int | None = None,
        preparation_id: int | None = None) -> int:
    cooldowns: dict[JobKey, float] = {}
    ready_results: dict[JobKey, dict] = {}
    while True:
        failures = 0
        seen: set[JobKey] = set()
        queues = []
        if batch_id is None:
            queues.append(("preparation_id", "preparation-account-vector-jobs", preparation_id))
        if preparation_id is None:
            queues.append(("batch_id", "account-vector-jobs", batch_id))
        completed_scopes = set()
        for identity, route, selected_id in queues:
            try:
                after_id = 0
                while True:
                    selected_filter = f"&{identity}={selected_id}" if selected_id is not None else ""
                    listed = json_request(
                        f"{cfg.api_url}/api/internal/{route}?limit=100&after_id={after_id}{selected_filter}",
                        "GET", headers={"X-Integration-Token": cfg.api_token})
                    jobs, next_after_id = listed.get("jobs"), listed.get("next_after_id")
                    if not isinstance(jobs, list) or type(next_after_id) is not int \
                            or next_after_id < after_id or (jobs and next_after_id == after_id):
                        raise WorkerError("账号向量任务列表或分页游标格式错误")
                    for job in jobs:
                        try:
                            key = job_key(job)
                            if key[0] != identity or (selected_id is not None and key[1] != selected_id):
                                raise WorkerError("账号向量任务不属于指定记录或队列")
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
                    after_id = next_after_id
                completed_scopes.add(identity)
            except WorkerError as exc:
                LOG.error("读取%s账号向量任务失败：%s", identity, exc)
                failures += 1
        ready_results = {key: result for key, result in ready_results.items()
                         if key[0] not in completed_scopes or key in seen}
        if once:
            return 1 if failures else 0
        cooldowns = {key: until for key, until in cooldowns.items() if until > time.monotonic()}
        time.sleep(cfg.poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="策划批次账号画像向量生成进程")
    parser.add_argument("--once", action="store_true", help="扫描一次任务队列后退出")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--batch-id", type=int, help="只处理指定正式策划批次")
    scope.add_argument("--preparation-id", type=int, help="只处理指定正式AI准备记录")
    parser.add_argument("--check-config", action="store_true", help="检查配置后退出，不读取任务或调用模型")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.batch_id is not None and args.batch_id < 1:
        parser.error("--batch-id 必须是正整数")
    if args.preparation_id is not None and args.preparation_id < 1:
        parser.error("--preparation-id 必须是正整数")
    try:
        cfg = read_config()
    except (ConfigurationError, DoubaoConfigurationError) as exc:
        LOG.error("账号向量进程配置无效：%s", exc)
        return 2
    if args.check_config:
        LOG.info("账号向量进程配置有效；未读取任务或调用模型")
        return 0
    return run(cfg, args.once, args.batch_id, args.preparation_id)


if __name__ == "__main__":
    raise SystemExit(main())
