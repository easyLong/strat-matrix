"""Read bank-owned facts through Java; never connects to the business database."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import TypeAdapter, ValidationError

from .contracts import (Account, EffectivePlacement, MarketingContent, MarketingProductionRecord,
                        Page, ProductionRecord, Topic)
from .ports import DataContractError, IntegrationUnavailable


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class JavaHTTPClient:
    """Stable DTOs and route mapping; actual bank URLs/auth are supplied on site."""

    ROUTES = {
        'accounts': 'accounts/query',
        'topics': 'topics/query',
        'marketing_contents': 'marketing-contents/query',
        'effective_marketing': 'effective-marketing/query',
        'production_results': 'production-status/query',
        'marketing_results': 'marketing-status/query',
    }

    def __init__(self, base_url, token, *, opener=None, routes=None, timeout=15, max_bytes=16 * 1024 * 1024,
                 encode_query=None, decode_response=None):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise IntegrationUnavailable('Java资料服务地址未配置或格式不正确')
        if not token or any(c in token for c in '\r\n\x00'):
            raise IntegrationUnavailable('Java资料服务鉴权尚未配置')
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.opener = opener or build_opener(NoRedirect())
        self.routes = {**self.ROUTES, **(routes or {})}
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.encode_query = encode_query
        self.decode_response = decode_response

    @classmethod
    def from_settings(cls):
        from ..system_config import get_setting
        from importlib import import_module
        name = __package__ + '.site_java_private'
        try:
            adapter = import_module(name)
        except ModuleNotFoundError as error:
            if error.name != name:
                raise
            adapter = None
        return cls(get_setting('JAVA_API_BASE_URL', ''), get_setting('JAVA_API_TOKEN', ''),
                   routes=getattr(adapter, 'ROUTES', None),
                   encode_query=getattr(adapter, 'encode_query', None),
                   decode_response=getattr(adapter, 'decode_response', None))

    def read(self, capability, query, result_type):
        path = self.routes[capability]
        if path.startswith('/') or '://' in path or '..' in path.split('/'):
            raise IntegrationUnavailable('Java查询路由配置不正确')
        fields = query.model_dump(mode='json', by_alias=True)
        if self.encode_query:
            fields = self.encode_query(capability, fields)
        request = Request(
            self.base_url + '/' + path,
            data=json.dumps(fields, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                     'X-Integration-Token': self.token}, method='POST')
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                if response.status != 200:
                    raise IntegrationUnavailable('Java资料查询未成功返回')
                raw = response.read(self.max_bytes + 1)
            if len(raw) > self.max_bytes:
                raise DataContractError('Java查询返回超过单页限制，请调整分页大小')
            payload = json.loads(raw)
            if self.decode_response:
                payload = self.decode_response(capability, payload)
            return TypeAdapter(result_type).validate_python(payload)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            if isinstance(error, HTTPError):
                error.close()
            # Never surface upstream bodies, credentials, URLs or private schema.
            raise IntegrationUnavailable('Java资料服务暂不可用，请检查地址、鉴权或网络') from None
        except (ValueError, ValidationError):
            raise DataContractError('Java查询返回与约定字段实体不一致') from None


class JavaHTTPSource:
    def __init__(self, client):
        self.client = client

    def accounts(self, query):
        page = self.client.read('accounts', query, Page[Account])
        if (page.page_no != query.page_no or page.page_size != query.page_size
                or any(not account.eligible or not self._updated(account.updated_at, query) for account in page.items)
                or query.account_ids is not None and any(a.account_id not in query.account_ids for a in page.items)):
            raise DataContractError('Java账号查询的分页或参与资格不符合约定')
        return page

    def topics(self, query):
        page = self.client.read('topics', query, Page[Topic])
        if (page.page_no != query.page_no or page.page_size != query.page_size
                or any(query.source and t.source != query.source for t in page.items)
                or any(query.topic_type and t.topic_type != query.topic_type for t in page.items)
                or any(not self._updated(t.updated_at, query) for t in page.items)
                or query.available_only and any(not t.available for t in page.items)
                or query.valid_at is not None and any(
                    t.valid_from is not None and t.valid_from > query.valid_at
                    or t.valid_to is not None and t.valid_to < query.valid_at for t in page.items)
                or query.topic_ids is not None and any(t.topic_id not in query.topic_ids for t in page.items)):
            raise DataContractError('Java选题查询的分页或来源不符合约定')
        return page

    def marketing_contents(self, query):
        page = self.client.read('marketing_contents', query, Page[MarketingContent])
        if (page.page_no != query.page_no or page.page_size != query.page_size
                or any(row.account_id != query.account_id for row in page.items)):
            raise DataContractError('Java营销内容查询的账号或分页不符合约定')
        return page

    def effective_marketing(self, query):
        rows = self.client.read('effective_marketing', query, list[EffectivePlacement])
        if (any(row.account_id != query.account_id or row.publish_date != query.publish_date for row in rows)
                or len({row.placement_id for row in rows}) != len(rows)):
            raise DataContractError('Java有效营销投放返回了其它账号、日期或重复记录')
        return rows

    @staticmethod
    def _updated(value, query):
        return ((query.updated_from is None or value >= query.updated_from)
                and (query.updated_to is None or value < query.updated_to))


class JavaProductionStatus:
    """Read-only port: execution, claiming and retries belong to the content side."""

    def __init__(self, client):
        self.client = client

    def production_results(self, query):
        rows = self.client.read('production_results', query, list[ProductionRecord])
        if any(row.slot_id not in query.slot_ids for row in rows):
            raise DataContractError('Java生产状态包含未查询的策划明细')
        keys = [(row.slot_id, row.version) for row in rows]
        if len(set(keys)) != len(keys):
            raise DataContractError('Java生产状态返回重复的明细版本')
        return rows

    def marketing_results(self, query):
        rows = self.client.read('marketing_results', query, list[MarketingProductionRecord])
        if any(row.task_code not in query.task_codes for row in rows):
            raise DataContractError('Java营销状态包含未查询的需求')
        if len(set(row.task_code for row in rows)) != len(rows):
            raise DataContractError('Java营销状态返回重复需求')
        return rows
