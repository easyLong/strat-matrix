"""Doubao contract, worker and protected service regression tests (no real model calls)."""

import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from pydantic import ValidationError

from app import doubao_labeling as service
from app import topic_label_model_api as api
from app import topic_label_worker as worker
from app.system_config import override_config


TAXONOMY = {"T1": ["非营销", "营销"], "T2": ["流量", "转化"],
            "T3": ["金融知识"], "T4": ["年轻客群"], "T5": ["日常理财"]}
LABELS = {key: values[0] for key, values in TAXONOMY.items()} | {"T6": "管理日常资金"}
ENV = {"ARK_API_KEY": "test-only-key", "DOUBAO_CHAT_MODEL": "chat-fixture",
       "DOUBAO_EMBEDDING_MODEL": "embedding-fixture", "INTEGRATION_TOKEN": "test-only-token",
       "TOPIC_LABEL_PROVIDER": "doubao", "BACKEND_PORT": "6930"}


def payload():
    return service.LabelInput(topic_id="T-001", taxonomy_version=3, taxonomy=TAXONOMY,
                              topic={"title": "年轻人如何管理零花钱", "outline": "分配日常资金"})


def chat(labels=None, finish_reason="stop"):
    return {"choices": [{"finish_reason": finish_reason,
                         "message": {"content": json.dumps({"labels": labels or LABELS})}}]}


def embedding(multimodal=True):
    row = {"embedding": [3.0, 4.0]}
    return {"model": "embedding-fixture-v1", "data": row if multimodal else [{**row, "index": 0}]}


def config(api_type="multimodal"):
    return service.DoubaoConfig("https://ark.example.invalid/api/v3", "test-only-key",
                                "chat-fixture", "embedding-fixture", api_type, 10)


