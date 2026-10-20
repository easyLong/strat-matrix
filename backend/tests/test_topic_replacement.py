"""Check replacement rules without changing live planning data."""

from contextlib import contextmanager
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import main as api
from app.models import ReplaceTopicInput


def slot_row(**changes):
    return {
        "id": 17,
        "account_id": "ACCOUNT-001",
        "topic_id": "TOPIC-001",
        "topic_type": "普通",
        "slot_type": "regular",
        "slot_id": "SLOT-001",
        "slot_topic_id": "TOPIC-001",
        "version": 1,
        "plan_type": "auto",
        "status": "已规划",
        "production_status": "planned",
        "published_at": None,
        "content_role": "流量",
        **changes,
    }


@contextmanager
def database_row(row):
    with patch.object(api, "connection") as connect:
        db = connect.return_value.__enter__.return_value
        cursor = db.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = row
        yield db, cursor


class TopicReplacementTests(unittest.TestCase):
    def test_waiting_topics_remain_replaceable_for_both_planning_types(self):
        for plan_type in ("auto", "manual"):
            with self.subTest(plan_type=plan_type):
                self.assertEqual(api.replacement_block_reason(slot_row(), plan_type), "")

    def test_production_in_progress_blocks_both_planning_types(self):
        for plan_type in ("auto", "manual"):
            with self.subTest(plan_type=plan_type):
                reason = api.replacement_block_reason(slot_row(production_status="ready"), plan_type)
                self.assertEqual(reason, "内容生产中，选题不可替换")

    def test_historical_in_progress_records_are_also_blocked(self):
        for label in ("生成中", "生产中"):
            with self.subTest(label=label):
                row = slot_row(production_status=None, status=label)
                self.assertEqual(api.replacement_block_reason(row, "auto"), "内容生产中，选题不可替换")

    def test_empty_hotspot_and_published_content_keep_existing_restrictions(self):
        empty = slot_row(topic_id="", slot_topic_id="", slot_type="hotspot")
        self.assertTrue(api.replacement_block_reason(empty, "auto"))
        self.assertIn("已发布", api.replacement_block_reason(slot_row(production_status="published"), "auto"))

    def test_existing_replacement_rules_after_production_are_preserved(self):
        for state in ("generated", "failed"):
            with self.subTest(state=state):
                self.assertEqual(api.replacement_block_reason(slot_row(production_status=state), "auto"), "")

    def test_read_response_marks_running_slot_as_not_replaceable(self):
        item = api.enrich_plan_item(slot_row(production_status="ready"), "auto")
        self.assertFalse(item["allow_replace"])
        self.assertEqual(item["replace_block_reason"], "内容生产中，选题不可替换")
        self.assertEqual(item["production_status"], "ready")

    def test_candidate_endpoint_rejects_running_slot_before_loading_topics(self):
        with database_row(slot_row(production_status="ready")) as (db, cursor), \
                patch.object(api, "available_replacement_topics") as candidates:
            with self.assertRaises(HTTPException) as raised:
                api.list_replacement_candidates(17)
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("生产中", raised.exception.detail)
            candidates.assert_not_called()
            db.commit.assert_not_called()
            cursor.execute.assert_called_once()

    def test_replace_endpoint_rejects_running_slot_without_writes(self):
        with database_row(slot_row(production_status="ready")) as (db, cursor), \
                patch.object(api, "available_replacement_topics") as candidates:
            with self.assertRaises(HTTPException) as raised:
                api.replace_topic(17, ReplaceTopicInput(new_topic_id="TOPIC-002", expected_version=1))
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("生产中", raised.exception.detail)
            candidates.assert_not_called()
            db.commit.assert_not_called()
            cursor.execute.assert_called_once()
            self.assertIn("FOR UPDATE", cursor.execute.call_args.args[0])

    def test_submit_rechecks_production_after_candidates_were_loaded(self):
        row = slot_row()
        with database_row(row) as (db, cursor), \
                patch.object(api, "available_replacement_topics", return_value=[]) as candidates, \
                patch.object(api, "attach_topic_labels"):
            self.assertEqual(api.list_replacement_candidates(17), [])
            row["production_status"] = "ready"
            with self.assertRaises(HTTPException) as raised:
                api.replace_topic(17, ReplaceTopicInput(new_topic_id="TOPIC-002", expected_version=1))
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("生产中", raised.exception.detail)
            candidates.assert_called_once()
            db.commit.assert_not_called()
            self.assertEqual(cursor.execute.call_count, 2)
            self.assertIn("FOR UPDATE", cursor.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
