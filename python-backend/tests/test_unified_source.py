"""Both runtime environments use Java; supplied-facts projection never performs a source read."""
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
from app.bank_bridge import factory
from app.bank_bridge.contracts import Account, Topic, AccountQuery, TopicQuery
from app.bank_bridge.java_http import JavaHTTPClient, JavaHTTPSource
from app.bank_bridge.ports import IntegrationUnavailable
from app.models import StrategyConfig
from app.services.catalog_projection import project_catalog
from app.system_config import override_config


def test_outside_selects_daily_java_and_auth_without_fixture_fallback():
    with override_config(dict(PLANNING_ENV='outside', BANK_SOURCE_MODE='local_fixture',
                              INTEGRATION_TOKEN='test-token')):
        client = JavaHTTPClient.from_settings()
        assert client.base_url == 'http://127.0.0.1:6931/api/plan/internal/source'
        assert client.token == 'test-token'
        assert isinstance(factory.get_source(None), JavaHTTPSource)


def test_inside_never_invents_outside_address_or_token():
    with override_config(dict(PLANNING_ENV='inside', INTEGRATION_TOKEN='python-only-token')):
        with pytest.raises(IntegrationUnavailable): JavaHTTPClient.from_settings()


def test_java_failure_does_not_read_python_fixture():
    from urllib.error import URLError
    with override_config(dict(PLANNING_ENV='outside', INTEGRATION_TOKEN='test-token')), \
         patch('app.bank_bridge.local_fixture.load_fixture') as fallback:
        source = factory.get_source(None)
        source.client.opener = MagicMock()
        source.client.opener.open.side_effect = URLError('test Java unavailable')
        with pytest.raises(IntegrationUnavailable): source.accounts(AccountQuery())
        fallback.assert_not_called()


def test_projection_uses_supplied_facts_and_restores_the_previous_source():
    now = datetime.now(timezone.utc)
    a = Account(account_id='SCOPE-A', nickname='test', eligible=True, followers=50,
                updated_at=now, persona='test persona')
    t = Topic(topic_id='SCOPE-T', title='test topic', source='普通', topic_type='非营销',
              available=True, updated_at=now)
    @contextmanager
    def database():
        yield MagicMock()
    previous = MagicMock()
    with factory.use_adapters(previous), patch('app.services.catalog_projection.connection', database), \
         patch('app.services.catalog_projection.get_config', return_value=SimpleNamespace(config=StrategyConfig())), \
         patch('app.services.catalog_projection.attach_topic_labels'):
        result = project_catalog([a], [t])
        assert result['accounts'][0]['account_id'] == 'SCOPE-A'
        assert result['topics'][0]['topic_id'] == 'SCOPE-T'
        assert result['algorithm_version']
        previous.accounts.assert_not_called(); previous.topics.assert_not_called()
        assert factory.get_source(None) is previous


def test_acceptance_scopes_ids_but_reuses_the_same_java_source():
    from testing.live_server import AcceptanceSource
    source = MagicMock()
    scoped = AcceptanceSource(source, 'A1', ['T1', 'T2'])
    scoped.accounts(AccountQuery(page_no=2, page_size=1))
    q = source.accounts.call_args.args[0]
    assert q.account_ids == ['A1'] and q.page_no == 2 and q.page_size == 1
    scoped.topics(TopicQuery(topic_ids=['T2', 'OTHER']))
    assert source.topics.call_args.args[0].topic_ids == ['T2']


def test_acceptance_scope_applies_to_preimported_functions_and_background_threads():
    from concurrent.futures import ThreadPoolExecutor
    from app.bank_bridge.bridge import get_source as preimported
    source = MagicMock()
    with patch.object(factory, 'SOURCE_PROVIDER', lambda _: source):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(preimported, None).result(timeout=2) is source
