"""Regression checks for planning status and historical content progress."""

from contextlib import closing, contextmanager
from datetime import date
import sqlite3
import unittest
from unittest.mock import patch

from app.main import list_batches
from app.planning_progress import COMPLETED_ACCOUNT_COUNT_SQL, planning_status_label, production_status


class PlanningProgressTests(unittest.TestCase):
    def test_count_accounts_only_after_all_their_slots_complete(self):
        with closing(sqlite3.connect(":memory:")) as db:
            count = db.execute(
                "WITH i(id, account_id, topic_id, status) AS (VALUES "
                "(1,'A','T1','待生成'), (2,'A','T2','待生成'), "
                "(3,'B','T1','待生成'), (4,'B','T2','待生成'), "
                "(5,'C','T1','生成失败'), (6,'D','','待生成'), "
                "(7,'E','T1','已生成')), "
                "s(item_id, production_status) AS (VALUES "
                "(1,'generated'), (2,'published'), (3,'generated'), (4,'ready'), "
                "(5,'failed'), (6,'planned')) "
                f"SELECT {COMPLETED_ACCOUNT_COUNT_SQL} FROM i LEFT JOIN s ON s.item_id=i.id"
            ).fetchone()[0]
        # A is counted once; E uses its historical completion record.
        # B is only partially complete; C failed; D has no assigned topic.
        self.assertEqual(count, 2)

    def test_current_slot_state_takes_precedence_over_historical_item_status(self):
        self.assertEqual(production_status({"production_status": "planned", "status": "已生成"}), "planned")
        self.assertEqual(production_status({"production_status": "generated", "status": "待生成"}), "generated")

    def test_legacy_items_recover_content_state_without_a_slot_record(self):
        for status, expected in (
            ("待生成", "planned"), ("待审核", "planned"), ("已分配", "planned"),
            ("生成中", "ready"), ("已生成", "generated"),
            ("已发布", "published"), ("生成失败", "failed"),
        ):
            with self.subTest(status=status):
                self.assertEqual(production_status({"status": status}), expected)

    def test_planning_status_has_three_values(self):
        for status in ("执行中", "进行中", "热点空槽待填充", None):
            self.assertEqual(planning_status_label(status), "生成中")
        for status in ("已完成", "已规划", "待生成", "已生成", "已发布"):
            self.assertEqual(planning_status_label(status), "已完成")
        self.assertEqual(planning_status_label("执行失败"), "生成失败")
        self.assertEqual(planning_status_label("已完成", failed_count=1), "生成失败")

    def test_content_failure_does_not_turn_successful_planning_into_failure(self):
        results = iter([
            [{"id": 1, "plan_type": "auto", "status": "未完成", "cycle_start": date(2026, 10, 12),
              "account_count": 2, "updated_at": None}],
            [],
            [{"batch_id": 1, "item_count": 6, "account_item_count": 2,
              "planning_failed_count": 0, "selected_topic_count": 4,
              "completed_account_count": 1,
              "production_completed_count": 3, "ready_count": 2, "failed_count": 1}],
        ])

        class Cursor:
            def execute(self, *args):
                pass

            def fetchall(self):
                return next(results)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        class Database:
            def cursor(self):
                return Cursor()

        @contextmanager
        def database():
            yield Database()

        with patch("app.main.connection", database):
            batch = list_batches()[0]
        self.assertEqual(batch["planning_status"], "已完成")
        self.assertEqual(batch["failed_count"], 0)
        self.assertEqual(batch["completed_count"], 2)
        self.assertEqual(batch["content_completed_account_count"], 1)
        self.assertEqual((batch["content_failed_count"], batch["content_completed_count"],
                          batch["content_total_count"]), (1, 3, 6))


if __name__ == "__main__":
    unittest.main()
