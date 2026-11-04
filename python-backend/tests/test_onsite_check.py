"""Preflight must be read-only, bounded, explicit about samples and secret-safe."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock,patch

from app import onsite_check as preflight
from app import db


def values():
    return dict(PLANNING_ENV='outside',ARK_API_KEY='test-private-key',MODEL_NAME='text',
                EMBEDDING_MODEL_NAME='vector',INTEGRATION_TOKEN='test-private-token')


def test_default_preflight_does_not_contact_java_or_models_or_write_database():
    connect=MagicMock();database=connect.return_value.__enter__.return_value
    with patch.object(preflight,'snapshot',return_value=values()),patch.object(db,'connection',connect),\
         patch.object(preflight,'inspect_schema',return_value={'status':'passed'}),\
         patch.object(preflight,'algorithm_checks',return_value=[preflight.check('assets',True)]),\
         patch.object(preflight,'java_probe') as java,patch.object(preflight,'model_probe') as model:
        report=preflight.run_check()
    assert report['status']=='local_checks_passed' and report['model_calls']==report['database_writes']==0
    assert not report['bank_acceptance']
    java.assert_not_called();model.assert_not_called();database.commit.assert_not_called()
    assert 'test-private' not in json.dumps(report)


def test_inside_validation_never_changes_saved_values_or_uses_public_default():
    settings=values()
    with patch.object(preflight,'snapshot',return_value=settings),patch.object(db,'connection'),\
         patch.object(preflight,'inspect_schema',return_value={'status':'not_ready'}),\
         patch.object(preflight,'algorithm_checks') as assets:
        report=preflight.run_check(target='inside')
    assert settings['PLANNING_ENV']=='outside'
    assert report['target']=='inside' and report['status']=='not_ready'
    assert next(c for c in report['checks'] if c['name']=='model_configuration')['status']=='not_ready'
    assets.assert_not_called()


def test_unexpected_errors_and_explicit_probe_failures_are_sanitized():
    with patch.object(preflight,'snapshot',side_effect=RuntimeError('test-private-key jdbc:private')):
        report=preflight.run_check()
    assert report['status']=='not_ready' and 'test-private' not in json.dumps(report)
    with patch.object(preflight,'snapshot',return_value=values()),patch.object(db,'connection'),\
         patch.object(preflight,'inspect_schema',return_value={'status':'passed'}),\
         patch.object(preflight,'algorithm_checks',return_value=[]),\
         patch.object(preflight,'java_probe',side_effect=ValueError('test-private-key')):
        report=preflight.run_check(check_java=True)
    assert report['status']=='not_ready' and 'test-private' not in json.dumps(report)


def test_empty_java_samples_do_not_pass_contract_acceptance():
    source=MagicMock()
    source.accounts.return_value=SimpleNamespace(items=[])
    source.topics.return_value=SimpleNamespace(items=[])
    with patch('app.bank_bridge.java_http.JavaHTTPSource',return_value=source),\
         patch('app.bank_bridge.java_http.JavaHTTPClient.from_settings'):
        result=preflight.java_probe()
    assert result['status']=='not_ready'
    assert source.accounts.call_args.args[0].page_size==1
    assert source.topics.call_args.args[0].page_size==1


def test_model_probe_uses_synthetic_text_and_counts_failed_calls_without_saving():
    config=SimpleNamespace(chat_model='text',embedding_model='vector')
    with patch('app.doubao_labeling.read_config',return_value=config),\
         patch('app.matching_quality_model.chat',return_value={'ok':True}) as text,\
         patch('app.doubao_labeling.embed_text',return_value={'vector':[1.,0.],'vector_model':'vector'}) as vector:
        result=preflight.model_probe()
    assert result['status']=='passed' and result['attempted_calls']==2
    assert text.call_args.args[2]=={'probe':'synthetic-connectivity-only'}
    assert '技术连通性测试' in vector.call_args.args[0]
    with patch('app.doubao_labeling.read_config',return_value=config),\
         patch('app.matching_quality_model.chat',side_effect=ValueError('test-private-key')):
        result=preflight.model_probe()
    assert result['attempted_calls']==1 and 'test-private' not in json.dumps(result)


def test_algorithm_preflight_rejects_preview_wrong_vector_and_unapproved_policy():
    document=SimpleNamespace(quality=SimpleNamespace(evaluation_only=False,mapping_version=1,unknown_persona='restricted_model'),
                             vector_space=SimpleNamespace(vector_model='vector',dimension=2048))
    taxonomy={d:[dict(id=d,enabled=True)] for d in ('T1','T2','T3','T4','T5')}
    for changes in ({'evaluation_only':True},{'model':'other'},{'status':'draft'}):
        document.quality.evaluation_only=changes.get('evaluation_only',False)
        document.vector_space.vector_model=changes.get('model','vector')
        cursor=MagicMock();cursor.fetchone.side_effect=[{'config_json':'{}'},{'status':changes.get('status','approved')}]
        with patch('app.services.account_mapping.load_taxonomy',return_value=(4,taxonomy)),\
             patch('app.matching_policy.intact_document',return_value=document),\
             patch('app.matching_policy.implementation_approval_errors',return_value=[]):
            checks=preflight.algorithm_checks(cursor,{**values(),'AUTO_PLANNING_POLICY_ID':'9'})
        assert next(c for c in checks if c['name']=='v19_policy')['status']=='not_ready'


def test_no_reviewed_rules_are_not_silently_promoted_or_treated_as_approved():
    document=SimpleNamespace(quality=SimpleNamespace(evaluation_only=False,mapping_version=1,unknown_persona='restricted_model'),
                             vector_space=SimpleNamespace(vector_model='vector',dimension=2048))
    taxonomy={d:[dict(id=d,enabled=True)] for d in ('T1','T2','T3','T4','T5')}
    for mode,expected in [('restricted_model','needs_confirmation'),('hold','not_ready')]:
        document.quality.unknown_persona=mode
        cursor=MagicMock();cursor.fetchone.side_effect=[{'config_json':'{}'},{'status':'approved'},{'n':0}]
        with patch('app.services.account_mapping.load_taxonomy',return_value=(4,taxonomy)),\
             patch('app.matching_policy.intact_document',return_value=document),\
             patch('app.matching_policy.implementation_approval_errors',return_value=[]):
            checks=preflight.algorithm_checks(cursor,{**values(),'AUTO_PLANNING_POLICY_ID':'9'})
        assert next(c for c in checks if c['name']=='reviewed_mapping')['status']==expected
        assert all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list)
