"""Optimization must preserve locks, hashes, scopes and admission checkpoints."""
from contextvars import ContextVar
from threading import Barrier
from unittest.mock import MagicMock,patch
import json
import pytest
import pymysql

from app.content_planning.connection_pool import MySQLPool
from app.content_planning import planning_input_runner as inputs
from app.content_planning.preparation_batches import InputBatch,BatchLimit
from app.content_planning.matching_precheck import role_coverage,InsufficientRoleCoverage
from app.content_planning.matching_quality_store import QualityRuntime
from app.content_planning.matching_quality_snapshot import content_hash
from app.content_planning import matching_quality_executor as executor,matching_executor_worker as worker
from app.content_planning.matching_quality import IMPLEMENTATION_KEY
from app.content_planning.doubao_labeling import DoubaoAccessError, DoubaoUnavailable
from app.content_planning.preparation_batches import InputModelBlocked,block_model_preparation
import test_matching_quality as quality_fixture


def frozen_inputs():
    return dict(accounts=[dict(account_id='A',profile=dict(lifecycle_stage='阶段'))],
        positions=[dict(account_id='A',publish_date='2027-01-'+day) for day in ('18','20','22')],
        config=dict(stage_targets=[dict(name='阶段',traffic=70,conversion=30)]),
        topics=[dict(topic_id='T',tags={'T2':['流量']})])


def test_role_coverage_blocks_missing_role_and_expired_topics_before_any_model_call():
    facts=frozen_inputs()
    assert role_coverage(facts)['deficits'][0]['required_role']=='转化'
    facts['topics'].append(dict(topic_id='C',tags={'T2':['转化']}))
    assert role_coverage(facts)['status']=='passed'
    facts['topics'][-1]['valid_to']='2026-01-01'
    assert role_coverage(facts)['status']=='blocked'
    document=quality_fixture.QualityPolicyAndAllocationTests().policy()
    context=quality_fixture.context();context['options']=document.quality.model_dump(mode='json',exclude_none=True)
    facts['supplemental']=dict(quality_context=context)
    job=dict(task_id=1,lease_id='a'*32,input_hash='b'*64,policy_hash='c'*64,
             policy=document.model_dump(mode='json'),inputs=facts)
    with patch.object(executor,'annotate_batch') as model,patch.object(executor,'save_quality_report') as report:
        with pytest.raises(InsufficientRoleCoverage):executor.execute_quality_job(job)
    model.assert_not_called()
    assert report.call_args.args[2:] == ('failed','role_coverage')
    assert report.call_args.args[1]['precheck']['status']=='blocked'


def test_worker_persists_explicit_coverage_failure_without_an_evaluation():
    job=dict(task_id=1,lease_id='a'*32,input_hash='b'*64,policy_hash='c'*64)
    with patch.object(worker,'claim_task',return_value={'job':job,'next_after_id':1}),\
         patch.object(worker,'EXECUTORS',{IMPLEMENTATION_KEY:MagicMock(side_effect=InsufficientRoleCoverage())}),\
         patch.object(worker,'fail_task') as fail,patch.object(worker,'save_evaluation') as save:
        assert worker.run_once(max_jobs=1)==1
    assert fail.call_args.args[1].error_code=='role_coverage_insufficient'
    save.assert_not_called()


def test_pool_dedicated_leases_clean_named_locks_and_isolation_only_when_needed():
    backing=MagicMock();raw=backing.connection.return_value
    cursor=raw.cursor.return_value.__enter__.return_value
    pool=MySQLPool({},size=1,timeout=0,pool=backing)
    with pool.connection() as db:
        with db.cursor() as c:
            c.execute('SELECT GET_LOCK(%s,0)',('test',))
            c.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
        with pytest.raises(pymysql.OperationalError):
            with pool.connection():pass
    assert raw.rollback.call_count==2
    statements=[call.args[0] for call in cursor.execute.call_args_list]
    # The tracking cursor uses raw.cursor directly, cleanup uses its context.
    assert 'SELECT RELEASE_ALL_LOCKS()' in statements
    assert 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ' in statements
    raw._con.close.assert_not_called()
    with pool.connection():pass
    assert backing.connection.call_count==2
    assert all(call.kwargs=={'shareable':False} for call in backing.connection.call_args_list)


