"""Supplemental facts and v1/v2 compatibility without business data writes."""

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import matching_policy as policies
from app import matching_supplemental as supplemental
from app import matching_tasks as tasks
from app.account_profile import canonical_json
from app.integration import source_record_json
from app.integration_models import HistoryFact
from app.init_db import column_definitions
from app.matching_contracts import (ClaimTask, MatchingInputOptions, MatchingTaskCreate,
                                   PolicyConfirmation)
import test_matching_execution as execution_fixtures
from test_matching_execution import policy_payload
from app.ai_preparation import frozen_input, input_digest
from test_matching_readiness import CHECKED_AT


def v2_policy_payload():
    result = policy_payload()
    result.document.schema_version = 2
    result.document.required_inputs += ["fallback_topics", "history", "official_usage"]
    result.document.input_options = MatchingInputOptions(history_window_days=30,
        history_completeness="allow_unknown", history_unknown_references="allow_unknown",
        official_usage_unknown="allow_unknown", fallback_unknown_heat="block")
    return result


class SupplementalTaskTests(unittest.TestCase):
    def setUp(self):
        execution_fixtures.MatchingExecutionTests.setUp(self)
        self.snapshot = None
        self.fail_snapshot_write = False
        first = deepcopy(self.store.topics[0])
        first["title"] = json.loads(first["payload_json"])["title"]
        source = json.loads(first["payload_json"])
        source["topic_heat"] = 0
        first["payload_json"] = canonical_json(source)
        # Build a consistent fixture: source heat is present in both the
        # current source and the preparation frozen before creating a task.
        self.store.topics[0]["payload_json"] = first["payload_json"]
        frozen = json.loads(self.store.frozen_topics[0]["snapshot_json"])
        frozen["source_payload"] = source
        self.store.frozen_topics[0]["snapshot_json"] = canonical_json(frozen)
        self.store.row["input_hash"] = input_digest(frozen_input(self.store.row, self.store.accounts, [frozen]))
        second = deepcopy(first)
        second.update(topic_id="FALLBACK-ONLY", label_status="处理中", tags_json=None, tag_ids_json=None,
                      tag_version=None, taxonomy_version=None, t6_tag_id=None)
        second_source = json.loads(second["payload_json"])
        second_source.update(title="尚未生成向量的普通选题", topic_heat=100)
        second["title"] = second_source["title"]
        second["payload_json"] = canonical_json(second_source)
        self.fallback_rows = [first, second]
        self.history_rows = [{"content_id": "CONTENT-001", "account_id": "ACCOUNT-001", "topic_id": "TOPIC-001",
                              "published_at": (CHECKED_AT - timedelta(days=2)).replace(tzinfo=None),
                              "source_updated_at": CHECKED_AT.replace(tzinfo=None),
                              "payload_json": '{"topic_type":"普通"}'},
                             {"content_id": "CONTENT-002", "account_id": "ACCOUNT-002", "topic_id": "",
                              "published_at": (CHECKED_AT - timedelta(days=10)).replace(tzinfo=None),
                              "source_updated_at": CHECKED_AT.replace(tzinfo=None), "payload_json": '{}'}]
        self.usage_rows = [{"topic_id": "TOPIC-001", "official_use_count": 0,
                            "source_revision": 5, "source_name": "fixture-counter"}]
        self.base_execute = self.store.execute
        self.store.cursor.execute.side_effect = self.execute

    evaluation = execution_fixtures.MatchingExecutionTests.evaluation
    assert_no_operations_writes = execution_fixtures.MatchingExecutionTests.assert_no_operations_writes

    def execute(self, sql, params=()):
        self.store.current_one, self.store.current_many = None, []
        if "FROM godp_topic_source s" in sql:
            now = params[0]
            ids = set(params[2:-1]) if "s.topic_id IN" in sql else None
            self.store.current_many = deepcopy([row for row in self.fallback_rows
                if (ids is None or row["topic_id"] in ids) and not row["topic_id"].startswith("DEMO-")
                and (row["valid_from"] is None or row["valid_from"] <= now)
                and (row["valid_to"] is None or row["valid_to"] >= now)])
        elif "FROM godp_content_history" in sql:
            ids, start, end = set(params[:-3]), params[-3], params[-2]
            self.store.current_many = deepcopy([row for row in self.history_rows
                if row["account_id"] in ids and start <= row["published_at"] <= end])
        elif "FROM godp_topic_official_usage" in sql:
            self.store.current_many = deepcopy([row for row in self.usage_rows if row["topic_id"] in params])
        elif sql.startswith("INSERT INTO godp_matching_input_snapshot"):
            if self.fail_snapshot_write:
                raise RuntimeError("simulated snapshot write failure")
            self.snapshot = dict(zip(("task_id", "as_of", "snapshot_json", "snapshot_hash", "counts_json"), params))
            self.store.cursor.lastrowid = 2001
        elif "FROM godp_matching_input_snapshot" in sql:
            self.store.current_one = self.snapshot
        else:
            self.base_execute(sql, params)
            if sql.startswith("INSERT INTO godp_matching_task"):
                self.store.task.update(contract_version=params[6], supplemental_hash=params[7])
            if "FROM godp_matching_task WHERE id=%s" in sql and self.store.task["id"] != params[0]:
                self.store.current_one = None

    def approve(self, payload=None):
        policy = policies.create_policy(payload or v2_policy_payload())
        return policies.confirm_policy(policy["policy_id"], PolicyConfirmation(
            expected_hash=policy["document_hash"], confirmed_by="fixture-reviewer"))

    def enqueue(self, payload=None):
        if not self.store.policies:
            self.approve(payload)
        return tasks.create_task(MatchingTaskCreate(preparation_id=123, expected_preparation_version=2, policy_id=1))

    def claim(self):
        self.enqueue()
        return tasks.claim_task(ClaimTask())["job"]

    def test_freezes_base_fallback_pool_and_distinguishes_known_zero_from_unknown_count(self):
        result = self.enqueue()
        self.assertEqual(result["contract_version"], 2)
        self.assertEqual(self.snapshot["task_id"], result["task_id"])
        frozen = tasks.read_task_inputs(result["task_id"])["inputs"]["supplemental"]
        self.assertEqual({row["topic_id"] for row in frozen["fallback_topics"]}, {"TOPIC-001", "FALLBACK-ONLY"})
        usage = {row["topic_id"]: row for row in frozen["official_usage"]["records"]}
        self.assertTrue(usage["TOPIC-001"]["known"])
        self.assertEqual(usage["TOPIC-001"]["official_use_count"], 0)
        self.assertFalse(usage["FALLBACK-ONLY"]["known"])
        self.assertIsNone(usage["FALLBACK-ONLY"]["official_use_count"])
        self.assertEqual(usage["TOPIC-001"]["source_revision"], 5)
        self.assert_no_operations_writes()

    def test_history_scope_is_frozen_and_untyped_topic_references_remain_unknown(self):
        extra = deepcopy(self.history_rows[0])
        extra.update(content_id="FUTURE", published_at=(CHECKED_AT + timedelta(seconds=1)).replace(tzinfo=None))
        old = deepcopy(extra)
        old.update(content_id="OLD", published_at=(CHECKED_AT - timedelta(days=31)).replace(tzinfo=None))
        foreign = deepcopy(self.history_rows[0])
        foreign.update(content_id="OTHER", account_id="OTHER-ACCOUNT")
        self.history_rows += [extra, old, foreign]
        self.enqueue()
        history = tasks.read_task_inputs(1001)["inputs"]["supplemental"]["history"]
        self.assertEqual(history["coverage"], "unknown")
        self.assertEqual(len(history["observed_records"]), 2)
        first, second = history["observed_records"]
        self.assertTrue(first["reference_known"])
        self.assertIsNone(second["topic_id"])
        self.assertIsNone(second["topic_type"])
        self.assertFalse(second["reference_known"])

    def test_no_observed_history_does_not_prove_complete_empty_history(self):
        self.history_rows = []
        self.enqueue()
        history = tasks.read_task_inputs(1001)["inputs"]["supplemental"]["history"]
        self.assertEqual(history["observed_records"], [])
        self.assertEqual(history["coverage"], "unknown")
        self.assertTrue(all(row["coverage"] == "unknown" for row in history["accounts"]))

    def test_block_unknown_settings_stop_creation_without_committing_task(self):
        for field, value, code in (("history_completeness", "require_complete", "history_coverage_unknown"),
                                  ("history_unknown_references", "block", "history_topic_reference_unknown"),
                                  ("official_usage_unknown", "block", "official_usage_unknown")):
            with self.subTest(field=field):
                self.store.policies = []
                payload = v2_policy_payload()
                setattr(payload.document.input_options, field, value)
                self.approve(payload)
                self.store.db.commit.reset_mock()
                with self.assertRaises(HTTPException) as caught:
                    self.enqueue()
                self.assertEqual(caught.exception.detail["code"], code)
                self.assertIsNone(self.store.task)
                self.assertIsNone(self.snapshot)
                self.store.db.commit.assert_not_called()

    def test_unknown_heat_is_not_converted_to_zero(self):
        source = json.loads(self.fallback_rows[1]["payload_json"])
        source.pop("topic_heat")
        self.fallback_rows[1]["payload_json"] = canonical_json(source)
        payload = v2_policy_payload()
        payload.document.input_options.fallback_unknown_heat = "allow_unknown"
        self.enqueue(payload)
        rows = tasks.read_task_inputs(1001)["inputs"]["supplemental"]["fallback_topics"]
        candidate = next(row for row in rows if row["topic_id"] == "FALLBACK-ONLY")
        self.assertFalse(candidate["heat_known"])
        self.assertIsNone(candidate["topic_heat"])

    def test_replay_keeps_original_snapshot_when_sources_change(self):
        result = self.enqueue()
        original = deepcopy(self.snapshot)
        self.usage_rows[0]["official_use_count"] = 8
        replay = self.enqueue()
        self.assertTrue(replay["reused"])
        self.assertEqual(replay["supplemental_hash"], result["supplemental_hash"])
        self.assertEqual(self.snapshot, original)
        # Historical audit remains available; execution rechecks current sources.
        self.assertEqual(tasks.read_task_inputs(1001)["inputs"]["supplemental"]["official_usage"]["records"][1]["official_use_count"], 0)
        response = tasks.claim_task(ClaimTask())
        self.assertIsNone(response["job"])
        self.assertEqual(response["invalidated_code"], "supplemental_inputs_stale")

    def test_new_topics_and_posts_after_cutoff_do_not_change_frozen_input(self):
        result = self.enqueue()
        new_topic = deepcopy(self.fallback_rows[1])
        new_topic["topic_id"] = "NEW-TOPIC"
        self.fallback_rows.append(new_topic)
        new_post = deepcopy(self.history_rows[0])
        new_post.update(content_id="AFTER-CUTOFF", published_at=(CHECKED_AT + timedelta(seconds=1)).replace(tzinfo=None))
        self.history_rows.append(new_post)
        job = tasks.claim_task(ClaimTask())["job"]
        self.assertEqual(job["input_hash"], result["input_hash"])
        self.assertNotIn("NEW-TOPIC", {row["topic_id"] for row in job["inputs"]["supplemental"]["fallback_topics"]})

    def test_fallback_history_and_counter_changes_reject_inflight_result(self):
        job = self.claim()
        result = self.evaluation(job)
        self.history_rows[0]["topic_id"] = "CORRECTED-TOPIC"
        with self.assertRaises(HTTPException) as caught:
            tasks.save_evaluation(1001, result)
        self.assertEqual(caught.exception.detail["code"], "supplemental_inputs_stale")
        self.assertEqual(self.store.task["status"], "invalidated")
        self.assertIsNone(self.store.task["result_json"])
        self.assert_no_operations_writes()

    def test_expired_fallback_invalidates_queued_task(self):
        self.enqueue()
        self.fallback_rows[1]["valid_to"] = (CHECKED_AT - timedelta(seconds=1)).replace(tzinfo=None)
        response = tasks.claim_task(ClaimTask())
        self.assertIsNone(response["job"])
        self.assertEqual(response["invalidated_code"], "supplemental_inputs_stale")

    def test_changed_counter_revision_is_not_silently_refreshed_on_retry(self):
        self.enqueue()
        self.usage_rows[0]["source_revision"] += 1
        response = tasks.claim_task(ClaimTask())
        self.assertIsNone(response["job"])
        self.assertEqual(response["invalidated_code"], "supplemental_inputs_stale")

    def test_fallback_candidate_without_vector_can_only_be_used_as_fallback(self):
        job = self.claim()
        result = self.evaluation(job)
        result.positions[0].topic_id = "FALLBACK-ONLY"
        with self.assertRaises(HTTPException) as caught:
            tasks.save_evaluation(1001, result)
        self.assertEqual(caught.exception.status_code, 422)
        result.positions[0].outcome = "fallback"
        result.positions[0].fit_score = None
        result.positions[0].reason = "fixture ordinary fallback"
        saved = tasks.save_evaluation(1001, result)
        self.assertEqual(saved["status"], "evaluated")
        self.assertFalse(saved["operations_result_committed"])

    def test_snapshot_body_hash_summary_and_missing_record_are_verified(self):
        self.enqueue()
        original = deepcopy(self.snapshot)
        for change in ("body", "hash", "summary", "missing"):
            self.snapshot = deepcopy(original)
            if change == "body":
                body = json.loads(self.snapshot["snapshot_json"])
                body["official_usage"]["records"][0]["official_use_count"] = 0
                self.snapshot["snapshot_json"] = canonical_json(body)
            elif change == "hash":
                self.snapshot["snapshot_hash"] = "f" * 64
            elif change == "summary":
                self.snapshot["counts_json"] = '{}'
            else:
                self.snapshot = None
            with self.subTest(change=change), self.assertRaises(HTTPException):
                tasks.read_task_inputs(1001)

    def test_failed_snapshot_insert_does_not_commit_partial_task(self):
        self.approve()
        self.fail_snapshot_write = True
        self.store.db.commit.reset_mock()
        with self.assertRaises(RuntimeError):
            self.enqueue()
        self.store.db.commit.assert_not_called()
        self.store.db.rollback.assert_called()
        self.assertIsNone(self.snapshot)

    def test_cancelled_preparation_retains_original_inputs_for_audit(self):
        self.enqueue()
        self.store.row.update(status="cancelled", version=3, reservation_key=None)
        audit = tasks.read_task_inputs(1001)
        self.assertFalse(audit["source_currentness_checked"])
        self.assertEqual(audit["preparation_version"], 2)
        self.assertIn("history", audit["inputs"]["supplemental"])

    def test_matching_engine_still_cannot_use_marketing_or_disabled_source_as_ordinary_fallback(self):
        source = json.loads(self.fallback_rows[1]["payload_json"])
        source["is_marketing"] = True
        self.fallback_rows[1]["payload_json"] = canonical_json(source)
        self.enqueue()
        rows = tasks.read_task_inputs(1001)["inputs"]["supplemental"]["fallback_topics"]
        self.assertEqual([row["topic_id"] for row in rows], ["TOPIC-001"])


