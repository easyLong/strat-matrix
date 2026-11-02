"""Preparation must report model failures and preserve newer concurrent results."""
from contextlib import ExitStack
import unittest
from unittest.mock import MagicMock, patch

from app import planning_input_runner as runner
from app.services.errors import ApplicationError


class PreparationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.mocks = {}
        self.stack.enter_context(patch.object(runner.InputBatch, 'persist'))
        db = MagicMock()
        db.__enter__.return_value = db
        db.cursor.return_value.__enter__.return_value.fetchone.return_value = {'acquired': 1}
        self.stack.enter_context(patch.object(runner, 'connection', return_value=db))
        self.stack.enter_context(patch.object(runner, 'open_scope', return_value=(None, {}, [])))
        defaults = {
            'retry_due': True,
            'list_topic_label_jobs': {'jobs': []},
            'topic_vector_jobs': {'jobs': [], 'next_after_id': 0},
            'preparation_account_jobs': {'jobs': [], 'next_after_id': 0},
            'claim_topic_label_job': {
                'topic': {'title': '测试'}, 'taxonomy': {f'T{i}': ['标签'] for i in range(1, 6)},
                'taxonomy_version': 1, 'lease_id': 'LEASE',
            },
            'label_topic': {'labels': {f'T{i}': '标签' for i in range(1, 7)},
                            't6_embedding': [1, 0], 't6_embedding_model': 'test-model'},
            'put_topic_tags': {},
            'embed_profile': {'status': 'ready', 'vector': [1, 0], 'vector_model': 'test-model'},
            'save_topic_vector': {},
            'save_preparation_account_vector': {},
        }
        for name, value in defaults.items():
            self.mocks[name] = self.stack.enter_context(patch.object(runner, name, return_value=value))

    def labels(self, count=2):
        self.mocks['list_topic_label_jobs'].side_effect = [
            {'jobs': [{'id': i, 'topic_id': f'T{i}'} for i in range(1, count + 1)]}, {'jobs': []}]

    def topics(self):
        self.mocks['topic_vector_jobs'].side_effect = [
            {'jobs': [{'id': i, 'topic_id': f'T{i}', 'profile': {'topic': i},
                       'content_hash': str(i) * 64, 'tag_version': 1} for i in (1, 2)], 'next_after_id': 2},
            {'jobs': [], 'next_after_id': 2}]

    def test_failed_model_is_reported_and_next_topic_can_finish(self):
        self.labels()
        self.mocks['label_topic'].side_effect = [RuntimeError('private model message'), self.mocks['label_topic'].return_value]
        report = runner.prepare_inputs()
        self.assertEqual((report['labels'], report['failed']), (1, 1))
        self.assertEqual(self.mocks['put_topic_tags'].call_args_list[0].args[1].label_status, '失败')
        self.assertNotIn('private model message', str(report))
        self.assertEqual(report['errors'][0]['identity'], 'T1')

    def test_failure_record_error_does_not_abort_other_jobs(self):
        self.labels()
        self.mocks['label_topic'].side_effect = [RuntimeError('model'), self.mocks['label_topic'].return_value]
        self.mocks['put_topic_tags'].side_effect = [ApplicationError(503, 'database'), {}]
        report = runner.prepare_inputs()
        self.assertEqual((report['labels'], report['failed'], report['failure_record_errors']), (1, 1, 1))

    def test_newer_label_result_is_not_downgraded_after_conflict(self):
        self.labels(1)
        self.mocks['put_topic_tags'].side_effect = ApplicationError(409, '租约已变化')
        report = runner.prepare_inputs()
        self.assertEqual((report['failed'], report['conflicts'], report['labels']), (0, 1, 0))
        self.assertEqual(self.mocks['put_topic_tags'].call_count, 1)

    def test_claim_contention_is_distinct_from_a_broken_taxonomy(self):
        self.labels(1)
        self.mocks['claim_topic_label_job'].side_effect = ApplicationError(409, '任务已被领取、完成或取消')
        report = runner.prepare_inputs()
        self.assertEqual((report['conflicts'], report['failed']), (1, 0))
        self.mocks['put_topic_tags'].assert_not_called()
        self.labels(1)
        self.mocks['claim_topic_label_job'].side_effect = ApplicationError(409, 'T1–T5 标签字典存在空维度')
        report = runner.prepare_inputs()
        self.assertEqual((report['conflicts'], report['failed']), (0, 1))

    def test_topic_vector_conflict_skips_failure_write_and_continues(self):
        self.topics()
        self.mocks['save_topic_vector'].side_effect = [ApplicationError(409, '画像已变化'), {}]
        report = runner.prepare_inputs()
        self.assertEqual((report['topic_vectors'], report['failed'], report['conflicts']), (1, 0, 1))
        self.assertEqual(self.mocks['save_topic_vector'].call_count, 2)
        self.assertTrue(all(c.args[1].status == 'ready' for c in self.mocks['save_topic_vector'].call_args_list))

    def test_account_failure_and_following_success_are_independent(self):
        self.mocks['preparation_account_jobs'].side_effect = [
            {'jobs': [{'id': i, 'account_id': f'A{i}', 'profile_hash': str(i) * 64, 'profile': {}} for i in (1, 2)], 'next_after_id': 2},
            {'jobs': [], 'next_after_id': 2}]
        self.mocks['embed_profile'].side_effect = [RuntimeError('model'), self.mocks['embed_profile'].return_value]
        report = runner.prepare_inputs(77)
        self.assertEqual((report['account_vectors'], report['failed']), (1, 1))
        calls = self.mocks['save_preparation_account_vector'].call_args_list
        self.assertEqual(calls[0].args[:2], (77, 'A1'))
        self.assertEqual(calls[0].args[2].status, 'failed')
        self.assertEqual(calls[1].args[2].status, 'ready')

    def test_retry_backoff_does_not_call_model_or_count_failure(self):
        self.labels(1)
        self.mocks['retry_due'].return_value = False
        report = runner.prepare_inputs()
        self.assertEqual((report['deferred'], report['failed']), (1, 0))
        self.mocks['claim_topic_label_job'].assert_not_called()
        self.mocks['label_topic'].assert_not_called()

    def test_broken_page_cursor_cannot_loop_forever(self):
        self.mocks['list_topic_label_jobs'].return_value = {'jobs': [{'id': 1, 'topic_id': 'T1'}]}
        with self.assertRaisesRegex(ValueError, '游标未推进'):
            runner.prepare_inputs()
        self.assertEqual(self.mocks['list_topic_label_jobs'].call_count, 2)

    def scoped_state(self):
        self.stack.enter_context(patch.object(runner, 'inspect_scope', return_value={'waiting_reasons': []}))
        return ({'topic_sources': {'T1': 'hash', 'T2': 'hash'}, 'account_ids': ['A1'],
                 'taxonomy_version': 1, 'embedding_model': 'test-model'}, {}, [])

    def test_scoped_queues_never_receive_an_unbounded_topic_query(self):
        state = self.scoped_state()
        self.labels()
        report = runner._prepare_batch(77, state, 24, 30)
        self.assertEqual(report['labels'], 2)
        for name in ('list_topic_label_jobs', 'topic_vector_jobs'):
            self.assertTrue(all(c.kwargs['topic_ids'] == ['T1', 'T2']
                                for c in self.mocks[name].call_args_list))

    def test_budget_checkpoint_resumes_after_last_completed_job(self):
        state = self.scoped_state()
        self.labels()
        first = runner._prepare_batch(77, state, 1, 30)
        self.assertTrue(first['budget_exhausted'])
        self.assertEqual(first['checkpoint']['cursors']['labels'], 1)
        self.mocks['list_topic_label_jobs'].side_effect = [
            {'jobs': [{'id': 2, 'topic_id': 'T2'}]}, {'jobs': []}]
        second = runner._prepare_batch(77, state, 2, 30)
        self.assertEqual(second['labels'], 1)
        self.assertEqual(self.mocks['claim_topic_label_job'].call_count, 2)
        self.assertEqual(state[1]['rounds'], 1)

    def test_changed_scope_stops_before_any_model_or_job_query(self):
        scope, progress, _ = self.scoped_state()
        report = runner._prepare_batch(77, (scope, progress, [{'code': 'chat_model_changed'}]), 24, 30)
        self.assertTrue(report['has_more'])
        self.mocks['list_topic_label_jobs'].assert_not_called()
        self.mocks['embed_profile'].assert_not_called()

    def test_result_with_wrong_model_cannot_be_saved_as_ready(self):
        state = self.scoped_state()
        self.topics()
        self.mocks['embed_profile'].return_value = {'status': 'ready', 'vector': [1, 0], 'vector_model': 'other'}
        report = runner._prepare_batch(77, state, 24, 30)
        self.assertEqual(report['failed'], 2)
        self.assertTrue(all(c.args[1].status == 'failed' for c in self.mocks['save_topic_vector'].call_args_list))

    def test_expired_budget_stops_before_model_request(self):
        self.labels(1)
        with patch('app.preparation_batches.monotonic', side_effect=[0, 31]):
            report = runner.prepare_inputs()
        self.assertTrue(report['budget_exhausted'])
        self.mocks['claim_topic_label_job'].assert_not_called()

    def test_frozen_task_does_not_query_or_prepare_input_jobs(self):
        runner.open_scope.return_value = None
        report = runner.prepare_inputs(77)
        self.assertTrue(report['skipped'])
        self.mocks['list_topic_label_jobs'].assert_not_called()


if __name__ == '__main__':
    unittest.main()
