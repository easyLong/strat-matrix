"""Compatibility source backed by the project's existing local test tables.

This is NOT the bank schema. No legacy marketing-topic record is exposed as
already generated/approved marketing content.
"""

from datetime import datetime, timezone
import json

from .contracts import Account, AccountQuery, Interaction, Topic, TopicQuery
from .memory import MemorySource
from .ports import IntegrationUnavailable


def object_value(raw):
    value = json.loads(raw) if isinstance(raw, str) else raw
    return value if isinstance(value, dict) else {}


def source_time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def text_value(value):
    if isinstance(value, list):
        return '、'.join(str(x) for x in value)
    return str(value or '')


class LocalSQLSource:
    def __init__(self, cursor):
        self.cursor = cursor

    def accounts(self, query: AccountQuery):
        self.cursor.execute(
            "SELECT a.account_code,a.account_name,a.persona,a.marketing_eligible,a.status,"
            "a.update_time,s.source_updated_at,s.payload_json,s.active_in_snapshot "
            "FROM godp_account a LEFT JOIN godp_account_source s "
            "ON s.account_id=a.account_code AND s.del_flag='N' WHERE a.del_flag='N' ORDER BY a.account_code")
        accounts = []
        for row in self.cursor.fetchall():
            raw = object_value(row.get('payload_json'))
            enabled = row['status'] == '启用' and row.get('active_in_snapshot') != 0
            enabled = enabled and raw.get('account_status', raw.get('enabled', True)) is not False
            certified = raw.get('certification_status', raw.get('certified'))
            account_type = raw.get('account_type') or ('认证' if certified is True else '非认证' if certified is False else None)
            interests = raw.get('interests') or []
            account = Account(
                account_id=row['account_code'], nickname=row['account_name'],
                owner_um=raw.get('um_no') or '', organization=raw.get('organization') or '',
                platform=raw.get('platform') or '', account_type=account_type, eligible=enabled,
                followers=raw.get('follower_count', raw.get('followers')),
                updated_at=source_time(row.get('source_updated_at') or row['update_time']),
                persona=raw.get('account_persona') or raw.get('persona') or row['persona'] or '',
                gender=raw.get('gender'), interests=interests if isinstance(interests, list) else [interests],
                expression_style=raw.get('expression_style') or '')
            account._local_payload = raw
            accounts.append(account)
        result = MemorySource(accounts=accounts).accounts(query)
        legacy = []
        for account in result.items:
            raw = account._local_payload
            if raw.get('interaction_data') is None:
                legacy.append(account.account_id)
                continue
            account.interactions = self._posts(account.account_id, raw['interaction_data'])
        if legacy:
            from ..account_metrics import months_ago
            now = datetime.now(timezone.utc)
            self.cursor.execute(
                "SELECT account_id,content_id,published_at,payload_json FROM godp_content_history "
                "WHERE del_flag='N' AND published_at>=%s AND published_at<=%s AND account_id IN ("
                + ','.join(['%s'] * len(legacy)) + ') ORDER BY account_id,published_at DESC,id DESC',
                (months_ago(now, 3).replace(tzinfo=None), now.replace(tzinfo=None), *legacy))
            grouped = {}
            for row in self.cursor.fetchall():
                raw = object_value(row.get('payload_json'))
                raw.update(content_id=row['content_id'], published_at=row['published_at'])
                grouped.setdefault(row['account_id'], []).append(raw)
            for account in result.items:
                if account.account_id in legacy:
                    account.interactions = self._posts(account.account_id, grouped.get(account.account_id, []))
        return result

    @staticmethod
    def _posts(account_id, rows):
        posts = []
        for raw in rows:
            if not raw.get('published_at'):
                continue
            posts.append(Interaction(
                content_id=raw.get('content_id') or f'LEGACY-{account_id}-{len(posts)}',
                account_id=account_id, published_at=source_time(raw['published_at']), title=raw.get('title') or '',
                likes=raw.get('red_star_count', raw.get('likes')),
                favorites=raw.get('favorite_count', raw.get('favorites')),
                comments=raw.get('comment_count', raw.get('comments')),
                updated_at=source_time(raw['updated_at']) if raw.get('updated_at') else None))
        return posts

    def topics(self, query: TopicQuery):
        self.cursor.execute(
            "SELECT t.topic_code,t.title,t.is_marketing,t.status,t.update_time,"
            "s.source_updated_at,s.payload_json,s.active_in_snapshot,s.valid_from,s.valid_to,s.approval_status "
            "FROM godp_topic t LEFT JOIN godp_topic_source s ON s.topic_id=t.topic_code AND s.del_flag='N' "
            "WHERE t.del_flag='N' ORDER BY t.topic_code")
        topics = []
        for row in self.cursor.fetchall():
            raw = object_value(row.get('payload_json'))
            source = '热点' if raw.get('topic_type') in ('hotspot', '热点') else '普通'
            available = row['status'] == '可用' and row.get('active_in_snapshot') != 0
            if row['is_marketing'] and row.get('payload_json'):
                available = available and row.get('approval_status') == 'approved'
            topics.append(self._topic(row['topic_code'], row['title'], source, bool(row['is_marketing']),
                                      available, row.get('source_updated_at') or row['update_time'],
                                      raw, row.get('valid_from'), row.get('valid_to')))
        self.cursor.execute(
            "SELECT topic_id,enabled,active_in_snapshot,source_snapshot_at,payload_json,valid_from,valid_to "
            "FROM godp_hotspot_topic_source WHERE del_flag='N' ORDER BY topic_id")
        for row in self.cursor.fetchall():
            raw = object_value(row.get('payload_json'))
            topics.append(self._topic(row['topic_id'], raw.get('title') or '', '热点', False,
                                      bool(row['enabled'] and row['active_in_snapshot']), row['source_snapshot_at'],
                                      raw, row['valid_from'], row['valid_to']))
        return MemorySource(topics=topics).topics(query)

    @staticmethod
    def _topic(identity, title, source, marketing, available, updated, raw, valid_from, valid_to):
        topic = Topic(topic_id=identity, source=source, topic_type='营销' if marketing else '非营销',
                      title=title, outline=raw.get('outline') or raw.get('summary') or '',
                      content_type=raw.get('content_type') or '', heat=raw.get('topic_heat', raw.get('heat')),
                      available=available, updated_at=source_time(updated),
                      valid_from=source_time(valid_from) if valid_from else None,
                      valid_to=source_time(valid_to) if valid_to else None,
                      related_product=text_value(raw.get('related_product') or raw.get('product_or_activity')),
                      related_activity=text_value(raw.get('related_activity')),
                      related_hotspot=text_value(raw.get('related_hotspot')))
        topic._local_payload = raw
        return topic

    def marketing_contents(self, query):
        raise IntegrationUnavailable('IF-03：本地旧营销选题表不是过审内容库存，请实现行内查询或使用 fixture 自检')

    def effective_marketing(self, query):
        raise IntegrationUnavailable('IF-04：目标日有效营销投放查询尚未对接，请实现行内查询或使用 fixture 自检')
