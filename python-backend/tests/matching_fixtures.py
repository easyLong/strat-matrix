"""Historical frozen facts for storage compatibility tests; no executable algorithm."""
from copy import deepcopy
IMPLEMENTATION_KEY = "builtin-cosine-balanced-v1"

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
                             "parameters": deepcopy(params),
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
