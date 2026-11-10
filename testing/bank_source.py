"""Bounded, read-only source-contract probe for outside and inside; no DB/model settings loaded."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CAPABILITIES = ('accounts', 'topics', 'marketing-contents', 'effective-marketing',
                'production-status', 'marketing-status', 'marketing-allocations')
PAGED = CAPABILITIES[:3]


class ProbeError(Exception):
    """Only constant diagnostic codes, never source data or remote error bodies."""


def _contracts():
    sys.path.insert(0, str(ROOT / 'python-backend'))
    from pydantic import Field, TypeAdapter, ValidationError
    from app.content_planning.bank_bridge.contracts import (
        Contract, AccountQuery, TopicQuery, MarketingQuery, EffectivePlacementQuery,
        ProductionQuery, MarketingStatusQuery, Account, Topic, MarketingContent, Page,
        EffectivePlacement, ProductionRecord, MarketingProductionRecord)

    class ApprovedQuery(Contract):
        task_code: str = Field(min_length=1, max_length=64)

    class ApprovedContent(Contract):
        task_code: str = Field(min_length=1, max_length=64)
        content_id: str = Field(min_length=1, max_length=64)
        account_id: str = Field(min_length=1, max_length=64)
        title: str = Field(min_length=1)
        body: str = Field(min_length=1)
        content_type: str = Field(min_length=1)
        approved_at: datetime

    requests = dict(zip(CAPABILITIES, (AccountQuery, TopicQuery, MarketingQuery,
                    EffectivePlacementQuery, ProductionQuery, MarketingStatusQuery, ApprovedQuery)))
    responses = dict(zip(CAPABILITIES, (Page[Account], Page[Topic], Page[MarketingContent],
                     list[EffectivePlacement], list[ProductionRecord], list[MarketingProductionRecord],
                     list[ApprovedContent])))
    return requests, {name: TypeAdapter(model) for name, model in responses.items()}, ValidationError


def prepare(config):
    requests, responses, validation_error = _contracts()
    if not isinstance(config, dict) or set(config) != {'queries'} or not isinstance(config['queries'], dict):
        raise ValueError('配置应只包含queries对象')
    if not config['queries'] or set(config['queries']) - set(CAPABILITIES):
        raise ValueError('配置包含未约定的资料查询能力')
    queries = {}
    for capability, raw in config['queries'].items():
        if not isinstance(raw, dict):
            raise ValueError('每个能力的query须为对象')
        raw = dict(raw)
        if capability in PAGED and 'page_size' not in raw and '每页条数' not in raw:
            raw['page_size'] = 10
        try:
            model = requests[capability].model_validate_json(json.dumps(raw), strict=True)
        except validation_error:
            raise ValueError('查询参数不符合契约，请检查配置字段、类型及范围') from None
        canonical = model.model_dump(mode='json', exclude_none=True)
        for key in ('account_ids', 'topic_ids', 'slot_ids', 'task_codes'):
            if key in requests[capability].model_fields:
                ids = canonical.get(key)
                if not ids or any(not isinstance(x, str) or not x.strip() or x != x.strip() for x in ids):
                    raise ValueError('验收须填写明确、非空的样本ID，禁止全量扫描')
        if capability in PAGED and (model.page_no != 1 or model.page_size > 50):
            raise ValueError('只读验收须从第1页开始，每页不超过50条')
        queries[capability] = model
    return queries, responses, validation_error


def _base_url(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or '\\' in value
            or any(ch.isspace() for ch in value) or '..' in parsed.path):
        raise ValueError('资料入口地址无效，不允许凭据、查询参数或路径跳转')
    return value.rstrip('/')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def http_transport(base, timeout):
    # Do not inherit a developer's external HTTP proxy when running inside the bank.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def send(capability, query, token):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Integration-Token'] = token
        request = urllib.request.Request(base + '/' + capability + '/query',
                                         data=json.dumps(query).encode('utf-8'), headers=headers)
        try:
            with opener.open(request, timeout=timeout) as response:
                data = response.read(8 * 1024 * 1024 + 1)
                if len(data) > 8 * 1024 * 1024:
                    raise ProbeError('RESPONSE_TOO_LARGE')
                try:
                    return response.status, json.loads(data)
                except (ValueError, UnicodeError):
                    raise ProbeError('INVALID_JSON') from None
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            return code, None
    return send


def _check(capability, parsed, query, seen):
    rows = parsed.items if capability in PAGED else parsed
    if capability in PAGED and (parsed.page_no != query.page_no or parsed.page_size != query.page_size):
        raise ProbeError('PAGE_METADATA_MISMATCH')
    for row in rows:
        identity = (row.slot_id, row.version) if capability == 'production-status' else (
            getattr(row, {'accounts': 'account_id', 'topics': 'topic_id', 'marketing-contents': 'content_id',
                          'effective-marketing': 'placement_id', 'marketing-status': 'task_code',
                          'marketing-allocations': 'content_id'}[capability]),)
        if identity in seen:
            raise ProbeError('DUPLICATE_ID_OR_UNSTABLE_PAGE')
        seen.add(identity)
        checks = [('account_ids', 'account_id'), ('topic_ids', 'topic_id'),
                  ('slot_ids', 'slot_id'), ('task_codes', 'task_code')]
        for query_field, result_field in checks:
            ids = getattr(query, query_field, None)
            if ids is not None and getattr(row, result_field) not in ids:
                raise ProbeError('RECORD_OUTSIDE_REQUEST')
        for field in ('account_id', 'task_code', 'publish_date'):
            expected = getattr(query, field, None)
            if expected is not None and getattr(row, field) != expected:
                raise ProbeError('RECORD_OUTSIDE_REQUEST')
        if capability == 'accounts':
            if not row.eligible or any(x.account_id != row.account_id for x in row.interactions):
                raise ProbeError('ACCOUNT_QUALIFICATION_OR_INTERACTION_MISMATCH')
        if capability in ('accounts', 'topics'):
            if ((query.updated_from and row.updated_at < query.updated_from)
                    or (query.updated_to and row.updated_at >= query.updated_to)):
                raise ProbeError('UPDATE_WINDOW_MISMATCH')
        if capability == 'topics':
            if ((query.source and row.source != query.source) or (query.topic_type and row.topic_type != query.topic_type)
                    or (query.available_only and not row.available)
                    or (query.valid_at and ((row.valid_from and query.valid_at < row.valid_from)
                                          or (row.valid_to and query.valid_at > row.valid_to)))):
                raise ProbeError('TOPIC_FILTER_MISMATCH')
    return len(rows)


def verify(config, token, send, pages=2):
    if not isinstance(token, str) or not token.strip() or any(ch in token for ch in '\r\n\0'):
        raise ValueError('须通过环境变量配置有效的内部查询令牌')
    if not isinstance(pages, int) or isinstance(pages, bool) or not 1 <= pages <= 3:
        raise ValueError('验收页数须为1～3')
    queries, models, validation_error = prepare(config)
    probe = next(iter(queries))
    auth_body = queries[probe].model_dump(mode='json', exclude_none=True)
    checks = []
    auth = False
    try:
        auth = send(probe, auth_body, None)[0] in (401, 403)
    except Exception:
        pass
    for capability in CAPABILITIES:
        result = dict(capability=capability, status='not_checked', row_count=0, pages=0)
        checks.append(result)
        if capability not in queries or not auth:
            continue
        query = queries[capability]
        seen = set()
        started = time.monotonic()
        try:
            for page in range(pages if capability in PAGED else 1):
                request = query.model_copy(update={'page_no': page + 1}) if capability in PAGED else query
                code, payload = send(capability, request.model_dump(mode='json', exclude_none=True), token)
                if code != 200:
                    raise ProbeError('HTTP_' + str(int(code)))
                parsed = models[capability].validate_python(payload)
                result['row_count'] += _check(capability, parsed, request, seen)
                result['pages'] += 1
                if capability not in PAGED:
                    break
                if page and result['total'] != parsed.total:
                    raise ProbeError('TOTAL_CHANGED_DURING_SCAN')
                result['total'] = parsed.total
                if request.page_no * request.page_size >= parsed.total:
                    break
            result['status'] = 'passed' if result['row_count'] else 'empty'
        except validation_error as error:
            result.update(status='failed', error='RESPONSE_CONTRACT_ERROR',
                          issues=[dict(path='.'.join(map(str, x['loc'])), type=x['type'])
                                  for x in error.errors(include_input=False, include_context=False, include_url=False)][:20])
        except ProbeError as error:
            result.update(status='failed', error=str(error))
        except Exception:
            result.update(status='failed', error='TRANSPORT_OR_RESPONSE_ERROR')
        result['duration_ms'] = round((time.monotonic() - started) * 1000)
    failed = not auth or any(x['status'] == 'failed' for x in checks)
    passed = auth and all(x['status'] == 'passed' for x in checks)
    return dict(status='failed' if failed else 'passed' if passed else 'incomplete',
                unauthorized_rejected=auth, checks=checks, model_calls=0, database_writes=0,
                note='只验证显式样本和有限分页；空结果不算字段验收通过，权限及性能仍需现场验收')


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='行内/行外资料接入只读验收；不加载数据库或模型配置')
    parser.add_argument('--init', type=Path, help='创建合成样本配置，编辑成现场样本ID后再验收')
    parser.add_argument('--cases', type=Path)
    parser.add_argument('--base', help='Java内部资料入口完整前缀，不是Python服务地址')
    parser.add_argument('--token-env', default='BANK_SOURCE_TEST_TOKEN')
    parser.add_argument('--pages', type=int, default=2)
    parser.add_argument('--timeout', type=int, default=15)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.init:
        if args.cases or args.base or args.output:
            parser.error('--init不能与验收参数混用')
        args.init.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.init.open('x', encoding='utf-8') as stream:
                stream.write((ROOT / 'testing/bank-source-cases.example.json').read_text(encoding='utf-8'))
        except FileExistsError:
            parser.error('样本配置已存在，不覆盖原文件')
        print('已生成合成样本配置，请替换现场样本ID；尚未发送请求。')
        return 0
    if not args.base or not args.cases or not 1 <= args.timeout <= 60:
        parser.error('须提供--base和--cases；timeout为1～60秒')
    output = args.output or ROOT / 'run/bank-source-check' / datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    if (output / 'summary.json').exists():
        parser.error('报告已存在，请选择新目录以保留验收证据')
    try:
        base = _base_url(args.base)
        config = json.loads(args.cases.read_text(encoding='utf-8-sig'))
        result = verify(config, os.environ.get(args.token_env), http_transport(base, args.timeout), args.pages)
    except (ValueError, OSError):
        parser.error('样本配置、入口地址或令牌无效，请检查文件和环境变量')
    output.mkdir(parents=True, exist_ok=True)
    report = output / 'summary.json'
    with report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print('接入验收：' + result['status'])
    for item in result['checks']:
        print(item['capability'] + ': ' + item['status'] + (' / ' + item['error'] if 'error' in item else ''))
    print('报告：' + str(report))
    return 0 if result['status'] == 'passed' else 2 if result['status'] == 'incomplete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
