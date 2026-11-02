"""V1 candidate allocation; shared rules live in core.matching_common."""
from collections import Counter, defaultdict
from datetime import date
import math
from .matching_contracts import MatchingEvaluation, MatchingPolicyDocument
from .core.matching_common import (
    CANDIDATE_CONTRACT_KEY as IMPLEMENTATION_KEY, ExecutorConfig,
    ExecutorPolicyError, ExecutorInputError, candidate_config as executor_config,
    dot_similarity, account_city, topic_cities, city_allowed, history_by_account,
    usage_by_topic, fit_score, stage_targets, role_plan,
)

def execute_job(job: dict) -> MatchingEvaluation:
    """Execute one already-leased matching task and return a validated proposal."""
    try:
        inputs = job["inputs"]
        policy = job["policy"]
        lease_id = job["lease_id"]
        input_hash = job["input_hash"]
        policy_hash = job["policy_hash"]
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("leased job identity is incomplete") from exc

    _, config = executor_config(policy)
    try:
        accounts = inputs["accounts"]
        topics = inputs["topics"]
        positions = inputs["positions"]
        supplemental = inputs["supplemental"]
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("leased inputs are incomplete") from exc
    if not accounts or not topics or not positions:
        raise ExecutorInputError("accounts, topics and positions must be non-empty")

    account_by_id = {str(row["account_id"]): row for row in accounts}
    topic_by_id = {str(row["topic_id"]): row for row in topics}
    if len(account_by_id) != len(accounts) or len(topic_by_id) != len(topics):
        raise ExecutorInputError("duplicate account or topic identifiers")
    for position in positions:
        if position.get("account_id") not in account_by_id:
            raise ExecutorInputError("position references an unknown account")
        try:
            date.fromisoformat(position["publish_date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ExecutorInputError("position publish_date is invalid") from exc

    history = history_by_account(supplemental)
    usage = usage_by_topic(supplemental)
    hard_gate_total = 0
    hard_gate_city_excluded = 0
    hard_gate_history_excluded = 0
    recalled: dict[str, list[dict]] = {}
    scored_edges = 0

    for account_id, account in sorted(account_by_id.items()):
        candidates = []
        for topic_id, topic in sorted(topic_by_id.items()):
            if not city_allowed(account, topic):
                hard_gate_city_excluded += 1
                continue
            if topic_id in history.get(account_id, set()):
                hard_gate_history_excluded += 1
                continue
            hard_gate_total += 1
            cosine = dot_similarity(account["vector"], topic["vector"])
            if cosine < config.min_cosine:
                continue
            candidates.append({
                "topic_id": topic_id,
                "cosine": cosine,
                "fit_score": fit_score(cosine),
            })
        candidates.sort(key=lambda item: (-item["cosine"], item["topic_id"]))
        recalled[account_id] = candidates[:config.top_k]
        scored_edges += len(recalled[account_id])

    stage_audits = [
        {"stage": "hard_gate", "summary": {
            "eligible_edges": hard_gate_total,
            "city_excluded_edges": hard_gate_city_excluded,
            "history_excluded_edges": hard_gate_history_excluded,
            "account_count": len(accounts),
            "topic_count": len(topics),
        }},
        {"stage": "recall", "summary": {
            "top_k": config.top_k,
            "min_cosine": config.min_cosine,
            "recalled_edges": scored_edges,
            "accounts_without_recall": sum(not recalled[key] for key in recalled),
        }},
        {"stage": "fit", "summary": {
            "scored_edges": scored_edges,
            "score_scale": "positive_cosine_0_100",
        }},
    ]

    fallback_topics = supplemental.get("fallback_topics")
    if not isinstance(fallback_topics, list):
        raise ExecutorInputError("fallback topic snapshot is missing")
    used_account: Counter[tuple[str, str]] = Counter()
    fallback_used_account: Counter[tuple[str, str]] = Counter()
    used_global: Counter[str] = Counter()
    matched_count = fallback_count = failed_count = 0
    selected_rows = []

    def normal_rank(candidate: dict) -> tuple:
        topic_id = candidate["topic_id"]
        known, official_count = usage.get(topic_id, (False, None))
        unknown_rank = 0 if known else 1
        adjusted = candidate["fit_score"] - config.global_reuse_penalty * used_global[topic_id]
        if known:
            adjusted -= config.official_usage_penalty * math.log1p(official_count or 0)
        return (unknown_rank, -adjusted, -candidate["fit_score"], used_global[topic_id], topic_id)

    def choose_fallback(account_id: str, account: dict) -> dict | None:
        choices = []
        for topic in fallback_topics:
            topic_id = str(topic.get("topic_id") or "")
            if not topic_id or not city_allowed(account, topic, fallback=True):
                continue
            if topic_id in history.get(account_id, set()):
                continue
            if used_account[(account_id, topic_id)] >= config.same_account_topic_max:
                continue
            if fallback_used_account[(account_id, topic_id)] >= config.fallback_same_account_max:
                continue
            heat_known = bool(topic.get("heat_known"))
            heat = topic.get("topic_heat") if heat_known else None
            if heat_known and (type(heat) not in (int, float) or not math.isfinite(float(heat))):
                raise ExecutorInputError("fallback heat is invalid")
            choices.append((0 if heat_known else 1, -(float(heat) if heat_known else 0.0), topic_id, topic))
        if not choices:
            return None
        choices.sort(key=lambda item: item[:3])
        return choices[0][3]

    for position in sorted(positions, key=lambda item: (item["publish_date"], item["account_id"])):
        account_id = str(position["account_id"])
        account = account_by_id[account_id]
        available = []
        for candidate in recalled[account_id]:
            topic_id = candidate["topic_id"]
            if used_account[(account_id, topic_id)] >= config.same_account_topic_max:
                continue
            if config.global_topic_max is not None and used_global[topic_id] >= config.global_topic_max:
                continue
            available.append(candidate)
        if available:
            chosen = min(available, key=normal_rank)
            topic_id = chosen["topic_id"]
            used_account[(account_id, topic_id)] += 1
            used_global[topic_id] += 1
            matched_count += 1
            selected_rows.append({
                "account_id": account_id,
                "publish_date": position["publish_date"],
                "outcome": "matched",
                "topic_id": topic_id,
                "fit_score": chosen["fit_score"],
                "reason": "",
            })
            continue

        fallback = choose_fallback(account_id, account)
        if fallback is not None:
            topic_id = str(fallback["topic_id"])
            used_account[(account_id, topic_id)] += 1
            fallback_used_account[(account_id, topic_id)] += 1
            fallback_count += 1
            selected_rows.append({
                "account_id": account_id,
                "publish_date": position["publish_date"],
                "outcome": "fallback",
                "topic_id": topic_id,
                "fit_score": None,
                "reason": "normal_candidates_exhausted",
            })
        else:
            failed_count += 1
            selected_rows.append({
                "account_id": account_id,
                "publish_date": position["publish_date"],
                "outcome": "failed",
                "topic_id": None,
                "fit_score": None,
                "reason": "no_eligible_normal_or_fallback_topic",
            })

    stage_audits.append({"stage": "global_allocation", "summary": {
        "matched_positions": matched_count,
        "fallback_positions": fallback_count,
        "failed_positions": failed_count,
        "unique_matched_topics": len(used_global),
        "maximum_matched_topic_reuse": max(used_global.values(), default=0),
    }})

    traffic_targets = stage_targets(inputs)
    positions_by_account: dict[str, list[dict]] = defaultdict(list)
    for position in positions:
        positions_by_account[str(position["account_id"])].append(position)
    roles = {}
    target_traffic = target_conversion = 0
    for account_id, account_positions in positions_by_account.items():
        account = account_by_id[account_id]
        try:
            lifecycle = account["profile"]["lifecycle_stage"]
        except (KeyError, TypeError) as exc:
            raise ExecutorInputError("account lifecycle_stage is missing") from exc
        if lifecycle not in traffic_targets:
            raise ExecutorInputError("lifecycle stage has no configured target")
        plan = role_plan(account, account_positions, traffic_targets[lifecycle])
        roles.update(plan)
        target_traffic += sum(role == "流量" for role in plan.values())
        target_conversion += sum(role == "转化" for role in plan.values())

    actual_traffic = actual_conversion = 0
    proposed_positions = []
    for row in selected_rows:
        if row["outcome"] == "failed":
            proposed_positions.append({
                "account_id": row["account_id"],
                "publish_date": row["publish_date"],
                "outcome": "failed",
                "reason": row["reason"],
            })
            continue
        role = roles[(row["account_id"], row["publish_date"])]
        actual_traffic += role == "流量"
        actual_conversion += role == "转化"
        if row["outcome"] == "matched":
            proposed_positions.append({
                "account_id": row["account_id"],
                "publish_date": row["publish_date"],
                "outcome": "matched",
                "topic_id": row["topic_id"],
                "content_role": role,
                "fit_score": row["fit_score"],
            })
        else:
            proposed_positions.append({
                "account_id": row["account_id"],
                "publish_date": row["publish_date"],
                "outcome": "fallback",
                "topic_id": row["topic_id"],
                "content_role": role,
                "reason": row["reason"],
            })

    stage_audits.append({"stage": "composition", "summary": {
        "target_traffic_positions": target_traffic,
        "target_conversion_positions": target_conversion,
        "actual_traffic_positions": actual_traffic,
        "actual_conversion_positions": actual_conversion,
        "failed_positions_without_role": failed_count,
        "rounding": "half_up",
        "role_order": "even_spread",
    }})

    return MatchingEvaluation.model_validate({
        "lease_id": lease_id,
        "input_hash": input_hash,
        "policy_hash": policy_hash,
        "implementation_key": IMPLEMENTATION_KEY,
        "stages": stage_audits,
        "positions": proposed_positions,
    })