class SupplementalCompatibilityTests(unittest.TestCase):
    def test_legacy_policy_fingerprint_is_not_changed_by_new_optional_fields(self):
        old = policy_payload().document.model_dump()
        old.pop("input_options")
        encoded = canonical_json(old)
        document = policies.intact_document({"document_json": encoded, "document_hash": policies.digest(encoded)})
        self.assertEqual(document.schema_version, 1)
        self.assertEqual(document.approval_errors(), [])
        row = {"id": 1, "policy_key": "ordinary-main", "version": 1, "status": "approved",
               "confirmed_by": None, "confirmed_at": None, "document_json": encoded,
               "document_hash": policies.digest(encoded)}
        response = policies.policy_summary(row, include_document=True)
        self.assertNotIn("input_options", response["document"])
        self.assertEqual(policies.digest(canonical_json(response["document"])), response["document_hash"])

    def test_legacy_task_hash_does_not_include_new_nullable_fields(self):
        preparation = {"id": 123, "version": 2, "input_hash": "a" * 64}
        policy = {"id": 1, "document_hash": "b" * 64}
        original = {"contract_version": 1, "evaluation_scope": "ordinary_only", "preparation_id": 123,
                    "preparation_version": 2, "preparation_input_hash": "a" * 64,
                    "policy_id": 1, "policy_hash": "b" * 64}
        self.assertEqual(tasks.execution_hash(preparation, policy), policies.digest(canonical_json(original)))

    def test_second_version_requires_explicit_unknown_handling_and_history_window(self):
        document = v2_policy_payload().document
        self.assertEqual(document.approval_errors(), [])
        document.input_options = None
        self.assertTrue(document.approval_errors())
        document = v2_policy_payload().document
        document.required_inputs.remove("history")
        self.assertTrue(document.approval_errors())

    def test_history_optional_type_preserves_old_incremental_retry_payload(self):
        old = {"content_id": "CONTENT-001", "account_id": "ACCOUNT-001", "topic_id": "TOPIC-001",
               "updated_at": CHECKED_AT.isoformat()}
        model = HistoryFact.model_validate(old)
        raw = json.loads(source_record_json(model, {"topic_type"}))
        self.assertNotIn("topic_type", raw)
        newer = HistoryFact.model_validate({**old, "topic_type": "营销"})
        self.assertEqual(json.loads(source_record_json(newer, {"topic_type"}))["topic_type"], "营销")

    def test_large_or_invalid_sources_are_rejected_instead_of_truncated(self):
        cursor = MagicMock()
        with patch.object(supplemental, "MAX_ROWS", 1):
            with self.assertRaises(supplemental.SupplementalInputError):
                supplemental.load_official_usage(cursor, ["A", "B"])
        cursor.fetchall.return_value = [{"topic_id": "A", "official_use_count": -1, "source_revision": 1, "source_name": "fixture"}]
        with self.assertRaises(supplemental.SupplementalInputError):
            supplemental.load_official_usage(cursor, ["A"])

    def test_new_table_and_migration_columns_have_chinese_comments(self):
        schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text(encoding="utf-8")
        columns = column_definitions(schema)
        self.assertIn("godp_matching_input_snapshot", columns)
        self.assertIn("contract_version", columns["godp_matching_task"])
        self.assertIn("supplemental_hash", columns["godp_matching_task"])


if __name__ == "__main__":
    unittest.main()