def test_dirty_pool_connection_is_disconnected_and_original_body_error_is_preserved():
    backing=MagicMock();raw=backing.connection.return_value
    raw.rollback.side_effect=RuntimeError('private cleanup')
    pool=MySQLPool({},size=1,timeout=0,pool=backing)
    with pytest.raises(ValueError,match='original'):
        with pool.connection():raise ValueError('original')
    raw._con.close.assert_called_once()
    raw.close.assert_called_once()
    with pool.connection():pass  # semaphore was returned even after cleanup failure


def test_pool_never_silently_replays_failed_sql():
    with patch('app.content_planning.connection_pool.PooledDB') as constructor:
        MySQLPool({'autocommit':False})
    options=constructor.call_args.kwargs
    assert not options['blocking'] and options['maxshared']==0
    assert options['ping']==1 and options['isfatal'](pymysql.OperationalError()) is False


def test_cache_prefetch_is_immutable_validated_and_avoids_per_item_reads():
    runtime=QualityRuntime(quality_fixture.context(),lambda:None)
    payloads=[{'title':'one'},{'title':'two'}]
    first=runtime.key('pair_precision',payloads[0])[0]
    db=MagicMock();cursor=db.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[dict(cache_key=first,result_json='{"value":1}',result_hash=content_hash({'value':1}))]
    with patch('app.content_planning.matching_quality_store.connection',return_value=db):
        runtime.prefetch('pair_precision',payloads)
        value=runtime.find('pair_precision',payloads[0]);value['value']=99
        assert runtime.find('pair_precision',payloads[0])=={'value':1}
        assert runtime.find('pair_precision',payloads[1]) is None
    assert cursor.execute.call_count==1


def test_cache_save_refreshes_negative_memo_and_consumes_concurrent_winner():
    runtime=QualityRuntime(quality_fixture.context(),lambda:None)
    payload={'title':'same'};key=runtime.key('pair_precision',payload)[0]
    runtime._memory[key]=None
    db=MagicMock();cursor=db.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=dict(result_json='{"winner":2}',result_hash=content_hash({'winner':2}))
    cursor.rowcount=0
    with patch('app.content_planning.matching_quality_store.connection',return_value=db):
        assert runtime.save('pair_precision',payload,{'winner':1})=={'winner':2}
    assert runtime.stats['cache_writes']==0


def test_batch_cache_corruption_is_rejected_without_publishing_partial_memo():
    runtime=QualityRuntime(quality_fixture.context(),lambda:None)
    payload={'title':'bad'};key=runtime.key('pair_precision',payload)[0]
    db=MagicMock();cursor=db.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value=[dict(cache_key=key,result_json='{"value":1}',result_hash='invalid')]
    with patch('app.content_planning.matching_quality_store.connection',return_value=db):
        with pytest.raises(ValueError,match='完整性'):runtime.prefetch('pair_precision',[payload])
    assert runtime._memory=={}


def test_parallel_labels_copy_context_and_checkpoint_in_order():
    context=ContextVar('test_label_context',default='missing');token=context.set('frozen')
    barrier=Barrier(2)
    batch=InputBatch(None,{'taxonomy_version':1},{},2,5)
    def label(job,scope):
        assert context.get()=='frozen'
        context.set('child')
        barrier.wait(timeout=2)
        result=inputs._counts();result['labels']=1
        return result
    try:
        counts=inputs._counts()
        with patch.object(inputs,'_label_job',side_effect=label),patch.object(inputs,'retry_due',return_value=True):
            inputs._parallel_labels([dict(id=1,topic_id='A'),dict(id=2,topic_id='B')],counts,batch,2)
        assert counts['labels']==2 and batch.cursor('labels')==2
        assert context.get()=='frozen'
    finally:context.reset(token)


