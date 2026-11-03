"""Request-triggered execution inside FastAPI; no polling thread or timer.

Wakeups are coalesced hints, not business tasks. Work is claimed from existing
durable queues, whose leases/checkpoints provide recovery after termination.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock

from ..db import connection
from .handlers import JOBS, execute


@contextmanager
def job_lock(name):
    with connection() as db, db.cursor() as cursor:
        key = 'godp:embedded:' + name
        cursor.execute('SELECT GET_LOCK(%s,0) acquired', (key,))
        acquired = cursor.fetchone()['acquired'] == 1
        try:
            yield acquired
        finally:
            if acquired:
                cursor.execute('SELECT RELEASE_LOCK(%s)', (key,))


class BackgroundExecutor:
    def __init__(self, *, jobs=None, locker=job_lock, max_workers=2):
        self._jobs = JOBS if jobs is None else jobs
        self._locker = locker
        self._lock = RLock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='planning-execution')
        self._pending = {}
        self._closed = False
        self._states = {name: {'status': 'idle', 'runs': 0, 'failures': 0, 'last_finished_at': None}
                        for name in self._jobs}

    def wake(self, names):
        names = list(dict.fromkeys(names))
        if any(name not in self._jobs for name in names):
            raise ValueError('未知后台执行类型')
        accepted, coalesced = [], []
        with self._lock:
            if self._closed:
                raise RuntimeError('后台执行器正在停止')
            for name in names:
                if name in self._pending:
                    coalesced.append(name)
                    continue
                # One future per fixed role; the queue cannot grow with wakeup requests.
                self._states[name]['status'] = 'queued'
                future = self._pool.submit(self._run, name)
                self._pending[name] = future
                future.add_done_callback(lambda completed, role=name: self._finished(role, completed))
                accepted.append(name)
        return {'status': 'accepted', 'accepted_jobs': accepted, 'coalesced_jobs': coalesced}

    def _run(self, name):
        with self._lock:
            self._states[name]['status'] = 'running'
        try:
            with self._locker(name) as acquired:
                if not acquired:
                    return {'status': 'busy'}
                return execute(name, self._jobs[name][1])
        except Exception as exc:
            return {'status': 'failed', 'error_type': type(exc).__name__}

    def _finished(self, name, future):
        with self._lock:
            if self._pending.get(name) is not future:
                return
            del self._pending[name]
            report = {'status': 'cancelled'} if future.cancelled() else future.result()
            state = self._states[name]
            state.update(status=report['status'], last_finished_at=datetime.now(timezone.utc).isoformat())
            state['runs'] += 1
            state['failures'] += int(report['status'] == 'failed')
            state['error_type'] = report.get('error_type')

    def snapshot(self):
        with self._lock:
            return {'mode': 'host_triggered', 'accepting': not self._closed,
                    'pending_jobs': list(self._pending),
                    'jobs': {name: dict(state) for name, state in self._states.items()}}

    def close(self):
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=True, cancel_futures=True)
