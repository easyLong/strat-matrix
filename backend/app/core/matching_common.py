"""Shared deterministic candidate rules used by both executor versions.

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

from ..matching_contracts import MatchingEvaluation, MatchingPolicyDocument


CANDIDATE_CONTRACT_KEY = "builtin-cosine-balanced-v1"
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


def candidate_config(policy: dict) -> tuple[MatchingPolicyDocument, ExecutorConfig]:
    """Validate the exact machine-readable contract for the built-in engine."""
    document = MatchingPolicyDocument.model_validate(policy)
    if document.schema_version != 2:
        raise ExecutorPolicyError("built-in executor requires policy schema_version=2")
    if document.implementation_key != CANDIDATE_CONTRACT_KEY:
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


def dot_similarity(left: list, right: list) -> float:
    if not left or len(left) != len(right):
        raise ExecutorInputError("vector dimensions do not match")
    try:
        value = math.fsum(float(a) * float(b) for a, b in zip(left, right))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ExecutorInputError("vector contains an invalid value") from exc
    if not math.isfinite(value):
        raise ExecutorInputError("cosine similarity is not finite")
    return max(-1.0, min(1.0, value))


def account_city(account: dict) -> str:
    try:
        city = account["profile"]["account"].get("city") or ""
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("account profile is missing account.city") from exc
    return str(city).strip()


def topic_cities(topic: dict, *, fallback: bool = False) -> list[str]:
    try:
        raw = (topic["source_payload"].get("applicable_cities") or []) if fallback \
            else (topic["profile"].get("applicable_cities") or [])
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("topic city scope is malformed") from exc
    if not isinstance(raw, list):
        raise ExecutorInputError("topic applicable_cities must be an array")
    return sorted({str(value).strip() for value in raw if str(value).strip()})


def city_allowed(account: dict, topic: dict, *, fallback: bool = False) -> bool:
    cities = topic_cities(topic, fallback=fallback)
    return not cities or account_city(account) in cities


def history_by_account(supplemental: dict) -> dict[str, set[str]]:
    try:
        rows = supplemental["history"]["observed_records"]
    except (KeyError, TypeError) as exc:
        raise ExecutorInputError("history snapshot is missing") from exc
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("reference_known") and row.get("topic_type") == "普通" and row.get("topic_id"):
            result[str(row["account_id"])].add(str(row["topic_id"]))
    return result


def usage_by_topic(supplemental: dict) -> dict[str, tuple[bool, int | None]]:
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


def fit_score(cosine: float) -> float:
    return round(max(0.0, min(1.0, cosine)) * 100.0, 6)


def stage_targets(inputs: dict) -> dict[str, int]:
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


def role_plan(account: dict, positions: list[dict], traffic_percent: int) -> dict[tuple[str, str], str]:
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
