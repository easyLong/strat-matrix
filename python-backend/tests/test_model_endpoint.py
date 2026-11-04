"""Bank gateway selection must not change model callers or leak endpoint values."""
from unittest.mock import patch
import pytest

from app.model_endpoint import DEFAULT_BASE_URL,ModelEndpointError,resolve_base_url
from app.system_config import override_config
from app.system_config_catalog import validate_value
from app.doubao_labeling import read_config,read_embedding_config,DoubaoConfigurationError


def test_outside_default_and_explicit_gateway_share_both_model_types():
    assert resolve_base_url({'PLANNING_ENV':'outside'})==DEFAULT_BASE_URL
    values=dict(PLANNING_ENV='inside',MODEL_BASE_URL='https://model.bank.test/gateway/v3/',
                ARK_API_KEY='test-secret',MODEL_NAME='text',EMBEDDING_MODEL_NAME='vector')
    with override_config(values),patch('app.doubao_labeling.open_request') as network:
        text,vector=read_config(),read_embedding_config()
    assert text.base_url==vector.base_url=='https://model.bank.test/gateway/v3'
    assert 'test-secret' not in repr(text) and 'test-secret' not in repr(vector)
    network.assert_not_called()


def test_inside_cannot_silently_fall_back_to_public_provider():
    for value in ('',None):
        with pytest.raises(ModelEndpointError):
            resolve_base_url({'PLANNING_ENV':'inside','MODEL_BASE_URL':value})
    with override_config(dict(PLANNING_ENV='inside',ARK_API_KEY='test-secret',MODEL_NAME='text',EMBEDDING_MODEL_NAME='vector')):
        with pytest.raises(DoubaoConfigurationError):read_config()


@pytest.mark.parametrize('value',[
    'https://user:test-secret@host/v3','https://host/v3?key=test-secret',
    'https://host/v3#test-secret','https://host:bad/v3','https://host:65536/v3',
    'https://host:0/v3','file:///test-secret','https://host/\ntest-secret',
    ' https://host/test-secret','https://host\\test-secret','https:///test-secret',
])
def test_gateway_rejects_credentials_controls_and_invalid_addresses_without_echo(value):
    with pytest.raises(ModelEndpointError) as raised:
        resolve_base_url({'MODEL_BASE_URL':value})
    assert value not in str(raised.value) and 'test-secret' not in str(raised.value)
    with pytest.raises(ValueError):validate_value('MODEL_BASE_URL',value)


def test_legacy_provider_switch_does_not_override_new_gateway():
    values=dict(MODEL_BASE_URL='http://127.0.0.1:8888/v3',DOUBAO_BASE_URL='https://wrong.test')
    assert resolve_base_url(values)=='http://127.0.0.1:8888/v3'
