"""Typer CLI surface for validation workflows.

Entry point registered as ``lmv`` in pyproject.toml.

Mirrors the REST API capabilities:
  lmv validate       — score one ADF pipeline JSON
  lmv validate-folder — batch validate a folder of ADF JSONs
  lmv synthetic       — generate synthetic test pipelines
  lmv batch           — evaluate against a golden set
  lmv regression-check — CI gate (exit 1 if below threshold)
  lmv harness         — end-to-end harness with fix loop
  lmv parallel-test   — ADF vs Databricks parallel run
  lmv adf-download    — download pipelines from Azure Data Factory
  lmv adf-upload      — upload local pipelines to Azure Data Factory
  lmv status          — show available capabilities
  lmv history         — show activity log
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import typer

from lakeflow_migration_validator import evaluate, evaluate_batch
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.serialization import snapshot_from_adf_payload
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite

app = typer.Typer(no_args_is_help=True, help="Lakeflow Migration Validator — CLI interface")

_CONVERT_FN: Callable[[dict], ConversionSnapshot] = snapshot_from_adf_payload
_JUDGE_PROVIDER: Any = None
_HARNESS_RUNNER: Any = None
_PARALLEL_RUNNER: Any = None


def configure_cli(
    *,
    convert_fn: Callable[[dict], ConversionSnapshot] | None = None,
    judge_provider: Any = None,
    harness_runner: Any = None,
    parallel_runner: Any = None,
) -> None:
    """Inject runtime dependencies for commands (primarily in tests)."""
    global _CONVERT_FN, _JUDGE_PROVIDER, _HARNESS_RUNNER, _PARALLEL_RUNNER
    _CONVERT_FN = convert_fn or snapshot_from_adf_payload
    _JUDGE_PROVIDER = judge_provider
    _HARNESS_RUNNER = harness_runner
    _PARALLEL_RUNNER = parallel_runner


def _auto_configure() -> None:
    """Auto-configure from environment if not already set."""
    global _CONVERT_FN, _JUDGE_PROVIDER
    if _CONVERT_FN is not snapshot_from_adf_payload:
        return  # already configured
    # Try to build wkmigrate converter
    try:
        from wkmigrate.translators.pipeline_translators.pipeline_translator import translate_pipeline
        from wkmigrate.preparers.preparer import prepare_workflow
        from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate
        from lakeflow_migration_validator.serialization import snapshot_from_dict

        def convert(payload: dict) -> ConversionSnapshot:
            if "tasks" in payload and "notebooks" in payload:
                return snapshot_from_dict(payload)
            pipeline_ir = translate_pipeline(payload)
            prepared = prepare_workflow(pipeline_ir)
            return from_wkmigrate(payload, prepared)

        _CONVERT_FN = convert
    except ImportError:
        pass
    # Try to build FMAPI judge
    host = os.environ.get("DATABRICKS_HOST")
    if host and _JUDGE_PROVIDER is None:
        try:
            from lakeflow_migration_validator.providers.fmapi import FMAPIJudgeProvider

            token = os.environ.get("DATABRICKS_TOKEN")
            _JUDGE_PROVIDER = FMAPIJudgeProvider(
                endpoint=f"{host.rstrip('/')}/serving-endpoints",
                token=token,
                timeout_seconds=60,
            )
        except Exception:
            pass


def _emit(data: Any) -> None:
    """Print JSON to stdout."""
    typer.echo(json.dumps(data, sort_keys=True, indent=2, default=str))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("validate")
def validate_command(
    adf_json: Path = typer.Option(..., "--adf-json", exists=True, readable=True, help="ADF pipeline JSON file"),
    output: Path | None = typer.Option(None, "--output", help="Write scorecard to this file"),
) -> None:
    """Validate one ADF pipeline through wkmigrate and score it."""
    _auto_configure()
    payload = _read_json(adf_json)
    snapshot = _CONVERT_FN(payload)
    scorecard = evaluate(snapshot)
    result = scorecard.to_dict()
    _emit(result)
    if output:
        output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"\nScorecard written to {output}", err=True)


@app.command("validate-folder")
def validate_folder_command(
    folder: Path = typer.Option(
        ..., "--folder", exists=True, file_okay=False, help="Folder containing ADF pipeline JSONs"
    ),
    threshold: float = typer.Option(90.0, "--threshold", help="CCS threshold for pass/fail"),
    glob_pattern: str = typer.Option("*.json", "--glob", help="Glob pattern for pipeline files"),
) -> None:
    """Batch validate all ADF pipeline JSONs in a folder."""
    _auto_configure()
    # Discover files (same logic as API)
    subfolder_files = sorted(folder.glob("*/adf_pipeline.json"))
    if subfolder_files:
        files = subfolder_files
    else:
        files = sorted(f for f in folder.glob(glob_pattern) if f.is_file() and f.name != "suite.json")
    if not files:
        typer.echo(f"No pipeline files found in {folder}", err=True)
        raise typer.Exit(code=1)

    cases = []
    scores = []
    below = 0
    for i, file_path in enumerate(files):
        with open(file_path, encoding="utf-8") as f:
            adf_json = json.load(f)
        name = adf_json.get("name", file_path.stem)
        try:
            snapshot = _CONVERT_FN(adf_json)
            scorecard = evaluate(snapshot)
            score = scorecard.score
            label = scorecard.label
        except Exception as exc:
            score = 0.0
            label = "ERROR"
            typer.echo(f"  [{i+1}/{len(files)}] {name}: ERROR — {exc}", err=True)
            cases.append({"pipeline_name": name, "score": score, "label": label})
            scores.append(score)
            if score < threshold:
                below += 1
            continue

        is_below = score < threshold
        if is_below:
            below += 1
        scores.append(score)
        marker = "PASS" if not is_below else "FAIL"
        typer.echo(f"  [{i+1}/{len(files)}] {name}: {score:.0f}% {marker}", err=True)
        cases.append({"pipeline_name": name, "score": score, "label": label, "below_threshold": is_below})

    mean = sum(scores) / len(scores) if scores else 0.0
    _emit(
        {
            "total": len(cases),
            "threshold": threshold,
            "mean_score": round(mean, 1),
            "min_score": round(min(scores), 1) if scores else 0.0,
            "max_score": round(max(scores), 1) if scores else 0.0,
            "below_threshold": below,
            "cases": cases,
        }
    )


@app.command("synthetic")
def synthetic_command(
    count: int = typer.Option(10, "--count", help="Number of pipelines to generate"),
    difficulty: str = typer.Option("medium", "--difficulty", help="simple, medium, or complex"),
    mode: str = typer.Option("template", "--mode", help="template, llm, or custom"),
    preset: str | None = typer.Option(None, "--preset", help="Template preset key"),
    prompt: str | None = typer.Option(None, "--prompt", help="Custom generation prompt"),
    output: Path | None = typer.Option(None, "--output", help="Output directory"),
    test_data: bool = typer.Option(False, "--test-data", help="Also generate test data"),
) -> None:
    """Generate synthetic ADF test pipelines."""
    _auto_configure()
    import tempfile
    from datetime import datetime, timezone

    if mode in ("llm", "custom") and _JUDGE_PROVIDER is not None:
        from lakeflow_migration_validator.synthetic.agent_generator import (
            AgentPipelineGenerator,
            GenerationConfig,
        )

        weak_spots = ("nested_expressions",)
        if preset:
            _PRESET_MAP = {
                "complex_expressions": ("nested_expressions", "math_on_params"),
                "deep_nesting": ("deep_nesting", "complex_conditions"),
                "pipeline_invocation": ("activity_output_chaining", "deep_nesting"),
            }
            weak_spots = _PRESET_MAP.get(preset, ("nested_expressions",))
        config = GenerationConfig(target_weak_spots=weak_spots, extra_instructions=prompt or "")
        agent = AgentPipelineGenerator(judge_provider=_JUDGE_PROVIDER)
        pipelines = []
        for ev in agent.generate_stream(count=count, config=config):
            if ev["type"] == "plan":
                typer.echo(f"Plan: {ev['plan'].count} pipelines", err=True)
            elif ev["type"] == "stage":
                if ev["stage"] in ("generating", "complete", "failed"):
                    typer.echo(f"  [{ev['pipeline_index']+1}] {ev['pipeline_name']}: {ev['stage']}", err=True)
            elif ev["type"] == "pipeline":
                if ev.get("pipeline"):
                    pipelines.append(ev["pipeline"])
        suite = GroundTruthSuite(pipelines=tuple(pipelines)) if pipelines else GroundTruthSuite.generate(count=count)
    else:
        suite = GroundTruthSuite.generate(count=count, difficulty=difficulty, mode="template")

    # Persist
    if output:
        out_dir = output
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        out_dir = Path(tempfile.gettempdir()) / "lmv_synthetic" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    suite.to_json(str(out_dir / "suite.json"))
    for i, p in enumerate(suite.pipelines):
        name = p.adf_json.get("name", f"pipeline_{i:03d}")
        safe = f"{i:03d}_{name.replace('/', '_').replace(' ', '_')[:60]}"
        pipe_dir = out_dir / safe
        pipe_dir.mkdir(parents=True, exist_ok=True)
        with open(pipe_dir / "adf_pipeline.json", "w", encoding="utf-8") as fh:
            json.dump(p.adf_json, fh, indent=2)

    typer.echo(f"\n{len(suite.pipelines)} pipelines generated → {out_dir}", err=True)
    _emit({"count": len(suite.pipelines), "output_path": str(out_dir)})


@app.command("batch")
def batch_command(
    golden_set: Path = typer.Option(..., "--golden-set", exists=True, readable=True, help="Golden set JSON file"),
    threshold: float = typer.Option(90.0, "--threshold"),
) -> None:
    """Evaluate a converter against a golden-set suite."""
    _auto_configure()
    suite = GroundTruthSuite.from_json(str(golden_set))
    report = evaluate_batch(suite, _CONVERT_FN, threshold=threshold)
    _emit(report.to_dict())


@app.command("regression-check")
def regression_check_command(
    golden_set: Path = typer.Option(..., "--golden-set", exists=True, readable=True),
    threshold: float = typer.Option(90.0, "--threshold"),
) -> None:
    """CI gate — exit 0 if mean score meets threshold, else exit 1."""
    _auto_configure()
    suite = GroundTruthSuite.from_json(str(golden_set))
    report = evaluate_batch(suite, _CONVERT_FN, threshold=threshold)
    _emit(report.to_dict())
    if report.mean_score >= threshold:
        raise typer.Exit(code=0)
    raise typer.Exit(code=1)


@app.command("harness")
def harness_command(
    pipeline_name: str = typer.Option(..., "--pipeline-name"),
) -> None:
    """Run end-to-end harness orchestration for one pipeline."""
    _auto_configure()
    if _HARNESS_RUNNER is None:
        typer.echo(json.dumps({"error": "harness runner not configured — set AZURE_* env vars"}))
        raise typer.Exit(code=2)
    result = _HARNESS_RUNNER.run(pipeline_name)
    _emit(
        {
            "pipeline_name": result.pipeline_name,
            "scorecard": result.scorecard.to_dict(),
            "iterations": result.iterations,
            "fix_suggestions": list(result.fix_suggestions),
        }
    )


@app.command("parallel-test")
def parallel_test_command(
    pipeline_name: str = typer.Option(..., "--pipeline-name"),
    parameters_json: Path | None = typer.Option(None, "--parameters-json", exists=True, readable=True),
    snapshot_json: Path | None = typer.Option(None, "--snapshot-json", exists=True, readable=True),
) -> None:
    """Run ADF-vs-Databricks parallel output comparison."""
    _auto_configure()
    if _PARALLEL_RUNNER is None:
        typer.echo(json.dumps({"error": "parallel runner not configured"}))
        raise typer.Exit(code=2)
    parameters = _read_json(parameters_json) if parameters_json else {}
    snapshot = _CONVERT_FN(_read_json(snapshot_json)) if snapshot_json else None
    result = _PARALLEL_RUNNER.run(pipeline_name, parameters=parameters, snapshot=snapshot)
    _emit(result.to_dict())


@app.command("adf-download")
def adf_download_command(
    factory_name: str = typer.Option(..., "--factory-name", help="Azure Data Factory name"),
    tenant_id: str = typer.Option(None, "--tenant-id", envvar="AZURE_TENANT_ID"),
    client_id: str = typer.Option(None, "--client-id", envvar="AZURE_CLIENT_ID"),
    client_secret: str = typer.Option(None, "--client-secret", envvar="AZURE_CLIENT_SECRET"),
    subscription_id: str = typer.Option(None, "--subscription-id", envvar="AZURE_SUBSCRIPTION_ID"),
    resource_group: str = typer.Option(None, "--resource-group", envvar="AZURE_RESOURCE_GROUP"),
    output: Path | None = typer.Option(None, "--output", help="Output directory"),
    pipeline_names: str | None = typer.Option(
        None, "--pipelines", help="Comma-separated pipeline names (default: all)"
    ),
) -> None:
    """Download ADF pipelines from Azure Data Factory to a local folder."""
    import tempfile
    from datetime import datetime, timezone

    missing = [
        k
        for k, v in {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "subscription_id": subscription_id,
            "resource_group": resource_group,
        }.items()
        if not v
    ]
    if missing:
        typer.echo(f"Missing credentials: {', '.join(missing)}. Set via --flags or AZURE_* env vars.", err=True)
        raise typer.Exit(code=2)

    from wkmigrate.clients.factory_client import FactoryClient

    client = FactoryClient(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        subscription_id=subscription_id,
        resource_group_name=resource_group,
        factory_name=factory_name,
    )

    names = pipeline_names.split(",") if pipeline_names else client.list_pipelines()
    typer.echo(f"Found {len(names)} pipelines in {factory_name}", err=True)

    if output:
        out_dir = output
    else:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = Path(tempfile.gettempdir()) / "lmv_adf_download" / f"{factory_name}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for i, name in enumerate(names):
        try:
            pipeline_json = client.get_pipeline(name)
            pipeline_json["name"] = name
            safe = name.replace("/", "_").replace(" ", "_")[:60]
            pipe_dir = out_dir / safe
            pipe_dir.mkdir(parents=True, exist_ok=True)
            with open(pipe_dir / "adf_pipeline.json", "w", encoding="utf-8") as fh:
                json.dump(pipeline_json, fh, indent=2)
            downloaded.append(name)
            typer.echo(f"  [{i+1}/{len(names)}] {name} ✓", err=True)
        except Exception as exc:
            typer.echo(f"  [{i+1}/{len(names)}] {name} ✗ {exc}", err=True)

    typer.echo(f"\n{len(downloaded)}/{len(names)} downloaded → {out_dir}", err=True)
    _emit({"folder": str(out_dir), "downloaded": len(downloaded), "total": len(names), "pipelines": downloaded})


@app.command("adf-upload")
def adf_upload_command(
    folder: Path = typer.Option(..., "--folder", exists=True, file_okay=False, help="Folder with ADF pipeline JSONs"),
    factory_name: str = typer.Option(..., "--factory-name", help="Target Azure Data Factory name"),
    tenant_id: str = typer.Option(None, "--tenant-id", envvar="AZURE_TENANT_ID"),
    client_id: str = typer.Option(None, "--client-id", envvar="AZURE_CLIENT_ID"),
    client_secret: str = typer.Option(None, "--client-secret", envvar="AZURE_CLIENT_SECRET"),
    subscription_id: str = typer.Option(None, "--subscription-id", envvar="AZURE_SUBSCRIPTION_ID"),
    resource_group: str = typer.Option(None, "--resource-group", envvar="AZURE_RESOURCE_GROUP"),
    name_prefix: str = typer.Option("", "--prefix", help="Prefix for uploaded pipeline names"),
) -> None:
    """Upload local ADF pipeline JSONs to an Azure Data Factory."""
    missing = [
        k
        for k, v in {
            "tenant_id": tenant_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "subscription_id": subscription_id,
            "resource_group": resource_group,
        }.items()
        if not v
    ]
    if missing:
        typer.echo(f"Missing credentials: {', '.join(missing)}", err=True)
        raise typer.Exit(code=2)

    from wkmigrate.clients.factory_client import FactoryClient
    from azure.mgmt.datafactory.models import PipelineResource

    client = FactoryClient(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        subscription_id=subscription_id,
        resource_group_name=resource_group,
        factory_name=factory_name,
    )

    subfolder_files = sorted(folder.glob("*/adf_pipeline.json"))
    files = subfolder_files if subfolder_files else sorted(f for f in folder.glob("*.json") if f.name != "suite.json")
    if not files:
        typer.echo(f"No pipeline files found in {folder}", err=True)
        raise typer.Exit(code=1)

    uploaded = []
    for i, file_path in enumerate(files):
        with open(file_path, encoding="utf-8") as fh:
            adf_json = json.load(fh)
        name = name_prefix + adf_json.get("name", file_path.parent.name)
        try:
            props = adf_json.get("properties", adf_json)
            resource = PipelineResource(**props)
            client.management_client.pipelines.create_or_update(
                client.resource_group_name,
                client.factory_name,
                name,
                resource,
            )
            uploaded.append(name)
            typer.echo(f"  [{i+1}/{len(files)}] {name} ✓", err=True)
        except Exception as exc:
            typer.echo(f"  [{i+1}/{len(files)}] {name} ✗ {exc}", err=True)

    typer.echo(f"\n{len(uploaded)}/{len(files)} uploaded to {factory_name}", err=True)
    _emit({"uploaded": len(uploaded), "total": len(files), "pipelines": uploaded})


@app.command("status")
def status_command() -> None:
    """Show which capabilities are available."""
    _auto_configure()
    _emit(
        {
            "wkmigrate": _CONVERT_FN is not snapshot_from_adf_payload,
            "judge": _JUDGE_PROVIDER is not None,
            "harness": _HARNESS_RUNNER is not None,
            "parallel": _PARALLEL_RUNNER is not None,
        }
    )


@app.command("history")
def history_command(
    pipeline_name: str | None = typer.Option(None, "--pipeline", help="Filter by pipeline name"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Show activity history from the SQLite store."""
    _auto_configure()
    from lakeflow_migration_validator.api import HistoryStore

    store = HistoryStore()
    if pipeline_name:
        entries = store.get(pipeline_name)
    else:
        entries = store.get_activity_log(limit)
    _emit(entries)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path, option_name: str = "--adf-json") -> dict:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"{option_name} must contain a JSON object")
    return payload
