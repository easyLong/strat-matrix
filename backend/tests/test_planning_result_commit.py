"""Pure composition tests for atomic Planning result commit V1."""

from datetime import date
import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
