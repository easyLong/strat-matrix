"""Algorithm and worker tests for the built-in Matching Executor V1."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from app import matching_executor_worker as worker
from app.matching_executor import IMPLEMENTATION_KEY, ExecutorPolicyError, execute_job


DECISIONS = {
    "ALG-01": {"similarity": "cosine_unit_vectors"},
    "ALG-02": {"city_gate": "allow_empty_or_exact", "history_gate": "exclude_observed_account_history"},
    "ALG-03": {"top_k": 20, "min_cosine": 0.0},
    "ALG-04": {"score_scale": "positive_cosine_0_100"},
    "ALG-05": {"same_account_topic_max": 1, "global_topic_max": None,
               "global_reuse_penalty": 3.0, "official_usage_penalty": 0.25},
    "ALG-06": {"rounding": "half_up", "role_order": "even_spread"},
    "ALG-07": {"official_usage_unknown_rank": "after_known"},
    "ALG-08": {"fallback_sort": "heat_desc_topic_id", "fallback_same_account_max": 1},
    "ALG-09": {"no_candidate": "fallback_then_failed", "system_error": "task_failure"},
}


def policy():
    return {
        "schema_version": 2,
        "implementation_key": IMPLEMENTATION_KEY,
        "vector_space": {"vector_model": "shared-v1", "dimension": 2,
                         "semantic_space_id": "fixture-shared-space"},
        "required_inputs": ["accounts", "topics", "config", "positions",
                            "fallback_topics", "history", "official_usage"],
        "input_options": {"history_window_days": 90, "history_completeness": "allow_unknown",
                          "history_unknown_references": "allow_unknown",
                          "official_usage_unknown": "allow_unknown",
                          "fallback_unknown_heat": "allow_unknown"},
        "decisions": {code: {"definition": f"{code} fixture rule",
                             "parameters": params,
                             "acceptance_examples": [f"{code} fixture example"]}
                      for code, params in DECISIONS.items()},
    }


def account(account_id, city, vector, lifecycle):
    return {"account_id": account_id, "vector": vector, "vector_model": "shared-v1",
            "profile": {"account": {"city": city}, "lifecycle_stage": lifecycle}}


def topic(topic_id, vector, cities=None):
    return {"topic_id": topic_id, "vector": vector, "vector_model": "shared-v1",
            "profile": {"applicable_cities": cities or []}, "source_payload": {}}


def fallback(topic_id, heat, cities=None):
    return {"topic_id": topic_id, "topic_heat": heat, "heat_known": heat is not None,
            "source_payload": {"applicable_cities": cities or []}}


def usage(topic_id, count):
    return {"topic_id": topic_id, "known": count is not None,
            "official_use_count": count}


def base_job():
    return {
        "task_id": 1001, "lease_id": "a" * 32, "input_hash": "b" * 64, "policy_hash": "c" * 64,
        "policy": policy(),
        "inputs": {
            "config": {"stage_targets": [
                {"name": "冷启动期", "traffic": 80, "conversion": 20},
                {"name": "流量增长期", "traffic": 70, "conversion": 30},
                {"name": "转化试探期", "traffic": 50, "conversion": 50},
                {"name": "转化放大期", "traffic": 30, "conversion": 70},
                {"name": "稳定经营期", "traffic": 50, "conversion": 50},
            ]},
            "accounts": [
                account("A", "上海", [1.0, 0.0], "冷启动期"),
                account("B", "北京", [0.0, 1.0], "稳定经营期"),
            ],
            "topics": [
                topic("T1", [1.0, 0.0]),
                topic("T2", [0.8, 0.6], ["上海"]),
                topic("T3", [0.0, 1.0], ["北京"]),
            ],
            "positions": [
                {"account_id": "A", "publish_date": "2026-10-26"},
                {"account_id": "A", "publish_date": "2026-10-28"},
                {"account_id": "B", "publish_date": "2026-10-26"},
                {"account_id": "B", "publish_date": "2026-10-28"},
            ],
            "supplemental": {
                "history": {"observed_records": [
                    {"account_id": "A", "topic_id": "T1", "topic_type": "普通",
                     "reference_known": True},
                ]},
                "fallback_topics": [fallback("F1", 50, ["上海"]), fallback("F2", 10)],
                "official_usage": {"records": [
                    usage("T1", 10), usage("T2", 1), usage("T3", 2),
                    usage("F1", 0), usage("F2", 0),
                ]},
            },
        },
    }


class MatchingExecutorTests(unittest.TestCase):
    def test_real_chain_applies_history_city_global_allocation_fallback_and_composition(self):
        result = execute_job(base_job())
        encoded = result.model_dump(mode="json")
        self.assertEqual([stage["stage"] for stage in encoded["stages"]],
                         ["hard_gate", "recall", "fit", "global_allocation", "composition"])
        by_position = {(row["account_id"], row["publish_date"]): row
                       for row in encoded["positions"]}
        self.assertEqual(by_position[("A", "2026-10-26")]["topic_id"], "T2")
        self.assertEqual(by_position[("A", "2026-10-28")]["outcome"], "fallback")
        self.assertEqual(by_position[("A", "2026-10-28")]["topic_id"], "F1")
        self.assertEqual(by_position[("B", "2026-10-26")]["topic_id"], "T3")
        self.assertEqual(by_position[("B", "2026-10-28")]["topic_id"], "T1")
        self.assertEqual({by_position[("A", day)]["content_role"] for day in ("2026-10-26", "2026-10-28")}, {"流量"})
        self.assertEqual({by_position[("B", day)]["content_role"] for day in ("2026-10-26", "2026-10-28")},
                         {"流量", "转化"})
        hard_gate = encoded["stages"][0]["summary"]
        self.assertEqual(hard_gate["history_excluded_edges"], 1)
        self.assertGreater(hard_gate["city_excluded_edges"], 0)

    def test_unknown_official_usage_is_not_silently_treated_as_zero(self):
        job = base_job()
        job["inputs"]["accounts"] = [account("A", "上海", [1.0, 0.0], "冷启动期")]
        job["inputs"]["topics"] = [
            topic("KNOWN", [0.99, 0.1410673598]),
            topic("UNKNOWN", [1.0, 0.0]),
        ]
        job["inputs"]["positions"] = [{"account_id": "A", "publish_date": "2026-10-26"}]
        job["inputs"]["supplemental"]["history"] = {"observed_records": []}
        job["inputs"]["supplemental"]["fallback_topics"] = [fallback("F", 1)]
        job["inputs"]["supplemental"]["official_usage"] = {"records": [
            usage("KNOWN", 3), usage("UNKNOWN", None), usage("F", 0),
        ]}
        result = execute_job(job)
        self.assertEqual(result.positions[0].topic_id, "KNOWN")

    def test_exhausted_normal_and_fallback_pool_produces_business_slot_failure(self):
        job = base_job()
        job["inputs"]["accounts"] = [account("A", "上海", [1.0, 0.0], "冷启动期")]
        job["inputs"]["topics"] = [topic("T1", [1.0, 0.0], ["北京"])]
        job["inputs"]["positions"] = [{"account_id": "A", "publish_date": "2026-10-26"}]
        job["inputs"]["supplemental"] = {
            "history": {"observed_records": []},
            "fallback_topics": [fallback("F1", 10, ["北京"])],
            "official_usage": {"records": [usage("T1", 0), usage("F1", 0)]},
        }
        result = execute_job(job)
        self.assertEqual(result.positions[0].outcome, "failed")
        self.assertEqual(result.positions[0].reason, "no_eligible_normal_or_fallback_topic")
        self.assertIsNone(result.positions[0].content_role)

    def test_executor_refuses_other_implementation_or_unreviewed_parameter_shape(self):
        job = base_job()
        job["policy"]["implementation_key"] = "some-other-engine"
        with self.assertRaises(ExecutorPolicyError):
            execute_job(job)
        job = base_job()
        job["policy"]["decisions"]["ALG-03"]["parameters"]["invented_default"] = 1
        with self.assertRaises(ExecutorPolicyError):
            execute_job(job)

    def test_execution_is_deterministic(self):
        first = execute_job(base_job()).model_dump(mode="json")
        second = execute_job(deepcopy(base_job())).model_dump(mode="json")
        self.assertEqual(first, second)

    def test_worker_claims_only_builtin_implementation_and_saves_evaluation(self):
        job = base_job()
        with patch.object(worker, "claim_task", side_effect=[
                {"job": job, "next_after_id": 1001},
                {"job": None, "next_after_id": 1001},
             ]) as claim, patch.object(worker, "save_evaluation",
                                      return_value={"status": "evaluated", "version": 3}) as save:
            self.assertEqual(worker.run_once(), 0)
        self.assertEqual(claim.call_args_list[0].kwargs["implementation_key"], IMPLEMENTATION_KEY)
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
