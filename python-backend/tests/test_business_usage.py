from unittest.mock import MagicMock, patch

import pytest

from app.bank_bridge.contracts import UsageOutput
from app.bank_bridge.official_usage import current_counts
from app.bank_bridge.ports import DataContractError
from app.matching_supplemental import load_official_usage
from app.planning_pipeline import _matching_projection
from app.system_config import override_config


def response(results):
    return UsageOutput.model_validate(dict(queried_at='2026-11-03T00:00:00Z',topic_results=results))


def test_business_usage_comes_from_java_not_the_legacy_counter():
    cursor=MagicMock()
    with patch('app.bank_bridge.official_usage.current_counts',return_value={'T':2}):
        result=load_official_usage(cursor,['T'])
    cursor.execute.assert_not_called()
    assert result['source']=='java_business_completed_content'
    assert result['unknown_count']==0
    assert result['records'][0]['official_use_count']==2


def test_java_usage_contract_must_return_each_requested_id_once():
    client=MagicMock()
    config={'PLANNING_ENV':'outside','JAVA_GATEWAY_URL':'','INTEGRATION_TOKEN':'test-only'}
    with override_config(config),patch('app.bank_bridge.official_usage.source_mode',return_value='local_fixture'), \
         patch('app.bank_bridge.official_usage.JavaHTTPClient',return_value=client):
        client.read.return_value=response([dict(topic_id='T',official_use_count=2)])
        assert current_counts(['T'])=={'T':2}
        client.read.return_value=response([])
        with pytest.raises(DataContractError):current_counts(['T'])
        client.read.return_value=response([dict(topic_id='T',official_use_count=2)]*2)
        with pytest.raises(DataContractError):current_counts(['T'])


def test_v19_unassigned_positions_fail_composition_instead_of_waiting_forever():
    task={'id':1,'status':'evaluated'}
    evaluation={'implementation_key':'builtin-v19-quality-v1','stages':[],
                'positions':[dict(account_id='A',publish_date='2026-11-09',outcome='failed',reason='no qualified conversion candidate')]}
    with patch('app.planning_pipeline.task_summary',return_value={}),patch('app.planning_pipeline.read_evaluation',return_value=evaluation):
        result=_matching_projection(task)
    assert result['composition']['status']=='failed'
    assert result['composition']['error_code']=='matching_slot_failed'
    assert result['composition']['detail']['unassigned_count']==1


def test_preview_and_historical_success_projections_remain_readable():
    with patch('app.planning_pipeline.task_summary',return_value={}), \
         patch('app.planning_pipeline.read_evaluation',return_value={'implementation_key':'builtin-v19-quality-v1','stages':[],
                 'positions':[dict(outcome='matched')]}):
        assert _matching_projection({'id':1,'status':'evaluated'})['composition']['status']=='succeeded'


def test_early_v19_composition_uses_original_positions_without_weakening_drift_guard():
    from app.planning_result_commit import build_final_plan, ResultCommitError
    from test_planning_result_commit import inputs, evaluation
    result=evaluation()
    result['implementation_key']='builtin-v19-quality-v1'
    summary=result['stages'][-1]['summary']
    summary.pop('actual_traffic_positions')
    summary.pop('actual_conversion_positions')
    assert len(build_final_plan(inputs(),result,[])['slots'])==2
    summary['actual_traffic_positions']=999
    with pytest.raises(ResultCommitError):build_final_plan(inputs(),result,[])
