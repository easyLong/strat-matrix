"""Pure composition tests for atomic Planning result commit V1."""

from contextlib import ExitStack
from copy import deepcopy
from datetime import date
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import planning_result_commit as service
from app.hotspot_scheduler import ai_hotspot_fallback
from app.models import StrategyConfig
from app.planning_result_commit import ResultCommitError, build_final_plan


def account(account_id="A", marketing=True):
    snapshot = {"account_id": account_id, "account_name": f"账号{account_id}",
                "marketing_eligible": marketing, "lifecycle_stage": "冷启动期"}
    return {"account_id": account_id, "snapshot": snapshot,
            "profile": {"lifecycle_stage": "冷启动期"}}


def topic(topic_id, title):
    return {"topic_id": topic_id, "source_payload": {"title": title, "outline": f"{title}大纲",
                                                        "content_type": "图文"},
            "profile": {"content": {"title": title, "outline": f"{title}大纲",
                                      "content_type": "图文"}}}


def inputs(hotspot_ratio=0):
    config = StrategyConfig(hotspot_ratio=hotspot_ratio, planning_days=[1, 3]).model_dump(mode="json")
    return {
        "config": config,
        "config_version": 9,
        "cycle_start": "2026-10-26",
        "cycle_end": "2026-11-01",
        "accounts": [account()],
        "positions": [
            {"account_id": "A", "weekday": 1, "publish_date": "2026-10-26"},
            {"account_id": "A", "weekday": 3, "publish_date": "2026-10-28"},
        ],
        "topics": [topic("T1", "普通一"), topic("T2", "普通二")],
        "supplemental": {"fallback_topics": []},
    }


def evaluation():
    return {
        "stages": [
            {"stage": "hard_gate", "summary": {}},
            {"stage": "recall", "summary": {}},
            {"stage": "fit", "summary": {}},
            {"stage": "global_allocation", "summary": {}},
            {"stage": "composition", "summary": {
                "actual_traffic_positions": 1,
                "actual_conversion_positions": 1,
            }},
        ],
        "positions": [
            {"account_id": "A", "publish_date": "2026-10-26", "outcome": "matched",
             "topic_id": "T1", "content_role": "流量", "fit_score": 90.0, "reason": ""},
            {"account_id": "A", "publish_date": "2026-10-28", "outcome": "matched",
             "topic_id": "T2", "content_role": "转化", "fit_score": 80.0, "reason": ""},
        ],
    }


def marketing(valid=True):
    return [{"topic_id": "M1", "account_id": "A", "title": "营销一", "outline": "营销大纲",
             "content_type": "视频", "approved_at": "2026-10-20T00:00:00",
             "source_snapshot_at": "2026-10-20T00:00:00", "valid": valid}]


class PlanningResultCommitTests(unittest.TestCase):
    def test_marketing_overlay_only_consumes_conversion_role(self):
        plan = build_final_plan(inputs(), evaluation(), marketing(True))
        self.assertEqual(plan["marketing_priority_slots"], 1)
        self.assertEqual(plan["marketing_topics"], 1)
        by_date = {row["publish_date"]: row for row in plan["slots"]}
        self.assertEqual(by_date["2026-10-26"]["topic_id"], "T1")
        self.assertEqual(by_date["2026-10-26"]["content_role"], "流量")
        self.assertEqual(by_date["2026-10-28"]["topic_id"], "M1")
        self.assertEqual(by_date["2026-10-28"]["content_role"], "转化")
        self.assertEqual((plan["traffic_slots"], plan["conversion_slots"]), (1, 1))

    def test_invalid_marketing_keeps_priority_slot_but_uses_matching_ordinary(self):
        plan = build_final_plan(inputs(), evaluation(), marketing(False))
        selected = next(row for row in plan["slots"] if row["slot_type"] == "marketing_priority")
        self.assertEqual(selected["topic_id"], "T2")
        self.assertEqual(selected["topic_type"], "普通")
        self.assertEqual(selected["content_role"], "转化")
        self.assertEqual(plan["marketing_ordinary_fallback_slots"], 1)

    def test_hotspot_placeholder_freezes_matching_ordinary_fallback_and_role(self):
        plan = build_final_plan(inputs(50), evaluation(), [])
        hotspots = [row for row in plan["slots"] if row["slot_type"] == "hotspot"]
        self.assertEqual(len(hotspots), 1)
        slot = hotspots[0]
        key = f"A|{slot['publish_date']}"
        fallback = plan["hotspot_fallbacks"][key]
        self.assertIn(fallback["topic_id"], {"T1", "T2"})
        self.assertIn(slot["content_role"], {"流量", "转化"})
        item = {"account_id": "A", "publish_date": date.fromisoformat(slot["publish_date"]),
                "topic_snapshot_json": json.dumps({"hotspot_fallbacks": plan["hotspot_fallbacks"]})}
        self.assertEqual(ai_hotspot_fallback(item)["topic_id"], fallback["topic_id"])
        self.assertEqual((plan["traffic_slots"], plan["conversion_slots"]), (1, 1))

    def test_failed_matching_position_blocks_formal_commit(self):
        result = evaluation()
        result["positions"][1] = {"account_id": "A", "publish_date": "2026-10-28",
                                  "outcome": "failed", "topic_id": None,
                                  "content_role": None, "fit_score": None,
                                  "reason": "no_eligible_normal_or_fallback_topic"}
        with self.assertRaises(ResultCommitError) as caught:
            build_final_plan(inputs(), result, [])
        self.assertEqual(caught.exception.code, "matching_slot_failed")

    def test_composition_count_drift_is_rejected(self):
        result = evaluation()
        result["stages"][-1]["summary"]["actual_conversion_positions"] = 2
        with self.assertRaises(ResultCommitError) as caught:
            build_final_plan(inputs(), result, [])
        self.assertEqual(caught.exception.code, "composition_role_changed")