@contextmanager
def local_ark():
    """Actual loopback HTTP exchange to verify serialization and response parsing."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("Authorization"), body))
            if self.path.endswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", "/redirect-target")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            result = chat() if self.path.endswith("/chat/completions") else embedding()
            raw = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization"), None))
            raw = b'{}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        cfg = service.DoubaoConfig(f"http://127.0.0.1:{server.server_port}/api/v3",
                                   "test-only-key", "chat-fixture", "embedding-fixture", "multimodal", 10)
        yield cfg, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class DoubaoLabelingTests(unittest.TestCase):
    def test_missing_credentials_or_embedding_model_fail_before_network(self):
        for missing in ("ARK_API_KEY", "DOUBAO_EMBEDDING_MODEL"):
            with self.subTest(missing=missing), override_config({**ENV, missing: ""}), \
                    patch.object(service, "ark_post") as network:
                with self.assertRaises(service.DoubaoConfigurationError):
                    service.label_topic(payload())
                network.assert_not_called()

    def test_invalid_endpoint_or_timeout_is_rejected_without_printing_secrets(self):
        for update in ({"DOUBAO_BASE_URL": "http://example.invalid/api/v3"},
                       {"DOUBAO_BASE_URL": "https://secret@example.invalid/api/v3"},
                       {"DOUBAO_EMBEDDING_API": "unknown"}, {"LABEL_MODEL_TIMEOUT_SECONDS": "bad"}):
            with self.subTest(update=update), override_config({**ENV, **update}):
                with self.assertRaises(service.DoubaoConfigurationError) as raised:
                    service.read_config()
                self.assertNotIn("test-only-key", str(raised.exception))
        self.assertNotIn("test-only-key", repr(config()))

    def test_incomplete_or_ambiguous_dictionary_is_rejected(self):
        for taxonomy in ({"T1": ["非营销"]}, {**TAXONOMY, "T3": []},
                         {**TAXONOMY, "T3": ["同名", "同名"]}):
            with self.subTest(taxonomy=taxonomy), self.assertRaises(ValidationError):
                service.LabelInput(topic_id="T", topic={"title": "title"}, taxonomy_version=1,
                                   taxonomy=taxonomy)

    def test_chat_and_multimodal_embedding_roundtrip_over_http(self):
        with local_ark() as (cfg, requests):
            result = service.label_topic(payload(), cfg)
        self.assertEqual(result["labels"], LABELS)
        self.assertEqual(result["t6_embedding"], [0.6, 0.8])
        self.assertEqual(result["t6_embedding_model"], "embedding-fixture-v1")
        self.assertEqual([row[0] for row in requests],
                         ["/api/v3/chat/completions", "/api/v3/embeddings/multimodal"])
        self.assertTrue(all(row[1] == "Bearer test-only-key" for row in requests))
        self.assertEqual(requests[0][2]["response_format"], {"type": "json_object"})
        self.assertEqual(requests[1][2]["input"], [{"type": "text", "text": LABELS["T6"]}])
        self.assertNotIn("test-only-key", json.dumps(requests[0][2]))

    def test_text_embedding_contract_is_supported(self):
        with patch.object(service, "ark_post", side_effect=[chat(), embedding(False)]) as post:
            result = service.label_topic(payload(), config("text"))
        self.assertEqual(result["t6_embedding"], [0.6, 0.8])
        self.assertEqual(post.call_args.args[1], "/embeddings")
        self.assertEqual(post.call_args.args[2]["input"], [LABELS["T6"]])

    def test_invalid_dictionary_label_is_not_embedded(self):
        with patch.object(service, "ark_post", return_value=chat({**LABELS, "T3": "字典外名称"})) as post:
            with self.assertRaises(service.DoubaoResponseError):
                service.label_topic(payload(), config())
        self.assertEqual(post.call_count, 1)

    def test_truncated_refused_or_malformed_chat_is_not_saved(self):
        for response in (chat(finish_reason="length"), {"choices": []},
                         {"choices": [{"finish_reason": "stop", "message": {"content": "not-json"}}]},
                         chat({**LABELS, "T6": ["两个", "标签"]})):
            with self.subTest(response=response), patch.object(service, "ark_post", return_value=response) as post:
                with self.assertRaises(service.DoubaoResponseError):
                    service.label_topic(payload(), config())
                self.assertEqual(post.call_count, 1)

    def test_invalid_embeddings_do_not_become_ready(self):
        for vector in ([0, 0], [True, 1], [float("nan"), 1], [], [float("inf"), 1]):
            response = {"model": "embedding-v1", "data": {"embedding": vector}}
            with self.subTest(vector=vector), patch.object(service, "ark_post", side_effect=[chat(), response]):
                with self.assertRaises(service.DoubaoResponseError):
                    service.label_topic(payload(), config())

    def test_upstream_errors_are_sanitized_and_classified(self):
        for status, expected in ((429, service.DoubaoUnavailable), (503, service.DoubaoUnavailable),
                                 (401, service.DoubaoResponseError)):
            error = HTTPError("https://secret.invalid", status, "secret-upstream-body", {}, None)
            with self.subTest(status=status), patch.object(service, "open_request", side_effect=error):
                with self.assertRaises(expected) as raised:
                    service.ark_post(config(), "/chat/completions", {})
                self.assertNotIn("secret", str(raised.exception))
        with patch.object(service, "open_request", side_effect=URLError("test-only-key")):
            with self.assertRaises(service.DoubaoUnavailable) as raised:
                service.ark_post(config(), "/chat/completions", {})
            self.assertNotIn("test-only-key", str(raised.exception))

    def test_provider_redirect_does_not_forward_credentials(self):
        with local_ark() as (cfg, requests):
            with self.assertRaises(service.DoubaoResponseError):
                service.ark_post(cfg, "/redirect", {})
        self.assertEqual(len(requests), 1)


class DoubaoWorkerTests(unittest.TestCase):
    def test_worker_preflight_does_not_claim_when_unconfigured(self):
        with override_config({**ENV, "ARK_API_KEY": ""}), \
                patch.object(worker, "json_request") as request:
            with self.assertRaises(service.DoubaoConfigurationError):
                worker.run(once=True)
            request.assert_not_called()

    def test_worker_doubao_route_uses_internal_token_and_sequential_timeout(self):
        with override_config(ENV):
            cfg = worker.worker_config()
        self.assertEqual(cfg["model_url"], "http://127.0.0.1:6930/api/internal/topic-label-model")
        self.assertEqual(cfg["model_timeout"], 255)

    def test_full_claim_inference_embedding_and_completion_handoff(self):
        calls = []
        with local_ark() as (cfg, network):
            def request(url, method, **kwargs):
                calls.append((url, method, kwargs))
                if url.endswith("/claim"):
                    return {"lease_id": "lease-fixture", "topic": payload().topic,
                            "taxonomy_version": 3, "taxonomy": TAXONOMY}
                if url.endswith("topic-label-model"):
                    return service.label_topic(service.LabelInput.model_validate(kwargs["body"]), cfg)
                return {"label_status": "已完成"}
            with patch.object(worker, "json_request", side_effect=request):
                result = worker.process_job("T-001", "http://backend", "integration-fixture",
                                            "http://backend/api/internal/topic-label-model", "", 255, "doubao")
        self.assertTrue(result)
        self.assertEqual(len(network), 2)
        completed = calls[-1][2]["body"]
        self.assertEqual(completed["lease_id"], "lease-fixture")
        self.assertEqual(completed["tags"], {key: [name] for key, name in LABELS.items()})
        self.assertEqual(completed["t6_embedding"], [0.6, 0.8])
        self.assertEqual(calls[1][2]["headers"], {"X-Integration-Token": "integration-fixture"})

    def test_model_failure_reports_failed_job_instead_of_fake_labels(self):
        claim = {"lease_id": "lease-fixture", "topic": payload().topic,
                 "taxonomy_version": 3, "taxonomy": TAXONOMY}
        with patch.object(worker, "json_request", side_effect=[claim, worker.WorkerError("HTTP 502"), {}]) as req:
            result = worker.process_job("T-001", "http://backend", "internal", "http://model", "", 120)
        self.assertFalse(result)
        self.assertEqual(req.call_args.kwargs["body"]["label_status"], "失败")
        self.assertEqual(req.call_args.kwargs["body"]["tags"], {})

    def test_expired_lease_does_not_write_over_new_task(self):
        claim = {"lease_id": "old", "topic": payload().topic, "taxonomy_version": 3, "taxonomy": TAXONOMY}
        result = {"labels": LABELS, "t6_embedding_model": "embedding-v1", "t6_embedding": [3, 4]}
        with patch.object(worker, "json_request", side_effect=[claim, result, worker.LeaseLost("HTTP 409")]) as req:
            self.assertIsNone(worker.process_job("T", "http://backend", "token", "http://model", "", 120))
        self.assertEqual(req.call_count, 3)

    def test_once_exits_with_failure_when_a_model_job_fails(self):
        with override_config(ENV), \
                patch.object(worker, "json_request", return_value={"jobs": [{"id": 1, "topic_id": "T"}]}), \
                patch.object(worker, "process_job", return_value=False):
            self.assertEqual(worker.run(once=True), 1)

    def test_legacy_http_provider_remains_supported(self):
        with override_config({"TOPIC_LABEL_PROVIDER": "http", "LABEL_MODEL_URL": "http://legacy/labels",
                              "INTEGRATION_TOKEN": "internal", "LABEL_MODEL_TOKEN": "model-token"}):
            cfg = worker.worker_config()
        self.assertEqual(cfg["model_url"], "http://legacy/labels")
        self.assertEqual(cfg["model_token"], "model-token")


class DoubaoApiTests(unittest.TestCase):
    def request(self, body, token=True):
        from app.main import app

        async def send_request():
            messages = []
            headers = [(b"content-type", b"application/json")]
            if token:
                headers.append((b"x-integration-token", b"test-only-token"))

            async def receive():
                return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}

            async def send(message):
                messages.append(message)

            path = "/api/internal/topic-label-model"
            await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                       "scheme": "http", "method": "POST", "path": path, "raw_path": path.encode(),
                       "query_string": b"", "root_path": "", "headers": headers,
                       "server": ("test", 80), "client": ("test", 1234)}, receive, send)
            return next(item["status"] for item in messages if item["type"] == "http.response.start")

        with override_config(ENV):
            return asyncio.run(send_request())

    def test_service_requires_authentication_before_model_call(self):
        with patch.object(api, "label_topic") as model:
            self.assertEqual(self.request(payload().model_dump(), token=False), 401)
            model.assert_not_called()

    def test_invalid_input_does_not_call_model(self):
        with patch.object(api, "label_topic") as model:
            self.assertEqual(self.request({"topic_id": "T"}), 422)
            model.assert_not_called()

    def test_service_returns_existing_worker_contract(self):
        result = {"labels": LABELS, "t6_embedding_model": "embedding-v1", "t6_embedding": [0.6, 0.8]}
        with patch.object(api, "label_topic", return_value=result):
            self.assertEqual(self.request(payload().model_dump()), 200)

    def test_provider_failures_have_explicit_http_status(self):
        for error, status in ((service.DoubaoConfigurationError("missing config"), 503),
                              (service.DoubaoUnavailable("temporary error"), 503),
                              (service.DoubaoResponseError("invalid output"), 502)):
            with self.subTest(status=status), patch.object(api, "label_topic", side_effect=error):
                self.assertEqual(self.request(payload().model_dump()), status)


if __name__ == "__main__":
    unittest.main()
