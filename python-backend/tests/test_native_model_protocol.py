"""Bank doubaoNative contract and loopback transport; never contacts the bank/model."""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from unittest.mock import patch

import pytest

from app.content_planning import doubao_labeling as model
from app.content_planning import matching_quality_model as quality
from app.content_planning.config import PlanningConfig
from app.content_planning.runtime import PlanningRuntime
from app.content_planning.system_config import override_config
from app.content_planning.native_model_protocol import request_body, completion_result, NativeProtocolError


def response(text='{"ok":true}'):
    return {'id': 'resp-test', 'model': 'bank-text', 'status': 'completed', 'output': [
        {'type': 'reasoning', 'summary': []},
        {'type': 'message', 'role': 'assistant', 'status': 'completed',
         'content': [{'type': 'output_text', 'text': text}]}],
        'usage': {'input_tokens': 12, 'output_tokens': 4, 'total_tokens': 16,
                  'output_tokens_details': {'reasoning_tokens': 0}}}


@contextmanager
def bank_gateway(result=None, status=200):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append((self.path, dict(self.headers), body))
            raw = json.dumps(result if result is not None else response()).encode()
            self.send_response(status)
            if status == 302:self.send_header('Location', '/must-not-follow')
            if status == 429:self.send_header('Retry-After', '3')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers();self.wfile.write(raw)
        def log_message(self, *args):pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True);thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/bank/doubaoNative', seen
    finally:
        server.shutdown();server.server_close();thread.join(3)


def config(url='http://bank.invalid/doubaoNative'):
    return model.DoubaoConfig(url, '', 'bank-text', 'vector', 5, protocol='doubao_native')


def payload():
    return {'model': 'bank-text', 'messages': [{'role': 'system', 'content': '系统提示词'},
        {'role': 'user', 'content': '完整提示词'}], 'temperature': 0,
        'thinking': {'type': 'disabled'}, 'max_tokens': 300,
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'TestResult', 'strict': True,
            'schema': {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
                       'required': ['ok'], 'additionalProperties': False}}}}


def test_native_roundtrip_matches_bank_request_and_keeps_usage():
    source = payload()
    with bank_gateway() as (url, seen):
        result = model.ark_post(config(url), '/chat/completions', source)
    assert len(seen) == 1 and seen[0][0] == '/bank/doubaoNative'
    _, headers, body = seen[0]
    assert not any(k.lower() == 'authorization' for k in headers)
    assert body['input'] == [{'role': m['role'], 'type': 'message', 'content': m['content']} for m in source['messages']]
    assert body['text']['format'] == {'type': 'json_schema', **source['response_format']['json_schema']}
    assert body['temperature'] == 0 and body['thinking'] == {'type': 'disabled'}
    assert body['stream'] is False and body['max_output_tokens'] == 300
    assert 'messages' not in body and 'response_format' not in body and 'max_tokens' not in body
    assert result['choices'][0]['message']['content'] == '{"ok":true}'
    assert result['usage'] == response()['usage']
    assert source == payload()  # Frozen caller input is not mutated.


def test_native_configuration_does_not_require_public_key_or_embedding_endpoint_for_text():
    values = {'PLANNING_ENV': 'inside', 'MODEL_PROTOCOL': 'doubao_native',
              'MODEL_BASE_URL': 'http://bank.invalid/doubaoNative', 'MODEL_NAME': 'bank-text'}
    with override_config(values), patch.object(model, 'open_request') as network:
        cfg = model.read_config()
        assert cfg.protocol == 'doubao_native' and cfg.api_key == ''
        assert cfg.base_url == values['MODEL_BASE_URL']
        with pytest.raises(model.DoubaoConfigurationError):model.read_embedding_config()
        with pytest.raises(model.DoubaoConfigurationError, match='EMBEDDING_BASE_URL'):
            model.embed_text('text', cfg)
    network.assert_not_called()


