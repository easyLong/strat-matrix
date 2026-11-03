"""On-site implementation; all bank-specific SQL/mapping lives in one private file."""

from datetime import datetime
from importlib import import_module

from pydantic import ValidationError

from .contracts import (Account, BEIJING, DemandReceipt, EffectivePlacement,
                        Interaction, MarketingContent, Page, ProductionRecord, Topic)
from .ports import DataContractError, IntegrationUnavailable


def load_site():
    name = __package__ + '.site_sql_private'
    try:
        return import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        raise IntegrationUnavailable('请在行内复制 site_sql_template.py 为 site_sql_private.py 并填写 SQL') from None


class BankSQLSource:
    def __init__(self, cursor, site=None):
        self.cursor = cursor
        self.site = site if site is not None else load_site()

    def _rows(self, key, params):
        statement = getattr(self.site, key, None)
        if not statement or not statement.strip():
            raise IntegrationUnavailable(f'行内方法未配置：{key}')
        bound = dict(params)
        for name in ('account_ids', 'topic_ids'):
            values = bound.pop(name, None)
            placeholders = []
            for index, value in enumerate(values or []):
                parameter = f'{name}_{index}'
                bound[parameter] = value
                placeholders.append(f'%({parameter})s')
            statement = statement.replace('{{' + name + '}}', ','.join(placeholders) or 'NULL')
        self.cursor.execute(statement, bound)
        return self.cursor.fetchall()

    def _page(self, prefix, query, entity, mapper):
        params = query.model_dump()
        params.update(limit=query.page_size, offset=query.offset,
                      all_accounts=getattr(query, 'account_ids', None) is None,
                      all_topics=getattr(query, 'topic_ids', None) is None)
        counts = self._rows(prefix + '_COUNT', params)
        if len(counts) != 1 or ('total' not in counts[0] and '总数' not in counts[0]):
            raise DataContractError(prefix + '_COUNT 必须返回一条带“总数”或 total 的记录')
        try:
            items = [entity.model_validate(mapper(row)) for row in self._rows(prefix + '_ROWS', params)]
            return Page[entity](total=counts[0].get('total', counts[0].get('总数')),
                                page_no=query.page_no, page_size=query.page_size, items=items)
        except ValidationError:
            raise DataContractError(prefix + ' 返回字段、枚举或分页不符合业务实体') from None

    def accounts(self, query):
        from .memory import in_window
        result = self._page('ACCOUNT', query, Account, self.site.map_account)
        if any((query.account_ids is not None and a.account_id not in query.account_ids)
               or not in_window(a.updated_at, query.updated_from, query.updated_to) for a in result.items):
            raise DataContractError('ACCOUNT 查询结果未应用账号或更新时间条件')
        if [a.account_id for a in result.items] != sorted(a.account_id for a in result.items):
            raise DataContractError('账号页须按账号ID稳定排序')
        now = datetime.now(BEIJING)
        from ..account_metrics import months_ago
        if result.items:
            rows = self._rows('ACCOUNT_POSTS', {'account_ids': [a.account_id for a in result.items],
                                              'history_from': months_ago(now, 3), 'history_to': now})
            by_id = {a.account_id: a for a in result.items}
            try:
                seen = set()
                for row in rows:
                    post = Interaction.model_validate(self.site.map_interaction(row))
                    key = (post.account_id, post.content_id)
                    if post.account_id not in by_id or key in seen:
                        raise DataContractError('账号互动明细存在重复或不属于当前页的账号')
                    if not months_ago(now, 3) <= post.published_at <= now:
                        raise DataContractError('账号互动明细超出近三个月范围')
                    seen.add(key)
                    by_id[post.account_id].interactions.append(post)
            except ValidationError:
                raise DataContractError('ACCOUNT_POSTS 返回字段不符合互动明细实体') from None
        if any(not a.eligible for a in result.items):
            raise DataContractError('IF-01 只能返回可参与策划账号，分页总数须使用相同过滤条件')
        return result

    def topics(self, query):
        from .memory import topic_matches
        result = self._page('TOPIC', query, Topic, self.site.map_topic)
        if any(not topic_matches(t, query) for t in result.items):
            raise DataContractError('TOPIC 查询结果未应用约定筛选条件')
        if [t.topic_id for t in result.items] != sorted(t.topic_id for t in result.items):
            raise DataContractError('选题页须按选题ID稳定排序')
        return result

    def marketing_contents(self, query):
        result = self._page('MARKETING', query, MarketingContent, self.site.map_marketing_content)
        if any(m.account_id != query.account_id for m in result.items):
            raise DataContractError('营销内容不属于查询账号')
        keys = [(m.approved_at, m.content_id) for m in result.items]
        if keys != sorted(keys):
            raise DataContractError('营销库存须先审核通过的优先，同时间按内容ID稳定排序')
        return result

    def effective_marketing(self, query):
        try:
            result = [EffectivePlacement.model_validate(self.site.map_effective_placement(row))
                      for row in self._rows('EFFECTIVE_MARKETING_ROWS', query.model_dump())]
        except ValidationError:
            raise DataContractError('有效营销投放返回字段不符合实体') from None
        if any(p.account_id != query.account_id or p.publish_date != query.publish_date for p in result):
            raise DataContractError('有效营销投放不属于目标账号或目标日期')
        return result


class BankSQLProduction:
    def __init__(self, cursor, site=None):
        self.cursor = cursor
        self.site = site if site is not None else load_site()

    def production_results(self, query):
        result = [ProductionRecord.model_validate(r) for r in self.site.production_results(self.cursor, query)]
        if any(r.slot_id not in query.slot_ids for r in result):
            raise DataContractError('生产结果包含未查询的策划明细')
        return result
