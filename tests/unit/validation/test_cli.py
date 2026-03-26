"""Unit tests for the Typer CLI surface."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from lakeflow_migration_validator.cli import app, configure_cli
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.harness.harness_runner import HarnessResult
from lakeflow_migration_validator.parallel.comparator import ComparisonResult
from lakeflow_migration_validator.parallel.parallel_test_runner import ParallelTestResult
from lakeflow_migration_validator.serialization import snapshot_to_dict
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite
from lakeflow_migration_validator import evaluate
from tests.unit.validation.conftest import make_notebook, make_snapshot, make_task

runner = CliRunner()


def test_evaluate_writes_scorecard_json(tmp_path):
    """'lmv evaluate --adf-json ... --output ...' writes a valid JSON scorecard."""
    snapshot = make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()])
    payload_path = tmp_path / "input.json"
    output_path = tmp_path / "scorecard.json"
    payload_path.write_text(json.dumps(snapshot_to_dict(snapshot)), encoding="utf-8")

    configure_cli()
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--adf-json",
            str(payload_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "score" in payload
    assert "dimensions" in payload


def test_evaluate_batch_prints_report(tmp_path):
    """'lmv evaluate-batch --golden-set ...' prints aggregate scores."""
    suite = GroundTruthSuite.generate(count=4, difficulty="simple")
    golden_set_path = tmp_path / "suite.json"
    suite.to_json(str(golden_set_path))

    by_name = {
        pipeline.adf_json["name"]: pipeline.expected_snapshot
        for pipeline in suite.pipelines
    }

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        return by_name[adf_json["name"]]

    configure_cli(convert_fn=convert_fn)
    result = runner.invoke(app, ["evaluate-batch", "--golden-set", str(golden_set_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["total"] == 4
    assert payload["below_threshold"] == 0


def test_regression_check_exits_0_on_pass(tmp_path):
    """'lmv regression-check' exits 0 when no regression detected."""
    suite = GroundTruthSuite.generate(count=3, difficulty="simple")
    golden_set_path = tmp_path / "suite.json"
    suite.to_json(str(golden_set_path))

    by_name = {
        pipeline.adf_json["name"]: pipeline.expected_snapshot
        for pipeline in suite.pipelines
    }

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        return by_name[adf_json["name"]]

    configure_cli(convert_fn=convert_fn)
    result = runner.invoke(
        app,
        ["regression-check", "--golden-set", str(golden_set_path), "--threshold", "90"],
    )

    assert result.exit_code == 0


def test_regression_check_exits_1_on_regression(tmp_path):
    """'lmv regression-check' exits 1 when regression detected."""
    suite = GroundTruthSuite.generate(count=3, difficulty="simple")
    golden_set_path = tmp_path / "suite.json"
    suite.to_json(str(golden_set_path))

    def convert_fn(_adf_json: dict) -> ConversionSnapshot:
        return make_snapshot(tasks=[make_task("missing", is_placeholder=True)], notebooks=[make_notebook()])

    configure_cli(convert_fn=convert_fn)
    result = runner.invoke(
        app,
        ["regression-check", "--golden-set", str(golden_set_path), "--threshold", "90"],
    )

    assert result.exit_code == 1


def test_harness_command_not_configured_exits_2():
    """'lmv harness' exits 2 with a deterministic error when no runner is configured."""
    configure_cli(harness_runner=None)
    result = runner.invoke(app, ["harness", "--pipeline-name", "pipe_a"])

    assert result.exit_code == 2
    assert json.loads(result.stdout.strip()) == {"error": "harness runner is not configured"}


def test_harness_command_returns_result():
    """'lmv harness' prints a valid JSON result payload when a runner is configured."""

    class _Runner:
        def run(self, pipeline_name: str) -> HarnessResult:
            snapshot = make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()])
            scorecard = evaluate(snapshot)
            return HarnessResult(
                pipeline_name=pipeline_name,
                scorecard=scorecard,
                snapshot=snapshot,
                fix_suggestions=({"dimension": "activity_coverage", "suggestion": "replace placeholder"},),
                iterations=2,
            )

    configure_cli(harness_runner=_Runner())
    result = runner.invoke(app, ["harness", "--pipeline-name", "pipe_a"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["pipeline_name"] == "pipe_a"
    assert "scorecard" in payload
    assert payload["iterations"] == 2
    assert payload["fix_suggestions"]


def test_synthetic_command_generates_pipelines(tmp_path):
    """'lmv synthetic --count N --output ...' writes a suite with N pipelines."""
    output_path = tmp_path / "synthetic.json"
    configure_cli()

    result = runner.invoke(
        app,
        ["synthetic", "--count", "3", "--output", str(output_path)],
    )

    assert result.exit_code == 0
    assert output_path.exists()
    suite = GroundTruthSuite.from_json(str(output_path))
    assert len(suite.pipelines) == 3


def test_parallel_test_command_not_configured_exits_2():
    configure_cli(parallel_runner=None)

    result = runner.invoke(app, ["parallel-test", "--pipeline-name", "pipe_a"])

    assert result.exit_code == 2
    assert json.loads(result.stdout.strip()) == {"error": "parallel runner is not configured"}


def test_parallel_test_command_returns_result():
    class _Runner:
        def run(self, pipeline_name: str, parameters: dict[str, str] | None = None, *, snapshot=None):
            scorecard = evaluate(make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()]))
            return ParallelTestResult(
                pipeline_name=pipeline_name,
                adf_outputs={"a": "1"},
                databricks_outputs={"a": "1"},
                comparisons=(
                    ComparisonResult(
                        activity_name="a",
                        adf_output="1",
                        databricks_output="1",
                        match=True,
                        diff=None,
                    ),
                ),
                equivalence_score=1.0,
                scorecard=scorecard,
            )

    configure_cli(parallel_runner=_Runner())
    result = runner.invoke(app, ["parallel-test", "--pipeline-name", "pipe_a"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["pipeline_name"] == "pipe_a"
    assert payload["equivalence_score"] == 1.0
    assert payload["comparisons"][0]["match"] is True
