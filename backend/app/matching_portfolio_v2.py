"""V2 account-portfolio objective and deterministic search heuristic.

MMR is used to reduce the candidate search space. The final portfolio score
contains one explicit redundancy term; the MMR score is never added again.
The production V2 task executor imports this module for allocation refinement.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping, Sequence

from .matching_algorithm_v2 import (
    AlgorithmConfigurationError,
    AlgorithmInputError,
    Assignment,
    Candidate,
    Slot,
    mmr_utility,
)


@dataclass(frozen=True)
class PortfolioPolicy:
    relevance_weight: float
    coverage_weight: float
    balance_weight: float
    redundancy_weight: float
    mmr_relevance_weight: float
    shortlist_per_slot: int
    max_improvement_passes: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "PortfolioPolicy":
        expected = {
            "relevance_weight", "coverage_weight", "balance_weight",
            "redundancy_weight", "mmr_relevance_weight",
            "shortlist_per_slot", "max_improvement_passes",
        }
        if set(raw) != expected:
            raise AlgorithmConfigurationError(
                f"portfolio policy fields must be exactly {sorted(expected)}"
            )
        weights = []
        for name in ("relevance_weight", "coverage_weight", "balance_weight", "redundancy_weight"):
            value = raw[name]
            if type(value) not in (int, float) or not math.isfinite(float(value)) or value < 0:
                raise AlgorithmConfigurationError(f"{name} must be finite and non-negative")
            weights.append(float(value))
        if not math.isclose(math.fsum(weights), 1.0, rel_tol=0, abs_tol=1e-9):
            raise AlgorithmConfigurationError("portfolio objective weights must sum to 1")
        mmr_weight = raw["mmr_relevance_weight"]
        if type(mmr_weight) not in (int, float) or not math.isfinite(float(mmr_weight)) \
                or not 0 <= mmr_weight <= 1:
            raise AlgorithmConfigurationError("mmr_relevance_weight must be explicitly set in [0, 1]")
        shortlist = raw["shortlist_per_slot"]
        passes = raw["max_improvement_passes"]
        if type(shortlist) is not int or shortlist < 1:
            raise AlgorithmConfigurationError("shortlist_per_slot must be a positive integer")
        if type(passes) is not int or passes < 1:
            raise AlgorithmConfigurationError("max_improvement_passes must be a positive integer")
        return cls(
            relevance_weight=weights[0], coverage_weight=weights[1],
            balance_weight=weights[2], redundancy_weight=weights[3],
            mmr_relevance_weight=float(mmr_weight), shortlist_per_slot=shortlist,
            max_improvement_passes=passes,
        )


@dataclass(frozen=True)
class PortfolioMetrics:
    relevance: float
    coverage: float
    balance: float
    redundancy: float
    utility: float


@dataclass(frozen=True)
class PortfolioOptimizationResult:
    assignments: tuple[Assignment, ...]
    metrics: PortfolioMetrics
    improvement_passes: int
    converged: bool
    candidate_edges: int
    shortlisted_edges: int
    search_edges: int


def mmr_candidate_shortlist(
    slots: Sequence[Slot],
    candidates: Sequence[Candidate],
    similarity: Callable[[str, str], float],
    policy: PortfolioPolicy,
) -> list[Candidate]:
    """Build a per-account MMR shortlist in publish order.

    The best MMR candidate for each slot seeds the next slot's provisional
    slate. Up to ``shortlist_per_slot`` alternatives are retained so the global
    search can recover from cross-account capacity conflicts.
    """
    slots_by_account: dict[str, list[Slot]] = {}
    candidates_by_slot: dict[str, list[Candidate]] = {}
    for slot in slots:
        slots_by_account.setdefault(slot.account_id, []).append(slot)
    for candidate in candidates:
        candidates_by_slot.setdefault(candidate.slot_id, []).append(candidate)

    selected: list[Candidate] = []
    for account_id in sorted(slots_by_account):
        provisional_topics: list[str] = []
        ordered_slots = sorted(
            slots_by_account[account_id],
            key=lambda item: (item.publish_date, item.slot_id),
        )
        for slot in ordered_slots:
            ranked: list[tuple[float, str, Candidate]] = []
            for candidate in candidates_by_slot.get(slot.slot_id, []):
                if candidate.account_id != account_id:
                    raise AlgorithmInputError("candidate account_id does not match its slot")
                mmr_score, _ = mmr_utility(
                    candidate.fit_score, provisional_topics, candidate.topic_id,
                    similarity, relevance_weight=policy.mmr_relevance_weight,
                )
                ranked.append((mmr_score, candidate.topic_id, candidate))
            ranked.sort(key=lambda item: (-item[0], item[1]))
            selected.extend(item[2] for item in ranked[:policy.shortlist_per_slot])
            if ranked:
                provisional_topics.append(ranked[0][1])
    return selected


def _metrics(
    slots: Sequence[Slot],
    assignments: Sequence[Assignment],
    candidate_by_key: Mapping[tuple[str, str], Candidate],
    topic_labels: Mapping[str, Mapping[str, str]],
    similarity: Callable[[str, str], float],
    policy: PortfolioPolicy,
) -> PortfolioMetrics:
    slots_by_account: dict[str, list[Slot]] = {}
    for slot in slots:
        slots_by_account.setdefault(slot.account_id, []).append(slot)
    assignment_by_slot = {item.slot_id: item for item in assignments}
    if len(assignment_by_slot) != len(assignments):
        raise AlgorithmInputError("an account slot can have at most one assigned topic")

    if not slots:
        raise AlgorithmInputError("portfolio scoring requires at least one slot")
    relevance_by_account: list[float] = []
    coverage_by_account: list[float] = []
    balance_by_account: list[float] = []
    redundancy_by_account: list[float] = []

    for account_id, account_slots in sorted(slots_by_account.items()):
        expected_count = len(account_slots)
        selected: list[Candidate] = []
        for slot in account_slots:
            assignment = assignment_by_slot.get(slot.slot_id)
            if assignment is None:
                continue
            if assignment.account_id != account_id:
                raise AlgorithmInputError("assignment account_id does not match its slot")
            candidate = candidate_by_key.get((slot.slot_id, assignment.topic_id))
            if candidate is None:
                raise AlgorithmInputError("assignment references a candidate outside the search pool")
            if not math.isfinite(candidate.fit_score) or not 0 <= candidate.fit_score <= 1:
                raise AlgorithmInputError("portfolio Fit scores must be in [0, 1]")
            selected.append(candidate)
        relevance_by_account.append(
            math.fsum(candidate.fit_score for candidate in selected) / expected_count
        )

        coverage_dimensions = []
        for dimension in ("T3", "T4", "T5"):
            values: set[str] = set()
            for candidate in selected:
                labels = topic_labels.get(candidate.topic_id)
                value = labels.get(dimension) if labels else None
                if not isinstance(value, str) or not value.strip():
                    raise AlgorithmInputError(
                        f"selected topic {candidate.topic_id} is missing stable {dimension} label id"
                    )
                values.add(value)
            coverage_dimensions.append(len(values) / expected_count)
        coverage_by_account.append(math.fsum(coverage_dimensions) / 3.0)

        fit_values = [candidate.fit_score for candidate in selected]
        fit_values.extend([0.0] * (expected_count - len(fit_values)))
        # Range balance is transparent and bounded: equal per-slot Fit is 1;
        # missing slots count as 0; an empty slate has no balance credit.
        balance_by_account.append(
            max(0.0, 1.0 - (max(fit_values) - min(fit_values))) if selected else 0.0
        )

        pair_similarities: list[float] = []
        for index, candidate in enumerate(selected):
            for other in selected[index + 1:]:
                value = similarity(candidate.topic_id, other.topic_id)
                if type(value) not in (int, float) or not math.isfinite(float(value)) \
                        or not 0 <= value <= 1:
                    raise AlgorithmInputError("portfolio similarity must be finite and in [0, 1]")
                pair_similarities.append(float(value))
        redundancy_by_account.append(
            math.fsum(pair_similarities) / len(pair_similarities) if pair_similarities else 0.0
        )

    # Average account portfolios equally, matching the aggregation used for
    # coverage, balance, and redundancy even if account slot counts differ.
    relevance = math.fsum(relevance_by_account) / len(relevance_by_account)
    coverage = math.fsum(coverage_by_account) / len(coverage_by_account)
    balance = math.fsum(balance_by_account) / len(balance_by_account)
    redundancy = math.fsum(redundancy_by_account) / len(redundancy_by_account)
    utility = (
        policy.relevance_weight * relevance
        + policy.coverage_weight * coverage
        + policy.balance_weight * balance
        - policy.redundancy_weight * redundancy
    )
    return PortfolioMetrics(relevance, coverage, balance, redundancy, utility)


def optimize_portfolios(
    slots: Sequence[Slot],
    candidates: Sequence[Candidate],
    initial_assignments: Sequence[Assignment],
    topic_labels: Mapping[str, Mapping[str, str]],
    similarity: Callable[[str, str], float],
    topic_capacities: Mapping[str, int],
    *,
    account_topic_capacity: int,
    reserved_account_topics: Mapping[tuple[str, str], int],
    policy: PortfolioPolicy,
    allow_unassignment: bool,
) -> PortfolioOptimizationResult:
    """Improve an initial matrix assignment against the full portfolio score.

    This deterministic best-improvement search is a heuristic, not an exact
    solver for the non-linear cross-slot objective. It respects explicit topic
    and account-topic capacities and reports whether it reached a local fixed
    point before the configured pass limit.
    """
    if type(account_topic_capacity) is not int or account_topic_capacity < 1:
        raise AlgorithmConfigurationError("account_topic_capacity must be positive")
    if any(type(cap) is not int or cap < 0 for cap in topic_capacities.values()):
        raise AlgorithmConfigurationError("topic capacities must be non-negative integers")
    if any(type(amount) is not int or amount < 0 for amount in reserved_account_topics.values()):
        raise AlgorithmConfigurationError("reserved account-topic amounts must be non-negative integers")
    if any(amount > account_topic_capacity for amount in reserved_account_topics.values()):
        raise AlgorithmInputError("reserved account-topic use already exceeds capacity")
    similarity_cache: dict[tuple[str, str], float] = {}

    def cached_similarity(left_topic_id: str, right_topic_id: str) -> float:
        # Semantic similarity is symmetric; canonical keys avoid calculating
        # the same pair again while evaluating successive portfolio moves.
        key = tuple(sorted((left_topic_id, right_topic_id)))
        if key not in similarity_cache:
            value = similarity(left_topic_id, right_topic_id)
            if type(value) not in (int, float) or not math.isfinite(float(value)) \
                    or not 0 <= value <= 1:
                raise AlgorithmInputError("portfolio similarity must be finite and in [0, 1]")
            similarity_cache[key] = float(value)
        return similarity_cache[key]

    slot_by_id = {slot.slot_id: slot for slot in slots}
    if len(slot_by_id) != len(slots):
        raise AlgorithmInputError("slot ids must be unique")
    slots_by_account: dict[str, list[Slot]] = {}
    for slot in slots:
        slots_by_account.setdefault(slot.account_id, []).append(slot)
    candidate_by_key = {(item.slot_id, item.topic_id): item for item in candidates}
    if len(candidate_by_key) != len(candidates):
        raise AlgorithmInputError("duplicate slot-topic candidate edges")
    for candidate in candidates:
        slot = slot_by_id.get(candidate.slot_id)
        if slot is None:
            raise AlgorithmInputError(f"candidate references unknown slot {candidate.slot_id}")
        if slot.account_id != candidate.account_id:
            raise AlgorithmInputError("candidate account_id does not match its slot")
        if not math.isfinite(candidate.fit_score) or not 0 <= candidate.fit_score <= 1:
            raise AlgorithmInputError("candidate Fit score must be in [0, 1]")
        if candidate.topic_id not in topic_capacities:
            raise AlgorithmConfigurationError(f"missing capacity for candidate topic {candidate.topic_id}")
    for assignment in initial_assignments:
        if assignment.slot_id not in slot_by_id or \
                (assignment.slot_id, assignment.topic_id) not in candidate_by_key:
            raise AlgorithmInputError("initial assignment is outside the candidate matrix")
        if assignment.account_id != slot_by_id[assignment.slot_id].account_id:
            raise AlgorithmInputError("initial assignment account_id does not match its slot")

    shortlisted = mmr_candidate_shortlist(slots, candidates, cached_similarity, policy)
    # Preserve the valid starting point even if MMR pruning would remove it.
    shortlist_by_key = {(item.slot_id, item.topic_id): item for item in shortlisted}
    for assignment in initial_assignments:
        candidate = candidate_by_key[(assignment.slot_id, assignment.topic_id)]
        shortlist_by_key[(candidate.slot_id, candidate.topic_id)] = candidate
    search_candidates = list(shortlist_by_key.values())
    search_by_key = {(item.slot_id, item.topic_id): item for item in search_candidates}
    search_by_slot: dict[str, list[Candidate]] = {}
    for candidate in search_candidates:
        search_by_slot.setdefault(candidate.slot_id, []).append(candidate)

    current: dict[str, Assignment] = {item.slot_id: item for item in initial_assignments}
    if len(current) != len(initial_assignments):
        raise AlgorithmInputError("initial assignment has duplicate slot ids")

    def counts() -> tuple[dict[str, int], dict[tuple[str, str], int]]:
        global_counts: dict[str, int] = {}
        account_counts: dict[tuple[str, str], int] = {}
        for item in current.values():
            global_counts[item.topic_id] = global_counts.get(item.topic_id, 0) + 1
            key = (item.account_id, item.topic_id)
            account_counts[key] = account_counts.get(key, 0) + 1
        return global_counts, account_counts

    def current_metrics() -> PortfolioMetrics:
        return _metrics(
            slots, list(current.values()), search_by_key,
            topic_labels, cached_similarity, policy,
        )

    def account_utility(account_id: str) -> float:
        account_slots = slots_by_account[account_id]
        account_assignments = [
            current[slot.slot_id] for slot in account_slots
            if slot.slot_id in current
        ]
        return _metrics(
            account_slots, account_assignments, search_by_key,
            topic_labels, cached_similarity, policy,
        ).utility

    global_counts, account_counts = counts()
    for topic_id, amount in global_counts.items():
        if topic_id not in topic_capacities or amount > topic_capacities[topic_id]:
            raise AlgorithmInputError("initial assignment violates global topic capacity")
    if any(amount + reserved_account_topics.get(key, 0) > account_topic_capacity
           for key, amount in account_counts.items()):
        raise AlgorithmInputError("initial assignment violates account-topic capacity")

    passes = 0
    converged = False
    while passes < policy.max_improvement_passes:
        baseline_by_account = {
            account_id: account_utility(account_id)
            for account_id in slots_by_account
        }
        best_delta = 1e-12
        best_move: tuple[str, Candidate | None, str | None, Candidate | None] | None = None
        for slot in sorted(slots, key=lambda item: (item.publish_date, item.account_id, item.slot_id)):
            previous = current.get(slot.slot_id)
            alternatives: list[Candidate | None] = [None] if allow_unassignment else []
            alternatives.extend(sorted(
                search_by_slot.get(slot.slot_id, []),
                key=lambda item: item.topic_id,
            ))
            for candidate in alternatives:
                if previous and candidate and previous.topic_id == candidate.topic_id:
                    continue
                if previous is None and candidate is None:
                    continue

                trial_global = dict(global_counts)
                trial_account = dict(account_counts)
                if previous:
                    trial_global[previous.topic_id] -= 1
                    old_key = (previous.account_id, previous.topic_id)
                    trial_account[old_key] -= 1
                if candidate:
                    if candidate.account_id != slot.account_id:
                        raise AlgorithmInputError("candidate account_id does not match its slot")
                    if candidate.topic_id not in topic_capacities:
                        raise AlgorithmConfigurationError(f"missing capacity for {candidate.topic_id}")
                    trial_global[candidate.topic_id] = trial_global.get(candidate.topic_id, 0) + 1
                    new_key = (candidate.account_id, candidate.topic_id)
                    trial_account[new_key] = trial_account.get(new_key, 0) + 1
                if candidate and trial_global.get(candidate.topic_id, 0) > topic_capacities[candidate.topic_id]:
                    continue
                if candidate and trial_account[(candidate.account_id, candidate.topic_id)] \
                        + reserved_account_topics.get((candidate.account_id, candidate.topic_id), 0) \
                        > account_topic_capacity:
                    continue

                if candidate:
                    current[slot.slot_id] = Assignment(
                        slot.slot_id, slot.account_id, candidate.topic_id, candidate.utility
                    )
                else:
                    current.pop(slot.slot_id, None)
                delta = account_utility(slot.account_id) - baseline_by_account[slot.account_id]
                if previous:
                    current[slot.slot_id] = previous
                else:
                    current.pop(slot.slot_id, None)
                if delta > best_delta:
                    best_delta = delta
                    best_move = (slot.slot_id, candidate, None, None)

        # Two-slot swaps can improve a portfolio when neither one-sided move
        # is legal or beneficial under a full topic capacity.
        current_topic_slots: dict[str, list[str]] = {}
        for slot_id, item in current.items():
            current_topic_slots.setdefault(item.topic_id, []).append(slot_id)
        swap_pairs: set[tuple[str, str]] = set()
        for slot_id, previous in current.items():
            for candidate in search_by_slot.get(slot_id, []):
                if candidate.topic_id == previous.topic_id:
                    continue
                for other_slot_id in current_topic_slots.get(candidate.topic_id, []):
                    if other_slot_id == slot_id:
                        continue
                    other_previous = current[other_slot_id]
                    if (other_slot_id, previous.topic_id) not in search_by_key:
                        continue
                    pair = tuple(sorted((slot_id, other_slot_id)))
                    swap_pairs.add(pair)

        for first_slot_id, second_slot_id in sorted(swap_pairs):
            first_previous, second_previous = current[first_slot_id], current[second_slot_id]
            first_candidate = search_by_key.get((first_slot_id, second_previous.topic_id))
            second_candidate = search_by_key.get((second_slot_id, first_previous.topic_id))
            if first_candidate is None or second_candidate is None:
                continue
            trial_account = dict(account_counts)
            for previous in (first_previous, second_previous):
                key = (previous.account_id, previous.topic_id)
                trial_account[key] = trial_account.get(key, 0) - 1
            for candidate in (first_candidate, second_candidate):
                key = (candidate.account_id, candidate.topic_id)
                trial_account[key] = trial_account.get(key, 0) + 1
            if any(amount + reserved_account_topics.get(key, 0) > account_topic_capacity
                   for key, amount in trial_account.items()):
                continue
            current[first_slot_id] = Assignment(
                first_slot_id, first_candidate.account_id,
                first_candidate.topic_id, first_candidate.utility,
            )
            current[second_slot_id] = Assignment(
                second_slot_id, second_candidate.account_id,
                second_candidate.topic_id, second_candidate.utility,
            )
            affected_accounts = {
                current[first_slot_id].account_id,
                current[second_slot_id].account_id,
            }
            delta = math.fsum(
                account_utility(account_id) - baseline_by_account[account_id]
                for account_id in affected_accounts
            )
            current[first_slot_id], current[second_slot_id] = first_previous, second_previous
            if delta > best_delta:
                best_delta = delta
                best_move = (first_slot_id, first_candidate, second_slot_id, second_candidate)

        if best_move is None:
            converged = True
            break
        slot_id, candidate, second_slot_id, second_candidate = best_move
        previous = current.get(slot_id)
        if previous:
            global_counts[previous.topic_id] -= 1
            account_counts[(previous.account_id, previous.topic_id)] -= 1
        if candidate:
            current[slot_id] = Assignment(slot_id, candidate.account_id,
                                          candidate.topic_id, candidate.utility)
            global_counts[candidate.topic_id] = global_counts.get(candidate.topic_id, 0) + 1
            key = (candidate.account_id, candidate.topic_id)
            account_counts[key] = account_counts.get(key, 0) + 1
        else:
            current.pop(slot_id, None)
        if second_slot_id is not None and second_candidate is not None:
            second_previous = current[second_slot_id]
            global_counts[second_previous.topic_id] -= 1
            account_counts[(second_previous.account_id, second_previous.topic_id)] -= 1
            current[second_slot_id] = Assignment(
                second_slot_id, second_candidate.account_id,
                second_candidate.topic_id, second_candidate.utility,
            )
            global_counts[second_candidate.topic_id] = global_counts.get(second_candidate.topic_id, 0) + 1
            second_key = (second_candidate.account_id, second_candidate.topic_id)
            account_counts[second_key] = account_counts.get(second_key, 0) + 1
        passes += 1

    final_metrics = current_metrics()
    assignments = tuple(sorted(current.values(), key=lambda item: (item.account_id, item.slot_id)))
    return PortfolioOptimizationResult(
        assignments, final_metrics, passes, converged,
        candidate_edges=len(candidates), shortlisted_edges=len(shortlisted),
        search_edges=len(search_candidates),
    )
