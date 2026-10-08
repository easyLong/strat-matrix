"""Run first-ingest ordinary topic labeling against a configured model service."""

import argparse
import json
import logging
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / "docs" / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
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
                model_url: str, model_token: str, model_timeout: int) -> None:
    topic_path = quote(topic_id, safe="")
    internal_headers = {"X-Integration-Token": api_token}
    claim = json_request(f"{api_url}/api/internal/topic-label-jobs/{topic_path}/claim",
                         "POST", headers=internal_headers, lease_conflict=True)
    try:
        lease_id = claim["lease_id"]
    except KeyError as exc:
        raise WorkerError("领取响应缺少 lease_id") from exc
    try:
        model_headers = {"Authorization": f"Bearer {model_token}"} if model_token else {}
        response = json_request(model_url, "POST", body={
            "task": "ordinary_topic_labels",
            "topic_id": topic_id,
            "topic": claim["topic"],
            "taxonomy_version": claim["taxonomy_version"],
            "taxonomy": claim["taxonomy"],
        }, headers=model_headers, timeout=model_timeout)
        tags = checked_labels(response, claim["taxonomy"])
        json_request(f"{api_url}/api/internal/topic-tags/{topic_path}", "PUT", body={
            "tags": tags,
            "label_status": "已完成",
            "taxonomy_version": claim["taxonomy_version"],
            "lease_id": lease_id,
        }, headers=internal_headers, lease_conflict=True)
        LOG.info("选题 %s 标签识别完成", topic_id)
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


def run(once: bool) -> int:
    model_url = os.getenv("LABEL_MODEL_URL", "").strip()
    api_token = os.getenv("INTEGRATION_TOKEN", "").strip()
    if not model_url or not api_token:
        LOG.error("需要配置 LABEL_MODEL_URL 和 INTEGRATION_TOKEN；未领取任何任务")
        return 2
    if not model_url.startswith(("http://", "https://")):
        LOG.error("LABEL_MODEL_URL 必须是完整的 HTTP(S) 地址；未领取任何任务")
        return 2
    api_url = os.getenv("TOPIC_LABEL_API_URL", "").strip().rstrip("/")
    if not api_url:
        api_url = f"http://127.0.0.1:{os.getenv('BACKEND_PORT', '6930')}"
    model_token = os.getenv("LABEL_MODEL_TOKEN", "").strip()
    model_timeout = max(1, min(int(os.getenv("LABEL_MODEL_TIMEOUT_SECONDS", "120")), 600))
    poll_seconds = max(5, int(os.getenv("TOPIC_LABEL_POLL_SECONDS", "30")))
    retry_seconds = max(60, int(os.getenv("TOPIC_LABEL_RETRY_SECONDS", "600")))
    cooldowns: dict[str, float] = {}
    while True:
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
                        process_job(topic_id, api_url, api_token, model_url, model_token,
                                    model_timeout)
                    except LeaseLost:
                        LOG.info("选题 %s 已由其他识别器领取", topic_id)
                    except WorkerError as exc:
                        LOG.error("选题 %s 处理异常：%s", topic_id, exc)
                    cooldowns[topic_id] = time.monotonic() + retry_seconds
                if len(jobs) < 100:
                    break
        except WorkerError as exc:
            LOG.error("读取标签任务失败：%s", exc)
            if once:
                return 1
        if once:
            return 0
        cooldowns = {key: until for key, until in cooldowns.items() if until > time.monotonic()}
        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="普通选题首次标签识别进程")
    parser.add_argument("--once", action="store_true", help="扫描一次任务队列后退出")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return run(args.once)
    except ValueError as exc:
        LOG.error("标签识别进程配置无效：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