def test_host_mapping_and_protocol_apply_without_changing_global_settings():
    cfg = PlanningConfig.from_mapping({'PLANNING_MODEL_PROTOCOL': 'doubao_native',
        'PLANNING_MODEL_BASE_URL': 'http://bank.invalid/doubaoNative',
        'PLANNING_MODEL_NAME': 'bank-text'})
    assert cfg.model_protocol == 'doubao_native' and cfg.settings['MODEL_PROTOCOL'] == 'doubao_native'
    runtime = PlanningRuntime(cfg)
    with runtime.bind():
        # Pure config selection; avoid any database access.
        with override_config(dict(cfg.settings)):
            assert model.read_config().protocol == 'doubao_native'


def test_native_text_never_forwards_embedding_key_and_can_use_host_gateway_header():
    runtime = PlanningRuntime(PlanningConfig(model_protocol='doubao_native',
        model_headers={'X-Gateway-App': 'planning-test'}))
    with bank_gateway() as (url, seen), runtime.bind():
        model.ark_post(replace(config(url), api_key='unused-synthetic-key'), '/chat/completions', payload())
    assert not any(k.lower() == 'authorization' for k in seen[0][1])
    assert seen[0][1]['X-Gateway-App'] == 'planning-test'


def test_preflight_reports_text_ready_but_vector_not_ready_without_network():
    from app.content_planning.onsite_check import configuration_checks
    with patch.object(model, 'open_request') as network:
        checks = configuration_checks({'MODEL_PROTOCOL': 'doubao_native',
            'MODEL_BASE_URL': 'http://bank.invalid/doubaoNative', 'MODEL_NAME': 'bank-text',
            'INTEGRATION_TOKEN': 'test-only-token'})
    network.assert_not_called()
    assert next(c for c in checks if c['name'] == 'model_configuration')['status'] == 'passed'
    assert next(c for c in checks if c['name'] == 'embedding_configuration')['status'] == 'not_ready'


@pytest.mark.parametrize('url', ['file:///vector', 'https://user:secret@vector/v3', 'https://vector/v3?key=secret'])
def test_embedding_gateway_rejects_unsafe_address_without_echo(url):
    from app.content_planning.system_config_catalog import validate_value
    with pytest.raises(ValueError) as error:validate_value('EMBEDDING_BASE_URL', url)
    assert 'secret' not in str(error.value)


def test_native_embeddings_use_explicit_separate_compatible_service():
    with bank_gateway({'data': {'embedding': [3., 4.]}, 'model': 'vector'}) as (url, seen):
        cfg = replace(config(), api_key='synthetic-key', embedding_base_url=url.rsplit('/', 1)[0]+'/vectors')
        result = model.embed_text('公开测试文本', cfg)
    assert result['vector'] == [.6, .8]
    assert seen[0][0] == '/bank/vectors/embeddings/multimodal'
    assert seen[0][1]['Authorization'] == 'Bearer synthetic-key'
    assert seen[0][2]['input'] == [{'type': 'text', 'text': '公开测试文本'}]


def test_separate_embedding_reader_cannot_fall_back_to_native_or_public_endpoint():
    values = {'MODEL_PROTOCOL': 'doubao_native', 'ARK_API_KEY': 'synthetic-key',
              'EMBEDDING_MODEL_NAME': 'vector', 'MODEL_BASE_URL': 'http://bank.invalid/doubaoNative'}
    with override_config(values):
        with pytest.raises(model.DoubaoConfigurationError, match='EMBEDDING_BASE_URL'):model.read_embedding_config()
    with override_config({**values, 'EMBEDDING_BASE_URL': 'http://vector.invalid/v3'}):
        assert model.read_embedding_config().base_url == 'http://vector.invalid/v3'


@pytest.mark.parametrize('status', ['incomplete', 'failed', 'queued', 'in_progress', None])
def test_unfinished_responses_never_become_success(status):
    with pytest.raises(NativeProtocolError):completion_result({**response(), 'status': status})


