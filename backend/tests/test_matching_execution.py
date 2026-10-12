"""Policy and leased proposal boundaries, with no live data or executor."""

import asyncio
from contextlib import ExitStack
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import ai_preparation as preparation
from app import matching_execution_api as api
from app import matching_policy as policies
from app import matching_tasks as tasks
from app.account_profile import canonical_json
from app.init_db import column_definitions, table_descriptions
from app.matching_contracts import (ALGORITHM_CODES, ClaimTask, LeaseHeartbeat, MatchingEvaluation,
                                   MatchingFailure, MatchingTaskCreate, PolicyConfirmation, PolicyCreate)
from test_ai_preparation import Store, START
from test_matching_readiness import CHECKED_AT


def policy_payload(version=0):
    return PolicyCreate.model_validate({"policy_key": "ordinary-main", "expected_latest_version": version,
        "document": {"implementation_key": "fixture-engine-v1",
                     "vector_space": {"vector_model": "shared-v1", "dimension": 2, "semantic_space_id": "fixture-space-v1"},
                     "required_inputs": ["accounts", "topics", "config", "positions"],
                     "decisions": {code: {"definition": "测试规则，不能用于实际算法", "acceptance_examples": ["固定测试样例"]}
                                   for code in sorted(ALGORITHM_CODES)}}})


class ExecutionStore(Store):
    def __init__(self):
        self.policies = []
        self.task = None
        self.attempts = []
        super().__init__()

    def execute(self, sql, params=()):
        if "godp_matching_" not in sql:
            return super().execute(sql, params)
        self.current_one, self.current_many = None, []
        if "FROM godp_matching_policy" in sql:
            if "policy_key=%s" in sql:
                matches = [p for p in self.policies if p["policy_key"] == params[0]]
                self.current_one = matches[-1] if matches else None
            else:
                self.current_one = next((p for p in self.policies if p["id"] == params[0]), None)
        elif sql.startswith("INSERT INTO godp_matching_policy"):
            row = dict(zip(("policy_key", "version", "document_json", "document_hash"), params))
            row.update(id=len(self.policies) + 1, status="draft", confirmed_by=None, confirmed_at=None)
            self.policies.append(row)
            self.cursor.lastrowid = row["id"]
        elif sql.startswith("UPDATE godp_matching_policy"):
            policy = next(p for p in self.policies if p["id"] == params[-1])
            if "status='approved'" in sql:
                policy.update(status="approved", confirmed_by=params[0], confirmed_at=CHECKED_AT.replace(tzinfo=None))
            else:
                policy["status"] = "disabled"
        elif "FROM godp_matching_attempt" in sql:
            self.current_many = self.attempts
        elif "FROM godp_matching_task" in sql:
            if "status='queued'" in sql:
                eligible = self.task and (self.task["status"] == "queued" or
                            self.task["status"] == "processing" and self.task["lease_expires_at"] <= params[1])
                if eligible and self.task["id"] > params[0]:
                    self.current_one = {"id": self.task["id"]}
            else:
                self.current_one = self.task
        elif sql.startswith("INSERT INTO godp_matching_task"):
            keys = ("preparation_id", "preparation_version", "preparation_input_hash", "policy_id", "policy_hash", "input_hash")
            self.task = {**dict(zip(keys, params)), "id": 1001, "status": "queued", "version": 1,
                         "attempt_count": 0, "lease_id": None, "lease_expires_at": None,
                         "error_code": "", "result_json": None, "result_hash": None, "completed_at": None}
            self.cursor.lastrowid = 1001
        elif sql.startswith("INSERT INTO godp_matching_attempt"):
            self.attempts.append({**dict(zip(("task_id", "attempt_number", "lease_id", "lease_expires_at"), params)),
                                  "status": "processing", "error_code": ""})
        elif sql.startswith("UPDATE godp_matching_attempt"):
            if sql.startswith("UPDATE godp_matching_attempt SET lease_expires_at"):
                row = next(p for p in self.attempts if p["lease_id"] == params[2])
                row["lease_expires_at"] = params[0]
            else:
                for row in self.attempts:
                    if row["lease_id"] == params[3] and row["status"] == "processing":
                        row.update(status=params[0], error_code=params[1])
        elif sql.startswith("UPDATE godp_matching_task"):
            if sql.startswith("UPDATE godp_matching_task SET lease_expires_at"):
                self.task["lease_expires_at"] = params[0]
                return
            self.task["version"] += 1
            if "status='processing'" in sql:
                self.task.update(status="processing", attempt_count=params[0], lease_id=params[1],
                                 lease_expires_at=params[2], error_code="")
            elif "status='evaluated'" in sql:
                self.task.update(status="evaluated", result_json=params[0], result_hash=params[1],
                                 completed_at=params[2], error_code="")
            elif "status='failed'" in sql:
                self.task.update(status="failed", error_code=params[0])
            elif "status='queued'" in sql:
                self.task.update(status="queued", lease_id=None, lease_expires_at=None, error_code="")
            elif "status='cancelled'" in sql:
                self.task.update(status="cancelled", lease_id=None, lease_expires_at=None, error_code="task_cancelled")
            elif "status='invalidated'" in sql:
                self.task.update(status="invalidated", lease_id=None, lease_expires_at=None, error_code=params[0])


