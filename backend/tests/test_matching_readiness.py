"""Matching safety checks using frozen fixtures, without a database or model."""

from copy import deepcopy
from datetime import date, datetime, timezone
import json
import unittest
from unittest.mock import MagicMock, patch

from app.account_profile import canonical_json, profile_from_snapshot
from app.matching_readiness import evaluate_readiness
from app.models import StrategyConfig
from app.topic_profile import profile_from_source


CHECKED_AT = datetime(2026, 10, 12, 8, tzinfo=timezone.utc)


def fixture():
    config = StrategyConfig()
    snapshots = [{
        "account_id": account_id, "account_name": account_id, "persona": "本地生活分享",
        "source_payload": {"city": "杭州", "account_tags": ["生活"]},
        "source_updated_at": "2026-10-12T07:00:00+00:00", "marketing_eligible": False,
        "followers_count": 1000, "interaction_data": [], "interaction_source": "if01",
        "metrics_as_of": CHECKED_AT.isoformat(), "rolling_posts": 10,
        "valid_content_count": 0, "rolling_interaction_count": 0, "traffic_trend": "数据不足",
        "lifecycle_stage": "冷启验证期", "business_goal": {"traffic": 80, "conversion": 20},
    } for account_id in ("ACCOUNT-001", "ACCOUNT-002")]
    batch = {"batch_id": 123, "batch_code": "AUTO-RULE-20261012", "cycle_end": date(2026, 10, 18),
             "config_version": 3, "config_json": config.model_dump_json(),
             "account_count": 2, "batch_account_count": 2,
             "account_snapshot_json": canonical_json(snapshots)}
    profiles = []
    for snapshot in snapshots:
        profile_json, fingerprint = profile_from_snapshot(snapshot, 123, 3)
        profiles.append({"batch_id": 123, "account_id": snapshot["account_id"], "config_version": 3,
                         "profile_json": profile_json, "snapshot_json": canonical_json(snapshot),
                         "profile_hash": fingerprint, "status": "ready",
                         "vector_json": "[0.6,0.8]", "vector_model": "shared-v1"})
    source = json.dumps({"title": "杭州周末散步路线", "outline": "介绍散步路线", "applicable_cities": ["杭州"]},
                        ensure_ascii=False)
    tags = json.dumps({f"T{i}": f"标签{i}" for i in range(1, 7)}, ensure_ascii=False)
    profile_json, fingerprint = profile_from_source(source, tags)
    topic = {"topic_id": "TOPIC-001", "payload_json": source, "active_in_snapshot": True,
             "valid_from": None, "valid_to": None, "is_marketing": False, "topic_status": "可用",
             "label_status": "已完成", "tags_json": tags, "tag_version": 1, "profile_tag_version": 1,
             "content_hash": fingerprint, "profile_json": profile_json, "profile_status": "ready",
             "vector_json": "[1.0,0.0]", "vector_model": "shared-v1"}
    return batch, profiles, [topic]


def codes(report):
    return {reason["code"] for reason in report["blocking_reasons"]}


