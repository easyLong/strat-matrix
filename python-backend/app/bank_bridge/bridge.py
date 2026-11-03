"""Project stable source DTOs; write use cases freeze HTTP inputs before row locks."""

from datetime import datetime, timezone
import json

from .contracts import AccountQuery, TopicQuery
from .factory import get_source
from .ports import DataContractError


def collect(source, method, query):
    """Read complete pages; detect changed totals and repeated IDs instead of looping."""
    expected = None
    ids = set()
    while True:
        result = getattr(source, method)(query)
        if result.page_no != query.page_no or result.page_size != query.page_size:
            raise DataContractError('数据源返回的页码或分页大小不匹配')
        if expected is None:
            expected = result.total
        if expected != result.total:
            raise DataContractError('同一轮读取的分页总数变化，请在一致性快照中重新读取')
        for row in result.items:
            identity = getattr(row, 'topic_id', None) or row.account_id
            if identity in ids:
                raise DataContractError('数据源跨页返回重复ID，请检查稳定排序与关联查询')
            ids.add(identity)
            yield row
        if query.offset + len(result.items) >= result.total:
            break
        query = query.model_copy(update={'page_no': query.page_no + 1})


def account_payload(account):
    return {**account._local_payload,
            'account_id': account.account_id, 'account_name': account.nickname,
            'um_no': account.owner_um, 'organization': account.organization, 'platform': account.platform,
            'account_status': account.eligible, 'account_persona': account.persona,
            'account_type': account.account_type, 'certification_status':
                None if account.account_type is None else account.account_type == '认证',
            'follower_count': account.followers, 'gender': account.gender,
            'interests': account.interests, 'expression_style': account.expression_style,
            'updated_at': account.updated_at.isoformat(),
            'interaction_data': [{'content_id': p.content_id, 'published_at': p.published_at.isoformat(),
                                  'title': p.title, 'red_star_count': p.likes,
                                  'favorite_count': p.favorites, 'comment_count': p.comments}
                                 for p in account.interactions]}


def topic_payload(topic):
    return {**topic._local_payload, 'topic_id': topic.topic_id, 'title': topic.title,
            'outline': topic.outline, 'content_type': topic.content_type,
            'topic_type': 'hotspot' if topic.source == '热点' else 'normal',
            'is_marketing': topic.topic_type == '营销', 'topic_heat': topic.heat,
            'status': topic.available, 'updated_at': topic.updated_at.isoformat(),
            'valid_from': topic.valid_from.isoformat() if topic.valid_from else None,
            'valid_to': topic.valid_to.isoformat() if topic.valid_to else None,
            'related_product': topic.related_product, 'related_activity': topic.related_activity,
            'related_hotspot': topic.related_hotspot}


def account_options(cursor, config, limit=1000, *, account_ids=None):
    from ..account_metrics import account_metrics
    from ..account_profile import interaction_snapshot
    from ..ordinary_planning import lifecycle_stage
    now = datetime.now(timezone.utc)
    rows = []
    for account in collect(get_source(cursor), 'accounts', AccountQuery(account_ids=account_ids)):
        payload = account_payload(account)
        metrics = account_metrics(interaction_snapshot(payload['interaction_data'], now), config.rolling_posts, now)
        rows.append(dict(account_id=account.account_id, account_name=account.nickname, city='',
                         persona=account.persona, marketing_eligible=account.account_type == '认证', status='启用',
                         account_alias='', um_no=account.owner_um, organization=account.organization,
                         platform=account.platform, business_line='', account_type=account.account_type or '',
                         certified=payload['certification_status'], followers=account.followers,
                         traffic_trend=metrics['traffic_trend'],
                         lifecycle_stage=lifecycle_stage(config, {**metrics, 'followers_count': account.followers or 0})))
        if len(rows) >= limit:
            break
    return rows


