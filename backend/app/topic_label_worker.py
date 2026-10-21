"""Run first-ingest ordinary topic labeling against a configured model service."""

import argparse
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .doubao_labeling import DoubaoConfigurationError, read_config as doubao_config
from .system_config import get_setting
from .t6_tags import normalized_embedding


LOG = logging.getLogger("topic-label-worker")
DIMENSIONS = tuple(f"T{number}" for number in range(1, 7))


class WorkerError(Exception):
    pass


class LeaseLost(WorkerError):
    pass


def json_request(url: str, method: str, *, body: dict | None = None,
                 headers: dict[str, str] | None = None, timeout: int = 30,
                 lease_conflict: bool = False) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = Request(url, data=data, method=method, headers={
        "Accept": "application/json",
        **({"Content-Type": "application/json"} if data is not None else {}),
        **(headers or {}),
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            result = json.load(response)
    except HTTPError as exc:
        if lease_conflict and exc.code in (404, 409):
            raise LeaseLost(f"HTTP {exc.code}") from exc
        raise WorkerError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        raise WorkerError(f"请求失败：{type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise WorkerError("响应必须是 JSON 对象")
    return result


def checked_labels(response: dict, taxonomy: dict) -> dict[str, list[str]]:
    labels = response.get("labels")
    if not isinstance(labels, dict):
        raise WorkerError("模型响应缺少 labels 对象")
    result = {}
    for dimension in DIMENSIONS:
        value = labels.get(dimension)
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
            raise WorkerError(f"{dimension} 必须是 1–80 字的单选名称")
        name = value.strip()
        if dimension != "T6" and name not in taxonomy.get(dimension, []):
            raise WorkerError(f"{dimension} 不属于领取时启用的字典")
        result[dimension] = [name]
    return result


def process_job(topic_id: str, api_url: str, api_token: str,
                model_timeout: int) -> bool | None:
    topic_path = quote(topic_id, safe="")
    internal_headers = {"X-Integration-Token": api_token}
    claim = json_request(f"{api_url}/api/internal/topic-label-jobs/{topic_path}/claim",
                         "POST", headers=internal_headers, lease_conflict=True)
    try:
        lease_id = claim["lease_id"]
    except KeyError as exc:
        raise WorkerError("领取响应缺少 lease_id") from exc
    try:
        response = json_request(f"{api_url}/api/internal/topic-label-model", "POST", body={
            "task": "ordinary_topic_labels",
            "topic_id": topic_id,
            "topic": claim["topic"],
            "taxonomy_version": claim["taxonomy_version"],
            "taxonomy": claim["taxonomy"],
        }, headers=internal_headers, timeout=model_timeout)
        tags = checked_labels(response, claim["taxonomy"])
        try:
            t6_embedding = normalized_embedding(
                response["t6_embedding"], response["t6_embedding_model"])
        except (KeyError, ValueError) as exc:
            raise WorkerError(f"模型返回的 T6 语义向量无效：{exc}") from exc
        json_request(f"{api_url}/api/internal/topic-tags/{topic_path}", "PUT", body={
            "tags": tags,
            "label_status": "已完成",
            "taxonomy_version": claim["taxonomy_version"],
            "lease_id": lease_id,
            "t6_embedding": t6_embedding,
            "t6_embedding_model": response["t6_embedding_model"].strip(),
        }, headers=internal_headers, lease_conflict=True)
        LOG.info("选题 %s 标签识别完成", topic_id)
        return True
    except LeaseLost:
        LOG.info("选题 %s 租约已失效，忽略旧结果", topic_id)
    except (WorkerError, KeyError) as exc:
        reason = str(exc)[:500]
        try:
            json_request(f"{api_url}/api/internal/topic-tags/{topic_path}", "PUT", body={
                "tags": {},
                "label_status": "失败",
                "label_error": reason,
                "lease_id": lease_id,
            }, headers=internal_headers, lease_conflict=True)
        except LeaseLost:
            LOG.info("选题 %s 失败回写时租约已失效", topic_id)
        except WorkerError as report_error:
            LOG.error("选题 %s 失败状态回写异常：%s", topic_id, report_error)
        LOG.warning("选题 %s 标签识别失败：%s", topic_id, reason)
        return False


def worker_config() -> dict:
    api_token = get_setting("INTEGRATION_TOKEN", "").strip()
    if not api_token:
        raise ValueError("需要配置 INTEGRATION_TOKEN；未领取任何任务")
    api_url = get_setting("TOPIC_LABEL_API_URL", "").strip().rstrip("/")
    if not api_url:
        api_url = f"http://127.0.0.1:{get_setting('BACKEND_PORT', '6930')}"
    if not api_url.startswith(("http://", "https://")):
        raise ValueError("TOPIC_LABEL_API_URL 必须是完整的 HTTP(S) 地址")
    model_timeout = int(get_setting("LABEL_MODEL_TIMEOUT_SECONDS", "120"))
    poll_seconds = int(get_setting("TOPIC_LABEL_POLL_SECONDS", "30"))
    retry_seconds = int(get_setting("TOPIC_LABEL_RETRY_SECONDS", "600"))
    if not 1 <= model_timeout <= 600 or not 5 <= poll_seconds <= 3600 or not 60 <= retry_seconds <= 86400:
        raise ValueError("打标超时需在 1–600 秒，轮询需在 5–3600 秒，重试需在 60–86400 秒")
    doubao_config()  # Fail before claiming jobs when shared credentials/models are missing.
    # Label generation uses one chat call and one shared-vector call.
    model_timeout = 2 * model_timeout + 15
    return {"api_url": api_url, "api_token": api_token,
            "model_timeout": model_timeout, "poll_seconds": poll_seconds,
            "retry_seconds": retry_seconds}


def run(once: bool) -> int:
    cfg = worker_config()
    api_url, api_token = cfg["api_url"], cfg["api_token"]
    cooldowns: dict[str, float] = {}
    while True:
        failures = 0
        try:
            after_id = 0
            while True:
                listed = json_request(
                    f"{api_url}/api/internal/topic-label-jobs?limit=100&after_id={after_id}",
                    "GET", headers={"X-Integration-Token": api_token})
                jobs = listed.get("jobs", [])
                if not isinstance(jobs, list):
                    raise WorkerError("任务列表格式错误")
                for job in jobs:
                    if not isinstance(job, dict) or not isinstance(job.get("id"), int):
                        raise WorkerError("任务记录缺少整数 ID")
                    after_id = job["id"]
                    topic_id = job.get("topic_id")
                    if not isinstance(topic_id, str) or cooldowns.get(topic_id, 0) > time.monotonic():
                        continue
                    try:
                        result = process_job(topic_id, api_url, api_token, cfg["model_timeout"])
                        if result is False:
                            failures += 1
                    except LeaseLost:
                        LOG.info("选题 %s 已由其他识别器领取", topic_id)
                    except WorkerError as exc:
                        failures += 1
                        LOG.error("选题 %s 处理异常：%s", topic_id, exc)
                    cooldowns[topic_id] = time.monotonic() + cfg["retry_seconds"]
                if len(jobs) < 100:
                    break
        except WorkerError as exc:
            LOG.error("读取标签任务失败：%s", exc)
            if once:
                return 1
        if once:
            return 1 if failures else 0
        cooldowns = {key: until for key, until in cooldowns.items() if until > time.monotonic()}
        time.sleep(cfg["poll_seconds"])


def main() -> int:
    parser = argparse.ArgumentParser(description="普通选题首次标签识别进程")
    parser.add_argument("--once", action="store_true", help="扫描一次任务队列后退出")
    parser.add_argument("--check-config", action="store_true", help="只检查配置，不领取任务或调用模型")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.check_config:
            cfg = worker_config()
            LOG.info("共享模型配置有效；未领取任务或调用模型")
            return 0
        return run(args.once)
    except (ValueError, DoubaoConfigurationError) as exc:
        LOG.error("标签识别进程配置无效：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
