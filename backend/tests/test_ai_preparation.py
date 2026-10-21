"""Preparation lifecycle safety, with no business database or model calls."""

from contextlib import ExitStack
import asyncio
from copy import deepcopy
from datetime import date, timedelta
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import ai_preparation as service
from app import ai_preparation_api as api
from app import account_vector_worker as worker
from app.account_profile import canonical_json, profile_from_preparation, profile_from_snapshot
from app.account_vector_api import AccountVectorResult
from app.init_db import column_definitions, table_descriptions
from app.worker_http import WorkerError
from test_matching_readiness import fixture, CHECKED_AT


START = date(2026, 10, 19)


class Store:
    """Small scripted SQL adapter; assertions focus on lifecycle effects."""
    def __init__(self):
        batch, _, self.topics = fixture()
        self.snapshots = json.loads(batch["account_snapshot_json"])
        self.config = {"version": batch["config_version"], "config_json": batch["config_json"]}
        self.row = None
        self.accounts = []
        self.frozen_topics = []
        self.result_batch = False
        self.fail_topic_write = False
        self.cursor = MagicMock()
        self.db = MagicMock()
        self.db.__enter__.return_value = self.db
        self.db.cursor.return_value = self.cursor
        self.cursor.__enter__.return_value = self.cursor
        self.cursor.execute.side_effect = self.execute
        self.current_one = None
        self.current_many = []
        self.cursor.fetchone.side_effect = lambda: deepcopy(self.current_one)
        self.cursor.fetchall.side_effect = lambda: deepcopy(self.current_many)
        self.topics[0].update(tag_ids_json=canonical_json({f"T{i}": f"T{i}-ID" for i in range(1, 6)}),
                              taxonomy_version=2, t6_tag_id=1, source_updated_at=CHECKED_AT.replace(tzinfo=None))

    def execute(self, sql, params=()):
        self.current_one, self.current_many = None, []
        if "GET_LOCK" in sql:
            self.current_one = {"acquired": 1}
        elif "FROM godp_planning_batch" in sql:
            self.current_one = {"id": 999} if self.result_batch else None
        elif "FROM godp_strategy_config" in sql:
            self.current_one = deepcopy(self.config)
        elif "FROM godp_ai_preparation_account" in sql:
            if "account_id=%s" in sql:
                self.current_one = next((p for p in self.accounts if p["account_id"] == params[1]), None)
            else:
                self.current_many = self.accounts
        elif "FROM godp_ai_preparation_topic" in sql:
            self.current_many = self.frozen_topics
        elif "FROM godp_ai_preparation " in sql:
            if self.row and ("reservation_key=%s" not in sql or self.row["reservation_key"] == params[0]):
                self.current_one = self.row
        elif sql.startswith("INSERT INTO godp_ai_preparation_account"):
            keys = ("preparation_id", "account_id", "config_version", "source_updated_at", "profile_hash",
                    "snapshot_json", "profile_json", "create_by", "update_by")
            self.accounts.append({**dict(zip(keys, params)), "id": len(self.accounts) + 1,
                                  "status": "pending", "vector_json": None, "vector_model": None,
                                  "last_error": "", "completed_at": None})
        elif sql.startswith("INSERT INTO godp_ai_preparation_topic"):
            if self.fail_topic_write:
                raise RuntimeError("simulated write failure")
            self.frozen_topics.append({"id": len(self.frozen_topics) + 1, "snapshot_json": params[2]})
        elif sql.startswith("INSERT INTO godp_ai_preparation "):
            keys = ("preparation_code", "reservation_key", "cycle_start", "cycle_end", "selection_json",
                    "config_version", "config_json", "account_snapshot_json", "slot_blueprint_json",
                    "account_count", "slot_count", "create_by", "update_by")
            self.row = {**dict(zip(keys, params)), "id": 123, "status": "waiting_inputs", "version": 1,
                        "topic_count": 0, "input_hash": None, "frozen_at": None,
                        "attempt_count": 0, "last_report_json": None}
            self.cursor.lastrowid = 123
        elif sql.startswith("UPDATE godp_ai_preparation_account"):
            account = next(p for p in self.accounts if p["id"] == params[-1])
            account.update(status=params[0], vector_json=params[1], vector_model=params[2], last_error=params[3])
        elif sql.startswith("UPDATE godp_ai_preparation "):
            self.row["version"] += 1
            if "status='cancelled'" in sql or "status='expired'" in sql:
                self.row.update(status="cancelled" if "cancelled" in sql else "expired", reservation_key=None)
            else:
                self.row.update(status=params[0], last_report_json=params[1], topic_count=params[2],
                                input_hash=params[3], frozen_at=params[4])
                self.row["attempt_count"] += 1

    def ready_accounts(self):
        for profile in self.accounts:
            profile.update(status="ready", vector_json="[0.6,0.8]", vector_model="shared-v1")


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(service, "connection", return_value=self.store.db))
        self.stack.enter_context(patch.object(api, "connection", return_value=self.store.db))
        self.stack.enter_context(patch.object(service, "today", return_value=CHECKED_AT.date()))
        self.stack.enter_context(patch.object(api, "today", return_value=CHECKED_AT.date()))
        self.stack.enter_context(patch.object(service, "current_next_monday", return_value=START))
        self.stack.enter_context(patch.object(service, "datetime")).now.return_value = CHECKED_AT
        self.load_accounts = self.stack.enter_context(patch.object(service, "load_accounts",
                                      side_effect=lambda *args: deepcopy(self.store.snapshots)))
        self.load_topics = self.stack.enter_context(patch.object(service, "load_matching_topics",
                                      side_effect=lambda *args: deepcopy(self.store.topics)))

    def create(self):
        return service.create_preparation(START)

    def assert_no_operations_writes(self):
        for call in self.store.cursor.execute.call_args_list:
            sql = call.args[0]
            if sql.startswith(("INSERT", "UPDATE", "DELETE")):
                self.assertNotIn("godp_planning_batch", sql)
                self.assertNotIn("godp_planning_item", sql)
                self.assertNotIn("godp_slot_state", sql)
                self.assertNotIn("godp_integration_outbox", sql)

    def test_create_replay_preserves_initial_config_and_accounts(self):
        first = self.create()
        initial = deepcopy(self.store.row)
        self.store.config["version"] += 1
        self.store.snapshots[0]["persona"] = "new source persona"
        replay = self.create()
        self.assertTrue(replay["reused"])
        self.assertEqual(replay["preparation_id"], first["preparation_id"])
        self.assertEqual(self.store.row, initial)
        self.load_accounts.assert_called_once()
        self.assertFalse(first["matching_executed"])
        self.assertIsNone(first["production_batch_id"])
        self.assert_no_operations_writes()

    def test_dates_match_frozen_weekdays_for_every_account(self):
        self.create()
        config = json.loads(self.store.row["config_json"])
        positions = json.loads(self.store.row["slot_blueprint_json"])
        self.assertEqual(len(positions), len(self.store.accounts) * len(config["planning_days"]))
        for position in positions:
            actual = date.fromisoformat(position["publish_date"])
            self.assertEqual(actual.isoweekday(), position["weekday"])
            self.assertTrue(START <= actual <= START + timedelta(days=6))

    def test_different_account_selection_and_existing_result_are_conflicts(self):
        self.create()
        with self.assertRaises(HTTPException) as caught:
            service.create_preparation(START, [self.store.snapshots[0]["account_id"]])
        self.assertEqual(caught.exception.status_code, 409)
        self.store.row = None
        self.store.result_batch = True
        with self.assertRaises(HTTPException) as caught:
            self.create()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIsNone(self.store.row)

    def test_invalid_or_unavailable_selection_does_not_create_partial_record(self):
        for ids in ([], ["DEMO-A"], ["A", "A"], ["UNKNOWN"]):
            with self.subTest(ids=ids), self.assertRaises(HTTPException):
                service.create_preparation(START, ids)
            self.assertIsNone(self.store.row)

    def test_pending_and_failed_vectors_stay_waiting_without_refreshing_sources(self):
        self.create()
        self.store.accounts[0]["status"] = "failed"
        first = service.advance_preparation(123, 1)
        self.assertEqual(first["status"], "waiting_inputs")
        self.assertEqual(first["last_report"]["accounts"]["counts"]["failed"], 1)
        self.store.snapshots[0]["persona"] = "new current persona"
        second = service.advance_preparation(123, first["version"])
        self.assertEqual(second["attempt_count"], 2)
        self.load_accounts.assert_called_once()
        self.assertEqual(self.store.frozen_topics, [])
        self.assert_no_operations_writes()

    def test_ready_inputs_freeze_once_and_keep_original_topic_after_source_edit(self):
        self.create()
        self.store.ready_accounts()
        result = service.advance_preparation(123, 1)
        self.assertEqual(result["status"], "inputs_frozen")
        original = service.read_inputs(123, 0, 1)
        self.assertEqual(original["inputs"]["topics"][0]["tag_ids"]["T1"], "T1-ID")
        self.store.topics[0]["payload_json"] = '{"title":"edited after freeze"}'
        replay = service.advance_preparation(123, result["version"])
        self.assertTrue(replay["reused"])
        self.assertEqual(replay["version"], result["version"])
        self.assertEqual(service.read_inputs(123, 0, 1)["inputs"], original["inputs"])
        self.load_topics.assert_called_once()
        self.assertEqual(len(self.store.frozen_topics), 1)
        self.assert_no_operations_writes()

    def test_mixed_spaces_and_changed_frozen_account_are_blocked(self):
        self.create()
        self.store.ready_accounts()
        self.store.accounts[0]["vector_model"] = "another-model"
        result = service.advance_preparation(123, 1)
        self.assertEqual(result["status"], "blocked")
        self.store.accounts[0]["vector_model"] = "shared-v1"
        altered = json.loads(self.store.accounts[0]["snapshot_json"])
        altered["persona"] = "replacement"
        self.store.accounts[0].update(snapshot_json=canonical_json(altered))
        self.store.accounts[0]["profile_json"], self.store.accounts[0]["profile_hash"] = profile_from_preparation(altered, 123, 3)
        result = service.advance_preparation(123, result["version"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(self.store.frozen_topics, [])

    def test_missing_stable_ids_cannot_enter_frozen_input(self):
        self.create()
        self.store.ready_accounts()
        self.store.topics[0]["tag_ids_json"] = '{}'
        result = service.advance_preparation(123, 1)
        self.assertEqual(result["status"], "waiting_inputs")
        self.assertIn("no_stable_tag_topics", {r["code"] for r in result["last_report"]["blocking_reasons"]})
        self.assertIsNone(result["input_hash"])

    def test_stale_version_does_not_advance_or_cancel_and_cancel_releases_cycle(self):
        self.create()
        for handler in (service.advance_preparation, service.cancel_preparation):
            with self.assertRaises(HTTPException) as caught:
                handler(123, 99)
            self.assertEqual(caught.exception.status_code, 409)
        cancelled = service.cancel_preparation(123, 1)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(self.store.row["reservation_key"])
        replay = service.cancel_preparation(123, cancelled["version"])
        self.assertEqual(replay["version"], cancelled["version"])
        self.assert_no_operations_writes()

    def test_expired_record_releases_reservation_and_does_not_freeze(self):
        self.create()
        with patch.object(service, "today", return_value=START + timedelta(days=7)):
            result = service.advance_preparation(123, 1)
        self.assertEqual(result["status"], "expired")
        self.assertIsNone(self.store.row["reservation_key"])
        self.assertEqual(self.store.frozen_topics, [])

    def test_partial_freeze_write_failure_rolls_back_without_committing_state(self):
        self.create()
        self.store.ready_accounts()
        self.store.fail_topic_write = True
        self.store.db.commit.reset_mock()
        with self.assertRaises(RuntimeError):
            service.advance_preparation(123, 1)
        self.store.db.commit.assert_not_called()
        self.store.db.rollback.assert_called()
        self.assertEqual(self.store.row["status"], "waiting_inputs")

    def test_frozen_input_corruption_is_rejected(self):
        self.create()
        self.store.ready_accounts()
        service.advance_preparation(123, 1)
        topic = json.loads(self.store.frozen_topics[0]["snapshot_json"])
        topic["vector"] = [0, 1]
        self.store.frozen_topics[0]["snapshot_json"] = canonical_json(topic)
        with self.assertRaises(HTTPException) as caught:
            service.read_inputs(123, 0, 100)
        self.assertEqual(caught.exception.status_code, 409)

    def test_input_pagination_keeps_same_full_snapshot_hash(self):
        self.create()
        self.store.ready_accounts()
        second = deepcopy(self.store.topics[0])
        second["topic_id"] = "TOPIC-002"
        self.store.topics.append(second)
        result = service.advance_preparation(123, 1)
        first_page = service.read_inputs(123, 0, 1)
        second_page = service.read_inputs(123, first_page["next_after_id"], 1)
        self.assertTrue(first_page["has_more"])
        self.assertFalse(second_page["has_more"])
        self.assertEqual(first_page["input_hash"], result["input_hash"])
        self.assertEqual(second_page["input_hash"], result["input_hash"])
        self.assertEqual(first_page["inputs"]["topics"][0]["topic_id"], "TOPIC-001")
        self.assertEqual(second_page["inputs"]["topics"][0]["topic_id"], "TOPIC-002")

    def test_vector_callback_retries_failure_but_never_overwrites_ready_or_cancelled(self):
        self.create()
        profile = self.store.accounts[0]
        account = profile["account_id"]
        fingerprint = profile["profile_hash"]
        api.save_preparation_account_vector(123, account, AccountVectorResult(profile_hash=fingerprint,
                                            status="failed", error="temporary failure"))
        result = AccountVectorResult(profile_hash=fingerprint, vector=[3, 4], vector_model="shared-v1")
        api.save_preparation_account_vector(123, account, result)
        self.assertEqual(profile["status"], "ready")
        api.save_preparation_account_vector(123, account, result)
        with self.assertRaises(HTTPException):
            api.save_preparation_account_vector(123, account, AccountVectorResult(profile_hash=fingerprint,
                                                vector=[1, 0], vector_model="shared-v1"))
        service.cancel_preparation(123, 1)
        with self.assertRaises(HTTPException):
            api.save_preparation_account_vector(123, account, result)

    def test_preparation_hash_cannot_be_confused_with_result_batch_hash(self):
        snapshot = self.store.snapshots[0]
        ordinary_profile, ordinary_hash = profile_from_snapshot(snapshot, 123, 3)
        prep_profile, prep_hash = profile_from_preparation(snapshot, 123, 3)
        self.assertEqual(ordinary_profile, prep_profile)
        self.assertNotEqual(ordinary_hash, prep_hash)
        self.assertNotEqual(prep_hash, profile_from_preparation(snapshot, 124, 3)[1])

    def test_all_new_tables_and_columns_have_chinese_comments(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        definitions, descriptions = column_definitions(schema), table_descriptions(schema)
        for table in ("godp_ai_preparation", "godp_ai_preparation_account", "godp_ai_preparation_topic"):
            self.assertIn(table, descriptions)
            self.assertTrue(definitions[table])
            self.assertTrue({"id", "create_time", "create_by", "update_time", "update_by", "del_flag"}
                            <= definitions[table].keys())


class PreparationWorkerTests(unittest.TestCase):
    def test_identity_separates_cache_and_routes_callback_to_preparation(self):
        cfg = worker.WorkerConfig("http://backend", "internal", 10, 5, 60)
        job = {"preparation_id": 123, "account_id": "ACCOUNT-001", "profile_hash": "a" * 64,
               "config_version": 3, "profile": {"account": {}}}
        cache = {}
        response = {"vector_model": "shared-v1", "vector": [3, 4]}
        with patch.object(worker, "json_request", side_effect=[response, WorkerError("temporary callback failure")]) as request:
            self.assertFalse(worker.process_job(job, cfg, cache))
            self.assertTrue(request.call_args_list[0].args[0].endswith("/api/internal/embedding-model"))
            self.assertEqual(request.call_args_list[0].kwargs["body"]["preparation_id"], 123)
            self.assertNotIn("batch_id", request.call_args_list[0].kwargs["body"])
        acknowledgment = {"preparation_id": 123, "account_id": "ACCOUNT-001", "profile_hash": "a" * 64, "status": "ready"}
        with patch.object(worker, "json_request", return_value=acknowledgment) as request:
            self.assertTrue(worker.process_job(job, cfg, cache))
            request.assert_called_once()
            self.assertIn("/preparation-account-vectors/123/", request.call_args.args[0])
        batch_job = {**job, "batch_id": 123}
        batch_job.pop("preparation_id")
        self.assertNotEqual(worker.job_key(job), worker.job_key(batch_job))

    def test_default_worker_visits_both_queues_even_when_one_fails(self):
        cfg = worker.WorkerConfig("http://backend", "internal", 10, 5, 60)
        with patch.object(worker, "json_request", side_effect=[WorkerError("unavailable"),
                                                             {"jobs": [], "next_after_id": 0}]) as request:
            self.assertEqual(worker.run(cfg, True), 1)
            self.assertEqual(request.call_count, 2)
            self.assertIn("/preparation-account-vector-jobs", request.call_args_list[0].args[0])
            self.assertIn("/account-vector-jobs", request.call_args_list[1].args[0])

    def test_preparation_poll_continues_after_record_failure(self):
        from app import ai_preparation_worker as advance_worker
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.side_effect = [[{"id": 1, "version": 2}, {"id": 2, "version": 3}], []]
        db = MagicMock()
        db.__enter__.return_value = db
        db.cursor.return_value = cursor
        with patch.object(advance_worker, "connection", return_value=db), \
                patch.object(advance_worker, "advance_preparation", side_effect=[RuntimeError("failure"),
                             {"status": "inputs_frozen", "version": 4}]) as advance:
            self.assertEqual(advance_worker.run_once(), 1)
            self.assertEqual(advance.call_args_list[1].args, (2, 3))


class PreparationAuthorizationTests(unittest.TestCase):
    def test_every_new_http_endpoint_requires_integration_token_before_database_access(self):
        from app.main import app

        async def request(method, path, body):
            messages = []
            async def receive():
                return {"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}
            async def send(message):
                messages.append(message)
            await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                       "scheme": "http", "method": method, "path": path, "raw_path": path.encode(),
                       "query_string": b"", "root_path": "", "headers": [(b"content-type", b"application/json")],
                       "server": ("test", 80), "client": ("test", 1234)}, receive, send)
            return next(message["status"] for message in messages if message["type"] == "http.response.start")

        endpoints = [("POST", "/api/internal/ai-preparations", {}),
                     ("GET", "/api/internal/ai-preparations", {}),
                     ("GET", "/api/internal/ai-preparations/1", {}),
                     ("GET", "/api/internal/ai-preparations/1/inputs", {}),
                     ("POST", "/api/internal/ai-preparations/1/advance", {"expected_version": 1}),
                     ("POST", "/api/internal/ai-preparations/1/cancel", {"expected_version": 1}),
                     ("GET", "/api/internal/preparation-account-vector-jobs", {}),
                     ("PUT", "/api/internal/preparation-account-vectors/1/ACCOUNT-001",
                      {"profile_hash": "a" * 64, "vector": [1, 0], "vector_model": "test"})]
        from app.system_config import override_config
        with override_config({"INTEGRATION_TOKEN": "test-only-internal-token"}), \
                patch.object(api, "connection") as api_db, patch.object(service, "connection") as service_db:
            for method, path, body in endpoints:
                with self.subTest(path=path):
                    self.assertEqual(asyncio.run(request(method, path, body)), 401)
            api_db.assert_not_called()
            service_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
