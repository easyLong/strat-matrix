"""Explicit in-memory provider for offline development and contract verification."""

from datetime import datetime
from .contracts import (Account, AccountQuery, DemandReceipt, EffectivePlacement,
                        EffectivePlacementQuery, MarketingContent, MarketingDemand,
                        MarketingQuery, Page, ProductionQuery, ProductionRecord,
                        Topic, TopicQuery, BEIJING)
from .ports import DataContractError


def in_window(value, start, end):
    return (start is None or value >= start) and (end is None or value < end)


def topic_matches(topic, query):
    return ((query.topic_ids is None or topic.topic_id in query.topic_ids)
            and (query.source is None or topic.source == query.source)
            and (query.topic_type is None or topic.topic_type == query.topic_type)
            and (not query.available_only or topic.available)
            and in_window(topic.updated_at, query.updated_from, query.updated_to)
            and (query.valid_at is None or
                 ((topic.valid_from is None or topic.valid_from <= query.valid_at)
                  and (topic.valid_to is None or topic.valid_to >= query.valid_at))))


def page(rows, query, entity):
    return Page[entity](total=len(rows), page_no=query.page_no, page_size=query.page_size,
                        items=rows[query.offset:query.offset + query.page_size])


class MemorySource:
    def __init__(self, accounts=(), topics=(), marketing=(), placements=()):
        self.account_rows = [Account.model_validate(x) for x in accounts]
        self.topic_rows = [Topic.model_validate(x) for x in topics]
        self.marketing_rows = [MarketingContent.model_validate(x) for x in marketing]
        self.placements = [EffectivePlacement.model_validate(x) for x in placements]
        for rows, key in ((self.account_rows, 'account_id'), (self.topic_rows, 'topic_id'),
                          (self.marketing_rows, 'content_id')):
            ids = [getattr(row, key) for row in rows]
            if len(set(ids)) != len(ids):
                raise DataContractError(f'模拟数据存在重复{key}')

    def accounts(self, query: AccountQuery):
        rows = [a for a in self.account_rows if a.eligible
                and (query.account_ids is None or a.account_id in query.account_ids)
                and in_window(a.updated_at, query.updated_from, query.updated_to)]
        return page(sorted(rows, key=lambda x: x.account_id), query, Account)

    def topics(self, query: TopicQuery):
        return page(sorted([t for t in self.topic_rows if topic_matches(t, query)],
                           key=lambda x: x.topic_id), query, Topic)

    def marketing_contents(self, query: MarketingQuery):
        rows = sorted([m for m in self.marketing_rows if m.account_id == query.account_id],
                      key=lambda x: (x.approved_at, x.content_id))
        return page(rows, query, MarketingContent)

    def effective_marketing(self, query: EffectivePlacementQuery):
        return [p for p in self.placements
                if p.account_id == query.account_id and p.publish_date == query.publish_date]


class MemoryProduction:
    def __init__(self):
        self.requests = {}
        self.results: list[ProductionRecord] = []

    def submit_marketing(self, demand: MarketingDemand):
        previous = self.requests.get(demand.request_id)
        if previous and previous != demand:
            raise DataContractError('相同营销请求标识的内容不一致')
        self.requests[demand.request_id] = demand.model_copy(deep=True)
        # Acceptance is not production completion. Tests may explicitly supply results.
        return DemandReceipt(request_id=demand.request_id, accepted=True,
                             external_request_id='MOCK-' + demand.request_id)

    def production_results(self, query: ProductionQuery):
        return [r for r in self.results if r.slot_id in query.slot_ids]


def fixture_source():
    now = datetime.now(BEIJING).replace(microsecond=0)
    accounts = [Account(account_id=f'FIXTURE-A{i:03}', nickname=f'驻场测试账号{i}',
                        owner_um=f'TESTUM{i:03}', organization='测试二级分行', platform='小红书',
                        account_type='认证' if i % 2 else '非认证', eligible=True,
                        followers=50 * i, updated_at=now, persona='车圈达人',
                        gender='女', interests=['汽车', '家庭生活'], expression_style='通俗自然')
                for i in range(1, 4)]
    topics = [Topic(topic_id=f'FIXTURE-T{i:03}', source='热点' if i == 3 else '普通',
                    topic_type='营销' if i == 2 else '非营销', title=f'驻场测试选题{i}',
                    outline=f'选题{i}的测试大纲', content_type='产品解读', heat=10 * i,
                    available=True, updated_at=now) for i in range(1, 4)]
    marketing = [MarketingContent(content_id='FIXTURE-C001', account_id='FIXTURE-A001',
                                 title='已过审内容', body='模拟过审正文', approved_at=now)]
    return MemorySource(accounts, topics, marketing)
