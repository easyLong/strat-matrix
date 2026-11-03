from contextlib import contextmanager
from threading import Event
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from app.bootstrap import app
from app.jobs.runtime import BackgroundExecutor, job_lock
from app.system_config import override_config
from app.api.manual_planning import submit_manual_preview


@contextmanager
def unlocked(name):
    yield True


class BackgroundExecutorTests(unittest.TestCase):
    def make_executor(self, jobs, **kwargs):
        executor = BackgroundExecutor(jobs=jobs, locker=kwargs.pop('locker', unlocked), **kwargs)
        self.addCleanup(executor.close)
        return executor

    def wait_for(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail('Background operation did not finish')

    def test_startup_is_idle_and_duplicate_wakeups_do_not_duplicate_running_work(self):
        release, started = Event(), Event()
        def handler():
            started.set()
            release.wait(3)
        executor = self.make_executor({'manual': (2, handler)})
        self.addCleanup(release.set)
        self.assertFalse(started.is_set())
        self.assertEqual(executor.snapshot()['jobs']['manual']['runs'], 0)
        self.assertEqual(executor.wake(['manual', 'manual'])['accepted_jobs'], ['manual'])
        self.assertTrue(started.wait(2))
        for _ in range(20):
            self.assertEqual(executor.wake(['manual'])['coalesced_jobs'], ['manual'])
        release.set()
        self.wait_for(lambda: not executor.snapshot()['pending_jobs'])
        self.assertEqual(executor.snapshot()['jobs']['manual']['runs'], 1)

    def test_pool_is_bounded_and_unknown_roles_are_rejected_before_any_submission(self):
        release = Event()
        executor = self.make_executor({name: (2, lambda *args: release.wait(3))
                                       for name in ('manual', 'planning', 'weekly', 'hotspot')})
        self.addCleanup(release.set)
        with self.assertRaises(ValueError):
            executor.wake(['manual', 'unknown'])
        self.assertEqual(executor.snapshot()['pending_jobs'], [])
        executor.wake(['manual', 'planning', 'weekly', 'hotspot'])
        self.wait_for(lambda: sum(row['status'] == 'running' for row in executor.snapshot()['jobs'].values()) == 2)
        self.assertEqual(len(executor.snapshot()['pending_jobs']), 4)
        self.assertEqual(sum(row['status'] == 'queued' for row in executor.snapshot()['jobs'].values()), 2)
        release.set()

    def test_database_role_lock_skips_work_owned_by_another_instance(self):
        @contextmanager
        def busy(name):
            yield False
        handler = MagicMock()
        executor = self.make_executor({'manual': (2, handler)}, locker=busy)
        executor.wake(['manual'])
        self.wait_for(lambda: not executor.snapshot()['pending_jobs'])
        handler.assert_not_called()
        self.assertEqual(executor.snapshot()['jobs']['manual']['status'], 'busy')

    def test_failure_is_visible_other_roles_continue_and_next_trigger_can_retry(self):
        handler = MagicMock(side_effect=[RuntimeError('private details'), {'completed': 1}])
        good = MagicMock(return_value={})
        executor = self.make_executor({'manual': (2, handler), 'planning': (10, good)})
        with self.assertLogs('application-worker', level='ERROR'):
            executor.wake(['manual', 'planning'])
            self.wait_for(lambda: not executor.snapshot()['pending_jobs'])
        state = executor.snapshot()
        self.assertEqual(state['jobs']['manual']['failures'], 1)
        self.assertNotIn('private details', str(state))
        good.assert_called_once()
        executor.wake(['manual'])
        self.wait_for(lambda: not executor.snapshot()['pending_jobs'])
        self.assertEqual(executor.snapshot()['jobs']['manual']['status'], 'ok')

    def test_shutdown_rejects_new_hints_and_a_new_service_can_resume_the_existing_queue(self):
        # The queue is external to the executor, just as persisted business rows are.
        queue = [1, 2]
        def claim_existing():
            return {'task_id': queue.pop(0)}
        first = self.make_executor({'manual': (2, claim_existing)})
        first.wake(['manual'])
        self.wait_for(lambda: not first.snapshot()['pending_jobs'])
        first.close()
        with self.assertRaises(RuntimeError):
            first.wake(['manual'])
        second = self.make_executor({'manual': (2, claim_existing)})
        self.assertEqual(queue, [2])
        second.wake(['manual'])
        self.wait_for(lambda: not second.snapshot()['pending_jobs'])
        self.assertEqual(queue, [])

    def test_database_advisory_lock_is_released_when_processing_raises(self):
        database, cursor = MagicMock(), MagicMock()
        database.__enter__.return_value = database
        database.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = {'acquired': 1}
        with patch('app.jobs.runtime.connection', return_value=database):
            with self.assertRaises(RuntimeError):
                with job_lock('manual') as acquired:
                    self.assertTrue(acquired)
                    raise RuntimeError()
        self.assertIn('RELEASE_LOCK', cursor.execute.call_args.args[0])


class BackgroundApiTests(unittest.TestCase):
    def test_lifespan_is_idle_internal_api_requires_auth_and_hints_return_without_waiting(self):
        handler, release = MagicMock(), Event()
        handler.side_effect = lambda: release.wait(3)
        executor = BackgroundExecutor(jobs={'manual': (2, handler)}, locker=unlocked)
        try:
            with override_config({'BANK_SOURCE_MODE': 'local_fixture', 'INTEGRATION_TOKEN': 'test-token'}), \
                    patch('app.api.background_execution.BackgroundExecutor', return_value=executor), TestClient(app) as client:
                handler.assert_not_called()
                self.assertEqual(client.post('/api/internal/wakeup', json={'jobs': ['manual']}).status_code, 401)
                headers = {'X-Integration-Token': 'test-token'}
                self.assertEqual(client.post('/api/internal/wakeup', json={'jobs': ['invalid']}, headers=headers).status_code, 422)
                response = client.post('/api/internal/wakeup', json={'jobs': ['manual']}, headers=headers)
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()['accepted_jobs'], ['manual'])
                self.assertFalse(release.is_set())
                state = client.get('/api/internal/executor', headers=headers).json()
                self.assertEqual(state['mode'], 'host_triggered')
                executor._closed = True
                self.assertEqual(client.post('/api/internal/wakeup', json={'jobs': ['manual']}, headers=headers).status_code, 503)
                release.set()
        finally:
            release.set()
            executor.close()

    def test_manual_submission_notifies_only_after_persistence_and_shutdown_keeps_acceptance(self):
        committed = []
        executor = MagicMock()
        executor.wake.side_effect = lambda jobs: self.assertEqual(committed, [True])
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(background_executor=executor)))
        def persist(*args, **kwargs):
            committed.append(True)
            return {'id': 7}
        with patch('app.api.manual_planning.invoke', side_effect=persist):
            self.assertEqual(submit_manual_preview('P', request), {'id': 7})
        executor.wake.assert_called_once_with(['manual'])
        executor.wake.side_effect = RuntimeError('closing')
        with patch('app.api.manual_planning.invoke', return_value={'id': 7}):
            self.assertEqual(submit_manual_preview('P', request), {'id': 7})
