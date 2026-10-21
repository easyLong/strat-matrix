"""Production executor for the explicitly versioned V2 portfolio objective.

V2 currently reuses the approved frozen-vector cosine candidate contract from
V1, then applies account-equal portfolio utility, MMR shortlist pruning, a
capacity-constrained matrix allocation, and deterministic local improvement.
It does not claim to use account-side T3/T4/T5 features until those mappings
are present in the frozen account snapshot.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
import math

from .matching_algorithm_v2 import (
    AlgorithmConfigurationError,
    Candidate,
    Slot,
    allocate_matrix,
)
from .matching_contracts import MatchingEvaluation, MatchingPolicyDocument
from .matching_executor import (
    IMPLEMENTATION_KEY as V1_IMPLEMENTATION_KEY,
    ExecutorInputError,
    ExecutorPolicyError,
    _dot,
    _history_by_account,
    _role_plan,
    _stage_targets,
    _city_allowed,
    executor_config,
)
from .matching_portfolio_v2 import PortfolioPolicy, optimize_portfolios


IMPLEMENTATION_KEY = "builtin-cosine-portfolio-v2"


def portfolio_policy(document: MatchingPolicyDocument) -> PortfolioPolicy:
    if document.implementation_key != IMPLEMENTATION_KEY:
        raise ExecutorPolicyError("unsupported V2 portfolio implementation_key")
    if document.schema_version != 2 or document.portfolio is None:
        raise ExecutorPolicyError("V2 requires schema_version=2 and explicit portfolio parameters")
    try:
        return PortfolioPolicy.from_mapping(document.portfolio.model_dump(mode="json"))
    except AlgorithmConfigurationError as exc:
        raise ExecutorPolicyError(str(exc)) from exc


def _cosine_similarity(topic_by_id: dict[str, dict], left: str, right: str) -> float:
    try:
        value = _dot(topic_by_id[left]["vector"], topic_by_id[right]["vector"])
    except KeyError as exc:
        raise ExecutorInputError("portfolio candidate references an unknown topic") from exc
    return max(0.0, min(1.0, value))


def _topic_role(topic: dict) -> str | None:
    tags = topic.get("tags")
    if not isinstance(tags, dict):
        return None
    value = tags.get("T2", tags.get("t2"))
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, str) or value not in ("\u6d41\u91cf", "\u8f6c\u5316"):
        return None
    return value


def execute_job_v2(job: dict) -> MatchingEvaluation:
    """Execute a leased ordinary matching task using the approved V2 policy."""
    try:
        inputs = job["inputs"]
        raw_policy = job["policy"]
        identity = {
            "lease_id": job["lease_id"], "input_hash": job["input_hash"],
            "policy_hash": job["policy_hash"],
        }
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("leased job identity is incomplete") from exc

    try:
        document = MatchingPolicyDocument.model_validate(raw_policy)
    except (TypeError, ValueError) as exc:
        raise ExecutorPolicyError("V2 policy document cannot be parsed") from exc
    portfolio = portfolio_policy(document)

    # The V2 key intentionally shares the exact, already-approved cosine
    # eligibility and lifecycle-role contract. Only allocation and composition
    # differ from V1; V2 does not consume official-use ranking signals.
    v1_policy = {**raw_policy, "implementation_key": V1_IMPLEMENTATION_KEY}
    _, config = executor_config(v1_policy)
    allocation_params = document.decisions["ALG-05"].parameters
    if allocation_params["global_reuse_penalty"] != 0 \
            or allocation_params["official_usage_penalty"] != 0:
        raise ExecutorPolicyError("V2 portfolio allocation requires both legacy reuse penalties to be zero")

    try:
        accounts = inputs["accounts"]
        topics = inputs["topics"]
        positions = inputs["positions"]
        supplemental = inputs["supplemental"]
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("leased V2 inputs are incomplete") from exc
    if not accounts or not topics or not positions:
        raise ExecutorInputError("accounts, topics and positions must be non-empty")
    if not isinstance(supplemental, dict):
        raise ExecutorInputError("supplemental snapshot must be an object")
    fallback_topics = supplemental.get("fallback_topics")
    if not isinstance(fallback_topics, list):
        raise ExecutorInputError("fallback topic snapshot is missing")
    if any(not isinstance(topic, dict) or not str(topic.get("topic_id") or "").strip()
           for topic in fallback_topics):
        raise ExecutorInputError("fallback topic snapshot contains an invalid topic")

    if any(not isinstance(row, dict) for row in accounts) or any(
        not isinstance(row, dict) for row in topics
    ):
        raise ExecutorInputError("account and topic snapshots must contain objects")
    account_by_id = {str(row["account_id"]): row for row in accounts}
    topic_by_id = {str(row["topic_id"]): row for row in topics}
    if len(account_by_id) != len(accounts) or len(topic_by_id) != len(topics):
        raise ExecutorInputError("duplicate account or topic identifiers")

    history = _history_by_account(supplemental)
    slots: list[Slot] = []
    for position in positions:
        if not isinstance(position, dict):
            raise ExecutorInputError("position snapshot must contain objects")
        account_id = str(position["account_id"])
        publish_date = str(position["publish_date"])
        if account_id not in account_by_id:
            raise ExecutorInputError("position references an unknown account")
        try:
            date.fromisoformat(publish_date)
        except ValueError as exc:
            raise ExecutorInputError("position publish_date is invalid") from exc
        slots.append(Slot(
            slot_id=f"{account_id}:{publish_date}", account_id=account_id,
            publish_date=publish_date,
        ))
    if len({slot.slot_id for slot in slots}) != len(slots):
        raise ExecutorInputError("duplicate account publish-date slots")

    role_targets = _stage_targets(inputs)
    slots_by_account: dict[str, list[Slot]] = {}
    for slot in slots:
        slots_by_account.setdefault(slot.account_id, []).append(slot)
    roles: dict[tuple[str, str], str] = {}
    for account_id, account_slots in slots_by_account.items():
        account = account_by_id[account_id]
        try:
            traffic_target = role_targets[account["profile"]["lifecycle_stage"]]
        except (KeyError, TypeError) as exc:
            raise ExecutorInputError("account lifecycle target is missing") from exc
        role_positions = [{"account_id": slot.account_id, "publish_date": slot.publish_date}
                          for slot in account_slots]
        roles.update(_role_plan(account, role_positions, traffic_target))

    topic_roles = {topic_id: _topic_role(topic) for topic_id, topic in topic_by_id.items()}
    fallback_topic_roles = {
        str(topic["topic_id"]): _topic_role(topic) for topic in fallback_topics
    }

    candidates: list[Candidate] = []
    eligible_edges = city_excluded = history_excluded = role_excluded = 0
    unknown_role_excluded = recalled_edges = 0
    account_recall_count: dict[str, int] = {}
    slot_recall_count: Counter[str] = Counter()
    for account_id, account_slots in sorted(slots_by_account.items()):
        account = account_by_id[account_id]
        role_slots: dict[str, list[Slot]] = {}
        for slot in account_slots:
            role_slots.setdefault(roles[(account_id, slot.publish_date)], []).append(slot)
        ranked_by_role: dict[str, list[tuple[float, str]]] = {
            role: [] for role in role_slots
        }
        for topic_id, topic in sorted(topic_by_id.items()):
            if not _city_allowed(account, topic):
                city_excluded += len(account_slots)
                continue
            if topic_id in history.get(account_id, set()):
                history_excluded += len(account_slots)
                continue
            eligible_edges += len(account_slots)
            topic_role = topic_roles[topic_id]
            if topic_role is None:
                unknown_role_excluded += len(account_slots)
                continue
            matched_role_slots = role_slots.get(topic_role, [])
            role_excluded += len(account_slots) - len(matched_role_slots)
            if not matched_role_slots:
                continue
            cosine = _dot(account["vector"], topic["vector"])
            if cosine < config.min_cosine:
                continue
            ranked_by_role[topic_role].append((cosine, topic_id))
        account_recalled = False
        for role, role_positions in sorted(role_slots.items()):
            ranked = ranked_by_role[role]
            ranked.sort(key=lambda item: (-item[0], item[1]))
            chosen = ranked[:config.top_k]
            recalled_edges += len(chosen) * len(role_positions)
            if chosen:
                account_recalled = True
            for slot in role_positions:
                if chosen:
                    slot_recall_count[slot.slot_id] = len(chosen)
                for cosine, topic_id in chosen:
                    candidates.append(Candidate(
                        slot_id=slot.slot_id, account_id=account_id,
                        topic_id=topic_id, signals={"cosine": max(0.0, min(1.0, cosine))},
                        fit_score=max(0.0, min(1.0, cosine)),
                        audit={"cosine": cosine, "score_scale": "positive_cosine_0_1",
                               "content_role": role, "topic_role": topic_roles[topic_id]},
                    ))
        account_recall_count[account_id] = int(account_recalled)

    capacities = {
        topic_id: config.global_topic_max if config.global_topic_max is not None else len(slots)
        for topic_id in topic_by_id
    }
    initial = allocate_matrix(
        slots, candidates, capacities,
        account_topic_capacity=config.same_account_topic_max,
        reserved_account_topics={},
    )

    topic_labels: dict[str, dict[str, str]] = {}
    for topic_id, topic in topic_by_id.items():
        raw_labels = topic.get("tag_ids")
        if not isinstance(raw_labels, dict):
            raise ExecutorInputError("V2 topic stable tag IDs are missing")
        topic_labels[topic_id] = {
            dimension: raw_labels.get(dimension)
            for dimension in ("T3", "T4", "T5")
        }
        if any(not isinstance(value, str) or not value.strip()
               for value in topic_labels[topic_id].values()):
            raise ExecutorInputError("V2 topic stable T3/T4/T5 IDs are incomplete")

    result = optimize_portfolios(
        slots, candidates, initial, topic_labels,
        lambda left, right: _cosine_similarity(topic_by_id, left, right),
        capacities,
        account_topic_capacity=config.same_account_topic_max,
        reserved_account_topics={},
        policy=portfolio,
        allow_unassignment=False,
    )
    assigned_by_slot = {assignment.slot_id: assignment for assignment in result.assignments}
    candidate_by_key = {(candidate.slot_id, candidate.topic_id): candidate
                        for candidate in candidates}
    candidate_slots = {candidate.slot_id for candidate in candidates}
    used_account: Counter[tuple[str, str]] = Counter(
        (assignment.account_id, assignment.topic_id) for assignment in result.assignments
    )
    used_global: Counter[str] = Counter(
        assignment.topic_id for assignment in result.assignments
    )
    fallback_used_account: Counter[tuple[str, str]] = Counter()
    fallback_counters: Counter[str] = Counter()
    proposed = []
    for slot in sorted(slots, key=lambda item: (item.publish_date, item.account_id, item.slot_id)):
        assignment = assigned_by_slot.get(slot.slot_id)
        role = roles[(slot.account_id, slot.publish_date)]
        if assignment is not None:
            candidate = candidate_by_key.get((slot.slot_id, assignment.topic_id))
            if candidate is None:
                raise ExecutorInputError("optimized assignment has no candidate evidence")
            proposed.append({
                "account_id": slot.account_id, "publish_date": slot.publish_date,
                "outcome": "matched", "topic_id": assignment.topic_id,
                "content_role": role, "fit_score": round(candidate.fit_score * 100.0, 6),
            })
            continue

        account = account_by_id[slot.account_id]
        choices = []
        for topic in fallback_topics:
            fallback_counters["topics_examined"] += 1
            topic_id = str(topic.get("topic_id") or "")
            if not _city_allowed(account, topic, fallback=True):
                fallback_counters["city_excluded"] += 1
                continue
            if topic_id in history.get(slot.account_id, set()):
                fallback_counters["history_excluded"] += 1
                continue
            if fallback_topic_roles[topic_id] is None:
                fallback_counters["unknown_role_excluded"] += 1
                continue
            if fallback_topic_roles[topic_id] != role:
                fallback_counters["role_excluded"] += 1
                continue
            if used_account[(slot.account_id, topic_id)] >= config.same_account_topic_max:
                fallback_counters["account_capacity_excluded"] += 1
                continue
            if config.global_topic_max is not None \
                    and used_global[topic_id] >= config.global_topic_max:
                fallback_counters["global_capacity_excluded"] += 1
                continue
            if fallback_used_account[(slot.account_id, topic_id)] >= config.fallback_same_account_max:
                fallback_counters["fallback_account_capacity_excluded"] += 1
                continue
            heat_known = bool(topic.get("heat_known"))
            heat = topic.get("topic_heat") if heat_known else None
            if heat_known and (type(heat) not in (int, float) or not math.isfinite(float(heat))):
                raise ExecutorInputError("fallback heat is invalid")
            if not heat_known:
                fallback_counters["unknown_heat_candidates"] += 1
            fallback_counters["eligible_candidates"] += 1
            choices.append((0 if heat_known else 1,
                            -(float(heat) if heat_known else 0.0), topic_id, topic))
        choices.sort(key=lambda item: item[:3])
        if choices:
            topic_id = choices[0][2]
            used_account[(slot.account_id, topic_id)] += 1
            used_global[topic_id] += 1
            fallback_used_account[(slot.account_id, topic_id)] += 1
            proposed.append({
                "account_id": slot.account_id, "publish_date": slot.publish_date,
                "outcome": "fallback", "topic_id": topic_id,
                "content_role": role,
                "reason": ("portfolio_capacity_or_objective_unassigned"
                           if slot.slot_id in candidate_slots
                           else "normal_candidates_exhausted"),
            })
        else:
            fallback_counters["slots_without_fallback"] += 1
            proposed.append({
                "account_id": slot.account_id, "publish_date": slot.publish_date,
                "outcome": "failed", "reason": "no_eligible_normal_or_fallback_topic",
            })

    matched = sum(position["outcome"] == "matched" for position in proposed)
    fallback = sum(position["outcome"] == "fallback" for position in proposed)
    failed = sum(position["outcome"] == "failed" for position in proposed)
    target_traffic = sum(role == "\u6d41\u91cf" for role in roles.values())
    target_conversion = sum(role == "\u8f6c\u5316" for role in roles.values())
    actual_traffic = sum(position.get("content_role") == "\u6d41\u91cf"
                         for position in proposed if position["outcome"] != "failed")
    actual_conversion = sum(position.get("content_role") == "\u8f6c\u5316"
                            for position in proposed if position["outcome"] != "failed")
    summaries = [
        {"stage": "hard_gate", "summary": {
        "eligible_edges": eligible_edges,
        "city_excluded_edges": city_excluded,
        "history_excluded_edges": history_excluded,
        "t2_role_excluded_edges": role_excluded,
        "unknown_t2_role_excluded_edges": unknown_role_excluded,
        "role_eligible_edges": eligible_edges - role_excluded,
        "account_count": len(accounts), "topic_count": len(topics),
        }},
        {"stage": "recall", "summary": {
        "top_k": config.top_k, "min_cosine": config.min_cosine,
        "recalled_edges": recalled_edges,
        "accounts_without_recall": sum(not account_recall_count.get(account_id, 0)
                                        for account_id in account_by_id),
        "slots_without_recall": sum(not slot_recall_count.get(slot.slot_id, 0)
                                     for slot in slots),
        }},
        {"stage": "fit", "summary": {
        "scored_edges": recalled_edges,
        "score_scale": "positive_cosine_0_1; output 0-100",
        }},
        {"stage": "global_allocation", "summary": {
        "matched_positions": matched, "fallback_positions": fallback,
        "failed_positions": failed,
        "unique_matched_topics": len({p["topic_id"] for p in proposed
                                       if p["outcome"] == "matched"}),
        "maximum_matched_topic_reuse": max((sum(
            p["outcome"] == "matched" and p.get("topic_id") == topic_id for p in proposed
        ) for topic_id in topic_by_id), default=0),
        }},
        {"stage": "composition", "summary": {
        "target_traffic_positions": target_traffic,
        "target_conversion_positions": target_conversion,
        "actual_traffic_positions": actual_traffic,
        "actual_conversion_positions": actual_conversion,
        "failed_positions": failed,
        "fallback_audit": dict(fallback_counters),
        "portfolio_objective": {
            "relevance": round(result.metrics.relevance, 6),
            "coverage": round(result.metrics.coverage, 6),
            "balance": round(result.metrics.balance, 6),
            "redundancy": round(result.metrics.redundancy, 6),
            "utility": round(result.metrics.utility, 6),
        },
        "objective_weights": {
            "relevance": portfolio.relevance_weight,
            "coverage": portfolio.coverage_weight,
            "balance": portfolio.balance_weight,
            "redundancy": portfolio.redundancy_weight,
        },
        "mmr_relevance_weight": portfolio.mmr_relevance_weight,
        "shortlist_per_slot": portfolio.shortlist_per_slot,
        "mmr_input_edges": result.candidate_edges,
        "mmr_shortlisted_edges": result.shortlisted_edges,
        "mmr_pruned_edges": result.candidate_edges - result.shortlisted_edges,
        "search_edges_including_preserved_initial": result.search_edges,
        "improvement_passes": result.improvement_passes,
        "local_optimum_reached": result.converged,
        }},
    ]
    return MatchingEvaluation.model_validate({
        **identity, "implementation_key": IMPLEMENTATION_KEY,
        "stages": summaries, "positions": proposed,
    })
