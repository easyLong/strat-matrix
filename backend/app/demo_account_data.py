"""Deterministic enrichment data for local demo accounts."""

from datetime import datetime, timedelta, timezone

from .account_metrics import account_metrics
from .models import StrategyConfig
from .ordinary_planning import lifecycle_stage


DEMO_PLATFORMS = ("小红书", "抖音", "视频号")
DEMO_ORGANIZATIONS = (
    "演示运营一组", "演示运营二组", "华东内容中心", "华南内容中心",
    "垂直领域工作室", "区域运营中心",
)


def _candidate_values(config: StrategyConfig, field: str) -> list[int]:
    values = {0, 1, 5, 10, 20, 50, 100, 200, 500, 1000, 2000}
    for rule in config.lifecycle_rules:
        for condition in rule.conditions:
            if condition.field == field:
                threshold = int(condition.value)
                values.update({max(0, threshold - 1), threshold, threshold + 1})
    return sorted(values)


def lifecycle_demo_profile(config: StrategyConfig, target_index: int,
                           now: datetime) -> tuple[int, list[dict]]:
    """Find demo followers/posts that exercise the configured lifecycle stage."""
    rolling = config.rolling_posts
    follower_values = _candidate_values(config, "followers_count")
    interaction_values = _candidate_values(config, "rolling_interaction_count")
    content_values = sorted(set(_candidate_values(config, "valid_content_count") +
                                [rolling, rolling * 2, rolling * 3]))
    target = config.lifecycle_rules[target_index % len(config.lifecycle_rules)].name
    instant = now.astimezone(timezone.utc)

    for followers in follower_values:
        for content_count in content_values:
            if content_count > rolling * 4:
                continue
            for interactions in interaction_values:
                posts = []
                for position in range(content_count):
                    published_at = instant - timedelta(days=1 + position * 2)
                    posts.append({
                        "content_id": f"DEMO-LIFECYCLE-{target_index}-{position + 1}",
                        "published_at": published_at.isoformat(),
                        "title": "演示账号互动样本",
                        "red_star_count": interactions * 6 // 10,
                        "favorite_count": interactions // 4,
                        "comment_count": interactions - interactions * 6 // 10 - interactions // 4,
                    })
                metrics = account_metrics(posts, rolling, instant)
                if lifecycle_stage(config, {**metrics, "followers_count": followers}) == target:
                    return followers, posts

    # A custom customer configuration may make a stage unreachable. Keep the
    # demo data usable and let the API display the stage actually calculated.
    return 0, []


def demo_account_dimensions(account_id: str, index: int, now: datetime,
                            config: StrategyConfig) -> dict:
    if not account_id.startswith("DEMO-"):
        raise ValueError("演示账号资料仅允许用于 DEMO- 测试账号")
    followers, interactions = lifecycle_demo_profile(config, index, now)
    return {
        "organization": DEMO_ORGANIZATIONS[index % len(DEMO_ORGANIZATIONS)],
        "platform": DEMO_PLATFORMS[index % len(DEMO_PLATFORMS)],
        "followers": followers,
        "interaction_data": interactions,
    }
