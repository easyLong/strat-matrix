"""Shared V19 vector, history, role and strict parameter helpers."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any

from ..matching_contracts import MatchingPolicyDocument


REQUIRED_INPUTS = {
    "accounts", "topics", "config", "positions",
    "fallback_topics", "history", "official_usage",
}


class ExecutorPolicyError(ValueError):
    """The approved policy does not describe this concrete implementation."""


class ExecutorInputError(ValueError):
    """The leased immutable inputs cannot be executed safely."""


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


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ExecutorPolicyError(f"{name} must be an integer between {low} and {high}")
    return value


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
