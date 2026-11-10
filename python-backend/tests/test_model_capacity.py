"""Admission, cross-caller model budgets and deferred jobs; no live models/DB."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from io import BytesIO
from threading import Event,RLock
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient
from app.content_planning import model_capacity as cap, doubao_labeling as model
from app.main import app
from app.content_planning.system_config import override_config,SystemConfigError
from app.content_planning import planning_input_runner as inputs, matching_executor_worker as matching
from app.content_planning import topic_label_worker,topic_vector_worker,account_vector_worker
from app.content_planning.worker_http import WorkerRateLimited,json_request
from app.content_planning.services.labels import defer_topic_label_job
from app.content_planning.matching_quality import IMPLEMENTATION_KEY
from app.content_planning.bank_bridge.operations import test_labels as run_label_test


ENV={'BANK_SOURCE_MODE':'local_fixture','INTEGRATION_TOKEN':'capacity-test-token'}
HEADERS={'X-Integration-Token':'capacity-test-token'}
TAXONOMY={f'T{i}':['标签'] for i in range(1,6)}
PAYLOAD={'topic_id':'T1','topic':{'title':'测试'},'taxonomy_version':1,'taxonomy':TAXONOMY}
CONFIG=model.DoubaoConfig('https://model.invalid','test-key','text','embedding',10)


def test_counter_limit_and_exception_release():
    gate=cap.ConcurrentBudget()
    with gate.slot('a',1):
        with pytest.raises(cap.CapacityExceeded):
            with gate.slot('a',1):pass
    with pytest.raises(ValueError):
        with gate.slot('a',1):raise ValueError()
    with gate.slot('a',1):pass


def test_limit_changes_keep_running_count_and_model_groups_are_independent():
    gate=cap.ConcurrentBudget()
    with gate.slot('text',2),gate.slot('text',2):
        with pytest.raises(cap.CapacityExceeded):
            with gate.slot('text',1):pass
        with gate.slot('embedding',1):pass
        with gate.slot('text',3):pass
    with gate.slot('text',1):pass


def test_concurrent_model_calls_share_budget_and_overflow_never_reaches_network():
    release=Event();started=[Event(),Event()];calls=[];lock=RLock()
    def network(*args):
        with lock:
            index=len(calls);calls.append(args);started[index].set()
        assert release.wait(3)
        return {'ok':True}
    with patch.object(model,'_ark_post',side_effect=network),ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(model.ark_post,CONFIG,'/chat/completions',{})
        second=pool.submit(model.ark_post,CONFIG,'/chat/completions',{})
        try:
            assert all(e.wait(2) for e in started)
            with pytest.raises(cap.CapacityExceeded):model.ark_post(CONFIG,'/chat/completions',{})
            assert len(calls)==2
        finally:release.set()
        assert first.result()==second.result()=={'ok':True}


def test_text_budget_does_not_block_embedding_and_network_failure_releases():
    with cap.budget.slot('text',2),cap.budget.slot('text',2),patch.object(model,'_ark_post',return_value={}) as network:
        assert model.ark_post(CONFIG,'/embeddings/multimodal',{})=={}
        network.assert_called_once()
    with patch.object(model,'_ark_post',side_effect=RuntimeError()):
        with pytest.raises(RuntimeError):model.ark_post(CONFIG,'/chat/completions',{})
    with cap.budget.slot('text',1):pass


def test_managed_model_reads_mysql_policy_each_call_without_replacing_gate():
    with override_config({'MODEL_MAX_CONCURRENT_REQUESTS':'1'}),cap.budget.slot('text',2),\
         patch.object(model,'_ark_post') as network:
        with pytest.raises(cap.CapacityExceeded):model.ark_post(replace(CONFIG,managed_capacity=True),'/chat/completions',{})
        network.assert_not_called()


@pytest.mark.parametrize('key,value',[(key,'0') for key in cap.KEYS.values()]+[('AI_LIMIT_SCOPE','bad')])
def test_invalid_limit_configuration_fails_closed(key,value):
    with override_config({key:value}),pytest.raises(SystemConfigError):cap.read_policy()


def test_model_api_rejects_at_entry_but_health_and_auth_are_independent():
    with override_config({**ENV,'AI_API_MAX_CONCURRENT_REQUESTS':'1'}),\
         patch('app.content_planning.topic_label_model_api.label_topic') as network,\
         patch('app.content_planning.bootstrap.check_database',return_value=True),TestClient(app) as client,app.state.planning_runtime.budget().slot('api',1):
        response=client.post('/api/internal/topic-label-model',headers=HEADERS,json=PAYLOAD)
        assert response.status_code==429
        assert response.headers['Retry-After']=='2'
        assert response.json()['code']=='ai_capacity_exceeded'
        assert client.post('/api/internal/topic-label-model',json=PAYLOAD).status_code==401
        assert client.get('/api/health').status_code==200
        network.assert_not_called()


def test_api_handler_error_and_return_do_not_leak_entry_permit():
    with override_config({**ENV,'AI_API_MAX_CONCURRENT_REQUESTS':'1'}),\
         patch('app.content_planning.topic_label_model_api.label_topic',side_effect=[model.DoubaoUnavailable('busy'),{}]),TestClient(app) as client:
        assert client.post('/api/internal/topic-label-model',headers=HEADERS,json=PAYLOAD).status_code==503
        assert client.post('/api/internal/topic-label-model',headers=HEADERS,json=PAYLOAD).status_code==200


def test_cancelled_async_entry_releases_its_permit():
    import asyncio
    async def scenario():
        with override_config({'AI_API_MAX_CONCURRENT_REQUESTS':'1'}):
            dependency=cap.model_api_admission()
            await dependency.__anext__()
            with pytest.raises(asyncio.CancelledError):await dependency.athrow(asyncio.CancelledError())
            with cap.budget.slot('api',1):pass
    asyncio.run(scenario())


def test_embedding_test_and_background_wakeup_are_protected_at_entry():
    with override_config({**ENV,'AI_API_MAX_CONCURRENT_REQUESTS':'1'}),TestClient(app) as client,app.state.planning_runtime.budget().slot('api',1):
        for path in ['/api/internal/embedding-model','/api/integrations/bank/op04/topic-labels/test','/api/internal/wakeup']:
            assert client.post(path,headers=HEADERS,json={}).status_code==429


def test_provider_429_is_retryable_capacity_error_with_sanitized_retry_after():
    error=HTTPError('https://private/secret',429,'secret',{'Retry-After':'999'},BytesIO(b'secret'))
    with patch.object(model,'open_request',side_effect=error),pytest.raises(cap.CapacityExceeded) as raised:
        model.ark_post(CONFIG,'/chat/completions',{})
    assert isinstance(raised.value,model.DoubaoUnavailable)
    assert raised.value.retry_after==120
    assert 'secret' not in str(raised.value)


class LockStore:
    def __init__(self):self.locks={};self.next_id=0
    @contextmanager
    def connection(self):
        self.next_id+=1;owner=self.next_id;store=self
        class Cursor:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def execute(self,sql,params):
                if 'IS_USED_LOCK' in sql:self.row={f's{i}':store.locks.get(name) for i,name in enumerate(params)}
                elif 'GET_LOCK' in sql:
                    key=params[0];ok=key not in store.locks
                    if ok:store.locks[key]=owner
                    self.row={'acquired':int(ok)}
                else:store.locks.pop(params[0],None)
            def fetchone(self):return self.row
        try:yield SimpleNamespace(cursor=lambda:Cursor())
        finally:
            store.locks={key:value for key,value in store.locks.items() if value!=owner}


def test_mysql_shared_budget_and_limit_reduction_count_high_numbered_old_slots():
    store=LockStore()
    with patch('app.content_planning.db.connection',store.connection),patch.object(cap,'lock_prefix',return_value='test'):
        first=cap.database_slot('text',2);first.__enter__()
        with cap.database_slot('text',2):
            first.__exit__(None,None,None)
            with pytest.raises(cap.CapacityExceeded):
                with cap.database_slot('text',1):pass
        with cap.database_slot('text',1):pass
        assert store.locks=={}


def task_db(existing=None,count=0):
    db=MagicMock();db.__enter__.return_value=db
    cursor=db.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect=[{'acquired':1},existing]
    cursor.fetchall.return_value=[{'id':i} for i in range(count)]
    return db,cursor


def test_pending_quota_rejects_new_task_and_releases_admission_lock():
    db,cursor=task_db(count=1)
    with patch('app.content_planning.db.connection',return_value=db),patch.object(cap,'lock_prefix',return_value='test'):
        with pytest.raises(cap.CapacityExceeded):
            with cap.pending_task_admission('matching',{'preparation_id':7},policy=cap.CapacityPolicy(pending=1)):
                pytest.fail('must not accept')
    assert cursor.execute.call_args.args[0].startswith('SELECT RELEASE_LOCK')


def test_idempotent_replay_bypasses_full_queue_but_terminal_retry_checks_capacity():
    for retry,should_reject in [(False,False),(True,True)]:
        db,cursor=task_db(existing={'id':7,'status':'failed'},count=1)
        with patch('app.content_planning.db.connection',return_value=db),patch.object(cap,'lock_prefix',return_value='test'):
            if should_reject:
                with pytest.raises(cap.CapacityExceeded):
                    with cap.pending_task_admission('matching',{'id':7,'retry':retry},policy=cap.CapacityPolicy(pending=1)):pass
            else:
                with cap.pending_task_admission('matching',{'id':7,'retry':retry},policy=cap.CapacityPolicy(pending=1)):pass
                cursor.fetchall.assert_not_called()


def test_http_pending_quota_rejects_before_creating_task():
    @contextmanager
    def full(*args,**kwargs):raise cap.CapacityExceeded('tasks');yield
    with override_config(ENV),patch.object(cap,'pending_task_admission',full),\
         patch('app.content_planning.planning_pipeline_api.start_v19_pipeline') as create,TestClient(app) as client:
        response=client.post('/api/internal/auto-planning/start',headers=HEADERS,json={'cycle_start':'2027-01-04'})
        assert response.status_code==429
        assert response.json()['scope']=='tasks'
        create.assert_not_called()


def test_deferred_label_release_only_updates_its_current_lease():
    db=MagicMock();db.__enter__.return_value=db
    cursor=db.cursor.return_value.__enter__.return_value;cursor.rowcount=1
    with patch('app.content_planning.services.labels.connection',return_value=db):
        assert defer_topic_label_job('T1','LEASE')['deferred']
    sql,params=cursor.execute.call_args.args
    assert "status='processing'" in sql and 'lease_id=%s' in sql and "del_flag='N'" in sql
    assert params==('T1','LEASE')
    assert 'godp_topic_tag ' not in sql


def test_vector_throttling_defers_without_failure_record_or_cursor_advance():
    from test_planning_input_runner import PreparationRunnerTests
    fixture=PreparationRunnerTests();fixture.setUp()
    try:
        fixture.topics();fixture.mocks['embed_profile'].side_effect=cap.CapacityExceeded('embedding')
        report=inputs.prepare_inputs()
        assert report['busy'] and report['has_more'] and report['failed']==0 and report['deferred']==1
        fixture.mocks['save_topic_vector'].assert_not_called()
        assert report['checkpoint']['cursors'].get('topic_vectors',0)==0
    finally:fixture.doCleanups()


def test_label_throttling_returns_claim_and_does_not_write_failed_tags():
    from test_planning_input_runner import PreparationRunnerTests
    fixture=PreparationRunnerTests();fixture.setUp()
    try:
        fixture.labels(1);fixture.mocks['label_topic'].side_effect=cap.CapacityExceeded('text')
        with patch.object(inputs,'defer_topic_label_job') as release:
            report=inputs.prepare_inputs()
        assert report['busy'] and report['failed']==0
        release.assert_called_once_with('T1','LEASE')
        fixture.mocks['put_topic_tags'].assert_not_called()
    finally:fixture.doCleanups()


def test_parallel_label_throttling_keeps_cursor_before_deferred_job():
    fixture_job={'id':1,'topic_id':'T1'}
    counts=inputs._counts()
    busy=cap.CapacityExceeded('text');busy.counts=inputs._counts();busy.counts['deferred']=1
    completed=inputs._counts();completed['labels']=1
    batch=MagicMock(scope={},max_jobs=4,visited=0)
    with patch.object(inputs,'retry_due',return_value=True),\
         patch.object(inputs,'_label_job',side_effect=[busy,completed]),pytest.raises(cap.CapacityExceeded):
        inputs._parallel_labels([fixture_job,{'id':2,'topic_id':'T2'}],counts,batch,2)
    assert counts['labels']==1 and counts['deferred']==1
    batch.checkpoint.assert_not_called()


def test_matching_throttling_yields_existing_task_without_marking_failure():
    job=dict(task_id=1,lease_id='a'*32,input_hash='b'*64,policy_hash='c'*64)
    with patch.object(matching,'claim_task',return_value={'job':job,'next_after_id':1}),\
         patch.object(matching,'EXECUTORS',{IMPLEMENTATION_KEY:MagicMock(side_effect=cap.CapacityExceeded('text'))}),\
         patch.object(matching,'yield_task') as defer,patch.object(matching,'fail_task') as fail,\
         patch.object(matching,'save_evaluation') as save,patch.object(matching,'lease_seconds',return_value=1800):
        assert matching.run_once(max_jobs=1)==0
        defer.assert_called_once();fail.assert_not_called();save.assert_not_called()


def test_http_worker_does_not_turn_429_into_failure_payload():
    error=HTTPError('http://local',429,'busy',{},BytesIO(b''))
    with patch('app.content_planning.worker_http.urlopen',side_effect=error),pytest.raises(WorkerRateLimited):json_request('http://local','POST',body={})
    topic={'topic_id':'T1','content_hash':'a'*64,'tag_version':1,'profile':{}}
    with patch.object(topic_vector_worker,'json_request',side_effect=WorkerRateLimited()) as request:
        topic_vector_worker.process_job(topic,'http://local','test')
        assert request.call_count==1


def test_old_label_worker_returns_claim_on_429_without_writing_failed_tags():
    def request(url,method,**kwargs):
        if url.endswith('/claim'):return {'lease_id':'LEASE','topic':{'title':'test'},'taxonomy_version':1,'taxonomy':TAXONOMY}
        if url.endswith('topic-label-model'):raise WorkerRateLimited()
        assert url.endswith('/defer')
        return {'deferred':True}
    with patch.object(topic_label_worker,'json_request',side_effect=request) as network:
        assert topic_label_worker.process_job('T1','http://local','test',30) is None
    assert network.call_count==3


def test_config_initializer_only_inserts_five_keys_and_keeps_existing_values():
    db=MagicMock();db.__enter__.return_value=db
    cursor=db.cursor.return_value.__enter__.return_value;cursor.rowcount=1
    with patch('app.content_planning.db.connection',return_value=db):assert cap.initialize_config()==5
    for call in cursor.execute.call_args_list:
        sql,params=call.args
        assert sql.startswith('INSERT IGNORE') and 'UPDATE ' not in sql
        assert params[0] in (*cap.KEYS.values(),'AI_LIMIT_SCOPE')


def test_op04_does_not_convert_throttling_to_label_failure():
    with patch('app.content_planning.bank_bridge.operations.taxonomy_snapshot',return_value=(1,{})),\
         patch('app.content_planning.taxonomy.active_tag_names',return_value=TAXONOMY),pytest.raises(cap.CapacityExceeded):
        run_label_test(None,SimpleNamespace(topics=[SimpleNamespace(topic_id='T1',title='title',outline='outline')]),
                       labeler=MagicMock(side_effect=cap.CapacityExceeded('text')))
