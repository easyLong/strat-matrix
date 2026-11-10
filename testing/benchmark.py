"""Outside-only control assembly: same rules, isolated cold caches, no global config edits."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime,timezone
from functools import wraps
from hashlib import sha256
import json
import sys


def clone_fixture(fixture,run_id):
    value=deepcopy(fixture)
    if len(value['accounts'])!=1 or len(value['topics'])!=12:
        raise ValueError('Benchmark requires one account and twelve raw topics')
    account=value['accounts'][0];identity='E2E-CHAIN-'+run_id
    now=datetime.now(timezone.utc).isoformat()
    account.update(account_id=identity,updated_at=now)
    for index,interaction in enumerate(account.get('interactions',[]),1):
        interaction.update(account_id=identity,content_id=f'BENCH-{run_id}-{index}')
    for index,topic in enumerate(value['topics'],1):
        if {'tags','vector','fit_score'}&topic.keys():raise ValueError('No injected algorithm outputs')
        topic.update(topic_id=f'{identity}-T{index:02}',updated_at=now)
    return value


def case_fingerprint(fixture):
    value=deepcopy(fixture)
    for account in value['accounts']:
        for key in ('account_id','updated_at'):account.pop(key,None)
        for interaction in account.get('interactions',[]):
            for key in ('account_id','content_id'):interaction.pop(key,None)
    for topic in value['topics']:
        for key in ('topic_id','updated_at'):topic.pop(key,None)
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def replace_aliases(original,replacement):
    for module in list(sys.modules.values()):
        if module and getattr(module,'__name__','').startswith('app.'):
            for key,value in list(vars(module).items()):
                if value is original:setattr(module,key,replacement)


def install(mode,namespace):
    if mode not in ('baseline','optimized') or not namespace:raise ValueError('Invalid benchmark mode')
    from app.content_planning.deployment_environment import current
    if current()['PLANNING_ENV']!='outside':raise ValueError('Benchmark is outside-only')
    from app.content_planning.matching_quality_store import QualityRuntime
    from app.content_planning.matching_quality_snapshot import content_hash
    original_key=QualityRuntime.key
    @wraps(original_key)
    def isolated_key(self,kind,payload):
        key,model=original_key(self,kind,payload)
        return content_hash({'benchmark_namespace':namespace,'original_key':key}),model
    QualityRuntime.key=isolated_key
    if mode=='optimized':return
    from app.content_planning import db,planning_input_runner
    import pymysql
    @contextmanager
    def direct_connection():
        connection=pymysql.connect(**db.settings())
        try:yield connection
        finally:connection.close()
    replace_aliases(db.connection,direct_connection)
    original_prepare=planning_input_runner.prepare_inputs
    @wraps(original_prepare)
    def serial_prepare(*args,**kwargs):
        return original_prepare(*args,**{**kwargs,'label_workers':1})
    replace_aliases(original_prepare,serial_prepare)
    original_find=QualityRuntime.find
    @wraps(original_find)
    def uncached_find(self,kind,payload,**kwargs):
        self._memory.pop(self.key(kind,payload)[0],None)
        return original_find(self,kind,payload,**kwargs)
    QualityRuntime.find=uncached_find
    QualityRuntime.prefetch=lambda self,kind,payloads:None
