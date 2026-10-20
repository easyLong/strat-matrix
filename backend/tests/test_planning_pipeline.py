"""Planning Pipeline V1 orchestration boundaries, without a live database or executor."""

from contextlib import ExitStack
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app import planning_pipeline as service
from app.init_db import column_definitions, table_descriptions


START = date(2026, 10, 26)


class PipelineStore:
    def __init__(self):
        self.pipeline = None
        self.stages = []
        self.cursor = MagicMock()
        self.db = MagicMock()
        self.db.__enter__.return_value = self.db
        self.db.cursor.return_value = self.cursor
        self.cursor.__enter__.return_value = self.cursor
        self.cursor.execute.side_effect = self.execute
        self.cursor.fetchone.side_effect = lambda: deepcopy(self.current_one)
        self.cursor.fetchall.side_effect = lambda: deepcopy(self.current_many)
        self.current_one = None
        self.current_many = []

    def execute(self, sql, params=()):
        self.current_one, self.current_many = None, []
        if "GET_LOCK" in sql:
            self.current_one = {"acquired": 1}
        elif "RELEASE_LOCK" in sql or sql.startswith("SET TRANSACTION"):
            return
        elif "FROM godp_planning_pipeline_run" in sql:
            if not self.pipeline:
                return
            if "reservation_key=%s" in sql and self.pipeline["reservation_key"] != params[0]:
                return
            if "id=%s" in sql and self.pipeline["id"] != params[0]:
                return
            self.current_one = self.pipeline
        elif "FROM godp_planning_stage_run" in sql:
            pipeline_id = params[0]
            self.current_many = sorted(
                [row for row in self.stages if row["pipeline_id"] == pipeline_id],
                key=lambda row: (row["stage_order"], row["id"]),
            )
        elif sql.startswith("INSERT INTO godp_planning_pipeline_run"):
            keys = ("pipeline_code", "reservation_key", "schema_version", "cycle_start", "cycle_end",
                    "selection_json", "selection_hash", "policy_id", "create_by", "update_by")
            self.pipeline = {**dict(zip(keys, params)), "id": 501, "status": "pending",
                             "current_stage": "source_ingestion", "version": 1,
                             "preparation_id": None, "matching_task_id": None,
                             "production_batch_id": None, "last_error_code": "",
                             "last_error_message": "", "del_flag": "N"}
            self.cursor.lastrowid = 501
        elif sql.startswith("INSERT INTO godp_planning_stage_run"):
            pipeline_id, stage_key, stage_order, create_by, update_by = params
            self.stages.append({"id": len(self.stages) + 1, "pipeline_id": pipeline_id,
                                "stage_key": stage_key, "stage_order": stage_order,
                                "status": "pending", "attempt_count": 0, "version": 1,
                                "backend_type": None, "backend_id": None, "detail_json": None,
                                "error_code": "", "error_message": "", "started_at": None,
                                "finished_at": None, "create_by": create_by, "update_by": update_by,
                                "del_flag": "N"})
        elif sql.startswith("UPDATE godp_planning_stage_run"):
            row = next(item for item in self.stages if item["id"] == params[-1])
            keys = ("status", "attempt_count", "backend_type", "backend_id", "detail_json",
                    "error_code", "error_message", "started_at", "finished_at", "update_by")
            row.update(dict(zip(keys, params[:-1])))
            row["version"] += 1
        elif sql.startswith("UPDATE godp_planning_pipeline_run SET status=%s"):
            (status, current_stage, preparation_id, matching_task_id, error_code,
             error_message, update_by, pipeline_id) = params
            assert pipeline_id == self.pipeline["id"]
            self.pipeline.update(status=status, current_stage=current_stage,
                                 preparation_id=preparation_id, matching_task_id=matching_task_id,
                                 last_error_code=error_code, last_error_message=error_message,
                                 update_by=update_by, version=self.pipeline["version"] + 1)
        elif sql.startswith("UPDATE godp_planning_pipeline_run SET status='cancelled'"):
            update_by, pipeline_id = params
            assert pipeline_id == self.pipeline["id"]
            self.pipeline.update(status="cancelled", reservation_key=None, current_stage=None,
                                 last_error_code="", last_error_message="", update_by=update_by,
                                 version=self.pipeline["version"] + 1)