def test_parallel_admission_does_not_exceed_budget_or_skip_deferred_jobs():
    batch=InputBatch(None,{}, {},1,5)
    result=inputs._counts();result['labels']=1
    with patch.object(inputs,'_label_job',return_value=result) as label,patch.object(inputs,'retry_due',return_value=True):
        with pytest.raises(BatchLimit):
            inputs._parallel_labels([dict(id=1,topic_id='A'),dict(id=2,topic_id='B')],inputs._counts(),batch,2)
    assert label.call_count==1 and batch.cursor('labels')==1
    batch=InputBatch(None,{}, {},2,5);counts=inputs._counts()
    with patch.object(inputs,'_label_job',return_value=result) as label,patch.object(inputs,'retry_due',side_effect=[False,True]):
        inputs._parallel_labels([dict(id=1,topic_id='A'),dict(id=2,topic_id='B')],counts,batch,2)
    assert label.call_count==1 and counts['deferred']==1 and counts['labels']==1


def test_unexpected_first_future_error_does_not_checkpoint_past_it():
    batch=InputBatch(None,{}, {},2,5)
    def label(job,scope):
        if job['id']==1:raise RuntimeError('unexpected')
        return inputs._counts()
    with patch.object(inputs,'_label_job',side_effect=label),patch.object(inputs,'retry_due',return_value=True):
        with pytest.raises(RuntimeError):
            inputs._parallel_labels([dict(id=1,topic_id='A'),dict(id=2,topic_id='B')],inputs._counts(),batch,2)
    assert batch.cursor('labels')==0


def test_denied_model_request_records_failure_then_blocks_but_transient_error_remains_retryable():
    for error in (DoubaoAccessError('sanitized'),DoubaoUnavailable('transient')):
        counts=inputs._counts();save=MagicMock()
        operation=MagicMock(side_effect=error)
        if isinstance(error,DoubaoAccessError):
            with pytest.raises(InputModelBlocked):
                inputs._execute_input(counts,'labels','T',operation,save,{'writing':False})
        else:inputs._execute_input(counts,'labels','T',operation,save,{'writing':False})
        save.assert_called_once_with(error)
        assert counts['failed']==1


def test_parallel_access_failure_drains_admitted_pair_and_stops_next_group():
    batch=InputBatch(None,{}, {},6,5);counts=inputs._counts()
    def label(job,scope):
        part=inputs._counts()
        if job['id']==1:
            part['failed']=1
            raise InputModelBlocked('DoubaoAccessError',part)
        part['labels']=1
        return part
    with patch.object(inputs,'_label_job',side_effect=label) as model,\
         patch.object(inputs,'retry_due',return_value=True):
        with pytest.raises(InputModelBlocked):
            inputs._parallel_labels([dict(id=i,topic_id=str(i)) for i in range(1,7)],counts,batch,2)
    assert model.call_count==2 and batch.cursor('labels')==2
    assert counts['failed']==1 and counts['labels']==1


def test_preparation_model_block_does_not_overwrite_frozen_or_cancelled_state():
    for status in ('waiting_inputs','inputs_frozen','cancelled'):
        db=MagicMock();cursor=db.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value=dict(status=status,last_report_json='{}')
        with patch('app.content_planning.preparation_batches.connection',return_value=db):
            block_model_preparation(42,'DoubaoAccessError')
        statements=[c.args[0] for c in cursor.execute.call_args_list]
        assert statements[-1].startswith('UPDATE') == (status=='waiting_inputs')
        if status=='waiting_inputs':
            assert 'reservation_key IS NOT NULL' in statements[-1]


def test_scoped_input_block_persists_and_does_not_request_another_automatic_pass():
    scope=dict(account_ids=['A'],topic_sources={'T':{}})
    with patch.object(inputs,'_run_jobs',side_effect=InputModelBlocked('DoubaoAccessError')),\
         patch.object(inputs,'block_model_preparation') as block,\
         patch.object(inputs,'inspect_scope',return_value={'waiting_reasons':['pending']}),\
         patch.object(InputBatch,'persist'):
        counts=inputs._prepare_batch(42,(scope,{},[]),24,30)
    assert counts['blocked'] and not counts['has_more']
    block.assert_called_once_with(42,'DoubaoAccessError')
