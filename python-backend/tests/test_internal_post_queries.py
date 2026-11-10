"""Exercise Java-facing POST routes through ASGI, without model or database I/O."""
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.content_planning import algorithm_config_commands as config
from app.content_planning import manual_compute as manual
from app.content_planning import planning_pipeline_api as pipeline
from app.content_planning.api import labels


@pytest.fixture
def client():
    app = FastAPI()
    for router in (config.router, labels.router, pipeline.router, manual.router):
        app.include_router(router)
    with patch('app.content_planning.api.security.get_setting', return_value='test-token'):
        with TestClient(app) as http:
            yield http


HEADERS = {'X-Integration-Token': 'test-token'}
QUERIES = [
    '/api/internal/algorithm-config/query', '/api/tag-taxonomy/query',
    '/api/internal/planning-pipelines/query', '/api/internal/planning-pipelines/88/query',
    '/api/internal/manual-computations/JMAN-test/query',
]


@pytest.mark.parametrize('url', QUERIES + ['/api/tag-taxonomy/save'])
def test_post_requires_service_identity_before_query_or_write(client, url):
    assert client.post(url, json={}).status_code == 401
    assert client.post(url, json={}, headers={'X-Integration-Token': 'wrong'}).status_code == 401


def test_read_routes_return_contract_and_reject_removed_methods(client):
    cases = [
        ('/api/internal/algorithm-config/query', '/api/internal/algorithm-config',
         'app.content_planning.services.configuration.get_config', {'version': 3}),
        ('/api/tag-taxonomy/query', '/api/tag-taxonomy',
         'app.content_planning.services.labels.get_tag_taxonomy', {'version': 2, 'items': {}}),
        ('/api/internal/planning-pipelines/88/query', '/api/internal/planning-pipelines/88',
         'app.content_planning.planning_pipeline_api.read_pipeline', {'id': 88, 'status': 'running'}),
        ('/api/internal/manual-computations/JMAN-test/query', '/api/internal/manual-computations/JMAN-test',
         'app.content_planning.manual_compute.read', {'request_id': 'JMAN-test', 'status': 'pending'}),
    ]
    for post_url, get_url, handler, result in cases:
        with patch(handler, return_value=result) as read:
            assert client.post(post_url, json={}, headers=HEADERS).json() == result
            assert client.get(get_url, headers=HEADERS).status_code in (404, 405)
            read.assert_called_once()


def test_pipeline_query_reads_json_pagination_and_validates_before_read(client):
    with patch.object(pipeline, 'list_planning_pipelines', return_value={'pipelines': []}) as read:
        for body in ({'limit': 0}, {'limit': 201}, {'after_id': -1}):
            assert client.post('/api/internal/planning-pipelines/query', json=body, headers=HEADERS).status_code == 422
        read.assert_not_called()
        result = client.post('/api/internal/planning-pipelines/query', json={'limit': 20, 'after_id': 8}, headers=HEADERS)
        assert result.status_code == 200
        read.assert_called_once_with(after_id=8, limit=20)


def test_post_taxonomy_save_validates_and_uses_trusted_operator(client):
    headers = {**HEADERS, 'X-Operator-Id': 'HOST-UM'}
    with patch.object(labels.service, 'put_tag_taxonomy', return_value={'version': 3}) as save:
        assert client.post('/api/tag-taxonomy/save', json={'items': []}, headers=headers).status_code == 422
        save.assert_not_called()
        body = {'tags': {f'T{i}': ['label'] for i in range(1, 6)}, 'expected_version': 2}
        result = client.post('/api/tag-taxonomy/save', json=body, headers=headers)
        assert result.status_code == 200
        assert save.call_args.kwargs['operator'] == 'HOST-UM'
        assert save.call_args.kwargs['payload'].expected_version == 2


def test_post_query_preserves_not_found_without_mutating_task(client):
    with patch.object(manual, 'read', side_effect=HTTPException(404, '计算任务不存在')) as read:
        result = client.post('/api/internal/manual-computations/JMAN-missing/query', json={}, headers=HEADERS)
        assert result.status_code == 404
        assert result.json()['detail'] == '计算任务不存在'
        read.assert_called_once_with('JMAN-missing')


def test_removed_taxonomy_write_and_pipeline_list_cannot_be_called(client):
    with patch.object(labels.service, 'put_tag_taxonomy') as save, patch.object(pipeline, 'connection') as connect:
        assert client.put('/api/tag-taxonomy', json={}, headers=HEADERS).status_code in (404, 405)
        assert client.get('/api/internal/planning-pipelines', headers=HEADERS).status_code == 405
        save.assert_not_called()
        connect.assert_not_called()
