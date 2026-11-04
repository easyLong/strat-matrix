"""Versioned synthetic facts, frozen inputs and model responses. No database access."""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "testing" / "data"
VERSION = "planning-synthetic-v19-1"
SPACE = "synthetic-test-8d-v1"
DOMAINS = ["家庭金融", "汽车生活", "亲子成长", "本地生活", "职场成长"]
PERSONAS = ["家庭理财分享者", "车圈达人", "亲子生活分享者", "本地生活推荐者", "职场经验分享者"]
STAGES = ["冷启动期", "流量增长期", "转化试探期", "转化放大期", "稳定经营期"]
TYPES = ["三公里好物种草", "产品权益种草", "三公里活动营销", "产品营销", "通用活动", "金融科普",
         "热点解读", "属地推荐", "一句话讨论", "财商教育", "客群兴趣内容", "人设故事"]
PROFILES = {"small": (5, 60), "scale": (100, 600)}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def vector(domain, variant=0):
    values = [.02] * 8
    values[domain] = 1.0
    values[5 + variant % 3] = .04 + variant % 7 * .01
    # Keep frozen fixture bytes stable across Python versions (float sum changed in 3.12).
    norm = math.sqrt(math.fsum(v * v for v in values))
    return [v / norm for v in values]


def policy(engine="v19", *, dimension=8):
    if engine != "v19":
        raise ValueError("Only V19 is supported")
    decisions = {
        "ALG-01": {"similarity": "cosine_unit_vectors"},
        "ALG-02": {"city_gate": "allow_empty_or_exact", "history_gate": "exclude_observed_account_history"},
        "ALG-03": {"top_k": 100, "min_cosine": 0.0},
        "ALG-04": {"score_scale": "positive_cosine_0_100"},
        "ALG-05": {"same_account_topic_max": 1, "global_topic_max": None,
                   "global_reuse_penalty": 0.0, "official_usage_penalty": 0.0},
        "ALG-06": {"rounding": "half_up", "role_order": "even_spread"},
        "ALG-07": {"official_usage_unknown_rank": "after_known"},
        "ALG-08": {"fallback_sort": "heat_desc_topic_id", "fallback_same_account_max": 1},
        "ALG-09": {"no_candidate": "fallback_then_failed", "system_error": "task_failure"},
    }
    value = {
        "schema_version": 2, "implementation_key": "builtin-v19-quality-v1",
        "vector_space": {"vector_model": SPACE, "dimension": dimension, "semantic_space_id": SPACE},
        "required_inputs": ["accounts", "topics", "config", "positions", "fallback_topics", "history", "official_usage"],
        "input_options": {"history_window_days": 90, "history_completeness": "allow_unknown",
                          "history_unknown_references": "allow_unknown", "official_usage_unknown": "allow_unknown",
                          "fallback_unknown_heat": "allow_unknown"},
        "decisions": {k: {"definition": f"{k} 合成回归契约", "parameters": v,
                          "acceptance_examples": [f"{k} 固定合成样例"]} for k, v in decisions.items()},
        "portfolio": {"relevance_weight": .55, "coverage_weight": .2, "balance_weight": .1,
                      "redundancy_weight": .15, "mmr_relevance_weight": .7,
                      "shortlist_per_slot": 20, "max_improvement_passes": 10},
    }
    if engine == "v19":
        from app.matching_contracts import MatchingQualityOptions
        from app.matching_quality import QUALITY_PARAMETERS
        value.update(implementation_key="builtin-v19-quality-v1",
                     quality=MatchingQualityOptions().model_dump(mode="json", exclude_none=True))
        for key, params in QUALITY_PARAMETERS.items():
            value["decisions"][key]["parameters"] = deepcopy(params)
    return value


