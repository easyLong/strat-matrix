import copy
import json
from pathlib import Path
import urllib.error
from unittest.mock import Mock, patch

import pytest

from testing.bank_source import CAPABILITIES, _base_url, http_transport, main, prepare, verify

ROOT = Path(__file__).resolve().parents[2]


def samples():
    config = json.loads((ROOT/'testing/bank-source-cases.example.json').read_text(encoding='utf-8'))
    fixture = json.loads((ROOT/'java-backend/src/test/resources/bank-source/contract-sample.json').read_text(encoding='utf-8'))
    for capability in CAPABILITIES[:3]:
        fixture[capability]['page_size'] = 10
    return config, fixture


def transport(fixture, calls):
    def send(capability, query, token):
        calls.append((capability, query, token))
        if token is None:
            return 401, None
        return 200, copy.deepcopy(fixture[capability])
    return send


def test_all_seven_contracts_auth_and_no_source_values_in_report():
    config, fixture = samples()
    calls = []
    result = verify(config, 'private-test-token', transport(fixture, calls))
    assert result['status'] == 'passed'
    assert len(calls) == 8
    assert result['unauthorized_rejected']
    report = json.dumps(result, ensure_ascii=False)
    assert all(value not in report for value in ('private-test-token', 'UM001', '契约测试账号', '营销正文'))
    assert result['model_calls'] == result['database_writes'] == 0


def test_missing_and_empty_capabilities_are_not_successful_field_verification():
    config, fixture = samples()
    fixture['production-status'] = []
    del config['queries']['marketing-status']
    result = verify(config, 'token', transport(fixture, []))
    statuses = {x['capability']: x['status'] for x in result['checks']}
    assert result['status'] == 'incomplete'
    assert statuses['production-status'] == 'empty'
    assert statuses['marketing-status'] == 'not_checked'


@pytest.mark.parametrize('patch_query', [
    {}, {'account_ids': []}, {'account_ids': [' A1']}, {'account_ids': ['A1'], 'page_size': 51},
    {'account_ids': ['A1'], 'page_no': 2}, {'account_ids': ['A1'], 'page_size': '1'},
    {'account_ids': ['A1'], 'unexpected': True},
])
def test_invalid_or_unbounded_queries_are_rejected_before_http(patch_query):
    config = {'queries': {'accounts': patch_query}}
    send = Mock()
    with pytest.raises(ValueError):
        verify(config, 'token', send)
    send.assert_not_called()


def test_auth_failure_aborts_authenticated_probes_and_remote_errors_do_not_leak():
    config, _ = samples()
    send = Mock(return_value=(200, {'private': 'must not appear'}))
    result = verify(config, 'token', send)
    assert result['status'] == 'failed' and send.call_count == 1
    assert all(x['status'] == 'not_checked' for x in result['checks'])
    def failed(capability, query, token):
        return (503, {'detail': 'private SQL password=secret'}) if token else (401, None)
    result = verify(config, 'token', failed)
    assert result['status'] == 'failed'
    assert all(x['error'] == 'HTTP_503' for x in result['checks'])
    assert 'secret' not in json.dumps(result)


def test_response_errors_include_field_paths_not_personal_values_and_scope_is_verified():
    config, fixture = samples()
    fixture['accounts']['items'][0]['nickname'] = {'private': 'hidden-name'}
    fixture['topics']['items'][0]['topic_id'] = 'UNREQUESTED'
    result = verify(config, 'token', transport(fixture, []))
    by_capability = {x['capability']: x for x in result['checks']}
    assert result['status'] == 'failed'
    assert by_capability['accounts']['issues'][0]['path'] == 'items.0.nickname'
    assert by_capability['topics']['error'] == 'RECORD_OUTSIDE_REQUEST'
    assert 'hidden-name' not in json.dumps(result)


def test_paging_is_bounded_and_repeated_ids_are_detected():
    config, fixture = samples()
    config = {'queries': {'accounts': {'account_ids': ['A1', 'A2', 'A3'], 'page_size': 1}}}
    fixture['accounts'].update(total=3, page_size=1)
    calls = []
    def send(capability, query, token):
        calls.append(query)
        if not token:
            return 401, None
        page = copy.deepcopy(fixture['accounts'])
        page['page_no'] = query['page_no']
        page['items'][0]['account_id'] = 'A' + str(query['page_no'])
        page['items'][0]['interactions'] = []
        return 200, page
    result = verify(config, 'token', send, pages=2)
    assert len(calls) == 3
    assert result['checks'][0]['pages'] == 2
    assert result['checks'][0]['row_count'] == 2
    assert result['status'] == 'incomplete'  # six capabilities absent
    def duplicate(capability, query, token):
        code, page = send(capability, query, token)
        if token:
            page['items'][0]['account_id'] = 'A1'
        return code, page
    assert verify(config, 'token', duplicate)['checks'][0]['error'] == 'DUPLICATE_ID_OR_UNSTABLE_PAGE'


def test_redirects_proxies_bad_json_and_large_bodies_are_controlled():
    from testing.bank_source import ProbeError
    with patch('testing.bank_source.urllib.request.build_opener') as build:
        opener = build.return_value
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = b'not-json'
        send = http_transport('http://host/api/plan/internal/source', 3)
        assert build.call_args.args[0].proxies == {}
        assert build.call_args.args[1].redirect_request(None, None, 302, None, None, 'http://other') is None
        with pytest.raises(ProbeError, match='INVALID_JSON'):
            send('accounts', {}, 'token')
        response.read.return_value = b'x' * (8*1024*1024+1)
        with pytest.raises(ProbeError, match='RESPONSE_TOO_LARGE'):
            send('accounts', {}, 'token')
        opener.open.side_effect = urllib.error.HTTPError('http://host', 302, 'redirect', {}, None)
        assert send('accounts', {}, 'token') == (302, None)
    for url in ('http://user:password@host/api', 'http://host/api?token=secret', 'http://host/../other', 'file:///tmp/data'):
        with pytest.raises(ValueError):
            _base_url(url)


def test_init_and_existing_report_do_not_send_http_or_overwrite(tmp_path):
    config = tmp_path/'cases.json'
    assert main(['--init', str(config)]) == 0
    before = config.read_text(encoding='utf-8')
    with pytest.raises(SystemExit):
        main(['--init', str(config)])
    assert config.read_text(encoding='utf-8') == before
    output = tmp_path/'report'
    output.mkdir()
    (output/'summary.json').write_text('{}')
    with patch('testing.bank_source.http_transport') as send, pytest.raises(SystemExit):
        main(['--cases',str(config),'--base','http://host/api/plan/internal/source','--output',str(output)])
    send.assert_not_called()
