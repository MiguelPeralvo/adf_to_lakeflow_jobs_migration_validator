"""Unit tests for ExecutionDimension and runtime success wrapper."""

from __future__ import annotations

from lakeflow_migration_validator.dimensions.execution import ExecutionDimension
from lakeflow_migration_validator.dimensions.runtime_success import create_runtime_success_dimension


class _Runner:
    def __init__(self, payload=None, raise_error: Exception | None = None):
        self.payload = payload
        self.raise_error = raise_error
        self.calls = []

    def run(self, output, params):
        self.calls.append((output, params))
        if self.raise_error is not None:
            raise self.raise_error
        return self.payload


def test_execution_dimension_scores_fraction_of_successful_tasks():
    runner = _Runner(
        {
            "a": {"success": True, "error": None},
            "b": {"success": False, "error": "boom"},
            "c": {"success": True, "error": None},
        }
    )
    dimension = ExecutionDimension(name="runtime_success", runner=runner, test_params={"x": "1"}, threshold=0.6)

    result = dimension.evaluate(None, {"prepared": True})

    assert result.score == 2 / 3
    assert result.passed is True
    assert result.details["task_results"]["b"]["error"] == "boom"
    assert runner.calls[0][1] == {"x": "1"}


def test_execution_dimension_returns_error_when_no_tasks():
    runner = _Runner({})
    dimension = ExecutionDimension(name="runtime_success", runner=runner)

    result = dimension.evaluate(None, {"prepared": True})

    assert result.score == 0.0
    assert result.passed is False
    assert result.details["error"] == "no tasks returned"


def test_execution_dimension_propagates_runner_error_as_failed_result():
    runner = _Runner(raise_error=RuntimeError("cluster unavailable"))
    dimension = ExecutionDimension(name="runtime_success", runner=runner)

    result = dimension.evaluate(None, {"prepared": True})

    assert result.score == 0.0
    assert result.passed is False
    assert "cluster unavailable" in result.details["error"]


def test_create_runtime_success_dimension_sets_defaults():
    runner = _Runner({"task": {"success": True, "error": None}})

    dimension = create_runtime_success_dimension(runner, test_params={"env": "qa"})
    result = dimension.evaluate(None, {"prepared": True})

    assert dimension.name == "runtime_success"
    assert dimension.threshold == 1.0
    assert result.score == 1.0
