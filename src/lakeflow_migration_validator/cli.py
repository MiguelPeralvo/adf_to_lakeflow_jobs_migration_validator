"""Typer CLI surface for validation workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import typer

from lakeflow_migration_validator import evaluate, evaluate_batch
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.serialization import snapshot_from_adf_payload
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite

app = typer.Typer(no_args_is_help=True, help="Lakeflow Migration Validator CLI")

_CONVERT_FN: Callable[[dict], ConversionSnapshot] = snapshot_from_adf_payload
_HARNESS_RUNNER = None


def configure_cli(
    *,
    convert_fn: Callable[[dict], ConversionSnapshot] | None = None,
    harness_runner=None,
) -> None:
    """Inject runtime dependencies for commands (primarily in tests)."""
    global _CONVERT_FN, _HARNESS_RUNNER
    _CONVERT_FN = convert_fn or snapshot_from_adf_payload
    _HARNESS_RUNNER = harness_runner


@app.command("evaluate")
def evaluate_command(
    adf_json: Path = typer.Option(..., "--adf-json", exists=True, readable=True),
    output: Path = typer.Option(..., "--output"),
) -> None:
    """Score one pipeline payload and write a JSON scorecard file."""
    payload = _read_json(adf_json)
    snapshot = _CONVERT_FN(payload)
    scorecard = evaluate(snapshot)
    rendered = json.dumps(scorecard.to_dict(), sort_keys=True, indent=2)
    output.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(rendered)


@app.command("evaluate-batch")
def evaluate_batch_command(
    golden_set: Path = typer.Option(..., "--golden-set", exists=True, readable=True),
    threshold: float = typer.Option(90.0, "--threshold"),
) -> None:
    """Evaluate a converter against a synthetic ground-truth suite."""
    suite = GroundTruthSuite.from_json(str(golden_set))
    report = evaluate_batch(suite, _CONVERT_FN, threshold=threshold)
    typer.echo(json.dumps(report.to_dict(), sort_keys=True))


@app.command("harness")
def harness_command(
    pipeline_name: str = typer.Option(..., "--pipeline-name"),
) -> None:
    """Run harness orchestration for one pipeline."""
    if _HARNESS_RUNNER is None:
        typer.echo(json.dumps({"error": "harness runner is not configured"}, sort_keys=True))
        raise typer.Exit(code=2)

    result = _HARNESS_RUNNER.run(pipeline_name)
    typer.echo(
        json.dumps(
            {
                "pipeline_name": result.pipeline_name,
                "scorecard": result.scorecard.to_dict(),
                "iterations": result.iterations,
                "fix_suggestions": list(result.fix_suggestions),
            },
            sort_keys=True,
        )
    )


@app.command("synthetic")
def synthetic_command(
    count: int = typer.Option(10, "--count"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """Generate synthetic pipelines and optionally write them to disk."""
    suite = GroundTruthSuite.generate(count=count)
    if output is not None:
        suite.to_json(str(output))
    typer.echo(
        json.dumps(
            {
                "count": len(suite.pipelines),
                "output": str(output) if output else None,
            },
            sort_keys=True,
        )
    )


@app.command("regression-check")
def regression_check_command(
    golden_set: Path = typer.Option(..., "--golden-set", exists=True, readable=True),
    threshold: float = typer.Option(90.0, "--threshold"),
) -> None:
    """Exit 0 when mean score meets threshold, else exit 1."""
    suite = GroundTruthSuite.from_json(str(golden_set))
    report = evaluate_batch(suite, _CONVERT_FN, threshold=threshold)
    rendered = json.dumps(report.to_dict(), sort_keys=True)
    typer.echo(rendered)
    if report.mean_score >= threshold:
        raise typer.Exit(code=0)
    raise typer.Exit(code=1)


def _read_json(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise typer.BadParameter("adf-json must contain a JSON object")
    return payload
