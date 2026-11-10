"""Real in-process host/child HTTP and lifespan checks, without MySQL or models."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
import gzip
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
from threading import Event
import time
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.content_planning.config import DatabaseConfig, PlanningConfig, PlanningDependencies
from app.content_planning.context import current_runtime
from app.content_planning.integration import install_content_planning
from app.content_planning.main import create_app
from app.content_planning.runtime import PlanningRuntime
from app.content_planning.system_config import get_setting, clear_cache, SystemConfigError
from app.content_planning.algorithm_schema import REQUIRED_TABLES

VALUES = dict(PLANNING_ENV='inside', JAVA_GATEWAY_URL='http://java.test',
              JAVA_API_BASE_URL='http://java.test/api/plan/internal/source', JAVA_API_TOKEN='host-token',
              INTEGRATION_TOKEN='planning-test-token', CONTENT_PRODUCTION_MODE='disabled',
              MODEL_NAME='text-test', EMBEDDING_MODEL_NAME='vector-test')
AUTH = {'X-Integration-Token': 'planning-test-token'}


class Pool:
    def __init__(self, events=None, ready=True):
        self.events = events if events is not None else []
        self.ready = ready
        self.closed = False
        self.statements = []

    @contextmanager
    def connection(self):
        assert not self.closed
        yield self

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, sql, *args):
        assert sql.upper().startswith(('SHOW ', 'SELECT ')), 'Startup cannot execute DDL or seed writes'
        self.statements.append(sql)

    def fetchall(self):
        return [{'table': t} for t in REQUIRED_TABLES] if self.ready else []

    def close(self):
        self.events.append('pool-close')
        self.closed = True


class Executor:
    def __init__(self, events=None): self.events = events if events is not None else []
    def close(self): self.events.append('executor-close')
    def snapshot(self): return {'mode': 'host_triggered', 'jobs': {}}
    def wake(self, jobs): return {'status': 'accepted', 'accepted_jobs': jobs}


def dependencies(*, pool=None, values=None, events=None, executor_factory=None):
    pool = pool or Pool(events)
    settings = Mock(return_value=dict(VALUES if values is None else values))
    return PlanningDependencies(database_pool_factory=lambda config: pool, settings_provider=settings,
                                executor_factory=executor_factory or (lambda runtime: Executor(events))), pool, settings


def host_app(events=None):
    @asynccontextmanager
    async def lifespan(app):
        if events is not None: events.append('host-start')
        yield {'host_state': 'unchanged'}
        if events is not None: events.append('host-stop')
    host = FastAPI(lifespan=lifespan)

    @host.get('/health')
    def healthy(request: Request):
        return {'host': 'ok', 'state': request.state.host_state}

    @host.exception_handler(ValueError)
    async def host_error(request, error):
        return JSONResponse({'host_error': True}, status_code=409, headers={'X-Host-Error': 'same'})

    @host.get('/host-error')
    def error(): raise ValueError('host business exception')
    return host


def test_disabled_installation_has_no_resource_or_config_access_and_preserves_host():
    host = host_app()
    pool, settings, executor = Mock(), Mock(), Mock()
    handle = install_content_planning(host, PlanningConfig(), dependencies=PlanningDependencies(
        database_pool_factory=pool, settings_provider=settings, executor_factory=executor))
    with TestClient(host) as client:
        assert client.get('/health').json() == {'host': 'ok', 'state': 'unchanged'}
        assert client.get('/host-error').status_code == 409
        r = client.get('/planning/api/health')
        assert r.status_code == 503 and r.json()['code'] == 'planning_disabled'
        assert client.post('/planning/api/internal/wakeup', json={}).status_code == 503
        assert client.get('/planning/api/accounts').status_code == 404
    pool.assert_not_called(); settings.assert_not_called(); executor.assert_not_called()
    assert handle.client is None and handle.runtime.database_pool is None


def test_enabled_module_auth_health_and_shutdown_are_isolated_from_host():
    events=[]; host=host_app(events); deps,pool,settings=dependencies(events=events)
    handle=install_content_planning(host, PlanningConfig(enabled=True), dependencies=deps)
    with TestClient(host) as client:
        assert handle.runtime.status == 'ready'
        assert client.get('/planning/api/health').json()['database'] == 'ok'
        assert client.get('/planning/api/internal/executor').status_code == 401
        assert client.get('/planning/api/internal/executor', headers=AUTH).json()['mode']=='host_triggered'
        assert client.get('/health').status_code == 200
        error=client.get('/host-error')
        assert error.json()=={'host_error': True} and error.headers['X-Host-Error']=='same'
        assert client.get('/health',headers=AUTH).json()['state']=='unchanged'
    assert events == ['host-start','executor-close','pool-close','host-stop']
    assert pool.closed and handle.runtime.status=='closed' and handle.client is None
    assert all(sql.startswith('SHOW ') for sql in pool.statements)


def test_startup_schema_failure_releases_created_pool_and_host_still_starts():
    host=host_app();pool=Pool(ready=False);deps,_,_=dependencies(pool=pool)
    executor=Mock();deps=replace(deps,executor_factory=executor)
    handle=install_content_planning(host, PlanningConfig(enabled=True),dependencies=deps)
    with TestClient(host) as client:
        assert client.get('/health').status_code==200
        r=client.get('/planning/api/health')
        assert r.status_code==503 and r.json()['code']=='planning_not_ready'
        assert handle.runtime.status=='failed' and pool.closed
    executor.assert_not_called()


def test_independent_app_fails_fast_without_exposing_provider_error():
    provider=Mock(side_effect=RuntimeError('PRIVATE-host-password'))
    app=create_app(PlanningConfig(enabled=True),dependencies=PlanningDependencies(settings_provider=provider))
    with pytest.raises(RuntimeError,match='could not be started') as error:
        with TestClient(app): pass
    assert 'PRIVATE' not in str(error.value)
    assert app.state.planning_runtime.status=='failed'


def test_configuration_cache_and_explicit_overrides_are_per_application():
    one=PlanningRuntime(PlanningConfig(enabled=True,settings={'MODEL_NAME':'explicit-one'}),
        PlanningDependencies(settings_provider=Mock(return_value={**VALUES,'MODEL_NAME':'database-one'})))
    two=PlanningRuntime(PlanningConfig(enabled=True),
        PlanningDependencies(settings_provider=Mock(return_value={**VALUES,'MODEL_NAME':'database-two'})))
    with one.bind():
        assert get_setting('MODEL_NAME')=='explicit-one'
        assert get_setting('MODEL_NAME')=='explicit-one'
    with two.bind(): assert get_setting('MODEL_NAME')=='database-two'
    one.dependencies.settings_provider.assert_called_once()
    two.dependencies.settings_provider.assert_called_once()
    with one.bind(): clear_cache()
    assert not one.configuration_cache.values and two.configuration_cache.values
    assert current_runtime() is None


def test_expired_application_cache_does_not_keep_a_stale_secret():
    provider=Mock(side_effect=[VALUES,RuntimeError('private-config-error')])
    runtime=PlanningRuntime(PlanningConfig(enabled=True),PlanningDependencies(settings_provider=provider))
    with runtime.bind():
        assert get_setting('INTEGRATION_TOKEN')==VALUES['INTEGRATION_TOKEN']
        runtime.configuration_cache.expires_at=0
        with pytest.raises(SystemConfigError) as error:get_setting('INTEGRATION_TOKEN')
        assert 'private' not in str(error.value)


def test_model_budgets_do_not_share_process_global_slots_between_apps():
    from app.content_planning.model_capacity import current_budget, CapacityExceeded
    one=PlanningRuntime(PlanningConfig(enabled=True));two=PlanningRuntime(PlanningConfig(enabled=True))
    with one.bind(),current_budget().slot('text',1):
        with pytest.raises(CapacityExceeded):
            with current_budget().slot('text',1):pass
        with two.bind(),current_budget().slot('text',1):pass
    assert one.capacity_controls is not two.capacity_controls


def test_background_thread_receives_runtime_and_actor_context_and_finishes_before_pool_closes():
    from app.content_planning.jobs.runtime import BackgroundExecutor
    from app.content_planning.core.actor import use_actor,current_actor
    started,release,done=Event(),Event(),Event();events=[];seen=[]
    @contextmanager
    def unlocked(name): yield True
    def work():
        seen.append((current_runtime(),get_setting('MODEL_NAME'),current_actor()))
        started.set();assert release.wait(3)
        assert not pool.closed
        events.append('job-finished');done.set();return {}
    deps,pool,_=dependencies(events=events,executor_factory=lambda rt: BackgroundExecutor(
        jobs={'manual_compute':(1,work)},locker=unlocked,max_workers=1))
    runtime=PlanningRuntime(PlanningConfig(enabled=True),deps)
    async def scenario():
        await runtime.start()
        with runtime.bind(),use_actor('TEST-UM'):
            runtime.background_executor.wake(['manual_compute'])
        assert started.wait(2)
        release.set();await runtime.close()
    asyncio.run(scenario())
    assert done.is_set() and seen==[(runtime,'text-test','TEST-UM')]
    assert events[-2:]==['job-finished','pool-close']


def test_forwarding_preserves_path_query_binary_body_status_and_duplicate_headers(monkeypatch):
    import app.content_planning.main as factory
    original=factory.create_app
    def with_probe(config,**kwargs):
        child=original(config,**kwargs)
        @child.post('/api/internal/probe/{name}')
        async def probe(name: str, request: Request):
            return {'name':name,'query':list(request.query_params.multi_items()),
                    'body':list(await request.body()),'operator':request.headers.get('x-operator-id')}
        @child.get('/api/internal/binary')
        async def binary():
            r=Response(gzip.compress(b'\x00\xffCONTENT'),status_code=429,media_type='application/octet-stream',
                       headers={'Content-Encoding':'gzip','Retry-After':'7','Content-Disposition':'attachment; filename="result.bin"'})
            r.raw_headers.extend([(b'set-cookie',b'one=1'),(b'set-cookie',b'two=2')]);return r
        return child
    monkeypatch.setattr(factory,'create_app',with_probe)
    deps,_,_=dependencies();host=host_app();install_content_planning(host,PlanningConfig(enabled=True),dependencies=deps)
    with TestClient(host) as client:
        r=client.post('/planning/api/internal/probe/%E4%B8%AD%E6%96%87?a=1&a=2&v=%2B',content=b'\x00\xffhello',
                      headers={**AUTH,'Content-Type':'application/octet-stream','X-Operator-ID':'TEST-UM'})
        assert r.status_code==200,r.text
        assert r.json()=={'name':'中文','query':[['a','1'],['a','2'],['v','+']],'body':[0,255,104,101,108,108,111],'operator':'TEST-UM'}
        binary=client.get('/planning/api/internal/binary',headers=AUTH)
        assert binary.status_code==429 and binary.headers['Retry-After']=='7'
        assert binary.content==b'\x00\xffCONTENT'
        assert binary.headers.get_list('set-cookie')==['one=1','two=2']


def test_forwarding_never_injects_service_credentials_and_preserves_validation():
    deps,_,_=dependencies();host=host_app();install_content_planning(host,PlanningConfig(enabled=True),dependencies=deps)
    with TestClient(host) as client:
        assert client.post('/planning/api/internal/manual-computations',json={}).status_code==401
        r=client.post('/planning/api/internal/manual-computations',json={},headers=AUTH)
        assert r.status_code==422
        assert client.post('/planning/api/internal/manual-computations',json={},headers={'X-Integration-Token':'wrong'}).status_code==401


def test_body_limit_is_checked_before_dispatch_and_host_is_unchanged():
    deps,_,_=dependencies();host=host_app();install_content_planning(host,PlanningConfig(enabled=True,max_forward_body_bytes=8),dependencies=deps)
    with TestClient(host) as client:
        assert client.post('/planning/api/internal/wakeup',content=b'x'*9,headers=AUTH).status_code==413
        assert client.get('/health').status_code==200


def test_openapi_keeps_host_components_and_namespaces_all_child_references():
    class WakeupInput(BaseModel): host_field:str
    host=host_app()
    @host.post('/host-schema',operation_id='host_operation',tags=['host'])
    def operation(value:WakeupInput): return value
    install_content_planning(host)
    schema=host.openapi();encoded=json.dumps(schema)
    assert schema['paths']['/host-schema']['post']['operationId']=='host_operation'
    assert schema['paths']['/host-schema']['post']['tags']==['host']
    assert 'WakeupInput' in schema['components']['schemas']
    op=schema['paths']['/planning/api/internal/wakeup']['post']
    assert op['operationId'].startswith('ContentPlanning_') and op['security']
    assert 'security' not in schema['paths']['/planning/api/health']['get']
    assert '/planning/api/accounts' not in schema['paths']
    def refs(value):
        if isinstance(value,list):
            for item in value:yield from refs(item)
        if isinstance(value,dict):
            if '$ref' in value:yield value['$ref']
            for item in value.values():yield from refs(item)
    for ref in refs(schema):
        assert ref.startswith('#/')
        target=schema
        for key in ref[2:].split('/'):target=target[key]


def test_two_installations_have_distinct_schema_names_and_lifetimes():
    host=host_app();one=install_content_planning(host,prefix='/one');two=install_content_planning(host,prefix='/two')
    assert one.runtime is not two.runtime
    s=host.openapi()
    assert s['paths']['/one/api/internal/wakeup']['post']['operationId']!=s['paths']['/two/api/internal/wakeup']['post']['operationId']
    with TestClient(host) as client:
        assert client.get('/one/api/health').status_code==client.get('/two/api/health').status_code==503
        assert client.get('/health').status_code==200


@pytest.mark.parametrize('prefix',['','/','planning','/planning/','/planning?x=1','/planning/{path:path}'])
def test_invalid_installation_prefix_is_rejected(prefix):
    with pytest.raises(ValueError):install_content_planning(FastAPI(),prefix=prefix)


def test_duplicate_installation_conflicting_routes_and_unknown_allowlist_are_rejected():
    host=FastAPI();install_content_planning(host)
    with pytest.raises(ValueError):install_content_planning(host)
    other=FastAPI()
    @other.get('/planning/api/health')
    def health():return {}
    with pytest.raises(ValueError):install_content_planning(other)
    with pytest.raises(ValueError):install_content_planning(FastAPI(),allowed_routes=['/api/not-a-real-route'])


def test_configuration_mapping_is_namespaced_and_secrets_do_not_appear_in_repr():
    values={'CONTENT_PLANNING_ENABLED':'true','PLANNING_MYSQL_HOST':'test','PLANNING_MYSQL_USER':'test',
            'PLANNING_MYSQL_PASSWORD':'private-password','PLANNING_MYSQL_DATABASE':'planning',
            'PLANNING_INTEGRATION_TOKEN':'private-token','ARK_API_KEY':'host-secret-ignored'}
    config=PlanningConfig.from_mapping(values)
    assert config.enabled and config.settings=={'INTEGRATION_TOKEN':'private-token'}
    assert all(secret not in repr(config) for secret in ('private-password','private-token','host-secret-ignored'))
    assert 'private-password' not in repr(config.database)
    assert not PlanningConfig.from_mapping({}).enabled
    with pytest.raises(ValueError):PlanningConfig(model_protocol='responses')


def test_host_mapping_supports_resource_limits_and_the_existing_environment_selector():
    config=PlanningConfig.from_mapping({'CONTENT_PLANNING_ENABLED':True,'PLANNING_ENV':'inside',
        'PLANNING_MAX_WORKERS':'3','PLANNING_POOL_SIZE':'12','PLANNING_CACHE_SECONDS':'1.5',
        'PLANNING_MODEL_AUTHORIZATION_SCHEME':'ApiKey','PLANNING_MODEL_HEADERS':{'X-Gateway':'planning'}})
    assert config.settings=={'PLANNING_ENV':'inside'}
    assert (config.max_workers,config.pool_size,config.cache_seconds)==(3,12,1.5)
    assert config.model_headers=={'X-Gateway':'planning'}
    with pytest.raises(ValueError):PlanningConfig(model_headers={'Authorization':'override'})


def test_owned_adapters_close_once_and_executor_failure_does_not_abort_host_shutdown():
    events=[];host=host_app(events);deps,pool,_=dependencies(events=events)
    executor=Mock();executor.close.side_effect=RuntimeError('private-executor-error')
    adapter=Mock()
    deps=replace(deps,executor_factory=lambda rt:executor,
                 model_adapters={'text':adapter,'embedding':adapter},model_adapters_owned=True)
    handle=install_content_planning(host,PlanningConfig(enabled=True),dependencies=deps)
    with TestClient(host):assert handle.runtime.status=='ready'
    assert events[-2:]==['pool-close','host-stop']
    adapter.close.assert_called_once();assert pool.closed and handle.runtime.status=='closed'


def test_second_start_is_rejected_without_closing_the_live_application():
    deps,pool,_=dependencies();runtime=PlanningRuntime(PlanningConfig(enabled=True),deps)
    async def scenario():
        await runtime.start()
        with pytest.raises(RuntimeError,match='more than once'):await runtime.start()
        assert runtime.status=='ready' and not pool.closed
        await runtime.close()
    asyncio.run(scenario())


def test_custom_model_adapter_is_explicit_and_does_not_call_the_builtin_transport():
    from app.content_planning.doubao_labeling import ark_post,DoubaoConfig
    text=Mock();text.post.return_value={'choices':[]}
    vector=Mock()
    deps,pool,_=dependencies()
    runtime=PlanningRuntime(PlanningConfig(enabled=True,model_protocol='custom'),
        replace(deps,model_adapters={'text':text,'embedding':vector}))
    async def scenario():
        await runtime.start()
        with runtime.bind(),patch('app.content_planning.doubao_labeling.open_request',side_effect=AssertionError('no HTTP')):
            config=DoubaoConfig('http://model.test','private','text','vector',5)
            assert ark_post(config,'/chat/completions',{'messages':[]})=={'choices':[]}
        await runtime.close()
    asyncio.run(scenario())
    text.post.assert_called_once();text.close.assert_not_called()


def test_enabled_installations_keep_settings_and_credentials_separate_and_preserve_root_path():
    host=host_app();deps_one,_,_=dependencies(values={**VALUES,'INTEGRATION_TOKEN':'one'})
    deps_two,_,_=dependencies(values={**VALUES,'INTEGRATION_TOKEN':'two'})
    install_content_planning(host,PlanningConfig(enabled=True),prefix='/one',dependencies=deps_one)
    install_content_planning(host,PlanningConfig(enabled=True),prefix='/two',dependencies=deps_two)
    with TestClient(host,root_path='/gateway') as client:
        assert client.get('/gateway/one/api/health').status_code==200
        for prefix,token,wrong in [('/one','one','two'),('/two','two','one')]:
            assert client.get('/gateway'+prefix+'/api/internal/executor',headers={'X-Integration-Token':token}).status_code==200
            assert client.get('/gateway'+prefix+'/api/internal/executor',headers={'X-Integration-Token':wrong}).status_code==401


def test_existing_host_startup_and_shutdown_handlers_still_run():
    events=[];host=FastAPI()
    host.router.add_event_handler('startup',lambda:events.append('start'))
    host.router.add_event_handler('shutdown',lambda:events.append('stop'))
    install_content_planning(host)
    with TestClient(host):assert events==['start']
    assert events==['start','stop']


def test_child_lifespan_does_not_leave_its_context_bound_in_the_host_task():
    deps,_,_=dependencies();host=host_app()
    handle=install_content_planning(host,PlanningConfig(enabled=True),dependencies=deps)
    async def scenario():
        assert current_runtime() is None
        async with host.router.lifespan_context(host) as state:
            assert state=={'host_state':'unchanged'}
            assert handle.runtime.status=='ready' and current_runtime() is None
        assert current_runtime() is None
    asyncio.run(scenario())


def test_default_model_transport_uses_explicit_gateway_headers_without_global_auth_changes():
    from app.content_planning.doubao_labeling import ark_post,DoubaoConfig
    deps,_,_=dependencies();runtime=PlanningRuntime(PlanningConfig(enabled=True,
        model_authorization_scheme='ApiKey',model_headers={'X-Gateway-App':'planning'}),deps)
    response=Mock();response.read.return_value=b'{"choices":[]}'
    transport=Mock();transport.return_value.__enter__=Mock(return_value=response)
    transport.return_value.__exit__=Mock(return_value=False)
    with runtime.bind(),patch('app.content_planning.doubao_labeling.open_request',transport):
        assert ark_post(DoubaoConfig('http://gateway.test','private-key','text','vector',5),
                        '/chat/completions',{'messages':[]})=={'choices':[]}
    request=transport.call_args.args[0]
    assert request.get_header('Authorization')=='ApiKey private-key'
    assert request.get_header('X-gateway-app')=='planning'


def test_portable_package_can_be_imported_inside_another_app_without_standalone_files(tmp_path):
    root=Path(__file__).resolve().parents[2]
    destination=tmp_path/'app/content_planning'
    destination.parent.mkdir();(destination.parent/'__init__.py').write_text('')
    shutil.copytree(root/'app/content_planning',destination,ignore=shutil.ignore_patterns('__pycache__'))
    (destination.parent/'db.py').write_text("raise RuntimeError('wrong host database imported')")
    (destination.parent/'services').mkdir();(destination.parent/'services/__init__.py').write_text("raise RuntimeError('wrong host services imported')")
    script="""import os
from unittest.mock import patch
original=dict(os.environ)
with patch('pymysql.connect',side_effect=AssertionError('no database')), patch('dotenv.dotenv_values',side_effect=AssertionError('no env file')), patch('concurrent.futures.ThreadPoolExecutor',side_effect=AssertionError('no executor')):
    import app.content_planning
    from app.content_planning.main import create_app
    from app.content_planning.config import PlanningConfig
    application=create_app(PlanningConfig())
assert dict(os.environ)==original
print('portable-import-ok')
"""
    result=subprocess.run([sys.executable,'-c',script],cwd=tmp_path,
                          env={**os.environ,'PYTHONPATH':str(tmp_path)},capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'portable-import-ok' in result.stdout