def build(profile):
    """Generation is deterministic: IDs, dates, vectors and responses never use the current clock."""
    from app.taxonomy import normalize_taxonomy
    count, topic_count = PROFILES[profile]
    taxonomy = {"T1": ["非营销", "营销"], "T2": ["流量", "转化"], "T3": [], "T4": [], "T5": []}
    for i, domain in enumerate(DOMAINS):
        taxonomy["T3"].extend([
            {"id": f"group-{i}", "name": domain, "node_type": "group", "enabled": True},
            {"id": f"leaf-{i}", "name": domain + "经验", "parent_id": f"group-{i}", "enabled": True},
            {"id": f"conditional-{i}", "name": domain + "权益", "parent_id": f"group-{i}", "enabled": True},
        ])
    taxonomy["T3"].append({"id": "unmapped", "name": "尚未映射方向", "enabled": True})
    for dimension, prefix, title in [("T4", "aud", "目标客群"), ("T5", "scene", "生活场景")]:
        taxonomy[dimension] = [{"id": prefix + "-group", "name": title, "node_type": "group", "enabled": True}] + [
            {"id": f"{prefix}-{i}", "name": domain, "parent_id": prefix + "-group", "enabled": True}
            for i, domain in enumerate(DOMAINS)]
    taxonomy = normalize_taxonomy(taxonomy)
    rules = []
    for i, persona in enumerate(PERSONAS):
        def add(**fields):
            rules.append(dict(id=len(rules) + 1, mapping_version=1, taxonomy_version=1,
                              source_field="persona", source_value=persona, status="active", **fields))
        for j in range(5):
            add(target_dimension="T3", target_level="L2", target_node_id=f"group-{j}",
                relation_type="CORE" if i == j else "OFF")
        add(target_dimension="T3", target_level="L3", target_node_id=f"conditional-{i}",
            relation_type="CONDITIONAL", condition_text="只介绍免费权益，不做收益承诺")
        for dimension, prefix in [("T4", "aud"), ("T5", "scene")]:
            add(target_dimension=dimension, target_level="L3", target_node_id=f"{prefix}-{i}", relation_type="CORE")
        add(target_dimension="T6", target_level="TEXT", relation_type="TEXT", target_text=f"合成需求-{DOMAINS[i]}")
    accounts = []
    for i in range(count):
        d = i % 5
        raw = dict(persona=PERSONAS[d], city="测试城甲" if i % 2 == 0 else "测试城乙",
                   marketing_eligible=i % 2 == 0, account_type="认证" if i % 2 == 0 else "非认证",
                   gender="未知", interests=[DOMAINS[d]], expression_style="经验分享")
        accounts.append(dict(account_id=f"SYN-ACC-{i + 1:03d}", account_name=f"合成测试账号{i + 1:03d}",
                             um_no=f"SYN-UM-{i + 1:03d}", vector=vector(d), vector_model=SPACE,
                             snapshot={"source_payload": raw}, profile={"account": raw, "lifecycle_stage": STAGES[d]}))
    topics, annotations, pairs = [], {}, {p: {} for p in PERSONAS}
    for i in range(topic_count):
        d = i % 5
        special = i >= topic_count - 10
        scenario = ["expired", "marketing", "disabled", "wrong_city", "unmapped", "model_drop",
                    "conditional_reject", "conditional_accept", "related_off", "history"][i - (topic_count - 10)] if special else "normal"
        identity = f"SYN-TOPIC-{i + 1:04d}"
        leaf = "unmapped" if scenario == "unmapped" else f"conditional-{d}" if scenario.startswith("conditional_") else f"leaf-{d}"
        annotation = dict(main_t3=leaf, related_t3=[f"leaf-{(d + 1) % 5}"] if scenario == "related_off" else [],
                          t4=[f"aud-{d}"], t5=[f"scene-{d}"])
        role = "流量" if (i // 5) % 2 == 0 else "转化"
        tags = dict(T1="营销" if scenario == "marketing" else "非营销", T2=[role], T3=[leaf],
                    T4=annotation["t4"], T5=annotation["t5"], T6=f"合成需求-{DOMAINS[d]}")
        title = f"{DOMAINS[d]}：第{i + 1:04d}份实用经验"
        source = dict(title=title, outline=f"围绕{DOMAINS[d]}说明具体问题、解决步骤及注意事项。案例完全虚构。",
                      content_type=TYPES[i % 12], is_marketing=scenario == "marketing",
                      valid_from="2026-01-01T00:00:00+08:00",
                      valid_to="2026-10-01T00:00:00+08:00" if scenario == "expired" else "2027-12-31T23:59:59+08:00",
                      available=scenario != "disabled")
        topics.append(dict(topic_id=identity, vector=vector(d, i), vector_model=SPACE, tags=tags,
                           tag_ids={"T3": leaf, "T4": annotation["t4"][0], "T5": annotation["t5"][0]},
                           t6_tag_id=d + 1, source_payload=source, profile={"applicable_cities": ["不存在的测试城"] if scenario == "wrong_city" else []},
                           scenario=scenario, fixture_domain=d))
        annotations[identity] = annotation
        for j, persona in enumerate(PERSONAS):
            fit = .94 - (i % 7) * .01 if j == d else .12
            pairs[persona][identity] = dict(decision="DROP" if j != d or scenario == "model_drop" else "ACCEPT",
                j_topic=fit, j_need=fit, j_aud=.8, j_scene=.8, j_style=.8,
                condition_met=scenario != "conditional_reject",
                reason="固定合成响应：方向相符" if j == d else "固定合成响应：专业方向不符")
    positions = [dict(account_id=a["account_id"], publish_date=day) for a in accounts for day in ["2026-11-02", "2026-11-04", "2026-11-06"]]
    history_topic = next(t for t in topics if t["scenario"] == "history")
    history = [dict(account_id=a["account_id"], topic_id=history_topic["topic_id"], topic_type="普通", reference_known=True,
                    source_payload={"title": history_topic["source_payload"]["title"]}) for a in accounts]
    scope = [t["topic_id"] for t in topics if t["scenario"] not in ("expired", "marketing", "disabled")]
    return dict(schema_version=1, dataset_id=f"{VERSION}-{profile}", profile=profile, data_origin="synthetic_only",
                cycle_start="2026-11-02", vector_space=SPACE,
                description="合成向量与模型响应仅用于代码回归，未经客户金标确认，不代表真实模型质量。",
                accounts=accounts, topics=topics, positions=positions, frozen_topic_ids=scope,
                config={"stage_targets": [dict(name=s, traffic=t, conversion=100-t) for s, t in zip(STAGES, [80, 70, 50, 30, 50])]},
                history=history, taxonomy=taxonomy, mapping_rules=rules,
                policies={e: policy(e) for e in ("v19",)},
                replay={"provider": "synthetic_replay", "chat_model": "synthetic-chat-v1", "embedding_model": SPACE,
                        "annotations": annotations, "pairs_by_persona": pairs,
                        "need_vectors": {f"合成需求-{domain}": vector(i) for i, domain in enumerate(DOMAINS)}},
                expected={"shared": {"position_shape_violations_max": 0, "failed_positions_max": 0, "history_violations_max": 0, "city_violations_max": 0,
                                     "duplicate_account_topics_max": 0, "role_violations_max": 0, "source_scope_violations_max": 0},
                          "v19": {"persona_violations_max": 0, "rejected_precision_used_max": 0}})


def load(profile):
    path = DATA / f"{profile}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    if digest(value) != manifest["datasets"][profile]["sha256"]:
        raise ValueError("固定测试数据指纹不一致，请核查修改并显式更新数据版本")
    return value


def write():
    DATA.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": 1, "version": VERSION, "datasets": {}}
    for name in PROFILES:
        value = build(name)
        (DATA / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["datasets"][name] = dict(sha256=digest(value), accounts=len(value["accounts"]), topics=len(value["topics"]),
                                         positions=len(value["positions"]))
    (DATA / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    import sys
    sys.path.insert(0, str(ROOT / "python-backend"))
    parser = argparse.ArgumentParser(description="显式生成版本化合成数据；常规回归只读已提交JSON")
    parser.add_argument("--write", action="store_true", required=True)
    parser.parse_args()
    write()


if __name__ == "__main__":
    main()