class MatchingReadinessTests(unittest.TestCase):
    def test_ready_inputs_do_not_execute_matching_or_expose_embeddings(self):
        batch, accounts, topics = fixture()
        report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
        self.assertTrue(report["inputs_ready"])
        self.assertFalse(report["matching_executed"])
        self.assertEqual(report["accounts"]["counts"]["ready"], 2)
        self.assertEqual(report["topics"]["compatible_ready"], 1)
        self.assertNotIn('"vector_json"', json.dumps(report))
        self.assertNotIn('"persona"', json.dumps(report))

    def test_profile_valid_on_its_own_cannot_replace_frozen_batch_account(self):
        batch, accounts, topics = fixture()
        replacement = json.loads(accounts[0]["snapshot_json"])
        replacement["persona"] = "已经更新的其他人设"
        accounts[0]["snapshot_json"] = canonical_json(replacement)
        accounts[0]["profile_json"], accounts[0]["profile_hash"] = profile_from_snapshot(replacement, 123, 3)
        report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
        self.assertFalse(report["inputs_ready"])
        self.assertEqual(report["accounts"]["counts"]["stale"], 1)

    def test_other_batch_profile_is_rejected_even_with_same_account_text(self):
        batch, accounts, topics = fixture()
        accounts[0]["batch_id"] = 456
        report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
        self.assertIn("account_inputs_not_ready", codes(report))

    def test_missing_pending_and_failed_accounts_block_matching(self):
        for status in ("missing", "pending", "failed"):
            with self.subTest(status=status):
                batch, accounts, topics = fixture()
                if status == "missing":
                    accounts.pop()
                else:
                    accounts[0]["status"] = status
                report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
                self.assertFalse(report["inputs_ready"])
                self.assertEqual(report["accounts"]["counts"][status], 1)

    def test_legacy_snapshot_cannot_be_reconstructed_from_current_profile(self):
        batch, accounts, topics = fixture()
        snapshots = json.loads(batch["account_snapshot_json"])
        del snapshots[0]["source_payload"]
        batch["account_snapshot_json"] = canonical_json(snapshots)
        report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
        self.assertEqual(report["accounts"]["counts"]["incomplete_snapshot"], 1)

    def test_source_edit_and_label_version_change_invalidate_topic(self):
        for change in ("content", "tag_version"):
            with self.subTest(change=change):
                batch, accounts, topics = fixture()
                if change == "content":
                    source = json.loads(topics[0]["payload_json"])
                    source["title"] = "另一个当前标题"
                    topics[0]["payload_json"] = json.dumps(source)
                else:
                    topics[0]["tag_version"] += 1
                report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
                self.assertEqual(report["topics"]["counts"]["stale"], 1)
                self.assertIn("no_ready_topics", codes(report))

    def test_model_and_dimension_mismatch_cannot_be_compared(self):
        for change in ("model", "dimension"):
            with self.subTest(change=change):
                batch, accounts, topics = fixture()
                if change == "model":
                    topics[0]["vector_model"] = "different-space"
                else:
                    topics[0]["vector_json"] = "[1,0,0]"
                report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
                self.assertIn("no_compatible_topics", codes(report))
                self.assertEqual(report["topics"]["compatible_ready"], 0)

    def test_mixed_account_spaces_block_whole_batch(self):
        batch, accounts, topics = fixture()
        accounts[1]["vector_model"] = "shared-v2"
        report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
        self.assertIn("mixed_account_vector_spaces", codes(report))
        self.assertIsNone(report["vector_space"])

    def test_compatible_topic_pool_excludes_other_models_and_unfinished_labels(self):
        batch, accounts, topics = fixture()
        incompatible, unfinished = deepcopy(topics[0]), deepcopy(topics[0])
        incompatible.update(topic_id="TOPIC-002", vector_model="shared-v2")
        unfinished.update(topic_id="TOPIC-003", label_status="处理中")
        report = evaluate_readiness(batch, accounts, topics + [incompatible, unfinished], CHECKED_AT)
        self.assertTrue(report["inputs_ready"])
        self.assertEqual(report["topics"]["compatible_ready"], 1)
        self.assertEqual(report["topics"]["incompatible_ready"], 1)

    def test_invalid_vectors_never_become_ready(self):
        for vector in ("[0,0]", "[true,0]", "[NaN,0]", "[3,4]", "not-json", "[1e309,0]"):
            with self.subTest(vector=vector):
                batch, accounts, topics = fixture()
                accounts[0]["vector_json"] = vector
                topics[0]["vector_json"] = vector
                report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
                self.assertFalse(report["inputs_ready"])
                self.assertEqual(report["accounts"]["counts"]["invalid_vector"], 1)
                self.assertEqual(report["topics"]["counts"]["invalid_vector"], 1)

    def test_batch_expiration_uses_beijing_day(self):
        batch, accounts, topics = fixture()
        beijing_next_day = datetime(2026, 10, 18, 18, tzinfo=timezone.utc)
        report = evaluate_readiness(batch, accounts, topics, beijing_next_day)
        self.assertIn("batch_expired", codes(report))

    def test_expired_disabled_marketing_and_demo_topics_are_excluded(self):
        changes = ({"valid_to": datetime(2026, 10, 12, 7)}, {"active_in_snapshot": False},
                   {"is_marketing": True}, {"topic_id": "DEMO-TOPIC"})
        for change in changes:
            with self.subTest(change=change):
                batch, accounts, topics = fixture()
                topics[0].update(change)
                report = evaluate_readiness(batch, accounts, topics, CHECKED_AT)
                self.assertFalse(report["inputs_ready"])
                self.assertEqual(report["topics"]["counts"]["unavailable"], 1)

    def test_corrupt_or_duplicate_snapshot_and_count_mismatch_block_batch(self):
        for change in ("invalid_json", "duplicate", "count", "config"):
            with self.subTest(change=change):
                batch, accounts, topics = fixture()
                if change == "invalid_json":
                    batch["account_snapshot_json"] = "not-json"
                elif change == "duplicate":
                    snapshots = json.loads(batch["account_snapshot_json"])
                    snapshots.append(snapshots[0])
                    batch["account_snapshot_json"] = canonical_json(snapshots)
                elif change == "count":
                    batch["account_count"] += 1
                else:
                    batch["config_json"] = "not-json"
                self.assertFalse(evaluate_readiness(batch, accounts, topics, CHECKED_AT)["inputs_ready"])


class ReadinessApiTests(unittest.TestCase):
    def test_missing_and_duplicate_batch_return_business_errors(self):
        from fastapi import HTTPException
        from app.matching_readiness_api import matching_readiness
        for rows, expected_status in (([], 404), ([{}, {}], 409)):
            with self.subTest(expected_status=expected_status):
                db, cursor = MagicMock(), MagicMock()
                db.cursor.return_value.__enter__.return_value = cursor
                cursor.fetchall.return_value = rows
                with patch("app.matching_readiness_api.connection") as connection:
                    connection.return_value.__enter__.return_value = db
                    with self.assertRaises(HTTPException) as error:
                        matching_readiness(123)
                self.assertEqual(error.exception.status_code, expected_status)
                db.commit.assert_not_called()

    def test_report_uses_supplied_database_snapshot_without_writing(self):
        from app.matching_readiness_api import matching_readiness
        batch, accounts, topics = fixture()
        db, cursor = MagicMock(), MagicMock()
        db.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchall.side_effect = ([batch], accounts, topics)
        with patch("app.matching_readiness_api.connection") as connection, \
                patch("app.matching_readiness_api.datetime") as clock:
            connection.return_value.__enter__.return_value = db
            clock.now.return_value = CHECKED_AT
            report = matching_readiness(123)
        self.assertTrue(report["inputs_ready"])
        db.commit.assert_not_called()
        for call in cursor.execute.call_args_list:
            self.assertNotRegex(call.args[0], r"\b(UPDATE|INSERT|DELETE|ALTER|CREATE)\b")


if __name__ == "__main__":
    unittest.main()