class MatchingExecutionTests(unittest.TestCase):
    def setUp(self):
        self.store = ExecutionStore()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for module in (preparation, policies, tasks, api):
            self.stack.enter_context(patch.object(module, "connection", return_value=self.store.db))
        self.stack.enter_context(patch.object(preparation, "today", return_value=CHECKED_AT.date()))
        self.stack.enter_context(patch.object(preparation, "current_next_monday", return_value=START))
        self.stack.enter_context(patch.object(preparation, "datetime")).now.return_value = CHECKED_AT
        self.stack.enter_context(patch.object(tasks, "now_utc", return_value=CHECKED_AT))
        self.stack.enter_context(patch.object(preparation, "load_accounts", return_value=deepcopy(self.store.snapshots)))
        self.stack.enter_context(patch.object(preparation, "load_matching_topics", side_effect=lambda *a: deepcopy(self.store.topics)))
        self.stack.enter_context(patch.object(tasks, "load_matching_topics", side_effect=lambda *a: deepcopy(self.store.topics)))
        preparation.create_preparation(START)
        self.store.ready_accounts()
        preparation.advance_preparation(123, 1)

    def approve(self):
        result = policies.create_policy(policy_payload())
        confirmation = PolicyConfirmation(expected_hash=result["document_hash"], confirmed_by="test-reviewer")
        return policies.confirm_policy(result["policy_id"], confirmation)

    def enqueue(self):
        if not self.store.policies:
            self.approve()
        return tasks.create_task(MatchingTaskCreate(preparation_id=123, expected_preparation_version=2, policy_id=1))

    def claim(self):
        self.enqueue()
        return tasks.claim_task(ClaimTask())["job"]

    def evaluation(self, job):
        return MatchingEvaluation.model_validate({
            **{key: job[key] for key in ("lease_id", "input_hash", "policy_hash")},
            "implementation_key": "fixture-engine-v1",
            "stages": [{"stage": name, "summary": {"fixture": True}} for name in
                       ("hard_gate", "recall", "fit", "global_allocation", "composition")],
            "positions": [{"account_id": p["account_id"], "publish_date": p["publish_date"],
                           "outcome": "matched", "topic_id": "TOPIC-001", "content_role": "流量", "fit_score": 80.0}
                          for p in job["inputs"]["positions"]]})

    def assert_no_operations_writes(self):
        for call in self.store.cursor.execute.call_args_list:
            sql = call.args[0]
            if sql.startswith(("INSERT", "UPDATE", "DELETE")):
                for table in ("godp_planning_batch", "godp_planning_item", "godp_slot_state", "godp_integration_outbox"):
                    self.assertNotIn(table, sql)

    def test_draft_missing_rules_cannot_be_approved_or_enqueued(self):
        payload = policy_payload()
        payload.document.decisions = {}
        result = policies.create_policy(payload)
        self.assertEqual(result["status"], "draft")
        self.assertEqual(len(result["approval_errors"]), 9)
        with self.assertRaises(HTTPException):
            policies.confirm_policy(1, PolicyConfirmation(expected_hash=result["document_hash"], confirmed_by="reviewer"))
        with self.assertRaises(HTTPException):
            self.enqueue()
        self.assertIsNone(self.store.task)

    def test_policy_version_conflict_and_document_corruption_are_rejected(self):
        first = self.approve()
        with self.assertRaises(HTTPException):
            policies.create_policy(policy_payload())
        second = policies.create_policy(policy_payload(1))
        self.assertEqual(second["version"], 2)
        self.assertEqual(first["status"], self.store.policies[0]["status"])
        self.store.policies[0]["document_json"] = self.store.policies[0]["document_json"].replace("fixture-engine-v1", "different-engine")
        with self.assertRaises(HTTPException):
            policies.intact_document(self.store.policies[0])

    def test_undeclared_history_and_official_count_inputs_block_approval(self):
        payload = policy_payload()
        payload.document.required_inputs.append("official_usage")
        self.assertTrue(payload.document.approval_errors())
        payload.document.required_inputs[-1] = "history"
        self.assertTrue(payload.document.approval_errors())

    def test_repeated_creation_keeps_same_policy_and_does_not_start_again(self):
        first = self.enqueue()
        second = self.enqueue()
        self.assertEqual(first["task_id"], second["task_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(self.store.task["attempt_count"], 0)
        policy = policies.create_policy(policy_payload(1))
        with self.assertRaises(HTTPException):
            tasks.create_task(MatchingTaskCreate(preparation_id=123, expected_preparation_version=2, policy_id=policy["policy_id"]))
        self.assert_no_operations_writes()

    def test_current_content_edit_and_vector_space_mismatch_block_creation(self):
        self.approve()
        source = json.loads(self.store.topics[0]["payload_json"])
        source["topic_heat"] = 10
        self.store.topics[0]["payload_json"] = canonical_json(source)
        with self.assertRaises(HTTPException) as caught:
            self.enqueue()
        self.assertEqual(caught.exception.detail["code"], "topic_inputs_stale")
        self.assertIsNone(self.store.task)
        document = json.loads(self.store.policies[0]["document_json"])
        document["vector_space"]["dimension"] = 3
        self.store.policies[0]["document_json"] = canonical_json(document)
        self.store.policies[0]["document_hash"] = policies.digest(canonical_json(document))
        with self.assertRaises(HTTPException) as caught:
            self.enqueue()
        self.assertEqual(caught.exception.detail["code"], "policy_vector_space_mismatch")

    def test_active_lease_cannot_be_claimed_twice_and_expired_lease_is_replaced(self):
        first = self.claim()
        self.assertIsNone(tasks.claim_task(ClaimTask())["job"])
        self.store.task["lease_expires_at"] = (CHECKED_AT - timedelta(seconds=1)).replace(tzinfo=None)
        second = tasks.claim_task(ClaimTask())["job"]
        self.assertNotEqual(first["lease_id"], second["lease_id"])
        self.assertEqual(second["attempt_count"], 2)
        self.assertEqual(self.store.attempts[0]["status"], "expired")
        with self.assertRaises(HTTPException):
            tasks.save_evaluation(1001, self.evaluation(first))
        self.assertEqual(self.store.task["status"], "processing")

    def test_heartbeat_extends_only_the_current_live_lease(self):
        job = self.claim()
        payload = LeaseHeartbeat(**{key: job[key] for key in ("lease_id", "input_hash", "policy_hash")}, lease_seconds=600)
        tasks.heartbeat_task(1001, payload)
        self.assertEqual(self.store.task["lease_expires_at"], (CHECKED_AT + timedelta(seconds=600)).replace(tzinfo=None))
        self.assertEqual(self.store.attempts[0]["lease_expires_at"], self.store.task["lease_expires_at"])
        payload.lease_id = "b" * 32
        with self.assertRaises(HTTPException):
            tasks.heartbeat_task(1001, payload)

    def test_evaluation_is_idempotent_and_cannot_overwrite_saved_proposal(self):
        job = self.claim()
        payload = self.evaluation(job)
        result = tasks.save_evaluation(1001, payload)
        self.assertEqual(result["status"], "evaluated")
        self.assertFalse(result["operations_result_committed"])
        self.store.policies[0]["status"] = "disabled"
        self.assertTrue(tasks.save_evaluation(1001, payload)["reused"])
        changed = payload.model_copy(deep=True)
        changed.positions[0].fit_score = 90.0
        with self.assertRaises(HTTPException):
            tasks.save_evaluation(1001, changed)
        self.assertEqual(self.store.attempts[0]["status"], "evaluated")
        self.assert_no_operations_writes()

    def test_saved_proposal_corruption_is_not_returned_as_valid_result(self):
        job = self.claim()
        tasks.save_evaluation(1001, self.evaluation(job))
        original = tasks.read_evaluation(self.store.task)
        self.assertEqual(original["implementation_key"], "fixture-engine-v1")
        changed = deepcopy(original)
        changed["positions"][0]["fit_score"] = 15.0
        self.store.task["result_json"] = canonical_json(changed)
        with self.assertRaises(HTTPException):
            api.matching_task_result(1001)

    def test_wrong_callback_input_hash_cannot_invalidate_another_valid_lease(self):
        job = self.claim()
        result = self.evaluation(job)
        result.input_hash = "f" * 64
        with self.assertRaises(HTTPException):
            tasks.save_evaluation(1001, result)
        self.assertEqual(self.store.task["status"], "processing")
        self.assertEqual(self.store.task["lease_id"], job["lease_id"])

    def test_new_policy_version_does_not_change_existing_task_binding(self):
        job = self.claim()
        newer = policies.create_policy(policy_payload(1))
        policies.confirm_policy(newer["policy_id"], PolicyConfirmation(expected_hash=newer["document_hash"], confirmed_by="reviewer"))
        self.assertEqual(self.store.task["policy_id"], 1)
        saved = tasks.save_evaluation(1001, self.evaluation(job))
        self.assertEqual(saved["status"], "evaluated")
        self.assertEqual(saved["policy_id"], 1)

    def test_missing_duplicate_foreign_positions_and_foreign_topics_are_rejected(self):
        job = self.claim()
        original = self.evaluation(job)
        for change in ("missing", "duplicate", "account", "date", "topic", "engine"):
            payload = original.model_copy(deep=True)
            if change == "missing":
                payload.positions.pop()
            elif change == "duplicate":
                payload.positions[1] = payload.positions[0]
            elif change == "account":
                payload.positions[0].account_id = "OTHER"
            elif change == "date":
                payload.positions[0].publish_date += timedelta(days=1)
            elif change == "topic":
                payload.positions[0].topic_id = "OTHER-TOPIC"
            else:
                payload.implementation_key = "OTHER-ENGINE"
            with self.subTest(change=change), self.assertRaises(HTTPException):
                tasks.save_evaluation(1001, payload)
            self.assertEqual(self.store.task["status"], "processing")
            self.assertIsNone(self.store.task["result_hash"])

    def test_disabled_policy_cancelled_preparation_and_changed_topic_reject_inflight_result(self):
        for change in ("policy", "preparation", "topic"):
            with self.subTest(change=change):
                # Reset only the task fixture; preserve the immutable baseline.
                self.store.task, self.store.attempts = None, []
                self.store.policies = []
                self.store.row.update(status="inputs_frozen", version=2)
                original_topic = deepcopy(self.store.topics[0])
                job = self.claim()
                if change == "policy":
                    self.store.policies[0]["status"] = "disabled"
                elif change == "preparation":
                    self.store.row["status"] = "cancelled"
                else:
                    self.store.topics[0]["tag_version"] += 1
                with self.assertRaises(HTTPException):
                    tasks.save_evaluation(1001, self.evaluation(job))
                self.assertEqual(self.store.task["status"], "invalidated")
                self.assertIsNone(self.store.task["result_json"])
                self.store.topics[0] = original_topic

    def test_failure_retry_has_new_attempt_and_preserves_old_failure(self):
        first = self.claim()
        payload = MatchingFailure(**{key: first[key] for key in ("lease_id", "input_hash", "policy_hash")}, error_code="engine_unavailable")
        failed = tasks.fail_task(1001, payload)
        self.assertTrue(tasks.fail_task(1001, payload)["reused"])
        with self.assertRaises(HTTPException):
            tasks.retry_task(1001, failed["version"] - 1)
        tasks.retry_task(1001, failed["version"])
        second = tasks.claim_task(ClaimTask())["job"]
        self.assertEqual(self.store.attempts[0]["status"], "failed")
        self.assertEqual(second["attempt_count"], 2)
        with self.assertRaises(HTTPException):
            tasks.fail_task(1001, payload)
        tasks.save_evaluation(1001, self.evaluation(second))
        self.assertEqual(self.store.task["status"], "evaluated")

    def test_cancelling_task_keeps_preparation_and_prevents_callback(self):
        job = self.claim()
        cancelled = tasks.cancel_task(1001, job["version"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.store.row["status"], "inputs_frozen")
        with self.assertRaises(HTTPException):
            tasks.save_evaluation(1001, self.evaluation(job))
        self.assertIsNone(tasks.claim_task(ClaimTask())["job"])

    def test_queued_task_becomes_invalid_when_binding_changes(self):
        self.enqueue()
        self.store.row["version"] += 1
        response = tasks.claim_task(ClaimTask())
        self.assertIsNone(response["job"])
        self.assertEqual(response["invalidated_code"], "task_binding_changed")
        self.assertEqual(self.store.task["attempt_count"], 0)

    def test_contract_rejects_missing_trace_nonfinite_score_and_fallback_fake_score(self):
        result = self.evaluation(self.claim()).model_dump(mode="json")
        for change in ("trace", "nan", "fallback", "failed"):
            invalid = deepcopy(result)
            if change == "trace":
                invalid["stages"].pop()
            elif change == "nan":
                invalid["positions"][0]["fit_score"] = float("nan")
            else:
                invalid["positions"][0]["outcome"] = change
            with self.subTest(change=change), self.assertRaises(ValidationError):
                MatchingEvaluation.model_validate(invalid)

    def test_new_schema_has_chinese_comments_and_required_audit_fields(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        columns, descriptions = column_definitions(schema), table_descriptions(schema)
        for name in ("godp_matching_policy", "godp_matching_task", "godp_matching_attempt"):
            self.assertIn(name, descriptions)
            self.assertTrue({"id", "create_time", "create_by", "update_time", "update_by", "del_flag"} <= columns[name].keys())


class MatchingExecutionAuthorizationTests(unittest.TestCase):
    def test_new_policy_and_execution_routes_are_protected_before_db_access(self):
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
            return next(item["status"] for item in messages if item["type"] == "http.response.start")
        routes = api.router.routes
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {"INTEGRATION_TOKEN": "test-only-token"}))
            database = [stack.enter_context(patch.object(module, "connection")) for module in (api, tasks, policies)]
            for route in routes:
                path = route.path.replace("{policy_id}", "1").replace("{task_id}", "1")
                for method in route.methods:
                    with self.subTest(method=method, path=path):
                        self.assertEqual(asyncio.run(request(method, path, {})), 401)
            for mock in database:
                mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
