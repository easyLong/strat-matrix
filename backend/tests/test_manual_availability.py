"""Regression coverage for per-date manual planning restrictions."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

from app.manual_availability import (
    ensure_manual_accounts_available, pending_manual_accounts, planned_manual_accounts,
)
from app.main import preview_manual_plan, submit_manual_preview
from app.models import ManualPreviewInput


class Cursor:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return next(self.results)

    def fetchone(self):
        return next(self.results)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class ManualAvailabilityTests(unittest.TestCase):
    day = date(2026, 10, 15)

    def test_only_completed_batch_results_are_reported_as_planned(self):
        cursor = Cursor([[{"account_id": "A"}]])
        self.assertEqual(planned_manual_accounts(cursor, self.day), {"A"})
        self.assertIn("b.plan_type='manual'", cursor.calls[0][0])
        self.assertIn("i.publish_date=%s", cursor.calls[0][0])

    def test_running_task_allocations_are_reserved_but_not_reported_as_planned(self):
        cursor = Cursor([[{"allocations_json": json.dumps([
            {"account_id": "B"}, {"account_id": "A"},
        ])}]])
        self.assertEqual(pending_manual_accounts(cursor, self.day), {"A", "B"})
        self.assertIn("t.status IN ('执行中','进行中')", cursor.calls[0][0])
        self.assertEqual(cursor.calls[0][1], (self.day,))

    def test_submission_locks_accounts_in_order_before_conflict_check(self):
        cursor = Cursor([[{"account_code": "A"}, {"account_code": "B"}],
                         [{"account_id": "B"}], []])
        with self.assertRaises(HTTPException) as raised:
            ensure_manual_accounts_available(cursor, self.day, ["B", "A"])
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("ORDER BY account_code FOR UPDATE", cursor.calls[0][0])
        self.assertEqual(cursor.calls[0][1], ["A", "B"])

    def test_worker_excludes_only_its_own_pending_task(self):
        cursor = Cursor([[{"account_code": "A"}], [], []])
        ensure_manual_accounts_available(cursor, self.day, ["A"], exclude_task_id=42)
        self.assertIn("t.id<>%s", cursor.calls[2][0])
        self.assertEqual(cursor.calls[2][1], (self.day, 42))

    def test_other_running_task_blocks_new_submission(self):
        cursor = Cursor([[{"account_code": "A"}], [], [
            {"allocations_json": '[{"account_id":"A"}]'},
        ]])
        with self.assertRaises(HTTPException) as raised:
            ensure_manual_accounts_available(cursor, self.day, ["A"])
        self.assertEqual(raised.exception.status_code, 409)

    def test_malformed_pending_allocations_do_not_allow_duplicate_planning(self):
        with self.assertRaises(ValueError):
            pending_manual_accounts(Cursor([[{"allocations_json": '{}'}]]), self.day)

    def test_disabled_accounts_are_rejected_before_allocation(self):
        cursor = Cursor([[]])
        with self.assertRaises(HTTPException):
            ensure_manual_accounts_available(cursor, self.day, ["A"])
        self.assertEqual(len(cursor.calls), 1)

    def test_preview_rejects_explicitly_selected_planned_account(self):
        account = dict(account_id="A", account_name="Account A", account_alias="", city="",
                       persona="", traffic_trend="", certified=False, followers=100)
        with patch('app.main.list_accounts', return_value=[account]), patch(
            'app.main.manual_account_availability', return_value={"planned_account_ids": ["A"]},
        ), patch('app.main.connection') as db:
            with self.assertRaises(HTTPException) as raised:
                preview_manual_plan(ManualPreviewInput(task_name="Test", publish_date=self.day,
                                                      account_ids=["A"], topic_ids=["T"]))
        self.assertEqual(raised.exception.status_code, 409)
        db.assert_not_called()

    def test_repeated_submission_reuses_running_task(self):
        preview = {"task_name": "Test", "publish_date": self.day, "allocations_json": '[]',
                   "status": "pending", "batch_id": None,
                   "expires_at": datetime.now() + timedelta(minutes=30)}
        existing = {"id": 42, "status": "执行中"}
        cursor = Cursor([preview, existing])

        class DB:
            def cursor(self):
                return cursor

        @contextmanager
        def connection():
            yield DB()

        background = BackgroundTasks()
        with patch('app.main.connection', connection):
            self.assertEqual(submit_manual_preview("P", background), existing)
        self.assertEqual(background.tasks, [])
        self.assertEqual(cursor.calls[0][0], "SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        self.assertFalse(any("INSERT INTO" in sql for sql, _ in cursor.calls))

    def test_stale_preview_conflict_is_rejected_before_task_creation(self):
        preview = {"task_name": "Test", "publish_date": self.day,
                   "allocations_json": json.dumps([{"account_id": "A", "account_name": "A",
                                                     "topic_id": "T", "topic_title": "T"}]),
                   "status": "pending", "batch_id": None,
                   "expires_at": datetime.now() + timedelta(minutes=30)}
        cursor = Cursor([preview, None])

        class DB:
            def cursor(self):
                return cursor

        @contextmanager
        def connection():
            yield DB()

        background = BackgroundTasks()
        with patch('app.main.connection', connection), patch(
            'app.main.ensure_manual_accounts_available',
            side_effect=HTTPException(status_code=409, detail="Already planned"),
        ):
            with self.assertRaises(HTTPException) as raised:
                submit_manual_preview("P", background)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertFalse(any("INSERT INTO" in sql for sql, _ in cursor.calls))
        self.assertEqual(background.tasks, [])


if __name__ == '__main__':
    unittest.main()
