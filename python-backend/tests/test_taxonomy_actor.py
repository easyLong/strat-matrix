"""The Java taxonomy boundary supplies a trusted operator, not a browser body field."""
from unittest.mock import patch
import pytest
from starlette.requests import Request
from app.api.labels import put_tag_taxonomy
from app.services.labels import TagTaxonomyInput
from app.services import labels
from app.services.errors import ApplicationError


def test_java_operator_is_passed_to_algorithm_service():
    request = Request({'type': 'http', 'headers': [(b'x-operator-id', b'HOST-UM')]})
    payload = TagTaxonomyInput(tags={f'T{i}': ['label'] for i in range(1, 6)})
    with patch.object(labels, 'put_tag_taxonomy', return_value={'version': 2}) as save:
        assert put_tag_taxonomy(payload, request) == {'version': 2}
        save.assert_called_once_with(payload=payload, operator='HOST-UM')


@pytest.mark.parametrize('actor', ['', 'a' * 65, 'bad\r\nactor'])
def test_invalid_operator_is_rejected_before_database_access(actor):
    payload = TagTaxonomyInput(tags={f'T{i}': ['label'] for i in range(1, 6)})
    with patch.object(labels, 'connection', side_effect=AssertionError('must not connect')):
        with pytest.raises(ApplicationError):
            labels.put_tag_taxonomy(payload, operator=actor)


def test_taxonomy_write_authenticates_java_before_using_operator_header():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.labels import router
    app = FastAPI()
    app.include_router(router)
    body = {'tags': {f'T{i}': ['label'] for i in range(1, 6)}, 'expected_version': 1}
    with patch('app.api.security.get_setting', return_value='test-token'), \
            patch.object(labels, 'put_tag_taxonomy', return_value={'version': 2}) as save:
        client = TestClient(app)
        assert client.put('/api/tag-taxonomy', json=body, headers={'X-Operator-Id': 'FORGED'}).status_code == 401
        save.assert_not_called()
        response = client.put('/api/tag-taxonomy', json=body, headers={
            'X-Integration-Token': 'test-token', 'X-Operator-Id': 'HOST-UM'})
        assert response.status_code == 200
        assert save.call_args.kwargs['operator'] == 'HOST-UM'
