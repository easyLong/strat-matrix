"""Non-blocking admission for model APIs, shared model calls and durable queues.

HTTP admission and actual model calls use different budgets: an accepted HTTP
request never owns the model permit its background task will need later.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock

from .services.errors import ApplicationError


class CapacityExceeded(ApplicationError):
    retry_after = 2

    def __init__(self, scope='model', retry_after=2):
        self.scope = scope
        self.retry_after = max(1, min(120, int(retry_after)))
        super().__init__(429, '模型服务繁忙，请稍后重试' if scope != 'tasks'
                         else '待处理算法任务已达上限，请稍后重试')


@dataclass(frozen=True)
class CapacityPolicy:
    api: int = 4
    text: int = 2
    embedding: int = 2
    pending: int = 32
    scope: str = 'process'


KEYS = {'api': 'AI_API_MAX_CONCURRENT_REQUESTS', 'text': 'MODEL_MAX_CONCURRENT_REQUESTS',
        'embedding': 'EMBEDDING_MAX_CONCURRENT_REQUESTS', 'pending': 'AI_PENDING_TASK_LIMIT'}


def read_policy():
    from .system_config import snapshot, SystemConfigError
    values = snapshot()
    defaults = CapacityPolicy()
    result = {}
    for field, key in KEYS.items():
        raw = values.get(key, str(getattr(defaults, field)))
        try:
            value = int(raw)
            if not 1 <= value <= (1000 if field == 'pending' else 64): raise ValueError()
        except (TypeError, ValueError):
            raise SystemConfigError(f'系统配置 {key} 无效或已停用') from None
        result[field] = value
    scope = values.get('AI_LIMIT_SCOPE', 'process')
    if scope not in ('process', 'mysql'):
        raise SystemConfigError('系统配置 AI_LIMIT_SCOPE 无效或已停用')
    return CapacityPolicy(**result, scope=scope)


class ConcurrentBudget:
    """Keep active counts when a live limit changes; never replace semaphores."""
    def __init__(self):
        self._lock = RLock()
        self._active = {}

    @contextmanager
    def slot(self, group, limit):
        with self._lock:
            if self._active.get(group, 0) >= limit: raise CapacityExceeded(group)
            self._active[group] = self._active.get(group, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                self._active[group] -= 1


budget = ConcurrentBudget()


def current_budget():
    from .context import current_runtime
    runtime = current_runtime()
    return runtime.budget() if runtime is not None else budget


def lock_prefix():
    from .db import settings
    return 'godp:ai:' + sha256(settings()['database'].encode()).hexdigest()[:12]


@contextmanager
def database_slot(group, limit):
    """Optional cross-process limit on the same planner MySQL; no new table."""
    from .db import connection
    with connection() as db, db.cursor() as cursor:
        acquired = None
        prefix=f'{lock_prefix()}:{group}'
        gate=prefix+':gate'
        cursor.execute('SELECT GET_LOCK(%s,0) AS acquired',(gate,))
        if cursor.fetchone()['acquired'] != 1: raise CapacityExceeded(group)
        try:
            names=[f'{prefix}:{index}' for index in range(64)]
            # Count the fixed maximum slot set, including high-numbered old
            # holders after lowering the limit. Admission itself is serialized.
            cursor.execute('SELECT '+','.join(f'IS_USED_LOCK(%s) AS s{i}' for i in range(64)),tuple(names))
            held=cursor.fetchone()
            if not held or len(held)!=64: raise ApplicationError(503,'模型并发控制暂不可用')
            if sum(value is not None for value in held.values()) >= limit: raise CapacityExceeded(group)
            name=next(names[i] for i in range(64) if held[f's{i}'] is None)
            cursor.execute('SELECT GET_LOCK(%s,0) AS acquired',(name,))
            if cursor.fetchone()['acquired'] != 1: raise CapacityExceeded(group)
            acquired=name
        finally:
            cursor.execute('SELECT RELEASE_LOCK(%s)',(gate,))
        try:
            yield
        finally:
            cursor.execute('SELECT RELEASE_LOCK(%s)', (acquired,))


@contextmanager
def model_slot(kind, *, managed=False):
    policy = read_policy() if managed else CapacityPolicy()
    limit = getattr(policy, kind)
    with current_budget().slot(kind, limit):
        if policy.scope == 'mysql':
            with database_slot(kind, limit): yield
        else:
            yield


async def model_api_admission():
    """Acquire before entering a sync model handler; never wait for capacity."""
    policy = read_policy()
    with current_budget().slot('api', policy.api):
        yield


def task_api_admission(kind, *, retry=False):
    from fastapi import Request, HTTPException
    from fastapi.concurrency import contextmanager_in_threadpool
    async def admission(request: Request):
        raw=await request.json()
        if not isinstance(raw,dict): raise HTTPException(422,'算法任务参数必须为对象')
        identity={k:raw[k] for k in ('cycle_start','preparation_id') if k in raw}
        identity.update(retry=retry)
        if retry:
            identity['id']=request.path_params.get('pipeline_id',request.path_params.get('task_id'))
        try:
            if identity.get('cycle_start'):
                from datetime import date
                date.fromisoformat(identity['cycle_start'])
        except (ValueError,TypeError):
            raise HTTPException(422,'策划周期日期无效') from None
        async with contextmanager_in_threadpool(pending_task_admission(kind,identity)):
            yield
    return admission


@contextmanager
def pending_task_admission(kind, identity=None, *, policy=None):
    """Serialize count+accept across HTTP callers until the handler commits.

    Only public task-creation/retry adapters use this gate. Pipeline child stages
    remain free to progress when the top-level admission quota is full.
    """
    from .db import connection
    from .ordinary_planning import current_next_monday
    from .planning_reservation import reservation_key
    policy = policy or read_policy()
    specs = {
        'pipeline': ('godp_planning_pipeline_run', ('pending','waiting','running')),
        'preparation': ('godp_ai_preparation', ('waiting_inputs',)),
        'matching': ('godp_matching_task', ('queued','processing')),
    }
    table, states = specs[kind]
    identity = identity or {}
    with connection() as db, db.cursor() as cursor:
        name = f'{lock_prefix()}:admit:{kind}'
        cursor.execute('SELECT GET_LOCK(%s,0) AS acquired', (name,))
        if cursor.fetchone()['acquired'] != 1: raise CapacityExceeded('tasks')
        try:
            existing = None
            if identity.get('id') is not None:
                cursor.execute(f"SELECT id,status FROM {table} WHERE id=%s AND del_flag='N'", (identity['id'],))
                existing = cursor.fetchone()
            elif kind == 'matching' and identity.get('preparation_id') is not None:
                cursor.execute(f"SELECT id,status FROM {table} WHERE preparation_id=%s AND del_flag='N'", (identity['preparation_id'],))
                existing = cursor.fetchone()
            elif kind in ('pipeline','preparation'):
                start = identity.get('cycle_start') or current_next_monday()
                from datetime import date
                if isinstance(start,str): start=date.fromisoformat(start)
                key = f'formal-planning:{start.isoformat()}' if kind=='pipeline' else reservation_key(start)
                cursor.execute(f"SELECT id,status FROM {table} WHERE reservation_key=%s AND del_flag='N'", (key,))
                existing = cursor.fetchone()
            # Idempotent creation must remain readable even at full capacity.
            if existing and (not identity.get('retry') or existing['status'] in states):
                yield
                return
            marks=','.join(['%s']*len(states))
            cursor.execute(f"SELECT id FROM {table} WHERE del_flag='N' AND status IN ({marks}) LIMIT %s",
                           (*states,policy.pending))
            if len(cursor.fetchall()) >= policy.pending: raise CapacityExceeded('tasks')
            yield
        finally:
            cursor.execute('SELECT RELEASE_LOCK(%s)', (name,))


def initialize_config():
    """Add only the five capacity settings; never overwrite existing values."""
    from .db import connection
    from .system_config import clear_cache
    from .system_config_catalog import CATALOG
    inserted=0
    with connection() as db,db.cursor() as cursor:
        for key in (*KEYS.values(),'AI_LIMIT_SCOPE'):
            spec=CATALOG[key]
            cursor.execute('INSERT IGNORE INTO godp_system_config '
                '(config_key,config_group,config_name,config_value,value_type,is_secret,create_by,update_by,created_by,updated_by) '
                "VALUES (%s,%s,%s,%s,%s,0,'capacity-init','capacity-init',create_by,update_by)",
                (key,spec.group,spec.name,spec.default,spec.kind))
            inserted+=int(cursor.rowcount==1)
        db.commit()
    clear_cache()
    return inserted


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='初始化模型并发限制参数，不改已有值')
    parser.add_argument('--init-config',action='store_true',required=True)
    parser.parse_args()
    print(f'模型限流配置已就绪，新增 {initialize_config()} 项')