class PlanningResultTransactionTests(unittest.TestCase):
    """Exercise the real transaction controller with isolated DB doubles."""

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.pipeline = {
            "id": 501, "version": 7, "status": "waiting",
            "cycle_start": date(2026, 10, 26), "cycle_end": date(2026, 11, 1),
            "production_batch_id": None, "preparation_id": 101,
            "matching_task_id": 201, "policy_id": 301,
        }
        self.initial_db, self.db = MagicMock(), MagicMock()
        self.initial_cursor, self.cursor = MagicMock(), MagicMock()
        for db, cursor in ((self.initial_db, self.initial_cursor), (self.db, self.cursor)):
            db.__enter__.return_value = db
            db.cursor.return_value = cursor
            cursor.__enter__.return_value = cursor
        self.initial_cursor.fetchone.return_value = deepcopy(self.pipeline)
        self.stack.enter_context(patch.object(service, "connection",
                                             side_effect=[self.initial_db, self.db]))
        self.lock_acquired = 1
        self.fail_on = None
        self.sql = []
        self.row = None
        self.cursor.execute.side_effect = self.execute
        self.cursor.fetchone.side_effect = lambda: deepcopy(self.row)
        self.frozen = inputs()
        self.task = {"id": 201, "preparation_id": 101, "policy_id": 301,
                     "status": "evaluated", "production_batch_id": None,
                     "result_hash": "f" * 64}
        self.patch("select_preparation", return_value={"id": 101, "config_version": 9,
                                                      "account_count": 1, "slot_count": 2})
        self.patch("select_policy", return_value={"id": 301, "document_hash": "e" * 64})
        self.patch("select_task", return_value=self.task)
        self.patch("check_binding")
        self.patch("checked_inputs", return_value=self.frozen)
        self.patch("load_frozen_inputs", return_value=(
            {k: v for k, v in self.frozen.items() if k != "supplemental"}, None))
        self.patch("intact_document")
        self.patch("read_evaluation", return_value=evaluation())
        self.existing = self.patch("_existing_formal_batch", return_value=None)
        self.marketing = self.patch("load_marketing", return_value=([], 401))
        self.profiles = self.patch("save_batch_account_profiles")

    def patch(self, name, **kwargs):
        return self.stack.enter_context(patch.object(service, name, **kwargs))

    def execute(self, sql, params=()):
        self.sql.append((sql, params))
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("injected persistence failure")
        if "GET_LOCK" in sql:
            self.row = {"acquired": self.lock_acquired}
        elif "FROM godp_planning_pipeline_run" in sql:
            self.row = self.pipeline
        elif "FROM godp_planning_stage_run" in sql:
            self.row = {"id": 601 if params[1] == "composition" else 602,
                        "status": "succeeded" if params[1] == "composition" else "waiting"}
        elif "FROM godp_planning_batch WHERE id=" in sql:
            self.row = {"id": 9001, "batch_code": "AUTO-AI-20261026"}
        elif sql.startswith("INSERT INTO godp_planning_batch"):
            self.cursor.lastrowid = 9001
        elif sql.startswith("INSERT INTO godp_planning_item"):
            self.cursor.lastrowid += 1

    def assert_rolled_back_and_unlocked(self):
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once()
        self.assertIn("RELEASE_LOCK", self.sql[-1][0])

    def test_success_commits_all_result_records_and_relations_together(self):
        result = service.commit_pipeline_result(501, 7)
        self.assertEqual(result["batch_id"], 9001)
        self.assertFalse(result["reused"])
        self.db.commit.assert_called_once()
        self.db.rollback.assert_not_called()
        for table, count in (("godp_planning_batch", 1), ("godp_planning_item", 2),
                             ("godp_slot_state", 2), ("godp_auto_plan_run", 1)):
            self.assertEqual(sum(sql.startswith(f"INSERT INTO {table} ")
                                 for sql, _ in self.sql), count)
        self.profiles.assert_called_once()
        self.assertTrue(any(sql.startswith("UPDATE godp_matching_task") for sql, _ in self.sql))
        self.assertTrue(any(sql.startswith("UPDATE godp_planning_pipeline_run") for sql, _ in self.sql))
        self.assertIn("RELEASE_LOCK", self.sql[-1][0])

    def test_failure_after_slot_inserts_rolls_back_without_success_relations(self):
        self.profiles.side_effect = RuntimeError("profile write failed")
        with self.assertRaisesRegex(RuntimeError, "profile write failed"):
            service.commit_pipeline_result(501, 7)
        self.assert_rolled_back_and_unlocked()
        self.assertTrue(any(sql.startswith("INSERT INTO godp_slot_state") for sql, _ in self.sql))
        self.assertFalse(any(sql.startswith("UPDATE godp_matching_task") for sql, _ in self.sql))

    def test_pipeline_update_failure_rolls_back_batch_items_and_task_relation(self):
        self.fail_on = "UPDATE godp_planning_pipeline_run"
        with self.assertRaisesRegex(RuntimeError, "injected persistence failure"):
            service.commit_pipeline_result(501, 7)
        self.assert_rolled_back_and_unlocked()
        self.assertTrue(any(sql.startswith("UPDATE godp_matching_task") for sql, _ in self.sql))

    def test_committed_replay_returns_same_batch_without_new_writes(self):
        self.pipeline["production_batch_id"] = 9001
        result = service.commit_pipeline_result(501, 7)
        self.assertTrue(result["reused"])
        self.assertEqual(result["batch_id"], 9001)
        self.assert_rolled_back_and_unlocked()
        self.assertFalse(any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in self.sql))

    def test_stale_version_rolls_back_before_any_write(self):
        with self.assertRaises(HTTPException) as caught:
            service.commit_pipeline_result(501, 6)
        self.assertEqual(caught.exception.status_code, 409)
        self.assert_rolled_back_and_unlocked()
        self.assertFalse(any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in self.sql))

    def test_existing_cycle_batch_blocks_duplicate_formal_result(self):
        self.existing.return_value = {"id": 8001}
        with self.assertRaises(ResultCommitError) as caught:
            service.commit_pipeline_result(501, 7)
        self.assertEqual(caught.exception.code, "formal_batch_conflict")
        self.assert_rolled_back_and_unlocked()
        self.assertFalse(any(sql.startswith("INSERT") for sql, _ in self.sql))

    def test_unavailable_cycle_lock_does_not_release_another_writers_lock(self):
        self.lock_acquired = 0
        with self.assertRaises(ResultCommitError) as caught:
            service.commit_pipeline_result(501, 7)
        self.assertEqual(caught.exception.code, "cycle_locked")
        self.db.commit.assert_not_called()
        self.assertFalse(any("RELEASE_LOCK" in sql for sql, _ in self.sql))

    def test_unavailable_marketing_snapshot_blocks_partial_result(self):
        self.marketing.side_effect = service.PlanningError("snapshot unavailable")
        with self.assertRaises(ResultCommitError) as caught:
            service.commit_pipeline_result(501, 7)
        self.assertEqual(caught.exception.code, "marketing_snapshot_unavailable")
        self.assert_rolled_back_and_unlocked()
        self.assertFalse(any(sql.startswith("INSERT") for sql, _ in self.sql))


if __name__ == "__main__":
    unittest.main()
