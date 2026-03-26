"""Unit tests for ParallelTestRunner orchestration."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.parallel.adf_runner import ADFExecutionRunner
from lakeflow_migration_validator.parallel.comparator import OutputComparator
from lakeflow_migration_validator.parallel.parallel_test_runner import ParallelTestRunner
from tests.unit.validation.conftest import make_notebook, make_snapshot, make_task


class _DatabricksRunner:
    def __init__(self, outputs: dict[str, str], fail: bool = False):
        self.outputs = outputs
        self.fail = fail

    def run(self, pipeline_name: str, parameters: dict[str, str] | None = None) -> dict[str, str]:
        if self.fail:
            raise RuntimeError("db run failed")
        assert pipeline_name
        assert isinstance(parameters, dict)
        return dict(self.outputs)


def _make_adf_runner(outputs: dict[str, str]) -> ADFExecutionRunner:
    return ADFExecutionRunner(
        trigger_run_fn=lambda _pipeline_name, _params: "run-1",
        get_run_status_fn=lambda _run_id: "SUCCEEDED",
        get_activity_outputs_fn=lambda _run_id: dict(outputs),
    )


def test_parallel_test_runner_happy_path_without_snapshot():
    runner = ParallelTestRunner(
        adf_runner=_make_adf_runner({"a": "1", "b": "2"}),
        databricks_runner=_DatabricksRunner({"a": "1", "b": "2"}),
    )

    result = runner.run("pipe_a", parameters={"p": "x"})

    assert result.pipeline_name == "pipe_a"
    assert result.equivalence_score == 1.0
    assert len(result.comparisons) == 2
    assert result.scorecard.results["parallel_equivalence"].score == 1.0
    assert result.scorecard.score == 100.0


def test_parallel_test_runner_includes_parallel_dimension_alongside_base_scorecard_when_snapshot_provided():
    snapshot = make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()])
    runner = ParallelTestRunner(
        adf_runner=_make_adf_runner({"a": "1"}),
        databricks_runner=_DatabricksRunner({"a": "1"}),
    )

    result = runner.run("pipe_a", snapshot=snapshot)

    assert "activity_coverage" in result.scorecard.results
    assert "parallel_equivalence" in result.scorecard.results
    assert result.scorecard.results["parallel_equivalence"].details["comparator_score"] == 1.0


def test_parallel_test_runner_reports_partial_mismatch_score():
    runner = ParallelTestRunner(
        adf_runner=_make_adf_runner({"a": "1", "b": "9"}),
        databricks_runner=_DatabricksRunner({"a": "1", "b": "2"}),
    )

    result = runner.run("pipe_a")

    assert result.equivalence_score == 0.5
    assert result.scorecard.results["parallel_equivalence"].score == 0.5


def test_parallel_test_runner_uses_comparator_tolerance_for_parallel_dimension():
    runner = ParallelTestRunner(
        adf_runner=_make_adf_runner({"a": "1.005"}),
        databricks_runner=_DatabricksRunner({"a": "1.0"}),
        comparator=OutputComparator(float_tolerance=0.01),
    )

    result = runner.run("pipe_a")

    assert result.equivalence_score == 1.0
    assert result.scorecard.results["parallel_equivalence"].score == 1.0


def test_parallel_test_runner_propagates_databricks_runner_errors():
    runner = ParallelTestRunner(
        adf_runner=_make_adf_runner({"a": "1"}),
        databricks_runner=_DatabricksRunner({"a": "1"}, fail=True),
    )

    with pytest.raises(RuntimeError, match="db run failed"):
        runner.run("pipe_a")