@pytest.mark.parametrize('value', [
    {'code': 200, 'data': response()}, {'choices': []},
    {**response(), 'output': []}, {**response(), 'output': [{'type': 'function_call'}]},
    {**response(), 'output': [{'type': 'message', 'role': 'assistant', 'content': [{'type': 'refusal', 'refusal': 'private'}]}]},
    {**response(), 'output': response()['output'][1:] * 2},
    {**response(), 'error': {'message': 'private upstream text'}},
])
def test_wrong_envelopes_refusals_and_ambiguous_outputs_fail_closed(value):
    with pytest.raises(NativeProtocolError) as error:completion_result(value)
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('status,error', [(401, model.DoubaoAccessError), (429, model.DoubaoRateLimited),
                                        (503, model.DoubaoUnavailable), (302, model.DoubaoResponseError)])
def test_native_http_errors_keep_existing_sanitized_semantics(status, error):
    with bank_gateway({'error': 'private upstream body'}, status) as (url, seen):
        with pytest.raises(error) as raised:model.ark_post(config(url), '/chat/completions', payload())
    assert len(seen) == 1 and 'private' not in str(raised.value) and url not in str(raised.value)


def test_native_inherits_shared_capacity_limit_before_any_http():
    from app.content_planning import model_capacity as capacity
    with capacity.budget.slot('text', 2), capacity.budget.slot('text', 2), patch.object(model, 'open_request') as network:
        with pytest.raises(capacity.CapacityExceeded):model.ark_post(config(), '/chat/completions', payload())
    network.assert_not_called()


def test_native_annotation_mapping_and_pair_judgment_schemas_are_closed():
    for name, item in [('topics', quality.TopicAnnotation), ('results', quality.PairJudgment)]:
        schema = quality.keyed_schema(name, ['topic-1', 'topic-2'], item)
        assert schema['additionalProperties'] is False
        assert schema['properties'][name]['required'] == ['topic-1', 'topic-2']
        assert schema['properties'][name]['properties']['topic-1']['additionalProperties'] is False
    schema = quality.ModelAccountMapping.model_json_schema()
    assert schema['$defs']['ModelMappingItem']['additionalProperties'] is False
    assert model.json_output_format(config(), 'AccountMapping', schema)['json_schema']['strict'] is True


def test_native_label_schema_covers_six_dimensions_before_embedding():
    tax = {f'T{i}': ['标签'] for i in range(1, 6)}
    labels = {**{k: v[0] for k, v in tax.items()}, 'T6': '具体需求'}
    with bank_gateway(response(json.dumps({'labels': labels}))) as (url, seen), \
            patch.object(model, 'embed_text', return_value={'vector': [1., 0.], 'vector_model': 'vector'}):
        got = model.label_topic(model.LabelInput(topic_id='T1', topic={'title': '测试'},
                                taxonomy_version=1, taxonomy=tax), config(url))
    assert got['labels'] == labels
    schema = seen[0][2]['text']['format']['schema']
    assert schema['properties']['labels']['required'] == list(model.DIMENSIONS)
    assert schema['properties']['labels']['properties']['T1']['enum'] == ['标签']


def test_native_v19_chat_consumes_normalized_response():
    with bank_gateway() as (url, seen), patch.object(quality, 'read_config', return_value=config(url)):
        got = quality.chat({'chat_model': 'bank-text', 'embedding_model': 'vector'},
                           '只返回JSON', {'public': 'fixture'}, response_schema=payload()['response_format']['json_schema']['schema'])
    assert got == {'ok': True} and seen[0][2]['text']['format']['type'] == 'json_schema'


@pytest.mark.parametrize('changes', [{'stream': True}, {'messages': []},
    {'messages': [{'role': 'tool', 'content': 'tool'}]}, {'response_format': {'type': 'invalid'}}])
def test_unsupported_requests_are_rejected_without_network(changes):
    with pytest.raises(NativeProtocolError):request_body({**payload(), **changes})
