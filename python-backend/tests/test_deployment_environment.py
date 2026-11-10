"""One selector, legacy migration and fail-closed host boundaries; no real services."""
from unittest.mock import MagicMock, patch
import pytest

from app.content_planning import deployment_environment as env
from app.content_planning.bank_bridge import factory
from app.content_planning.system_config import override_config, public_settings
from app.content_planning import init_system_config
from app.content_planning.ordinary_scheduler import schedule_owner


def host_values():
    return dict(PLANNING_ENV='inside', JAVA_GATEWAY_URL='https://host.example',
                JAVA_API_BASE_URL='https://host.example/internal/facts', JAVA_API_TOKEN='test-only-java-token',
                INTEGRATION_TOKEN='test-only-python-token', CONTENT_PRODUCTION_MODE='disabled')


def test_outside_and_inside_override_conflicting_legacy_flags():
    assert env.resolve({'PLANNING_ENV':'outside','JAVA_ACCESS_MODE':'bank','BANK_SOURCE_MODE':'local_fixture'})['BANK_SOURCE_MODE']=='java_http'
    result=env.resolve({'PLANNING_ENV':'inside','JAVA_ACCESS_MODE':'local_development','BANK_SOURCE_MODE':'local_fixture'})
    assert result['JAVA_ACCESS_MODE']=='bank' and result['BANK_SOURCE_MODE']=='java_http'
    with override_config(host_values()), patch.object(factory,'SOURCE_MODE',None):
        assert factory.source_mode()=='java_http'
        assert schedule_owner()=='java'
        assert public_settings()['PLANNING_ENV']=='inside'
        assert public_settings()['JAVA_ACCESS_MODE']=='bank'


def test_legacy_settings_still_work_until_selector_is_initialized():
    assert env.resolve({'JAVA_ACCESS_MODE':'bank'})['PLANNING_ENV']=='inside'
    assert env.resolve({'BANK_SOURCE_MODE':'java_http'})['BANK_SOURCE_MODE']=='java_http'
    assert env.resolve({})['PLANNING_ENV']=='outside'


@pytest.mark.parametrize('value',[None,'','local','bank','INSIDE'])
def test_disabled_or_invalid_selector_never_falls_back(value):
    with pytest.raises(ValueError):env.resolve({'PLANNING_ENV':value})


def test_inside_requires_host_endpoints_auth_and_disallows_mock_production():
    assert len(env.validation_errors({'PLANNING_ENV':'inside'}))==4
    assert not env.validation_errors(host_values())
    with pytest.raises(ValueError,match='local_mock'):
        env.require_ready({**host_values(),'CONTENT_PRODUCTION_MODE':'local_mock'})
    with pytest.raises(ValueError):env.require_ready({**host_values(),'JAVA_GATEWAY_URL':'https://u:p@host.example'})


def test_failed_inside_selection_does_not_change_database():
    with patch('app.content_planning.system_config.snapshot',return_value={}), patch('app.content_planning.db.connection') as connect:
        with pytest.raises(ValueError):env.select('inside')
        connect.assert_not_called()


def test_selection_only_writes_the_environment_key():
    db=MagicMock();cursor=db.__enter__.return_value.cursor.return_value.__enter__.return_value
    with patch('app.content_planning.system_config.snapshot',return_value=host_values()),patch('app.content_planning.db.connection',return_value=db):
        assert env.select('inside')['PLANNING_ENV']=='inside'
    assert cursor.execute.call_count==1
    sql,args=cursor.execute.call_args.args
    assert "'PLANNING_ENV'" in sql and 'inside' in args
    assert 'JAVA_API_TOKEN' not in sql and 'JAVA_GATEWAY_URL' not in sql
    db.__enter__.return_value.commit.assert_called_once()


def test_upgrade_seeds_inside_for_existing_bank_deployment():
    cursor=MagicMock();cursor.fetchone.return_value={'config_value':'bank'}
    init_system_config.seed_config(cursor,migrate_legacy=False)
    inserted=[call.args[1] for call in cursor.execute.call_args_list if call.args[0].startswith('INSERT')]
    assert next(row[3] for row in inserted if row[0]=='PLANNING_ENV')=='inside'


def test_upgrade_never_replaces_an_existing_java_data_source_with_a_fixture():
    cursor=MagicMock();cursor.fetchone.side_effect=[{'config_value':'local_development'},{'config_value':'java_http'}]
    init_system_config.seed_config(cursor,migrate_legacy=False)
    inserted=[call.args[1] for call in cursor.execute.call_args_list if call.args[0].startswith('INSERT')]
    assert next(row[3] for row in inserted if row[0]=='PLANNING_ENV')=='inside'


def test_inside_fails_before_starting_python_background_executor():
    from fastapi.testclient import TestClient
    from app.main import app
    with override_config({'PLANNING_ENV':'inside'}),patch('app.content_planning.api.background_execution.BackgroundExecutor') as pool:
        with pytest.raises(RuntimeError, match='Content planning resources could not be started'):
            with TestClient(app):pass
        pool.assert_not_called()
