"""Unit tests for DatabricksJobRunner normalization behavior."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.providers.databricks_runner import DatabricksJobRunner


def test_databricks_runner_passes_through_normalized_results():
    def run_job_and_wait(_output, _params):
        return {
            "task_a": {"success": True, "error": None},
            "task_b": {"success": False, "error": "failed"},
        }

    runner = DatabricksJobRunner(run_job_and_wait=run_job_and_wait)
    results = runner.run(output={"prepared": True}, params={"env": "dev"})

    assert results["task_a"]["success"] is True
    assert results["task_b"]["error"] == "failed"


def test_databricks_runner_normalizes_databricks_task_shape():
    def run_job_and_wait(_output, _params):
        return {
            "tasks": [
                {"task_key": "first", "state": {"result_state": "SUCCESS"}},
                {
                    "task_key": "second",
                    "state": {"result_state": "FAILED", "state_message": "Notebook error"},
                },
            ]
        }

    runner = DatabricksJobRunner(run_job_and_wait=run_job_and_wait)
    results = runner.run(output={"prepared": True}, params={})

    assert results == {
        "first": {"success": True, "error": None},
        "second": {"success": False, "error": "Notebook error"},
    }


def test_databricks_runner_raises_when_payload_is_not_dict():
    def run_job_and_wait(_output, _params):
        return ["bad"]

    runner = DatabricksJobRunner(run_job_and_wait=run_job_and_wait)

    with pytest.raises(ValueError, match="must be a dict"):
        runner.run(output={"prepared": True}, params={})


def test_databricks_runner_propagates_callable_errors():
    def run_job_and_wait(_output, _params):
        raise RuntimeError("job submission failed")

    runner = DatabricksJobRunner(run_job_and_wait=run_job_and_wait)

    with pytest.raises(RuntimeError, match="job submission failed"):
        runner.run(output={"prepared": True}, params={})
