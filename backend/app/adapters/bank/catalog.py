"""Read planner-owned results and hydrate optional source fields through the port."""

import json
from ...bank_bridge.bridge import collect, account_payload, topic_payload
from ...bank_bridge.contracts import AccountQuery, TopicQuery
from ...bank_bridge.factory import get_source


def source_maps(cursor, rows):
    source = get_source(cursor)
    topics, accounts = {}, {}
    for name, values, query_class, target in (
        ('topics', sorted({r.get('topic_id') for r in rows if r.get('topic_id')}), TopicQuery, topics),
        ('accounts', sorted({r.get('account_id') for r in rows if r.get('account_id')}), AccountQuery, accounts),
    ):
        for offset in range(0, len(values), 500):
            query = query_class(**{('topic_ids' if name == 'topics' else 'account_ids'): values[offset:offset + 500]})
            for item in collect(source, name, query):
                target[getattr(item, 'topic_id', None) or item.account_id] = item
    return accounts, topics


def hydrate(cursor, rows):
    if not rows:
        return rows
    accounts, topics = source_maps(cursor, rows)
    for row in rows:
        topic = topics.get(row.get('topic_id'))
        account = accounts.get(row.get('account_id'))
        if topic:
            row['topic_payload'] = json.dumps(topic_payload(topic), ensure_ascii=False)
            row['source_is_marketing'] = topic.topic_type == '营销'
        if account:
            row['account_source_payload'] = json.dumps(account_payload(account), ensure_ascii=False)
            row['account_owner'] = account.organization
        # Missing live source data must not erase historical planning snapshots.
    return rows
