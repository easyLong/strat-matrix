"""One failed preparation must not suppress unrelated results or state reads."""
from contextlib import ExitStack
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from app.content_planning import planning_workflow_worker as worker
from app.content_planning.jobs.worker import execute
from app.content_planning.services.errors import ApplicationError


def state(status='waiting', version=1, matching=None, batch=None):
    return {'status': status, 'version': version, 'preparation_id': 7,
            'matching_task_id': matching, 'production_batch_id': batch}


class WorkflowIsolationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.db = MagicMock()
        self.db.__enter__.return_value = self.db
        self.cursor = self.db.cursor.return_value.__enter__.return_value
        self.cursor.fetchone.return_value = {'acquired': 1}
        self.stack.enter_context(patch.object(worker, 'connection', return_value=self.db))
        self.discovery = self.stack.enter_context(patch.object(worker, 'discover_topics', return_value={'scanned': 1}))
        self.scan = self.stack.enter_context(patch.object(worker, '_pending_pipelines', return_value=[]))
        self.prepare = self.stack.enter_context(patch.object(worker, 'prepare_inputs', return_value={'failed': 0}))
        self.read = self.stack.enter_context(patch.object(worker, 'read_pipeline', return_value=state()))
        self.advance = self.stack.enter_context(patch.object(worker, 'advance_pipeline_to_commit'))
        self.match = self.stack.enter_context(patch.object(worker, 'execute_matching', return_value=0))
        self.production = self.stack.enter_context(patch.object(worker, 'reconcile_results', return_value={'applied': 1}))
        self.marketing = self.stack.enter_context(patch.object(worker, 'reconcile_marketing', return_value={'applied': 1}))

    def test_source_failure_skips_stale_input_work_but_reads_content_status(self):
        self.discovery.side_effect = RuntimeError('private connection string')
        report = worker.run_once()
        self.assertEqual(report['failed'], 1)
        self.scan.assert_not_called()
        self.prepare.assert_not_called()
        self.production.assert_called_once()
        self.marketing.assert_called_once()
        self.assertNotIn('private connection string', str(report))
        self.assertIn('RELEASE_LOCK', self.cursor.execute.call_args.args[0])

    def test_source_busy_is_waiting_not_failure_and_does_not_block_status(self):
        self.discovery.return_value = {'busy': True}
        report = worker.run_once()
        self.assertEqual(report['failed'], 0)
        self.scan.assert_not_called()
        self.production.assert_called_once()

    def test_content_read_failure_does_not_suppress_marketing_read(self):
        self.production.side_effect = ApplicationError(502, 'upstream')
        report = worker.run_once()
        self.assertEqual(report['failed'], 1)
        self.assertEqual(report['errors'][0]['phase'], 'production_results')
        self.marketing.assert_called_once()

    def test_input_failures_reach_worker_result_without_false_completion(self):
        self.scan.return_value = [1]
        self.advance.side_effect = [state(version=2), state(version=3)]
        self.prepare.return_value = {'failed': 2, 'labels': 3}
        report = worker.run_once()
        self.assertEqual(report['failed'], 2)
        self.assertEqual(execute('planning', lambda: report)['status'], 'failed')

    def test_idle_worker_does_not_prepare_global_model_queues(self):
        report = worker.run_once()
        self.prepare.assert_not_called()
        self.assertEqual(report['failed'], 0)

    def test_matching_uses_frozen_inputs_without_preparing_other_topics_again(self):
        self.scan.return_value = [1]
        self.read.return_value = state(matching=99)
        self.advance.side_effect = [state(version=2, matching=99), state('succeeded', version=3, matching=99, batch=55)]
        report = worker.run_once()
        self.prepare.assert_not_called()
        self.match.assert_called_once_with(task_id=99, max_jobs=1)
        self.assertEqual(report['pipelines'][0]['batch_id'], 55)
        self.assertEqual(report['failed'], 0)

    def test_pending_inputs_are_checked_before_matching_and_formal_commit(self):
        self.scan.return_value = [1]
        self.advance.side_effect = [state(version=2), state(version=3, matching=99),
                                   state('succeeded', version=4, matching=99, batch=55)]
        report = worker.run_once()
        self.prepare.assert_called_once_with(7)
        self.assertEqual([c.args for c in self.advance.call_args_list], [(1, 1), (1, 2), (1, 3)])
        self.assertEqual(report['pipelines'][0]['status'], 'succeeded')

    def test_failed_pipeline_does_not_abort_following_pipeline(self):
        self.scan.return_value = [1, 2]
        self.read.side_effect = [ApplicationError(503, 'database'), state('succeeded', batch=56)]
        report = worker.run_once()
        self.assertEqual(report['failed'], 1)
        self.assertEqual(report['pipelines'][1]['batch_id'], 56)
        self.production.assert_called_once()

    def test_version_race_is_distinct_from_business_conflict(self):
        self.scan.return_value = [1]
        self.read.side_effect = HTTPException(409, 'Pipeline版本已变化，请重新查询后再操作')
        report = worker.run_once()
        self.assertEqual((report['failed'], report['conflicts']), (0, 1))
        self.read.side_effect = ApplicationError(409, '策略配置无效')
        report = worker.run_once()
        self.assertEqual((report['failed'], report['conflicts']), (1, 0))

    def test_singleton_lock_and_content_disabled_mode_keep_their_boundaries(self):
        self.cursor.fetchone.return_value = {'acquired': 0}
        report = worker.run_once()
        self.assertTrue(report['busy'])
        self.discovery.assert_not_called()
        self.production.assert_not_called()
        self.cursor.fetchone.return_value = {'acquired': 1}
        worker.run_once(process_content=False)
        self.production.assert_not_called()
        self.marketing.assert_not_called()


if __name__ == '__main__':
    unittest.main()
