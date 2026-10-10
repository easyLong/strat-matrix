"""Build ordinary-topic vectors through a configured project model service."""

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

from .topic_profile import normalized_topic_vector


load_dotenv(Path(__file__).resolve().parents[2] / "docs" / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)
LOG = logging.getLogger("topic-vector-worker")


class WorkerError(Exception):
    pass


class StaleResult(WorkerError):
    pass


def json_request(url: str, method: str, *, body: dict | None = None,
                 headers: dict[str, str] | None = None, timeout: int = 30,
                 stale_conflict: bool = False) -> dict:
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
        if stale_conflict and exc.code in (404, 409):
            raise StaleResult(f"HTTP {exc.code}") from exc
        raise WorkerError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError) as exc:
        raise WorkerError(f"请求失败：{type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise WorkerError("响应必须是 JSON 对象")
    return result


def process_job(job: dict, api_url: str, api_token: str,
                model_url: str, model_token: str, model_timeout: int) -> None:
    topic_id = job["topic_id"]
    topic_path = quote(topic_id, safe="")
    endpoint = f"{api_url}/api/internal/topic-vectors/{topic_path}"
    headers = {"X-Integration-Token": api_token}
    version = {"content_hash": job["content_hash"], "tag_version": job["tag_version"]}
    try:
        model_headers = {"Authorization": f"Bearer {model_token}"} if model_token else {}
        response = json_request(model_url, "POST", body={
            "task": "ordinary_topic_embedding",
            "topic_id": topic_id,
            **version,
            "profile": job["profile"],
        }, headers=model_headers, timeout=model_timeout)
        try:
            vector = normalized_topic_vector(response["vector"], response["vector_model"])
        except (KeyError, ValueError) as exc:
            raise WorkerError(f"模型返回的选题向量无效：{exc}") from exc
        json_request(endpoint, "PUT", body={
            **version, "status": "ready", "vector": vector,
            "vector_model": response["vector_model"].strip(),
        }, headers=headers, stale_conflict=True)
        LOG.info("选题 %s 当前画像向量已就绪", topic_id)
    except StaleResult:
        LOG.info("选题 %s 画像版本已变化或结果已由其他进程提交", topic_id)
    except (WorkerError, KeyError) as exc:
        reason = str(exc).strip()[:500] or "选题向量服务返回无效结果"
        try:
            json_request(endpoint, "PUT", body={
                **version, "status": "failed", "error": reason,
            }, headers=headers, stale_conflict=True)
        except StaleResult:
            LOG.info("选题 %s 失败回写时画像版本已变化", topic_id)
        except WorkerError as report_error:
            LOG.error("选题 %s 失败状态回写异常：%s", topic_id, report_error)
        LOG.warning("选题 %s 向量生成失败：%s", topic_id, reason)


def run(once: bool) -> int:
    model_url = os.getenv("TOPIC_VECTOR_MODEL_URL", "").strip()
    api_token = os.getenv("INTEGRATION_TOKEN", "").strip()
    if not model_url or not api_token:
        LOG.error("需要配置 TOPIC_VECTOR_MODEL_URL 和 INTEGRATION_TOKEN；未处理任何任务")
        return 2
    if not model_url.startswith(("http://", "https://")):
        LOG.error("TOPIC_VECTOR_MODEL_URL 必须是完整的 HTTP(S) 地址；未处理任何任务")
        return 2
    api_url = os.getenv("TOPIC_VECTOR_API_URL", "").strip().rstrip("/")
    if not api_url:
        api_url = f"http://127.0.0.1:{os.getenv('BACKEND_PORT', '6930')}"
    model_token = os.getenv("TOPIC_VECTOR_MODEL_TOKEN", "").strip()
    model_timeout = max(1, min(int(os.getenv("TOPIC_VECTOR_MODEL_TIMEOUT_SECONDS", "120")), 600))
    poll_seconds = max(5, int(os.getenv("TOPIC_VECTOR_POLL_SECONDS", "30")))
    retry_seconds = max(60, int(os.getenv("TOPIC_VECTOR_RETRY_SECONDS", "600")))
    cooldowns: dict[str, float] = {}
    headers = {"X-Integration-Token": api_token}
    while True:
        try:
            after_id = 0
            while True:
                listed = json_request(
                    f"{api_url}/api/internal/topic-vector-jobs?limit=100&after_id={after_id}",
                    "GET", headers=headers)
                jobs = listed.get("jobs")
                next_after_id = listed.get("next_after_id")
                if not isinstance(jobs, list) or not isinstance(next_after_id, int):
                    raise WorkerError("向量任务列表格式错误")
                for job in jobs:
                    if not isinstance(job, dict) or not isinstance(job.get("topic_id"), str):
                        raise WorkerError("向量任务缺少选题 ID")
                    topic_id = job["topic_id"]
                    if cooldowns.get(topic_id, 0) > time.monotonic():
                        continue
                    try:
                        process_job(job, api_url, api_token, model_url, model_token,
                                    model_timeout)
                    except (WorkerError, KeyError) as exc:
                        LOG.error("选题 %s 处理异常：%s", topic_id, exc)
                    cooldowns[topic_id] = time.monotonic() + retry_seconds
                if next_after_id <= after_id:
                    break
                after_id = next_after_id
        except WorkerError as exc:
            LOG.error("读取向量任务失败：%s", exc)
            if once:
                return 1
        if once:
            return 0
        cooldowns = {key: until for key, until in cooldowns.items() if until > time.monotonic()}
        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="普通选题当前画像向量生成进程")
    parser.add_argument("--once", action="store_true", help="扫描一次任务队列后退出")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return run(args.once)
    except ValueError as exc:
        LOG.error("选题向量进程配置无效：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
