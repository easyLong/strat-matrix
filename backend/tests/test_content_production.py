"""Contract and safety boundaries complement the real MySQL workflow acceptance command."""

import unittest
from datetime import datetime
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError

from app.content_production import enqueue_batch, batch_flow
from app.content_production_api import ProductionResult
from app.integration_models import OfficialUsageQuery


class ContentProductionTests(unittest.TestCase):
    def test_utc_task_timestamps_have_an_offset_for_business_timezone_display(self):
        with patch('app.content_production.connection') as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = [{'request_json': '{}', 'response_json': None,
                                             'accepted_at': datetime(2026, 10, 21, 6, 0), 'completed_at': None}]
            task = batch_flow(123)['tasks'][0]
        self.assertEqual(task['accepted_at'], '2026-10-21T06:00:00+00:00')
        self.assertIsNone(task['completed_at'])

    def test_unconfigured_provider_never_marks_a_slot_running(self):
        with patch('app.content_production.get_setting', return_value='disabled'), \
                patch('app.content_production.connection') as db:
            with self.assertRaises(HTTPException) as exc:
                enqueue_batch(123)
            self.assertEqual(exc.exception.status_code, 503)
            db.assert_not_called()

    def test_callback_only_needs_task_identity_and_result(self):
        result = ProductionResult(production_task_id='SLOT-123-v2', status='completed')
        self.assertEqual(result.production_task_id, 'SLOT-123-v2')
        with self.assertRaises(ValidationError):
            ProductionResult(production_task_id='SLOT-123-v2', status='arbitrary')

    def test_usage_query_accepts_only_topic_ids(self):
        query = OfficialUsageQuery(topic_ids=['TOPIC-1'])
        self.assertEqual(query.topic_type, '普通')
        with self.assertRaises(ValidationError):
            OfficialUsageQuery(topic_ids=['TOPIC-1', 'TOPIC-1'])


if __name__ == '__main__':
    unittest.main()
