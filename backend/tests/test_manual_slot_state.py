"""Manual slots need local replacement state regardless of event eligibility."""

import unittest
from unittest.mock import Mock, patch

from app.integration import queue_manual_slot


class ManualSlotStateTests(unittest.TestCase):
    def create(self, cursor, code):
        return queue_manual_slot(cursor, 17, 3, code, 'ACCOUNT-1', 'TOPIC-1', '2026-10-29')

    def assert_state_created(self, cursor):
        inserts = [c for c in cursor.execute.call_args_list if 'INSERT INTO godp_slot_state' in c.args[0]]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0].args[1][:3], (17, 'SLOT-17', 'TOPIC-1'))

    @patch('app.integration.queue_event')
    def test_demo_has_local_state_without_external_event(self, event):
        cursor = Mock()
        self.assertFalse(self.create(cursor, 'DEMO-MAN-1'))
        self.assert_state_created(cursor)
        cursor.fetchone.assert_not_called()
        event.assert_not_called()

    @patch('app.integration.queue_event')
    def test_unsynced_source_has_local_state_without_external_event(self, event):
        cursor = Mock()
        cursor.fetchone.return_value = None
        self.assertFalse(self.create(cursor, 'MAN-1'))
        self.assert_state_created(cursor)
        event.assert_not_called()

    @patch('app.integration.queue_event')
    def test_synced_source_has_one_local_state_and_event(self, event):
        cursor = Mock()
        cursor.fetchone.return_value = {'id': 1}
        self.assertTrue(self.create(cursor, 'MAN-1'))
        self.assert_state_created(cursor)
        event.assert_called_once()


if __name__ == '__main__':
    unittest.main()
