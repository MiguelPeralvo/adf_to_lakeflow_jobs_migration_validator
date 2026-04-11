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
    # Try to build wkmigrate converter. The adapter module is importable
    # even when wkmigrate isn't installed (the PreparedWorkflow import is
    # behind TYPE_CHECKING for LA-3 graceful degradation), so an explicit
    # `import wkmigrate` probe is needed here to detect a missing dep —
    # otherwise `_CONVERT_FN` would be set to a `convert` function that
    # explodes at runtime instead of falling back to the passthrough.
    try:
        import wkmigrate  # noqa: F401  # availability probe; see comment above
        from lakeflow_migration_validator.adapters.wkmigrate_adapter import adf_to_snapshot
        from lakeflow_migration_validator.serialization import snapshot_from_dict

        def convert(payload: dict) -> ConversionSnapshot:
            if "tasks" in payload and "notebooks" in payload:
                return snapshot_from_dict(payload)
            return adf_to_snapshot(payload)

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


@app.command("sweep-activity-contexts")
def sweep_activity_contexts_command(
    golden_set: Path = typer.Option(
        ...,
        "--golden-set",
        exists=True,
        readable=True,
        help="Path to a golden set JSON file with an 'expressions' array (e.g. golden_sets/expressions.json)",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        help="Optional output path for the full aggregated JSON (defaults to stdout only)",
    ),
    contexts: str | None = typer.Option(
        None,
        "--contexts",
        help="Comma-separated subset of activity context names. Default: all 7. "
        "Available: set_variable, notebook_base_param, if_condition, for_each, web_body, lookup_query, copy_query",
    ),
) -> None:
    """Run an activity-context sweep across a golden set of expression pairs.

    For each (expression, activity_context) cell, embeds the expression at the
    expression-bearing property of the activity, runs it through wkmigrate via
    ``adf_to_snapshot``, and aggregates per-cell + per-context counts of
    resolved/placeholder/error outcomes.

    The primary target is the deferred wkmigrate#28 Lookup/Copy translator
    adoption gap — those two contexts are expected to have low resolution
    rates on alpha_1 until #28 lands. See L-F5 in
    ``dev/autodev-sessions/LMV-AUTODEV-2026-04-08-session2.md``.
    """
    _auto_configure()
    if _CONVERT_FN is snapshot_from_adf_payload:
        typer.echo(
            "ERROR: wkmigrate not available — sweep requires the real adf_to_snapshot adapter. "
            "Install wkmigrate via 'poetry install --with dev' first.",
            err=True,
        )
        raise typer.Exit(code=2)

    from lakeflow_migration_validator.synthetic.activity_context_wrapper import (
        sweep_activity_contexts,
    )

    # Read the golden set directly via json.loads — we accept BOTH a JSON
    # object with an "expressions" key (the canonical golden_sets/expressions.json
    # shape) AND a bare JSON array of pairs. The shared _read_json helper
    # rejects lists, so it's intentionally not used here.
    raw = golden_set.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if isinstance(payload, dict) and "expressions" in payload:
        corpus = payload["expressions"]
    elif isinstance(payload, list):
        corpus = payload
    else:
        typer.echo(
            "ERROR: --golden-set must be a JSON object with an 'expressions' key OR a JSON array of pairs.",
            err=True,
        )
        raise typer.Exit(code=2)

    if contexts is None:
        selected_contexts: list[str] | None = None
    else:
        # Filter empty entries so `--contexts ""` or `--contexts " , , "`
        # doesn't silently produce a zero-cell sweep.
        selected_contexts = [c.strip() for c in contexts.split(",") if c.strip()]
        if not selected_contexts:
            typer.echo(
                "ERROR: --contexts was passed but contained no non-empty names. "
                "Either omit --contexts (to sweep all 7 by default) or pass at "
                "least one valid name.",
                err=True,
            )
            raise typer.Exit(code=2)
    result = sweep_activity_contexts(corpus, _CONVERT_FN, contexts=selected_contexts)

    _emit(result)
    if output:
        output.write_text(json.dumps(result, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
        typer.echo(f"\nSweep result written to {output}", err=True)


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


@app.command("optimize-judge")
def optimize_judge_command(
    calibration_set: Path = typer.Option(
        "golden_sets/calibration_pairs.json",
        "--calibration-set",
        exists=True,
        readable=True,
        help="Path to calibration pairs JSON",
    ),
    optimizer: str = typer.Option("MIPROv2", "--optimizer", help="DSPy optimizer: MIPROv2 or SIMBA"),
    model: str = typer.Option(
        "databricks-claude-sonnet-4-6",
        "--model",
        help="Model for optimization (primary: databricks-claude-opus-4-6, batch: databricks-gpt-5-4)",
    ),
    num_trials: int = typer.Option(20, "--num-trials", help="Number of optimization trials"),
    output: Path | None = typer.Option(None, "--output", help="Save optimized state to this path"),
    evaluate_only: bool = typer.Option(False, "--evaluate-only", help="Only evaluate current judge, no optimization"),
) -> None:
    """Optimize the LLM judge using DSPy against human-labelled calibration pairs.

    Uses Databricks Anthropic (Opus 4.6 for high-stakes, Sonnet 4.6 for optimization)
    as primary; Databricks ChatGPT 5.4 as batch fallback.
    """
    _auto_configure()
    if _JUDGE_PROVIDER is None:
        typer.echo("ERROR: FMAPI judge not configured — set DATABRICKS_HOST and DATABRICKS_TOKEN env vars.", err=True)
        raise typer.Exit(code=2)

    if evaluate_only:
        from lakeflow_migration_validator.optimization.dspy_judge import evaluate_judge_quality
        from lakeflow_migration_validator.optimization.judge_optimizer import ManualCalibrator

        calibrator = ManualCalibrator.from_file(calibration_set)
        judge = calibrator.to_optimized_judge(_JUDGE_PROVIDER, model=model)
        scores = evaluate_judge_quality(judge, calibration_set)
        _emit({"mode": "evaluate_only", "agreement_scores": scores})
        return

    try:
        from lakeflow_migration_validator.optimization.dspy_judge import DSPyJudgeOptimizer

        opt = DSPyJudgeOptimizer(
            _JUDGE_PROVIDER,
            optimizer=optimizer,
            model=model,
            num_trials=num_trials,
        )
        typer.echo(f"Running {optimizer} optimization with {num_trials} trials on {model}...", err=True)
        result = opt.optimize(calibration_set)
        _emit(
            {
                "mode": "dspy",
                "optimizer": optimizer,
                "model": model,
                "train_agreement": result.train_agreement,
                "dev_agreement": result.dev_agreement,
                "improvement_over_baseline": result.improvement_over_baseline,
                "num_trials": result.num_trials,
            }
        )
        if output:
            opt.save(output)
            typer.echo(f"\nOptimized state saved to {output}", err=True)
    except ImportError:
        typer.echo("DSPy not installed — falling back to ManualCalibrator.", err=True)
        from lakeflow_migration_validator.optimization.judge_optimizer import ManualCalibrator

        calibrator = ManualCalibrator.from_file(calibration_set)
        judge = calibrator.to_optimized_judge(_JUDGE_PROVIDER, model=model)
        agreement = calibrator.evaluate_agreement(judge)
        _emit(
            {
                "mode": "manual_calibrator",
                "model": model,
                "agreement": agreement,
                "examples_selected": len(calibrator.select_examples()),
            }
        )


@app.command("adversarial-loop")
def adversarial_loop_command(
    rounds: int = typer.Option(10, "--rounds", help="Maximum rounds"),
    pipelines_per_round: int = typer.Option(10, "--pipelines", help="Pipelines to generate per round"),
    patience: int = typer.Option(3, "--patience", help="Stop if no new clusters for this many rounds"),
    time_budget: float = typer.Option(3600.0, "--time-budget", help="Max seconds (default 1 hour)"),
    llm_budget: int = typer.Option(500, "--llm-budget", help="Max LLM calls"),
    threshold: float = typer.Option(0.75, "--threshold", help="Score below this = failure"),
    weak_spots: str = typer.Option(
        "nested_expressions,math_on_params,foreach_expression_items,complex_conditions",
        "--weak-spots",
        help="Comma-separated weak spots to target",
    ),
    golden_set_output: Path | None = typer.Option(
        None, "--golden-set-output", help="Write discovered failures as a golden set"
    ),
    model: str = typer.Option(
        "databricks-claude-opus-4-6",
        "--model",
        help="Model for pipeline generation (primary: opus-4-6, batch: gpt-5-4)",
    ),
    quiet: bool = typer.Option(False, "--quiet", help="Only print final result JSON"),
) -> None:
    """Run a closed-loop adversarial testing loop against wkmigrate.

    Generates ADF pipelines targeting weak spots, converts them through wkmigrate,
    scores dimensions, clusters failures, and feeds results back to generate harder
    test cases each round.

    Uses Databricks Anthropic Opus 4.6 for generation (primary) and
    Databricks ChatGPT 5.4 for batch scoring (secondary).
    """
    _auto_configure()
    if _JUDGE_PROVIDER is None:
        typer.echo("ERROR: FMAPI judge not configured — set DATABRICKS_HOST and DATABRICKS_TOKEN env vars.", err=True)
        raise typer.Exit(code=2)
    if _CONVERT_FN is snapshot_from_adf_payload:
        typer.echo(
            "ERROR: wkmigrate not available — adversarial loop requires the real converter. "
            "Install wkmigrate via 'poetry install --with dev' first.",
            err=True,
        )
        raise typer.Exit(code=2)

    from lakeflow_migration_validator.optimization.adversarial_loop import (
        AdversarialLoop,
        LoopConfig,
    )

    config = LoopConfig(
        max_rounds=rounds,
        pipelines_per_round=pipelines_per_round,
        convergence_patience=patience,
        max_time_seconds=time_budget,
        max_llm_calls=llm_budget,
        failure_threshold=threshold,
        target_weak_spots=tuple(s.strip() for s in weak_spots.split(",") if s.strip()),
        golden_set_output_path=str(golden_set_output) if golden_set_output else None,
    )

    loop = AdversarialLoop(
        _JUDGE_PROVIDER,
        convert_fn=_CONVERT_FN,
        config=config,
        model=model,
    )

    if quiet:
        result = loop.run()
    else:
        typer.echo(f"Adversarial loop: {rounds} rounds, {pipelines_per_round} pipelines/round", err=True)
        typer.echo(f"Targets: {', '.join(config.target_weak_spots)}", err=True)
        typer.echo(f"Model: {model} | Budget: {llm_budget} calls, {time_budget:.0f}s", err=True)
        typer.echo("---", err=True)
        result = None
        for event in loop.run_stream():
            if event["type"] == "round_start":
                typer.echo(f"\n[Round {event['round']}]", err=True)
            elif event["type"] == "round_end":
                r = event["result"]
                typer.echo(
                    f"  Generated: {r.pipelines_generated} | Failures: {r.failures_found} | "
                    f"New clusters: {r.new_clusters} | Worst: {r.worst_dimension}",
                    err=True,
                )
            elif event["type"] == "new_cluster":
                typer.echo(
                    f"  NEW CLUSTER: {event['signature']} — {event.get('example_expression', '')[:60]}", err=True
                )
            elif event["type"] == "budget_warning":
                typer.echo(f"  BUDGET: {event['resource']} {event['used']}/{event['limit']}", err=True)
            elif event["type"] == "complete":
                result = event["result"]

    assert result is not None
    summary = {
        "rounds_completed": result.rounds_completed,
        "total_pipelines": result.total_pipelines,
        "total_failures": result.total_failures,
        "unique_clusters": result.unique_clusters,
        "termination_reason": result.termination_reason,
        "elapsed_seconds": round(result.elapsed_seconds, 1),
        "discovered_signatures": result.discovered_signatures,
        "golden_set_path": result.golden_set_path,
    }
    _emit(summary)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path, option_name: str = "--adf-json") -> dict:
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"{option_name} must contain a JSON object")
    return payload
