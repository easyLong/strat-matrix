"""Behavioral regression tests for the shared-database execution boundaries."""

from copy import deepcopy
from datetime import date, datetime, timedelta
import json
import io
from contextlib import redirect_stdout
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import shared_production as production
from app import ordinary_scheduler as scheduler
from app.source_discovery import discovery_action, source_signature
from app.topic_profile import profile_from_source
from app.bank_bridge.memory import fixture_source
from app.shared_production_api import ResultInput


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.dumps({'title': '家庭账单整理', 'outline': '整理收入和支出'})
        tags = json.dumps({f'T{i}': ['标签'] for i in range(1, 7)})
        _, fingerprint = profile_from_source(self.payload, tags)
        self.topic = dict(payload_json=self.payload, tags_json=tags, label_status='已完成',
                          taxonomy_version=7, tag_version=2, profile_tag_version=2, content_hash=fingerprint)
        self.job = dict(source_payload_json=self.payload, status='completed', taxonomy_version=7)

    def test_new_topic_enqueues_but_existing_valid_profile_baselines(self):
        self.assertEqual(discovery_action(self.topic, None, 7), 'baseline')
        self.assertEqual(discovery_action({'payload_json': self.payload}, None, 7), 'enqueue')

    def test_metadata_changes_do_not_trigger_model_calls(self):
        changed = json.loads(self.payload) | {'heat': 999, 'updated_at': '2026-10-30'}
        self.assertEqual(source_signature(changed), source_signature(self.payload))
        self.topic['payload_json'] = json.dumps(changed)
        self.assertEqual(discovery_action(self.topic, self.job, 7), 'unchanged')

    def test_outline_change_invalidates_an_inflight_job(self):
        self.job['status'] = 'processing'
        self.topic['payload_json'] = json.dumps({'title': '家庭账单整理', 'outline': '新的大纲'})
        self.assertEqual(discovery_action(self.topic, self.job, 7), 'enqueue')

    def test_dictionary_change_requires_new_labels(self):
        self.assertEqual(discovery_action(self.topic, self.job, 8), 'enqueue')

    def test_identical_processing_job_keeps_its_lease(self):
        self.job['status'] = 'processing'
        self.assertEqual(discovery_action(self.topic, self.job, 7), 'unchanged')

    def test_deleted_job_is_reactivated(self):
        self.job['del_flag'] = 'Y'
        self.assertEqual(discovery_action(self.topic, self.job, 7), 'baseline')

    def test_product_association_change_requires_new_labels(self):
        self.topic['payload_json'] = json.dumps(json.loads(self.payload) | {'related_product': '信用卡'})
        self.assertEqual(discovery_action(self.topic, self.job, 7), 'enqueue')


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, 9)
        self.slot = dict(id=10, state_id=20, slot_id='SLOT-10', version=2, topic_id='TOPIC-1',
                         topic_title='家庭账单整理', topic_type='普通', slot_type='ordinary',
                         production_status='ready', content_id=None, production_task_id='PROD-1',
                         production_reported_at=self.now - timedelta(seconds=5),
                         production_lease_expires_at=self.now + timedelta(seconds=60))
        self.cursor = MagicMock()
        self.cursor.rowcount = 1

    def test_success_writes_one_usage_fact_and_one_counter_in_the_same_transaction(self):
        result = production.apply_result(self.cursor, self.slot, 'generated', 'CONTENT-1', self.now)
        sql = [str(call.args[0]) for call in self.cursor.execute.call_args_list]
        self.assertTrue(result['accepted'])
        self.assertEqual(sum('INSERT IGNORE INTO godp_topic_usage_fact' in q for q in sql), 1)
        self.assertEqual(sum('INSERT INTO godp_topic_official_usage' in q for q in sql), 1)

    def test_duplicate_completion_has_no_writes(self):
        self.slot.update(production_status='generated', content_id='CONTENT-1')
        result = production.apply_result(self.cursor, self.slot, 'generated', 'CONTENT-1', self.now)
        self.assertTrue(result['reused'])
        self.cursor.execute.assert_not_called()

    def test_existing_usage_fact_does_not_increment_counter_again(self):
        self.cursor.rowcount = 0
        production.apply_result(self.cursor, self.slot, 'generated', 'CONTENT-1', self.now)
        self.assertFalse(any('INSERT INTO godp_topic_official_usage' in call.args[0]
                             for call in self.cursor.execute.call_args_list))

    def test_failure_never_counts_usage(self):
        production.apply_result(self.cursor, self.slot, 'failed', None, self.now, '生产失败')
        self.assertFalse(any('godp_topic_usage_fact' in call.args[0]
                             for call in self.cursor.execute.call_args_list))

    def test_completed_content_cannot_regress(self):
        self.slot['production_status'] = 'generated'
        with self.assertRaises(HTTPException):
            production.apply_result(self.cursor, self.slot, 'failed', None, self.now)
        self.cursor.execute.assert_not_called()

    def test_out_of_order_result_cannot_regress(self):
        result = production.apply_result(self.cursor, self.slot, 'planned', None, self.now)
        self.assertTrue(result['stale'])
        self.cursor.execute.assert_not_called()

    def test_expired_attempt_is_rejected_before_writes(self):
        self.slot['production_lease_expires_at'] = self.now - timedelta(seconds=1)
        with patch.object(production, 'now_utc', return_value=self.now), \
                patch.object(production, 'connection') as connect:
            db = connect.return_value.__enter__.return_value
            cursor = db.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = self.slot
            with self.assertRaises(HTTPException):
                production.finish_task('PROD-1', '已完成')
            db.commit.assert_not_called()

    def test_counter_failure_does_not_commit_content_success(self):
        with patch.object(production, 'now_utc', return_value=self.now), \
                patch.object(production, 'connection') as connect:
            db = connect.return_value.__enter__.return_value
            cursor = db.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = self.slot
            def execute(sql, params):
                if 'INSERT INTO godp_topic_official_usage' in sql:
                    raise RuntimeError('simulated count failure')
            cursor.execute.side_effect = execute
            cursor.rowcount = 1
            with self.assertRaises(RuntimeError):
                production.finish_task('PROD-1', '已完成')
            db.commit.assert_not_called()

    def test_content_result_contract_only_requires_task_and_status(self):
        result = ResultInput(production_task_id='PROD-1', status='已完成')
        self.assertIsNone(result.content_id)

    def test_approved_marketing_content_is_not_sent_to_topic_production(self):
        source = fixture_source()
        slot = {**self.slot, 'account_id': source.account_rows[0].account_id,
                'topic_id': source.topic_rows[1].topic_id}
        with self.assertRaises(production.DataContractError):
            production.production_input(slot, {a.account_id:a for a in source.account_rows},
                                        {t.topic_id:t for t in source.topic_rows})

    def test_old_pending_rows_without_results_do_not_starve_newer_pages(self):
        pages = [{'status': 'reconciled', 'applied': 0, 'scanned': 2, 'next_after_id': 10},
                 {'status': 'reconciled', 'applied': 1, 'scanned': 1, 'next_after_id': 12}]
        with patch.object(production, '_reconcile_page', side_effect=pages) as read:
            report = production.reconcile_results(limit=2)
        self.assertEqual(report['applied'], 1)
        self.assertEqual(report['scanned'], 3)
        self.assertEqual(read.call_args_list[1].args, (None, 2, 10))


