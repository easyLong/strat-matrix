"""Composable algorithm primitives for the V102 matching method.

This module provides strict, deterministic primitives used by the separately
versioned V2 portfolio executor. Generic multi-feature extraction remains an
injected interface; the current production V2 executor uses the approved cosine
candidate contract until account-side taxonomy features are frozen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
import math
from typing import Callable, Iterable, Mapping, Protocol, Sequence


class AlgorithmConfigurationError(ValueError):
    """A V2 policy is incomplete or internally inconsistent."""


class AlgorithmInputError(ValueError):
    """Frozen matching inputs cannot be interpreted safely."""


@dataclass(frozen=True)
class GateDecision:
    eligible: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Slot:
    slot_id: str
    account_id: str
    publish_date: str


@dataclass(frozen=True)
class Candidate:
    slot_id: str
    account_id: str
    topic_id: str
    signals: Mapping[str, float]
    fit_score: float
    allocation_score: float | None = None
    audit: Mapping[str, object] = field(default_factory=dict)

    @property
    def utility(self) -> float:
        return self.fit_score if self.allocation_score is None else self.allocation_score


@dataclass(frozen=True)
class Assignment:
    slot_id: str
    account_id: str
    topic_id: str
    utility: float


class HardGate(Protocol):
    def evaluate(self, account: Mapping[str, object],
                 topic: Mapping[str, object]) -> GateDecision: ...


class FeatureExtractor(Protocol):
    """Return named, normalized [0, 1] account-topic fit signals."""

    def extract(self, account: Mapping[str, object],
                topic: Mapping[str, object]) -> Mapping[str, float]: ...


class PortfolioUtility(Protocol):
    """Business-owned utility for comparing a complete account slate."""

    def score(self, account_id: str,
              slate: Sequence[Candidate]) -> float: ...


@dataclass(frozen=True)
class FitPolicy:
    weights: Mapping[str, float]
    missing_signal: str
    minimum_weight_coverage: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "FitPolicy":
        if set(value) != {"weights", "missing_signal", "minimum_weight_coverage"}:
            raise AlgorithmConfigurationError(
                "fit policy requires exactly weights, missing_signal, and minimum_weight_coverage"
            )
        raw_weights = value["weights"]
        if not isinstance(raw_weights, Mapping) or not raw_weights:
            raise AlgorithmConfigurationError("weights must be a non-empty object")
        weights: dict[str, float] = {}
        for name, raw in raw_weights.items():
            if not isinstance(name, str) or not name.strip():
                raise AlgorithmConfigurationError("weight names must be non-empty strings")
            if type(raw) not in (int, float) or not math.isfinite(float(raw)) or raw < 0:
                raise AlgorithmConfigurationError(f"weight {name!r} must be finite and non-negative")
            weights[name] = float(raw)
        if not math.isclose(math.fsum(weights.values()), 1.0, rel_tol=0, abs_tol=1e-9):
            raise AlgorithmConfigurationError("fit weights must sum to 1")
        missing = value["missing_signal"]
        if not isinstance(missing, str) or missing not in {"reject", "renormalize"}:
            raise AlgorithmConfigurationError(
                "missing_signal must explicitly be reject or renormalize; zero imputation is unsupported"
            )
        coverage = value["minimum_weight_coverage"]
        if type(coverage) not in (int, float) or not math.isfinite(float(coverage)) \
                or not 0 < coverage <= 1:
            raise AlgorithmConfigurationError("minimum_weight_coverage must be explicitly set in (0, 1]")
        return cls(weights=weights, missing_signal=missing,
                   minimum_weight_coverage=float(coverage))


def weighted_fit(
    signals: Mapping[str, float], policy: FitPolicy,
) -> tuple[float, dict[str, float], float]:
    """Score an account-topic pair and retain each weighted contribution."""
    unknown = set(signals) - set(policy.weights)
    if unknown:
        raise AlgorithmInputError(f"unconfigured fit signals: {sorted(unknown)}")
    normalized: dict[str, float] = {}
    for name, raw in signals.items():
        if type(raw) not in (int, float) or not math.isfinite(float(raw)) or not 0 <= raw <= 1:
            raise AlgorithmInputError(f"signal {name!r} must be finite and in [0, 1]")
        normalized[name] = float(raw)
    missing = set(policy.weights) - set(normalized)
    if missing and policy.missing_signal == "reject":
        raise AlgorithmInputError(f"required fit signals are missing: {sorted(missing)}")
    active = {name: weight for name, weight in policy.weights.items() if name in normalized}
    denominator = math.fsum(active.values())
    if denominator <= 0:
        raise AlgorithmInputError("no configured fit signal is available")
    if denominator + 1e-12 < policy.minimum_weight_coverage:
        raise AlgorithmInputError(
            f"available fit weight {denominator:.6f} is below minimum coverage "
            f"{policy.minimum_weight_coverage:.6f}"
        )
    contributions = {
        name: normalized[name] * weight / denominator
        for name, weight in active.items()
    }
    score = math.fsum(contributions.values())
    return score, contributions, denominator


def score_candidates(
    slots: Sequence[Slot],
    accounts: Mapping[str, Mapping[str, object]],
    topics: Mapping[str, Mapping[str, object]],
    gate: HardGate,
    features: FeatureExtractor,
    fit_policy: FitPolicy,
) -> tuple[list[Candidate], dict[str, list[str]]]:
    """Apply the injected hard gate and score every eligible slot-topic edge."""
    candidates: list[Candidate] = []
    rejected: dict[str, list[str]] = {}
    for slot in sorted(slots, key=lambda item: (item.publish_date, item.account_id, item.slot_id)):
        try:
            account = accounts[slot.account_id]
        except KeyError as exc:
            raise AlgorithmInputError(f"unknown account {slot.account_id}") from exc
        for topic_id in sorted(topics):
            topic = topics[topic_id]
            decision = gate.evaluate(account, topic)
            edge_key = f"{slot.slot_id}:{topic_id}"
            if not decision.eligible:
                rejected[edge_key] = list(decision.reasons)
                continue
            signals = dict(features.extract(account, topic))
            fit, contributions, coverage = weighted_fit(signals, fit_policy)
            candidates.append(Candidate(
                slot_id=slot.slot_id,
                account_id=slot.account_id,
                topic_id=topic_id,
                signals=signals,
                fit_score=fit,
                audit={"weighted_contributions": contributions,
                       "fit_weight_coverage": coverage},
            ))
    return candidates, rejected


def mmr_utility(
    relevance: float,
    selected_topic_ids: Sequence[str],
    candidate_topic_id: str,
    similarity: Callable[[str, str], float],
    *,
    relevance_weight: float,
 ) -> tuple[float, float]:
    """Return MMR utility and its redundancy term for one slate addition.

    The caller owns slate construction and ordering. This keeps the formula
    reusable inside a portfolio/assignment strategy without silently choosing
    how account slots are traversed.
    Similarity must use the declared semantic space and return [0, 1].
    """
    if type(relevance_weight) not in (int, float) or not math.isfinite(float(relevance_weight)) \
            or not 0 <= relevance_weight <= 1:
        raise AlgorithmConfigurationError("relevance_weight must be explicitly set in [0, 1]")
    if type(relevance) not in (int, float) or not math.isfinite(float(relevance)) \
            or not 0 <= relevance <= 1:
        raise AlgorithmInputError("MMR relevance must be finite and in [0, 1]")
    similarities = [similarity(candidate_topic_id, topic_id) for topic_id in selected_topic_ids]
    if any(type(value) not in (int, float) or not math.isfinite(float(value))
           or not 0 <= value <= 1 for value in similarities):
        raise AlgorithmInputError("MMR similarity must be finite and in [0, 1]")
    redundancy = max((float(value) for value in similarities), default=0.0)
    score = float(relevance_weight) * float(relevance) \
        - (1.0 - float(relevance_weight)) * redundancy
    return score, redundancy


@dataclass
class _FlowEdge:
    to: int
    reverse: int
    capacity: int
    cost: int


def _add_edge(graph: list[list[_FlowEdge]], source: int, target: int,
              capacity: int, cost: int) -> _FlowEdge:
    forward = _FlowEdge(target, len(graph[target]), capacity, cost)
    backward = _FlowEdge(source, len(graph[source]), 0, -cost)
    graph[source].append(forward)
    graph[target].append(backward)
    return forward


def allocate_matrix(
    slots: Sequence[Slot],
    candidates: Sequence[Candidate],
    topic_capacities: Mapping[str, int],
    *,
    account_topic_capacity: int,
    reserved_account_topics: Mapping[tuple[str, str], int],
) -> list[Assignment]:
    """Maximize total assignment utility with explicit capacities.

    The flow graph enforces one assignment per slot, global topic capacities,
    and per-account topic reuse capacity after fixed/reserved uses. No topic cap
    or reuse default is inferred. Unassigned slots have zero utility. Utility
    is quantized to 1e-6 for deterministic integer flow.
    """
    if type(account_topic_capacity) is not int or account_topic_capacity < 1:
        raise AlgorithmConfigurationError("account_topic_capacity must be explicit and positive")
    if any(type(amount) is not int or amount < 0 for amount in reserved_account_topics.values()):
        raise AlgorithmConfigurationError("reserved account-topic amounts must be non-negative integers")
    if any(amount > account_topic_capacity for amount in reserved_account_topics.values()):
        raise AlgorithmInputError("reserved account-topic use already exceeds capacity")
    for topic_id, capacity in topic_capacities.items():
        if type(capacity) is not int or capacity < 0:
            raise AlgorithmConfigurationError(f"capacity for {topic_id!r} must be a non-negative integer")
    slot_by_id = {slot.slot_id: slot for slot in slots}
    if len(slot_by_id) != len(slots):
        raise AlgorithmInputError("slot ids must be unique")
    candidate_by_key: dict[tuple[str, str], Candidate] = {}
    for candidate in candidates:
        if candidate.slot_id not in slot_by_id:
            raise AlgorithmInputError(f"candidate references unknown slot {candidate.slot_id}")
        if candidate.account_id != slot_by_id[candidate.slot_id].account_id:
            raise AlgorithmInputError("candidate account_id does not match its slot")
        if not math.isfinite(candidate.utility):
            raise AlgorithmInputError("candidate utility must be finite")
        if candidate.topic_id not in topic_capacities:
            raise AlgorithmConfigurationError(f"missing global capacity for topic {candidate.topic_id}")
        key = (candidate.slot_id, candidate.topic_id)
        previous = candidate_by_key.get(key)
        if previous is None or candidate.utility > previous.utility:
            candidate_by_key[key] = candidate

    slot_ids = sorted(slot_by_id)
    pair_ids = sorted({(c.account_id, c.topic_id) for c in candidate_by_key.values()})
    topic_ids = sorted(topic_capacities)
    source = 0
    slot_nodes = {key: i + 1 for i, key in enumerate(slot_ids)}
    offset = 1 + len(slot_nodes)
    pair_nodes = {key: offset + i for i, key in enumerate(pair_ids)}
    offset += len(pair_nodes)
    topic_nodes = {key: offset + i for i, key in enumerate(topic_ids)}
    sink = offset + len(topic_nodes)
    graph: list[list[_FlowEdge]] = [[] for _ in range(sink + 1)]
    for slot_id in slot_ids:
        _add_edge(graph, source, slot_nodes[slot_id], 1, 0)
    for account_topic, node in pair_nodes.items():
        remaining_capacity = account_topic_capacity - reserved_account_topics.get(account_topic, 0)
        _add_edge(graph, node, topic_nodes[account_topic[1]], remaining_capacity, 0)
    for topic_id in topic_ids:
        _add_edge(graph, topic_nodes[topic_id], sink, topic_capacities[topic_id], 0)

    tracked: list[tuple[Candidate, _FlowEdge]] = []
    for candidate in sorted(candidate_by_key.values(), key=lambda item: (item.slot_id, item.topic_id)):
        edge = _add_edge(
            graph,
            slot_nodes[candidate.slot_id],
            pair_nodes[(candidate.account_id, candidate.topic_id)],
            1,
            -round(candidate.utility * 1_000_000),
        )
        tracked.append((candidate, edge))

    # Initialize feasible node potentials once (forward candidate edges have
    # negative costs), then use Dijkstra on non-negative reduced costs.
    node_count = len(graph)
    potential: list[int | None] = [None] * node_count
    potential[source] = 0
    for _ in range(node_count - 1):
        changed = False
        for node in range(node_count):
            if potential[node] is None:
                continue
            for edge in graph[node]:
                if edge.capacity <= 0:
                    continue
                next_distance = potential[node] + edge.cost
                if potential[edge.to] is None or next_distance < potential[edge.to]:
                    potential[edge.to] = next_distance
                    changed = True
        if not changed:
            break
    potential = [value if value is not None else 0 for value in potential]

    while True:
        distance: list[int | None] = [None] * node_count
        previous: list[tuple[int, int] | None] = [None] * node_count
        distance[source] = 0
        queue = [(0, source)]
        while queue:
            current_distance, node = heapq.heappop(queue)
            if distance[node] != current_distance:
                continue
            for edge_index, edge in enumerate(graph[node]):
                if edge.capacity <= 0:
                    continue
                reduced_cost = edge.cost + potential[node] - potential[edge.to]
                next_distance = current_distance + reduced_cost
                if distance[edge.to] is None or next_distance < distance[edge.to]:
                    distance[edge.to] = next_distance
                    previous[edge.to] = (node, edge_index)
                    heapq.heappush(queue, (next_distance, edge.to))
        if distance[sink] is None:
            break
        original_path_cost = distance[sink] - potential[source] + potential[sink]
        if original_path_cost >= 0:
            # An unassigned slot has zero utility. Stop when every remaining
            # augmentation would reduce (or leave unchanged) total utility.
            break
        for node, value in enumerate(distance):
            if value is not None:
                potential[node] += value
        node = sink
        while node != source:
            step = previous[node]
            if step is None:
                raise AlgorithmInputError("matrix allocation produced an incomplete augmenting path")
            parent, edge_index = step
            edge = graph[parent][edge_index]
            edge.capacity -= 1
            graph[node][edge.reverse].capacity += 1
            node = parent

    assignments = [
        Assignment(candidate.slot_id, candidate.account_id, candidate.topic_id, candidate.utility)
        for candidate, edge in tracked if edge.capacity == 0
    ]
    return sorted(assignments, key=lambda item: (item.account_id, item.slot_id, item.topic_id))


def evaluate_portfolios(
    assignments: Sequence[Assignment],
    candidates: Sequence[Candidate],
    utility: PortfolioUtility,
) -> dict[str, float]:
    """Calculate account slate utility with an injected, reviewed objective."""
    by_key = {(item.slot_id, item.topic_id): item for item in candidates}
    grouped: dict[str, list[Candidate]] = {}
    for assignment in assignments:
        candidate = by_key.get((assignment.slot_id, assignment.topic_id))
        if candidate is None:
            raise AlgorithmInputError("assigned edge has no candidate audit record")
        grouped.setdefault(assignment.account_id, []).append(candidate)
    scores: dict[str, float] = {}
    for account_id, slate in sorted(grouped.items()):
        score = utility.score(account_id, sorted(slate, key=lambda item: item.slot_id))
        if type(score) not in (int, float) or not math.isfinite(float(score)):
            raise AlgorithmInputError(f"portfolio utility for {account_id} is invalid")
        scores[account_id] = float(score)
    return scores
