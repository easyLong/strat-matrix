"""Pipeline control-plane tests for the result-commit handoff."""

import unittest
from unittest.mock import patch

from app import planning_pipeline_runner as runner
from app.planning_result_commit import ResultCommitError


def waiting_result(status="waiting", version=7):
    return {
        "pipeline_id": 501,
        "version": version,
        "status": status,
        "production_batch_id": None,
        "active_stages": ["result_commit"],
        "stages": [
            {"stage_key": "single_account_matching", "status": "succeeded"},
            {"stage_key": "matrix_allocation", "status": "succeeded"},
            {"stage_key": "composition", "status": "succeeded"},
            {"stage_key": "result_commit", "status": status},
        ],
    }


class PlanningPipelineRunnerTests(unittest.TestCase):
    def test_advance_commits_evaluated_pipeline_in_same_control_call(self):
        pending = waiting_result()
        succeeded = {**pending, "version": 8, "status": "succeeded",
                     "production_batch_id": 9001, "active_stages": []}
        with patch.object(runner, "advance_pipeline", return_value=pending) as advance, \
             patch.object(runner, "commit_pipeline_result", return_value={"batch_id": 9001}) as commit, \
             patch.object(runner, "read_pipeline", return_value=succeeded):
            result = runner.advance_pipeline_to_commit(501, 6)
        advance.assert_called_once_with(501, 6)
        commit.assert_called_once_with(501, 7)
        self.assertEqual(result["production_batch_id"], 9001)
        self.assertEqual(result["status"], "succeeded")

    def test_result_commit_retry_reopens_stage_without_rerunning_matching_task(self):
        failed = waiting_result(status="failed", version=9)
        reopened = waiting_result(status="waiting", version=10)
        succeeded = {**reopened, "version": 11, "status": "succeeded",
                     "production_batch_id": 9002, "active_stages": []}
        with patch.object(runner, "read_pipeline", side_effect=[failed, succeeded]), \
             patch.object(runner, "advance_pipeline", return_value=reopened) as advance, \
             patch.object(runner, "retry_pipeline") as base_retry, \
             patch.object(runner, "commit_pipeline_result", return_value={"batch_id": 9002}) as commit:
            result = runner.retry_pipeline_to_commit(501, 9)
        advance.assert_called_once_with(501, 9, retry=True)
        base_retry.assert_not_called()
        commit.assert_called_once_with(501, 10)
        self.assertEqual(result["production_batch_id"], 9002)

    def test_business_commit_failure_is_persisted_as_retryable_stage_failure(self):
        pending = waiting_result()
        failed = {**pending, "version": 8, "status": "failed"}
        error = ResultCommitError("marketing_snapshot_unavailable", "营销快照暂不可用")
        with patch.object(runner, "advance_pipeline", return_value=pending), \
             patch.object(runner, "commit_pipeline_result", side_effect=error), \
             patch.object(runner, "_record_commit_failure", return_value=failed) as record:
            result = runner.advance_pipeline_to_commit(501, 6)
        record.assert_called_once_with(501, 7, error)
        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