class PlanningPipelineTests(unittest.TestCase):
    def setUp(self):
        self.store = PipelineStore()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(service, "connection", return_value=self.store.db))
        self.stack.enter_context(patch.object(service, "current_next_monday", return_value=START))
        self.stack.enter_context(patch.object(service, "_validate_policy", return_value=None))

    def create(self):
        return service.create_pipeline(START, ["ACC-2", "ACC-1"], 7)

    def test_create_is_idempotent_and_parallel_frontier_is_explicit(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first["pipeline_id"], second["pipeline_id"])
        self.assertTrue(second["reused"])
        self.assertEqual(json.loads(self.store.pipeline["selection_json"]), ["ACC-1", "ACC-2"])
        self.assertEqual(first["active_stages"], ["source_ingestion"])
        self.store.stages[0]["status"] = "succeeded"
        detail = service.read_pipeline(first["pipeline_id"])
        self.assertEqual(detail["active_stages"], ["topic_profile", "account_profile"])

    def test_pipeline_reuses_preparation_and_matching_then_stops_before_formal_commit(self):
        created = self.create()
        waiting = {"preparation_id": 123, "status": "waiting_inputs", "version": 1,
                   "last_report": {"inputs_ready": False}}
        frozen = {"preparation_id": 123, "status": "inputs_frozen", "version": 2,
                  "last_report": {"inputs_ready": True}}
        task = {"id": 1001, "preparation_id": 123, "preparation_version": 2,
                "policy_id": 7, "policy_hash": "p" * 64, "input_hash": "i" * 64,
                "status": "queued", "version": 1, "attempt_count": 0,
                "lease_expires_at": None, "error_code": "", "result_hash": None,
                "completed_at": None, "contract_version": 1, "supplemental_hash": None}
        evaluated = {**task, "status": "evaluated", "version": 2,
                     "result_hash": "r" * 64}
        evaluation = {"stages": [
            {"stage": "hard_gate", "summary": {"ok": True}},
            {"stage": "recall", "summary": {"ok": True}},
            {"stage": "fit", "summary": {"ok": True}},
            {"stage": "global_allocation", "summary": {"ok": True}},
            {"stage": "composition", "summary": {"ok": True}},
        ]}
        with patch.object(service, "create_preparation", return_value=waiting), \
             patch.object(service, "advance_preparation", return_value=waiting), \
             patch.object(service, "read_preparation", return_value=waiting):
            result = service.advance_pipeline(501, created["version"])
        self.assertEqual(result["status"], "waiting")
        self.assertEqual(result["preparation_id"], 123)
        self.assertEqual({stage["stage_key"]: stage["status"] for stage in result["stages"]}["source_ingestion"],
                         "succeeded")

        with patch.object(service, "read_preparation", return_value=frozen), \
             patch.object(service, "create_task", return_value={"task_id": 1001}), \
             patch.object(service, "_read_task", return_value=task):
            result = service.advance_pipeline(501, result["version"])
        self.assertEqual(result["matching_task_id"], 1001)
        stages = {stage["stage_key"]: stage for stage in result["stages"]}
        self.assertEqual(stages["topic_profile"]["status"], "succeeded")
        self.assertEqual(stages["account_profile"]["status"], "succeeded")
        self.assertEqual(stages["single_account_matching"]["status"], "waiting")

        with patch.object(service, "read_preparation", return_value=frozen), \
             patch.object(service, "_read_task", return_value=evaluated), \
             patch.object(service, "read_evaluation", return_value=evaluation):
            result = service.advance_pipeline(501, result["version"])
        stages = {stage["stage_key"]: stage for stage in result["stages"]}
        self.assertEqual(stages["single_account_matching"]["status"], "succeeded")
        self.assertEqual(stages["matrix_allocation"]["status"], "succeeded")
        self.assertEqual(stages["composition"]["status"], "succeeded")
        self.assertEqual(stages["result_commit"]["status"], "waiting")
        self.assertEqual(stages["result_commit"]["error_code"], "result_commit_not_implemented")
        self.assertFalse(result["operations_result_committed"])
        self.assertIsNone(result["production_batch_id"])
        for call in self.store.cursor.execute.call_args_list:
            sql = call.args[0]
            self.assertNotIn("INSERT INTO godp_planning_batch", sql)
            self.assertNotIn("INSERT INTO godp_planning_item", sql)
            self.assertNotIn("godp_slot_state", sql)

    def test_result_commit_wait_cannot_be_retried_into_a_fake_success(self):
        created = self.create()
        for stage in self.store.stages:
            stage["status"] = "succeeded"
        self.store.stages[-1].update(status="waiting", error_code="result_commit_not_implemented",
                                     error_message="not implemented")
        self.store.pipeline.update(status="waiting", current_stage="result_commit")
        with self.assertRaises(HTTPException) as caught:
            service.retry_pipeline(501, created["version"])
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("正式结果提交适配器尚未实现", str(caught.exception.detail))

    def test_schema_has_chinese_table_and_column_comments(self):
        schema = (Path(__file__).resolve().parents[1] / "pipeline_schema.sql").read_text(encoding="utf-8")
        tables = table_descriptions(schema)
        columns = column_definitions(schema)
        self.assertEqual(set(tables), {"godp_planning_pipeline_run", "godp_planning_stage_run"})
        self.assertTrue(all(columns[table] for table in tables))


if __name__ == "__main__":
    unittest.main()