class SchedulerTests(unittest.TestCase):
    def test_created_pipeline_dates_can_be_logged(self):
        output = io.StringIO()
        with redirect_stdout(output):
            scheduler.log({'status': 'created', 'cycle_start': date(2026, 11, 2)})
        self.assertEqual(json.loads(output.getvalue())['cycle_start'], '2026-11-02')

    def test_due_time_creates_a_v2_pipeline_without_running_legacy_planner(self):
        start = date(2026, 11, 2)
        with patch.object(scheduler, 'due_cycle', return_value=start), \
                patch.object(scheduler, 'start_v2_pipeline', return_value={'status': 'created'}) as create:
            self.assertEqual(scheduler.run_due(datetime(2026, 10, 30))['status'], 'created')
            create.assert_called_once_with(start)

    def test_unbound_policy_does_not_create_tasks(self):
        with patch.object(scheduler, 'get_setting', side_effect=lambda key, default: default), \
                patch.object(scheduler, 'create_pipeline') as create:
            with self.assertRaises(scheduler.PlanningError):
                scheduler.start_v2_pipeline(date(2026, 11, 2))
            create.assert_not_called()

    def test_duplicate_account_scope_is_rejected(self):
        values = {'AUTO_PLANNING_POLICY_ID': '5', 'AUTO_PLANNING_ACCOUNT_IDS': '["A","A"]'}
        with patch.object(scheduler, 'get_setting', side_effect=lambda key, default: values.get(key, default)), \
                patch.object(scheduler, 'create_pipeline') as create:
            with self.assertRaises(scheduler.PlanningError):
                scheduler.start_v2_pipeline(date(2026, 11, 2))
            create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