def planning_accounts(cursor, scope, config, *, account_ids=None):
    from ..account_metrics import account_metrics
    from ..account_profile import interaction_snapshot
    from ..ordinary_planning import PlanningError, lifecycle_stage
    now = datetime.now(timezone.utc)
    result = []
    for account in collect(get_source(cursor), 'accounts', AccountQuery(account_ids=account_ids)):
        if account.account_id.startswith('DEMO-') != (scope == 'demo'):
            continue
        if not account.persona.strip():
            continue
        if account.followers is None:
            raise DataContractError('参与算法的账号缺少粉丝量，不能按0自动判定生命周期')
        payload = account_payload(account)
        posts = interaction_snapshot(payload['interaction_data'], now)
        metrics = account_metrics(posts, config.rolling_posts, now)
        stage = lifecycle_stage(config, {**metrics, 'followers_count': account.followers})
        target = next(t for t in config.stage_targets if t.name == stage)
        result.append(dict(account_id=account.account_id, account_name=account.nickname,
                           persona=account.persona, marketing_eligible=account.account_type == '认证',
                           followers_count=account.followers, source_updated_at=account.updated_at.isoformat(),
                           source_payload=payload, interaction_data=posts, interaction_source='bank_source',
                           metrics_as_of=now.isoformat(), rolling_posts=config.rolling_posts,
                           lifecycle_stage=stage, business_goal={'traffic': target.traffic, 'conversion': target.conversion},
                           **metrics))
    if not result:
        raise PlanningError(f'{scope} 范围内没有可参与策划且人设完整的账号')
    return result


def topic_options(cursor, limit=1000, topic_ids=None, available_only=True):
    query = TopicQuery(topic_ids=topic_ids, available_only=available_only,
                       valid_at=datetime.now(timezone.utc) if available_only else None)
    rows = []
    for topic in collect(get_source(cursor), 'topics', query):
        rows.append(dict(topic_id=topic.topic_id, topic_title=topic.title, category=topic.content_type,
                         is_marketing=topic.topic_type == '营销', status='可用' if topic.available else '停用',
                         content_type=topic.content_type, outline=topic.outline, account_type='',
                         topic_type='营销' if topic.topic_type == '营销' else topic.source,
                         valid_from=topic.valid_from.isoformat() if topic.valid_from else None,
                         valid_to=topic.valid_to.isoformat() if topic.valid_to else None,
                         related_product=topic.related_product, related_activity=topic.related_activity,
                         related_hotspot=topic.related_hotspot, _catalog_topic=True,
                         topic_payload=topic_payload(topic)))
        if len(rows) >= limit:
            break
    return rows


def planning_topics(cursor, scope):
    from ..ordinary_planning import PlanningError
    query = TopicQuery(source='普通', topic_type='非营销', available_only=True,
                       valid_at=datetime.now(timezone.utc))
    topics = [t for t in collect(get_source(cursor), 'topics', query)
              if t.topic_id.startswith('DEMO-') == (scope == 'demo')]
    if not topics:
        raise PlanningError(f'{scope} 范围内没有可用普通选题')
    cursor.execute('SELECT topic_id,tags_json FROM godp_topic_tag WHERE del_flag=\'N\' AND topic_id IN ('
                   + ','.join(['%s'] * len(topics)) + ')', [t.topic_id for t in topics])
    tags = {r['topic_id']: json.loads(r['tags_json'] or '{}') for r in cursor.fetchall()}
    result = []
    for topic in topics:
        role = tags.get(topic.topic_id, {}).get('T2', [])
        role = role[0] if isinstance(role, list) and role else role
        result.append(dict(topic_id=topic.topic_id, title=topic.title, outline=topic.outline,
                           content_type=topic.content_type, topic_heat=topic.heat or 0,
                           content_role=role if role in ('流量', '转化') else '流量',
                           source_updated_at=topic.updated_at.isoformat()))
    return sorted(result, key=lambda row: (-row['topic_heat'], row['topic_id']))


def matching_topics(cursor, checked_at, topic_ids=None):
    from .current_topics import rows
    if topic_ids is None:
        return rows(cursor, as_of=checked_at)
    return [topic for start in range(0, len(topic_ids), 500)
            for topic in rows(cursor, topic_ids[start:start + 500], as_of=checked_at)]
