"""Opt-in timing in the acceptance process only; never log prompts, SQL or secrets."""
from contextvars import ContextVar
from datetime import datetime,timezone
from functools import wraps
from importlib import import_module
from itertools import count
import json
import os
from pathlib import Path
import sys
from threading import RLock
from time import perf_counter


class Recorder:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=RLock()
        self.sequence=count(1)
        self.current=ContextVar('acceptance_timing_parent',default=None)

    def wrap(self,name,operation,metadata=None,result_metadata=None):
        @wraps(operation)
        def timed(*args,**kwargs):
            started=perf_counter()
            event=dict(name=name(*args,**kwargs) if callable(name) else name,
                       span_id=next(self.sequence),parent_id=self.current.get(),
                       process_id=os.getpid(),
                       started_at=datetime.now(timezone.utc).isoformat(),start_s=started,status='ok')
            if metadata:event.update(metadata(*args,**kwargs))
            token=self.current.set(event['span_id'])
            try:
                result=operation(*args,**kwargs)
                if result_metadata:event.update(result_metadata(result))
                return result
            except BaseException as error:
                event.update(status='checkpoint' if type(error).__name__=='QualityPending' else 'error',
                             error_type=type(error).__name__)
                from app.doubao_labeling import DoubaoError
                if isinstance(error,DoubaoError):event['error_reason']=str(error)[:160]
                raise
            finally:
                event['duration_s']=round(perf_counter()-started,6)
                self.current.reset(token)
                with self.lock,self.path.open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(event,ensure_ascii=True)+'\n')
        return timed

    def patch(self,module_name,attribute,name,metadata=None,result_metadata=None):
        owner=import_module(module_name)
        original=getattr(owner,attribute)
        wrapped=self.wrap(name,original,metadata,result_metadata)
        setattr(owner,attribute,wrapped)
        # Existing from-import aliases must observe the same timer. Future
        # imports obtain the wrapped function from its canonical owner.
        for module in list(sys.modules.values()):
            if module and getattr(module,'__name__','').startswith('app.'):
                for key,value in list(vars(module).items()):
                    if value is original:setattr(module,key,wrapped)
        return original


def _model_usage(result):
    usage=result.get('usage',{}) if isinstance(result,dict) else {}
    if not isinstance(usage,dict):return {}
    return {key:value for key,value in usage.items()
            if key in ('prompt_tokens','completion_tokens','total_tokens') and type(value) is int and value>=0}


def install(directory):
    recorder=Recorder(Path(directory)/'python-timings.jsonl')
    targets=[
        ('app.source_discovery','discover_topics','source.discovery'),
        ('app.ai_preparation','create_preparation','preparation.create'),
        ('app.ai_preparation','advance_preparation','preparation.advance'),
        ('app.planning_input_runner','prepare_inputs','input.prepare'),
        ('app.doubao_labeling','label_topic','label.request'),
        ('app.planning_input_runner','_execute_input',lambda counts,kind,*args,**kwargs:'input.'+kind),
        ('app.account_profile','profile_from_preparation','account.profile'),
        ('app.matching_tasks','create_task','matching.freeze'),
        ('app.matching_executor_worker','run_once','matching.worker'),
        ('app.matching_quality_model','annotate_batch','matching.annotations'),
        ('app.matching_quality_model','map_account','matching.mapping'),
        ('app.matching_quality_model','judge_batch','matching.precision'),
        ('app.matching_quality_executor','_need_vector','matching.need_vector'),
        ('app.matching_quality_executor','recall','matching.recall'),
        ('app.matching_quality_executor','allocate_quality','matching.allocation'),
        ('app.matching_quality_executor','allocate_matrix','matching.capacity'),
        ('app.matching_quality_executor','optimize_portfolios','matching.portfolio'),
        ('app.planning_workflow_worker','run_once','pipeline.worker'),
        ('app.planning_pipeline','advance_pipeline','pipeline.advance'),
    ]
    for module,attribute,name in targets:recorder.patch(module,attribute,name)
    recorder.patch('app.doubao_labeling','ark_post',
                   lambda config,path,payload:'model.chat' if path=='/chat/completions' else 'model.embedding',
                   result_metadata=_model_usage)
    from app.bank_bridge.java_http import JavaHTTPClient
    JavaHTTPClient.read=recorder.wrap('source.java_http',JavaHTTPClient.read,
        metadata=lambda self,capability,*args,**kwargs:dict(capability=capability))
    from app.matching_quality_store import QualityRuntime
    QualityRuntime.find=recorder.wrap('cache.lookup',QualityRuntime.find,
        metadata=lambda self,kind,payload,*args,**kwargs:dict(kind=kind,cache_key=self.key(kind,payload)[0]),
        result_metadata=lambda value:dict(hit=value is not None))
    # Driver/statement round trips only, not connection lifetime (which can
    # include waiting for the LLM). Never retain SQL text, values or DSNs.
    import pymysql
    from pymysql.cursors import Cursor
    from pymysql.connections import Connection
    pymysql.connect=recorder.wrap('db.connect',pymysql.connect)
    Cursor.execute=recorder.wrap('db.execute',Cursor.execute)
    Connection.commit=recorder.wrap('db.commit',Connection.commit)
    return recorder
