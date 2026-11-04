import json
from concurrent.futures import ThreadPoolExecutor
import pytest

from testing.timing import Recorder,_model_usage
from testing.live import fixture_for,fresh_fixture_for
from testing.performance import intervals_union,summarize
from testing.benchmark import clone_fixture,case_fingerprint


def test_timing_preserves_results_exceptions_and_records_nested_calls_without_payloads(tmp_path):
    path=tmp_path/'timing.jsonl';timer=Recorder(path)
    child=timer.wrap('child',lambda secret:secret)
    parent=timer.wrap('parent',lambda:child('private-prompt-key'))
    assert parent()=='private-prompt-key'
    events=[json.loads(line) for line in path.read_text().splitlines()]
    assert events[0]['parent_id']==events[1]['span_id']
    assert events[1]['parent_id'] is None
    assert all(e['duration_s']>=0 and e['status']=='ok' for e in events)
    assert 'private-prompt-key' not in path.read_text()
    def fail():raise ValueError('private-upstream-body')
    with pytest.raises(ValueError,match='private-upstream-body'):timer.wrap('failed',fail)()
    assert 'private-upstream-body' not in path.read_text()
    assert json.loads(path.read_text().splitlines()[-1])['error_type']=='ValueError'


def test_parallel_timing_records_are_atomic_and_parent_state_is_isolated(tmp_path):
    path=tmp_path/'timing.jsonl';timer=Recorder(path)
    operation=timer.wrap('call',lambda:1)
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(lambda _:operation(),range(40)))==[1]*40
    events=[json.loads(line) for line in path.read_text().splitlines()]
    assert len({e['span_id'] for e in events})==40
    assert all(e['parent_id'] is None for e in events)


def test_model_usage_only_retains_allowlisted_numeric_counters():
    assert _model_usage({'usage':{'prompt_tokens':12,'total_tokens':13,'api_key':'private','completion_tokens':True},
                         'choices':['private-input']})=={'prompt_tokens':12,'total_tokens':13}
    assert _model_usage({'usage':None})=={}


def test_fresh_cases_change_business_content_without_injecting_labels_or_scores():
    plain=fixture_for('20261103220000');fresh=fresh_fixture_for('20261103220000')
    assert len(fresh['accounts'])==1 and len(fresh['topics'])==12
    assert fresh['accounts'][0]['interests']!=plain['accounts'][0]['interests']
    assert all(a['outline']!=b['outline'] for a,b in zip(plain['topics'],fresh['topics']))
    assert all(not ({'tags','vector','fit_score'}&t.keys()) for t in fresh['topics'])


def test_analysis_does_not_add_overlapping_times_or_mistake_checkpoint_hits_for_warm_cache():
    def event(name,span,parent,start,duration,**extra):
        return dict(name=name,process_id=11,span_id=span,parent_id=parent,
                    started_at=f'2026-11-03T00:00:{start:02d}+00:00',start_s=start,
                    duration_s=duration,status='ok',**extra)
    python=[event('pipeline.worker',1,None,0,6),event('input.labels',2,1,0,4),
            event('model.chat',3,2,1,3),
            event('cache.lookup',4,1,0,0.1,kind='pair',cache_key='new',hit=False),
            event('cache.lookup',5,1,4,0.1,kind='pair',cache_key='new',hit=True),
            event('cache.lookup',6,1,5,0.1,kind='pair',cache_key='old',hit=True)]
    java=[dict(name='java.planning_closed_loop',started_at='2026-11-03T00:00:00Z',duration_s=10,status='ok')]
    result=summarize(python,java,[],{})
    assert result['planning_wall_s']==10 and result['worker_gap_s']==4
    assert result['model_active_union_s']==3
    assert result['models']['input.labels.model.chat']['count']==1
    assert result['cache']['pair']==dict(lookups=3,hits=2,unique_keys=2,preexisting_keys=1,cold_keys=1)
    assert intervals_union([(0,4),(1,3),(4,5),(8,9)])==6


def test_partial_run_is_not_reported_as_completed():
    event=dict(name='model.chat',span_id=1,parent_id=None,process_id=1,status='ok',duration_s=2,
               start_s=1,started_at='2026-11-03T00:00:00Z')
    result=summarize([event],[],[],{})
    assert not result['complete_planning_timing'] and result['planning_wall_s'] is None


def test_benchmark_preserves_business_case_and_does_not_mutate_original():
    original=fresh_fixture_for('20261103220314')
    before=json.dumps(original,sort_keys=True)
    baseline=clone_fixture(original,'20261104000101')
    optimized=clone_fixture(original,'20261104000102')
    assert case_fingerprint(original)==case_fingerprint(baseline)==case_fingerprint(optimized)
    assert baseline['topics'][0]['topic_id']!=optimized['topics'][0]['topic_id']
    assert json.dumps(original,sort_keys=True)==before
