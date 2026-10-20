"""Deterministic built-in Matching Executor V1.

The executor never interprets natural-language policy definitions. It only runs
an approved policy whose implementation_key and structured decision parameters
match the contract below. Inputs are the immutable snapshots returned by the
existing matching-task lease.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any

from .matching_contracts import MatchingEvaluation, MatchingPolicyDocument


IMPLEMENTATION_KEY = "builtin-cosine-balanced-v1"
REQUIRED_INPUTS = {
    "accounts", "topics", "config", "positions",
    "fallback_topics", "history", "official_usage",
}


class ExecutorPolicyError(ValueError):
    """The approved policy does not describe this concrete implementation."""


class ExecutorInputError(ValueError):
    """The leased immutable inputs cannot be executed safely."""


@dataclass(frozen=True)
class ExecutorConfig:
    top_k: int
    min_cosine: float
    same_account_topic_max: int
    global_topic_max: int | None
    global_reuse_penalty: float
    official_usage_penalty: float
    fallback_same_account_max: int


def _strict_parameters(document: MatchingPolicyDocument, code: str,
                       expected: set[str]) -> dict[str, Any]:
    try:
        params = document.decisions[code].parameters
    except KeyError as exc:
        raise ExecutorPolicyError(f"missing decision {code}") from exc
    if set(params) != expected:
        raise ExecutorPolicyError(
            f"{code} parameters must be exactly {sorted(expected)}"
        )
    return params


def _number(value: Any, name: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ExecutorPolicyError(f"{name} must be a finite number")
    number = float(value)
    if not low <= number <= high:
        raise ExecutorPolicyError(f"{name} must be between {low} and {high}")
    return number


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ExecutorPolicyError(f"{name} must be an integer between {low} and {high}")
    return value


def executor_config(policy: dict) -> tuple[MatchingPolicyDocument, ExecutorConfig]:
    """Validate the exact machine-readable contract for the built-in engine."""
    document = MatchingPolicyDocument.model_validate(policy)
    if document.schema_version != 2:
        raise ExecutorPolicyError("built-in executor requires policy schema_version=2")
    if document.implementation_key != IMPLEMENTATION_KEY:
        raise ExecutorPolicyError("unsupported implementation_key")
    if set(document.required_inputs) != REQUIRED_INPUTS:
        raise ExecutorPolicyError("built-in executor requires all V2 frozen inputs")
    if document.approval_errors():
        raise ExecutorPolicyError("policy is not approval-complete")

    p1 = _strict_parameters(document, "ALG-01", {"similarity"})
    p2 = _strict_parameters(document, "ALG-02", {"city_gate", "history_gate"})
    p3 = _strict_parameters(document, "ALG-03", {"top_k", "min_cosine"})
    p4 = _strict_parameters(document, "ALG-04", {"score_scale"})
    p5 = _strict_parameters(document, "ALG-05", {
        "same_account_topic_max", "global_topic_max",
        "global_reuse_penalty", "official_usage_penalty",
    })
    p6 = _strict_parameters(document, "ALG-06", {"rounding", "role_order"})
    p7 = _strict_parameters(document, "ALG-07", {"official_usage_unknown_rank"})
    p8 = _strict_parameters(document, "ALG-08", {"fallback_sort", "fallback_same_account_max"})
    p9 = _strict_parameters(document, "ALG-09", {"no_candidate", "system_error"})

    expected_literals = {
        "ALG-01.similarity": (p1["similarity"], "cosine_unit_vectors"),
        "ALG-02.city_gate": (p2["city_gate"], "allow_empty_or_exact"),
        "ALG-02.history_gate": (p2["history_gate"], "exclude_observed_account_history"),
        "ALG-04.score_scale": (p4["score_scale"], "positive_cosine_0_100"),
        "ALG-06.rounding": (p6["rounding"], "half_up"),
        "ALG-06.role_order": (p6["role_order"], "even_spread"),
        "ALG-07.official_usage_unknown_rank": (p7["official_usage_unknown_rank"], "after_known"),
        "ALG-08.fallback_sort": (p8["fallback_sort"], "heat_desc_topic_id"),
        "ALG-09.no_candidate": (p9["no_candidate"], "fallback_then_failed"),
        "ALG-09.system_error": (p9["system_error"], "task_failure"),
    }
    for name, (actual, expected) in expected_literals.items():
        if actual != expected:
            raise ExecutorPolicyError(f"{name} must be {expected}")

    global_max = p5["global_topic_max"]
    if global_max is not None:
        global_max = _integer(global_max, "global_topic_max", 1, 20000)
    config = ExecutorConfig(
        top_k=_integer(p3["top_k"], "top_k", 1, 1000),
        min_cosine=_number(p3["min_cosine"], "min_cosine", -1.0, 1.0),
        same_account_topic_max=_integer(
            p5["same_account_topic_max"], "same_account_topic_max", 1, 1000
        ),
        global_topic_max=global_max,
        global_reuse_penalty=_number(
            p5["global_reuse_penalty"], "global_reuse_penalty", 0.0, 100.0
        ),
        official_usage_penalty=_number(
            p5["official_usage_penalty"], "official_usage_penalty", 0.0, 100.0
        ),
        fallback_same_account_max=_integer(
            p8["fallback_same_account_max"], "fallback_same_account_max", 1, 1000
        ),
    )
    return document, config


def _dot(left: list, right: list) -> float:
    if not left or len(left) != len(right):
        raise ExecutorInputError("vector dimensions do not match")
    try:
        value = math.fsum(float(a) * float(b) for a, b in zip(left, right))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExecutorInputError("vector contains an invalid value") from exc
    if not math.isfinite(value):
        raise ExecutorInputError("cosine similarity is not finite")
    return max(-1.0, min(1.0, value))


def _account_city(account: dict) -> str:
    try:
        city = account["profile"]["account"].get("city") or ""
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("account profile is missing account.city") from exc
    return str(city).strip()


def _topic_cities(topic: dict, *, fallback: bool = False) -> list[str]:
    try:
        raw = (topic["source_payload"].get("applicable_cities") or []) if fallback \
            else (topic["profile"].get("applicable_cities") or [])
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("topic city scope is malformed") from exc
    if not isinstance(raw, list):
        raise ExecutorInputError("topic applicable_cities must be an array")
    return sorted({str(value).strip() for value in raw if str(value).strip()})


def _city_allowed(account: dict, topic: dict, *, fallback: bool = False) -> bool:
    cities = _topic_cities(topic, fallback=fallback)
    return not cities or _account_city(account) in cities


def _history_by_account(supplemental: dict) -> dict[str, set[str]]:
    try:
        rows = supplemental["history"]["observed_records"]
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("history snapshot is missing") from exc
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("reference_known") and row.get("topic_type") == "普通" and row.get("topic_id"):
            result[str(row["account_id"])].add(str(row["topic_id"]))
    return result


def _usage_by_topic(supplemental: dict) -> dict[str, tuple[bool, int | None]]:
    try:
        rows = supplemental["official_usage"]["records"]
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("official usage snapshot is missing") from exc
    result = {}
    for row in rows:
        known = bool(row.get("known"))
        count = row.get("official_use_count") if known else None
        if known and (type(count) is not int or count < 0):
            raise ExecutorInputError("official usage count is invalid")
        result[str(row["topic_id"])] = (known, count)
    return result


def _fit_score(cosine: float) -> float:
    return round(max(0.0, min(1.0, cosine)) * 100.0, 6)


def _stage_targets(inputs: dict) -> dict[str, int]:
    try:
        targets = inputs["config"]["stage_targets"]
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("config.stage_targets is missing") from exc
    result = {}
    for target in targets:
        name, traffic = target.get("name"), target.get("traffic")
        conversion = target.get("conversion")
        if not isinstance(name, str) or type(traffic) is not int or type(conversion) is not int \
                or traffic < 0 or conversion < 0 or traffic + conversion != 100:
            raise ExecutorInputError("stage target is invalid")
        result[name] = traffic
    return result


def _role_plan(account: dict, positions: list[dict], traffic_percent: int) -> dict[tuple[str, str], str]:
    ordered = sorted(positions, key=lambda item: item["publish_date"])
    total = len(ordered)
    if not total:
        return {}
    traffic_count = int(
        (Decimal(total * traffic_percent) / Decimal(100)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    result = {}
    for index, position in enumerate(ordered):
        before = (index * traffic_count) // total
        after = ((index + 1) * traffic_count) // total
        role = "流量" if after > before else "转化"
        result[(position["account_id"], position["publish_date"])] = role
    return result


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

    history = _history_by_account(supplemental)
    usage = _usage_by_topic(supplemental)
    hard_gate_total = 0
    hard_gate_city_excluded = 0
    hard_gate_history_excluded = 0
    recalled: dict[str, list[dict]] = {}
    scored_edges = 0

    for account_id, account in sorted(account_by_id.items()):
        candidates = []
        for topic_id, topic in sorted(topic_by_id.items()):
            if not _city_allowed(account, topic):
                hard_gate_city_excluded += 1
                continue
            if topic_id in history.get(account_id, set()):
                hard_gate_history_excluded += 1
                continue
            hard_gate_total += 1
            cosine = _dot(account["vector"], topic["vector"])
            if cosine < config.min_cosine:
                continue
            candidates.append({
                "topic_id": topic_id,
                "cosine": cosine,
                "fit_score": _fit_score(cosine),
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
            if not topic_id or not _city_allowed(account, topic, fallback=True):
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

    traffic_targets = _stage_targets(inputs)
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
        plan = _role_plan(account, account_positions, traffic_targets[lifecycle])
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
