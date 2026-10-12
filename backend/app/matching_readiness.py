"""Assess matching inputs without scoring, allocating, or changing a batch."""

from collections import Counter
from datetime import datetime, timezone
import json
import math
from zoneinfo import ZoneInfo

from .account_profile import canonical_json, profile_from_snapshot
from .models import StrategyConfig
from .topic_profile import profile_from_source
from .vector_utils import normalized_vector


ACCOUNT_STATES = ("ready", "missing", "incomplete_snapshot", "pending", "failed", "stale", "invalid_vector")
TOPIC_STATES = ("ready", "missing", "awaiting_labels", "label_failed", "pending", "failed", "stale",
                "invalid_vector", "unavailable")


def vector_space(row: dict) -> tuple[str, int] | None:
    try:
        values = json.loads(row["vector_json"])
        normalized_vector(values, row["vector_model"], "匹配输入")
        if row["vector_model"] != row["vector_model"].strip():
            return None
        # Stored vectors must already be unit vectors. Silently normalizing
        # corrupted records here would hide inconsistent matching inputs.
        if not math.isclose(math.fsum(float(value) ** 2 for value in values),
                            1.0, rel_tol=1e-6, abs_tol=1e-6):
            return None
        return row["vector_model"], len(values)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def account_state(snapshot: dict, profile: dict | None, batch: dict) -> tuple[str, tuple | None]:
    try:
        expected_json, expected_hash = profile_from_snapshot(
            snapshot, batch["batch_id"], batch["config_version"],
        )
    except (KeyError, TypeError, ValueError):
        return "incomplete_snapshot", None
    if profile is None:
        return "missing", None
    try:
        if profile["batch_id"] != batch["batch_id"] or profile["account_id"] != snapshot["account_id"] \
                or profile["config_version"] != batch["config_version"] \
                or profile["profile_hash"] != expected_hash or profile["profile_json"] != expected_json \
                or canonical_json(json.loads(profile["snapshot_json"])) != canonical_json(snapshot):
            return "stale", None
    except (KeyError, TypeError, ValueError):
        return "stale", None
    status = profile.get("status")
    if status in ("pending", "failed"):
        return status, None
    if status != "ready":
        return "stale", None
    space = vector_space(profile)
    return ("ready", space) if space else ("invalid_vector", None)


def topic_state(row: dict, checked_at: datetime) -> tuple[str, tuple | None]:
    instant = checked_at.astimezone(timezone.utc).replace(tzinfo=None)
    if row["topic_id"].startswith("DEMO-") or not row["active_in_snapshot"] \
            or row["is_marketing"] or row["topic_status"] != "可用" \
            or (row["valid_from"] and row["valid_from"] > instant) \
            or (row["valid_to"] and row["valid_to"] < instant):
        return "unavailable", None
    if row["label_status"] != "已完成":
        return ("label_failed" if row["label_status"] == "失败" else "awaiting_labels"), None
    if row["profile_status"] is None:
        return "missing", None
    try:
        expected_json, expected_hash = profile_from_source(row["payload_json"], row["tags_json"])
        if expected_hash != row["content_hash"] or row["tag_version"] != row["profile_tag_version"] \
                or expected_json != row["profile_json"]:
            return "stale", None
    except (KeyError, TypeError, ValueError):
        return "stale", None
    status = row["profile_status"]
    if status in ("pending", "failed"):
        return status, None
    if status != "ready":
        return "stale", None
    space = vector_space(row)
    return ("ready", space) if space else ("invalid_vector", None)


