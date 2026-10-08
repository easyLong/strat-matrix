"""Derive account metrics from the synced three-month post history."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone


def months_ago(now: datetime, count: int) -> datetime:
    month_index = now.year * 12 + now.month - 1 - count
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return now.replace(year=year, month=month, day=min(now.day, monthrange(year, month)[1]))


def post_time(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def interaction_count(post: dict) -> int:
    return sum(int(post.get(primary, post.get(legacy, 0)) or 0) for primary, legacy in (
        ("red_star_count", "likes"), ("favorite_count", "favorites"),
        ("comment_count", "comments"),
    ))


def account_metrics(posts: list[dict], rolling_posts: int, now: datetime) -> dict:
    instant = now.astimezone(timezone.utc)
    cutoff = months_ago(instant, 3)
    recent = []
    for post in posts:
        published_at = post_time(post.get("published_at"))
        if published_at and cutoff <= published_at <= instant:
            recent.append((published_at, interaction_count(post)))
    recent.sort(key=lambda record: record[0], reverse=True)
    interactions = [count for _, count in recent]
    current = interactions[:rolling_posts]
    average = sum(current) / len(current) if current else 0
    trend = "数据不足"
    if len(interactions) >= rolling_posts * 2:
        previous = interactions[rolling_posts:rolling_posts * 2]
        previous_average = sum(previous) / rolling_posts
        if previous_average == 0:
            trend = "上升" if average > 0 else "平稳"
        elif average >= previous_average * 1.2:
            trend = "上升"
        elif average <= previous_average * 0.8:
            trend = "下滑"
        else:
            trend = "平稳"
    return {"valid_content_count": len(recent),
            "rolling_interaction_count": average, "traffic_trend": trend}
