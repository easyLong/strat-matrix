"""Marketing completion uses content totals, including tasks without accounts."""

import unittest
from datetime import datetime

from app.manual_marketing_api import summary
from app.models import ManualTaskSummary


class MarketingSummaryTests(unittest.TestCase):
    def task(self, **changes):
        row = dict(id=1, task_code='MKT-TEST', task_name='Marketing test',
                   allocation_count=12, account_count=0, content_per_account=0,
                   topic_snapshot_json='[{"topic_id":"T-1"}]', status='待分配',
                   create_time=datetime(2026, 10, 30), create_by='Tester',
                   update_time=datetime(2026, 10, 30))
        row.update(changes)
        return ManualTaskSummary(**summary(row))

    def test_completed_request_without_accounts_has_full_content_progress(self):
        task = self.task(status='已完成')
        self.assertEqual(task.content_status, '已完成')
        self.assertEqual((task.content_completed_count, task.content_total_count), (12, 12))
        self.assertEqual(task.content_completed_account_count, 0)

    def test_marketing_content_total_is_independent_of_allocated_accounts(self):
        task = self.task(status='已完成', account_count=3)
        self.assertEqual((task.content_completed_count, task.content_total_count), (12, 12))
        self.assertEqual(task.content_completed_account_count, 3)

    def test_pending_request_is_not_reported_as_completed(self):
        task = self.task()
        self.assertEqual(task.content_status, '待分配')
        self.assertEqual((task.content_completed_count, task.content_total_count), (0, 12))

    def test_completed_legacy_task_uses_accounts_times_quantity(self):
        task = self.task(status='已完成', allocation_count=0, account_count=3, content_per_account=2)
        self.assertEqual(task.content_status, '已完成')
        self.assertEqual((task.content_completed_count, task.content_total_count), (6, 6))


if __name__ == '__main__':
    unittest.main()
