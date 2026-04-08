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


def test_validate_writes_scorecard_json(tmp_path):
    """'lmv validate --adf-json ... --output ...' writes a valid JSON scorecard."""
    snapshot = make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()])
    payload_path = tmp_path / "input.json"
    output_path = tmp_path / "scorecard.json"
    payload_path.write_text(json.dumps(snapshot_to_dict(snapshot)), encoding="utf-8")

    configure_cli()
    result = runner.invoke(app, ["validate", "--adf-json", str(payload_path), "--output", str(output_path)])

    assert result.exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "score" in payload
    assert "dimensions" in payload


def test_batch_prints_report(tmp_path):
    """'lmv batch --golden-set ...' prints aggregate scores."""
    suite = GroundTruthSuite.generate(count=4, difficulty="simple")
    golden_set_path = tmp_path / "suite.json"
    suite.to_json(str(golden_set_path))

    by_name = {p.adf_json["name"]: p.expected_snapshot for p in suite.pipelines}

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        return by_name[adf_json["name"]]

    configure_cli(convert_fn=convert_fn)
    result = runner.invoke(app, ["batch", "--golden-set", str(golden_set_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["total"] == 4
    assert payload["below_threshold"] == 0


def test_regression_check_exits_0_on_pass(tmp_path):
    suite = GroundTruthSuite.generate(count=3, difficulty="simple")
    golden_set_path = tmp_path / "suite.json"
    suite.to_json(str(golden_set_path))
    by_name = {p.adf_json["name"]: p.expected_snapshot for p in suite.pipelines}
    configure_cli(convert_fn=lambda adf: by_name[adf["name"]])
    result = runner.invoke(app, ["regression-check", "--golden-set", str(golden_set_path), "--threshold", "90"])
    assert result.exit_code == 0


def test_regression_check_exits_1_on_regression(tmp_path):
    suite = GroundTruthSuite.generate(count=3, difficulty="simple")
    golden_set_path = tmp_path / "suite.json"
    suite.to_json(str(golden_set_path))
    configure_cli(
        convert_fn=lambda _: make_snapshot(tasks=[make_task("x", is_placeholder=True)], notebooks=[make_notebook()])
    )
    result = runner.invoke(app, ["regression-check", "--golden-set", str(golden_set_path), "--threshold", "90"])
    assert result.exit_code == 1


def test_harness_command_not_configured_exits_2():
    configure_cli(harness_runner=None)
    result = runner.invoke(app, ["harness", "--pipeline-name", "pipe_a"])
    assert result.exit_code == 2
    assert "harness runner not configured" in result.stdout


def test_harness_command_returns_result():
    class _Runner:
        def run(self, pipeline_name: str) -> HarnessResult:
            snapshot = make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()])
            return HarnessResult(
                pipeline_name=pipeline_name,
                scorecard=evaluate(snapshot),
                snapshot=snapshot,
                fix_suggestions=({"dimension": "activity_coverage", "suggestion": "replace placeholder"},),
                iterations=2,
            )

    configure_cli(harness_runner=_Runner())
    result = runner.invoke(app, ["harness", "--pipeline-name", "pipe_a"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["pipeline_name"] == "pipe_a"
    assert payload["iterations"] == 2


def test_synthetic_command_generates_pipelines(tmp_path):
    output_dir = tmp_path / "synthetic_out"
    configure_cli()
    result = runner.invoke(app, ["synthetic", "--count", "3", "--output", str(output_dir)])
    assert result.exit_code == 0
    assert (output_dir / "suite.json").exists()
    suite = GroundTruthSuite.from_json(str(output_dir / "suite.json"))
    assert len(suite.pipelines) == 3
    # Check per-pipeline subfolders created
    subdirs = [d for d in output_dir.iterdir() if d.is_dir()]
    assert len(subdirs) == 3


def test_validate_folder_command(tmp_path):
    """'lmv validate-folder --folder ...' validates all JSON files."""
    for i in range(2):
        p = tmp_path / f"pipe_{i}.json"
        p.write_text(
            json.dumps(
                {
                    "name": f"pipe_{i}",
                    "properties": {
                        "activities": [
                            {"name": "nb", "type": "DatabricksNotebook", "depends_on": [], "notebook_path": "/test"}
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
    configure_cli()
    result = runner.invoke(app, ["validate-folder", "--folder", str(tmp_path)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["total"] == 2


def test_status_command():
    configure_cli()
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert "wkmigrate" in payload
    assert "judge" in payload


def test_parallel_test_command_not_configured_exits_2():
    configure_cli(parallel_runner=None)
    result = runner.invoke(app, ["parallel-test", "--pipeline-name", "pipe_a"])
    assert result.exit_code == 2
    assert "parallel runner not configured" in result.stdout


def test_parallel_test_command_returns_result():
    class _Runner:
        def run(self, pipeline_name: str, parameters=None, *, snapshot=None):
            scorecard = evaluate(make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()]))
            return ParallelTestResult(
                pipeline_name=pipeline_name,
                adf_outputs={"a": "1"},
                databricks_outputs={"a": "1"},
                comparisons=(
                    ComparisonResult(activity_name="a", adf_output="1", databricks_output="1", match=True, diff=None),
                ),
                equivalence_score=1.0,
                scorecard=scorecard,
            )

    configure_cli(parallel_runner=_Runner())
    result = runner.invoke(app, ["parallel-test", "--pipeline-name", "pipe_a"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip())
    assert payload["equivalence_score"] == 1.0