def evaluate_readiness(batch: dict, profiles: list[dict], topics: list[dict],
                       checked_at: datetime) -> dict:
    if checked_at.tzinfo is None:
        raise ValueError("检查时间必须带时区")
    reasons = []

    def block(code: str, message: str) -> None:
        reasons.append({"code": code, "message": message})

    if batch["cycle_end"] < checked_at.astimezone(ZoneInfo("Asia/Shanghai")).date():
        block("batch_expired", "该策划周期已结束")
    try:
        StrategyConfig.model_validate_json(batch["config_json"])
    except (TypeError, ValueError):
        block("invalid_config_snapshot", "批次配置快照缺失或无效")
    try:
        snapshots = json.loads(batch["account_snapshot_json"])
        if not isinstance(snapshots, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("account_id"), str)
            or not item["account_id"].strip() or item["account_id"].startswith("DEMO-")
            for item in snapshots
        ):
            raise ValueError("无效的正式账号快照")
        identifiers = [item["account_id"] for item in snapshots]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("重复账号")
    except (TypeError, ValueError):
        block("invalid_account_snapshot", "批次账号快照缺失、重复或无效")
        snapshots, identifiers = [], []
    if not snapshots:
        block("no_batch_accounts", "批次没有可检查的正式账号输入")
    if len(snapshots) != batch["account_count"] or batch["account_count"] != batch["batch_account_count"]:
        block("account_count_mismatch", "批次账号数量与冻结输入不一致")
    by_account = {row["account_id"]: row for row in profiles}
    if len(by_account) != len(profiles) or set(by_account) - set(identifiers):
        block("unexpected_account_profiles", "存在重复或不属于冻结账号集合的画像")

    account_counts = Counter()
    account_spaces = Counter()
    account_samples: dict[str, list[str]] = {}
    for snapshot in snapshots:
        state, space = account_state(snapshot, by_account.get(snapshot["account_id"]), batch)
        account_counts[state] += 1
        if state != "ready":
            sample = account_samples.setdefault(state, [])
            if len(sample) < 10:
                sample.append(snapshot["account_id"])
        if space:
            account_spaces[space] += 1
    if snapshots and account_counts["ready"] != len(snapshots):
        block("account_inputs_not_ready", "部分批次账号缺少完整画像或有效向量")
    if len(account_spaces) > 1:
        block("mixed_account_vector_spaces", "批次账号向量使用了不同模型或维度")
    common_space = next(iter(account_spaces)) if len(account_spaces) == 1 else None

    topic_counts = Counter()
    topic_spaces = Counter()
    topic_samples: dict[str, list[str]] = {}
    for row in topics:
        state, space = topic_state(row, checked_at)
        topic_counts[state] += 1
        if space:
            topic_spaces[space] += 1
        if state != "ready":
            sample = topic_samples.setdefault(state, [])
            if len(sample) < 10:
                sample.append(row["topic_id"])
    compatible = topic_spaces[common_space] if common_space else 0
    if not topic_counts["ready"]:
        block("no_ready_topics", "当前没有标签、画像及向量均有效的普通选题")
    elif common_space and not compatible:
        block("no_compatible_topics", "已就绪选题与批次账号的向量模型或维度不兼容")

    def spaces_report(spaces: Counter) -> list[dict]:
        return [{"vector_model": model, "dimension": dimension, "count": count}
                for (model, dimension), count in sorted(spaces.items())]

    ready = not reasons and bool(compatible)
    return {
        "batch_id": batch["batch_id"], "batch_code": batch["batch_code"],
        "config_version": batch["config_version"], "checked_at": checked_at.isoformat(),
        "status": "ready" if ready else "blocked", "inputs_ready": ready,
        "matching_executed": False,
        "account_input_scope": "batch_snapshot", "topic_input_scope": "current_eligible_pool",
        "vector_space": ({"vector_model": common_space[0], "dimension": common_space[1]}
                         if common_space else None),
        "accounts": {"expected": batch["account_count"],
                     "counts": {state: account_counts[state] for state in ACCOUNT_STATES},
                     "vector_spaces": spaces_report(account_spaces), "samples": account_samples},
        "topics": {"inspected": len(topics), "counts": {state: topic_counts[state] for state in TOPIC_STATES},
                   "compatible_ready": compatible,
                   "incompatible_ready": topic_counts["ready"] - compatible if common_space else 0,
                   "vector_spaces": spaces_report(topic_spaces), "samples": topic_samples},
        "blocking_reasons": reasons,
    }
