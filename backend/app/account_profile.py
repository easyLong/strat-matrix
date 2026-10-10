"""Freeze account profiles from the inputs already read by a planning batch."""

from datetime import datetime
import hashlib
import json

from .account_metrics import months_ago, post_time


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def interaction_snapshot(posts: list[dict], as_of: datetime) -> list[dict]:
    """Use the same three-month window and counts as lifecycle computation."""
    cutoff = months_ago(as_of, 3)
    recent = []
    for post in posts:
        published = post_time(post.get("published_at"))
        if published is None or not cutoff <= published <= as_of:
            continue
        recent.append({
            "content_id": post.get("content_id") or "",
            "published_at": published.isoformat(), "title": post.get("title") or "",
            **{primary: int(post.get(primary, post.get(legacy, 0)) or 0)
               for primary, legacy in (("red_star_count", "likes"),
                                       ("favorite_count", "favorites"),
                                       ("comment_count", "comments"))},
        })
    # Preserve stable input order for posts sharing a publication time; this
    # is also the order used to choose the rolling metric window.
    return sorted(recent, key=lambda post: post["published_at"], reverse=True)


def profile_from_snapshot(snapshot: dict, batch_id: int, config_version: int) -> tuple[str, str]:
    required = {"source_payload", "interaction_data", "interaction_source", "metrics_as_of",
                "business_goal", "rolling_posts", "lifecycle_stage", "source_updated_at"}
    if not required <= snapshot.keys():
        raise ValueError("该批次缺少完整账号输入快照，不能使用当前账号数据补造历史画像")
    source = snapshot["source_payload"]
    if not isinstance(source, dict) or not isinstance(snapshot["interaction_data"], list):
        raise ValueError("账号快照内容格式错误")
    certification = source.get("certification_status")
    profile = {
        "schema_version": 1,
        "account": {
            "account_id": snapshot["account_id"], "account_name": snapshot["account_name"],
            "account_alias": source.get("account_alias") or "",
            "platform": source.get("platform") or "", "organization": source.get("organization") or "",
            "city": source.get("city") or "", "persona": snapshot["persona"],
            "certified": certification if certification is not None else bool(source.get("certified")),
            "marketing_eligible": snapshot["marketing_eligible"],
            "followers_count": snapshot["followers_count"],
            **{key: sorted(set(source.get(key) or []))
               for key in ("account_tags", "target_audience", "interests")},
            "family_identity": source.get("family_identity") or "",
            "expression_style": source.get("expression_style") or "",
        },
        "interaction": {
            "source": snapshot["interaction_source"], "as_of": snapshot["metrics_as_of"],
            "window_months": 3, "rolling_posts": snapshot["rolling_posts"],
            "valid_content_count": snapshot["valid_content_count"],
            "rolling_interaction_count": snapshot["rolling_interaction_count"],
            "traffic_trend": snapshot["traffic_trend"], "posts": snapshot["interaction_data"],
        },
        "lifecycle_stage": snapshot["lifecycle_stage"], "business_goal": snapshot["business_goal"],
    }
    # Include batch identity and frozen inputs: a different batch must generate
    # its own vector even when its account text happens to be unchanged.
    fingerprint = canonical_json({"batch_id": batch_id, "config_version": config_version,
                                  "profile": profile, "snapshot": snapshot})
    return canonical_json(profile), hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()


def save_batch_account_profiles(cursor, batch_id: int, accounts: list[dict],
                               config_version: int, actor: str) -> None:
    for account in accounts:
        profile_json, profile_hash = profile_from_snapshot(account, batch_id, config_version)
        # No upsert: batch input is immutable. Repeated planning returns the
        # existing batch before reaching this code.
        cursor.execute(
            "INSERT INTO godp_account_profile "
            "(batch_id, account_id, config_version, source_updated_at, profile_hash, "
            "snapshot_json, profile_json, create_by, update_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (batch_id, account["account_id"], config_version,
             post_time(account["source_updated_at"]).replace(tzinfo=None),
             profile_hash, canonical_json(account), profile_json, actor, actor),
        )
