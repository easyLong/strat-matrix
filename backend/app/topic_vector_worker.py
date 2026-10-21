"""Build ordinary-topic vectors through a configured project model service."""

import argparse
import logging
import time
from urllib.parse import quote

from .topic_profile import normalized_topic_vector
from .system_config import get_setting
from .worker_http import StaleResult, WorkerError, json_request
from .doubao_labeling import DoubaoConfigurationError, read_embedding_config


LOG = logging.getLogger("topic-vector-worker")


def process_job(job: dict, api_url: str, api_token: str, model_timeout: int = 180) -> None:
    topic_id = job["topic_id"]
    topic_path = quote(topic_id, safe="")
    endpoint = f"{api_url}/api/internal/topic-vectors/{topic_path}"
    headers = {"X-Integration-Token": api_token}
    version = {"content_hash": job["content_hash"], "tag_version": job["tag_version"]}
    try:
        response = json_request(f"{api_url}/api/internal/embedding-model", "POST", body={
            "task": "ordinary_topic_embedding",
            "topic_id": topic_id,
            **version,
            "profile": job["profile"],
        }, headers=headers, timeout=model_timeout)
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


def worker_config() -> dict:
    api_token = get_setting("INTEGRATION_TOKEN", "").strip()
    if not api_token:
        raise ValueError("需要配置 INTEGRATION_TOKEN；未处理任何任务")
    read_embedding_config()
    api_url = get_setting("TOPIC_VECTOR_API_URL", "").strip().rstrip("/")
    if not api_url:
        api_url = f"http://127.0.0.1:{get_setting('BACKEND_PORT', '6930')}"
    model_timeout = max(1, min(int(get_setting("TOPIC_VECTOR_MODEL_TIMEOUT_SECONDS", "120")), 600))
    poll_seconds = max(5, int(get_setting("TOPIC_VECTOR_POLL_SECONDS", "30")))
    retry_seconds = max(60, int(get_setting("TOPIC_VECTOR_RETRY_SECONDS", "600")))
    return {"api_token": api_token, "api_url": api_url, "model_timeout": model_timeout,
            "poll_seconds": poll_seconds, "retry_seconds": retry_seconds}


def run(once: bool) -> int:
    try:
        cfg = worker_config()
    except (ValueError, DoubaoConfigurationError) as exc:
        LOG.error("选题向量进程配置无效：%s", exc)
        return 2
    api_token, api_url = cfg["api_token"], cfg["api_url"]
    model_timeout, poll_seconds, retry_seconds = cfg["model_timeout"], cfg["poll_seconds"], cfg["retry_seconds"]
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
                        process_job(job, api_url, api_token, model_timeout)
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
    parser.add_argument("--check-config", action="store_true", help="检查共享模型配置后退出，不读取任务")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.check_config:
            worker_config()
            LOG.info("共享向量模型配置有效；未读取任务或调用模型")
            return 0
        return run(args.once)
    except (ValueError, DoubaoConfigurationError) as exc:
        LOG.error("选题向量进程配置无效：%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
