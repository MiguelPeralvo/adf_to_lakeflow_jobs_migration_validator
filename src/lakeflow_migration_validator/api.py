"""FastAPI surface for validation, harness, and synthetic workflows."""

from __future__ import annotations

import json as _json
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from lakeflow_migration_validator import evaluate, evaluate_batch
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.golden_set import load_pipeline_golden_set
from lakeflow_migration_validator.serialization import snapshot_from_adf_payload
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite


@dataclass(slots=True)
class InMemoryHistoryStore:
    """Simple in-memory history store for scorecards."""

    _history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def append(self, pipeline_name: str, scorecard: dict[str, Any]) -> None:
        entries = self._history.setdefault(pipeline_name, [])
        entries.append(
            {
                "pipeline_name": pipeline_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scorecard": scorecard,
            }
        )

    def get(self, pipeline_name: str) -> list[dict[str, Any]]:
        return list(self._history.get(pipeline_name, []))


class ValidateRequest(BaseModel):
    """Request payload for /api/validate.

    Accepts three input modes:
    - ``adf_json``: raw ADF pipeline JSON (dict) — creates a minimal snapshot
    - ``snapshot``: a pre-converted ConversionSnapshot dict (from wkmigrate adapter)
    - ``adf_yaml``: raw ADF pipeline definition as a YAML string — parsed to dict
    """

    adf_json: dict[str, Any] | None = None
    adf_yaml: str | None = None
    snapshot: dict[str, Any] | None = None
    pipeline_name: str | None = None
    input_mode: str | None = None  # "adf_json", "adf_yaml", "snapshot" — auto-detected if not set

    @model_validator(mode="after")
    def _validate_source(self):
        if self.adf_json is None and self.snapshot is None and self.adf_yaml is None:
            raise ValueError("provide one of: adf_json, adf_yaml, or snapshot")
        return self


class ValidateExpressionRequest(BaseModel):
    """Request payload for /api/validate/expression."""

    adf_expression: str = Field(min_length=1)
    python_code: str = Field(min_length=1)


class ValidateBatchRequest(BaseModel):
    """Request payload for /api/validate/batch."""

    pipelines_path: str
    threshold: float = 90.0


class ValidateFolderRequest(BaseModel):
    """Request payload for /api/validate/folder — scan a directory of ADF JSON files."""

    folder_path: str = Field(min_length=1)
    threshold: float = 90.0
    glob_pattern: str = "*.json"


class HarnessRunRequest(BaseModel):
    """Request payload for /api/harness/run."""

    pipeline_name: str = Field(min_length=1)


class SyntheticGenerateRequest(BaseModel):
    """Request payload for /api/synthetic/generate.

    Modes:
    - ``template``: deterministic templates (fast, no LLM)
    - ``llm``: LLM generation using a preset or custom prompt
    - ``custom``: user-provided prompt (free-form)
    """

    count: int = 10
    difficulty: str = "medium"
    max_activities: int = 20
    mode: str = "template"
    preset: str | None = None           # key from PROMPT_TEMPLATES (for llm mode)
    custom_prompt: str | None = None    # user-edited prompt (for custom mode)
    generate_test_data: bool = False    # also generate test data for parallel testing
    output_path: str | None = None
    spec: dict[str, Any] | None = None  # pre-generated spec — skips planning


class ParallelRunRequest(BaseModel):
    """Request payload for /api/parallel/run."""

    pipeline_name: str = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)
    snapshot: dict[str, Any] | None = None


def create_app(
    *,
    convert_fn: Callable[[dict], ConversionSnapshot] | None = None,
    judge_provider: JudgeProvider | None = None,
    history_store: InMemoryHistoryStore | None = None,
    harness_runner=None,
    parallel_runner=None,
) -> FastAPI:
    """Create the FastAPI app with injectable dependencies for tests and runtime."""

    app = FastAPI(title="lakeflow-migration-validator", version="0.1.0")
    convert = convert_fn or snapshot_from_adf_payload
    history = history_store or InMemoryHistoryStore()

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        """Return which capabilities are active."""
        return {
            "validator": True,
            "judge": judge_provider is not None,
            "harness": harness_runner is not None,
            "parallel": parallel_runner is not None,
        }

    @app.post("/api/validate")
    def post_validate(request: ValidateRequest) -> dict[str, Any]:
        snapshot = _resolve_snapshot(request, convert)
        scorecard = evaluate(snapshot)

        if request.pipeline_name:
            pipeline_name = request.pipeline_name
        elif request.adf_json:
            pipeline_name = str(request.adf_json.get("name", "<unknown>"))
        elif request.adf_yaml:
            pipeline_name = str(snapshot.source_pipeline.get("name", "<yaml>"))
        else:
            pipeline_name = "<snapshot>"

        payload = scorecard.to_dict()
        history.append(pipeline_name, payload)
        return payload

    @app.post("/api/validate/expression")
    def post_validate_expression(request: ValidateExpressionRequest) -> dict[str, Any]:
        if judge_provider is None:
            raise HTTPException(status_code=503, detail="judge_provider is not configured")

        prompt = (
            "Evaluate semantic equivalence between ADF and Python code. "
            f"ADF: {request.adf_expression}\nPython: {request.python_code}"
        )
        response = judge_provider.judge(prompt)
        try:
            score = float(response.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        return {
            "score": max(0.0, min(1.0, score)),
            "reasoning": str(response.get("reasoning", "")),
        }

    @app.get("/api/history/{pipeline_name}")
    def get_history(pipeline_name: str) -> list[dict[str, Any]]:
        return history.get(pipeline_name)

    @app.post("/api/validate/batch")
    def post_validate_batch(request: ValidateBatchRequest) -> dict[str, Any]:
        suite = load_pipeline_golden_set(request.pipelines_path)
        report = evaluate_batch(suite, convert, threshold=request.threshold)
        return report.to_dict()

    @app.post("/api/validate/folder")
    def post_validate_folder(
        request: ValidateFolderRequest,
        stream: bool = Query(False),
    ):
        """Scan a folder of ADF JSON files, translate each through wkmigrate, and evaluate."""
        import glob as _glob

        folder = Path(request.folder_path)
        if not folder.is_dir():
            raise HTTPException(status_code=422, detail=f"Not a directory: {request.folder_path}")

        files = sorted(folder.glob(request.glob_pattern))
        if not files:
            raise HTTPException(status_code=422, detail=f"No {request.glob_pattern} files found in {request.folder_path}")

        if stream:
            return StreamingResponse(
                _validate_folder_stream(files, convert, request.threshold),
                media_type="application/x-ndjson",
            )

        # Non-streaming: evaluate all and return report
        cases = []
        scores = []
        below = 0
        for file_path in files:
            with open(file_path, encoding="utf-8") as f:
                adf_json = _json.load(f)
            name = adf_json.get("name", file_path.stem)
            try:
                snapshot = convert(adf_json)
                scorecard = evaluate(snapshot)
                score = scorecard.score
                label = scorecard.label
            except Exception as exc:
                score = 0.0
                label = "ERROR"
            is_below = score < request.threshold
            if is_below:
                below += 1
            scores.append(score)
            cases.append({
                "pipeline_name": name,
                "file": str(file_path),
                "score": score,
                "label": label,
                "ccs_below_threshold": is_below,
            })

        mean = sum(scores) / len(scores) if scores else 0.0
        return {
            "total": len(cases),
            "threshold": request.threshold,
            "mean_score": mean,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "below_threshold": below,
            "cases": cases,
        }

    def _validate_folder_stream(files: list, convert_fn, threshold: float):
        """Yield NDJSON progress events for folder validation."""
        total = len(files)
        cases = []
        scores = []
        below = 0
        for i, file_path in enumerate(files):
            name = file_path.stem
            try:
                with open(file_path, encoding="utf-8") as f:
                    adf_json = _json.load(f)
                name = adf_json.get("name", name)
                snapshot = convert_fn(adf_json)
                scorecard = evaluate(snapshot)
                score = scorecard.score
                label = scorecard.label
                dims = scorecard.to_dict().get("dimensions", {})
                error = None
            except Exception as exc:
                score = 0.0
                label = "ERROR"
                dims = {}
                error = f"{type(exc).__name__}: {exc}"

            is_below = score < threshold
            if is_below:
                below += 1
            scores.append(score)

            case = {
                "pipeline_name": name,
                "file": str(file_path),
                "score": score,
                "label": label,
                "ccs_below_threshold": is_below,
                "dimensions": dims,
            }
            cases.append(case)

            yield _json.dumps({
                "type": "progress",
                "completed": i + 1,
                "total": total,
                "pipeline_name": name,
                "score": score,
                "label": label,
                "ok": error is None,
                "error": error,
            }) + "\n"

        mean = sum(scores) / len(scores) if scores else 0.0
        yield _json.dumps({
            "type": "complete",
            "result": {
                "total": len(cases),
                "threshold": threshold,
                "mean_score": mean,
                "min_score": min(scores) if scores else 0.0,
                "max_score": max(scores) if scores else 0.0,
                "below_threshold": below,
                "cases": cases,
            },
        }) + "\n"

    @app.post("/api/harness/run")
    def post_harness_run(request: HarnessRunRequest) -> dict[str, Any]:
        if harness_runner is None:
            raise HTTPException(status_code=503, detail="harness_runner is not configured")
        result = harness_runner.run(request.pipeline_name)
        return {
            "pipeline_name": result.pipeline_name,
            "scorecard": result.scorecard.to_dict(),
            "iterations": result.iterations,
            "fix_suggestions": list(result.fix_suggestions),
        }

    # ------------------------------------------------------------------
    # wkmigrate repo/branch configuration
    # ------------------------------------------------------------------
    _wkmigrate_config: dict[str, Any] = {
        "repos": [
            {"url": "https://github.com/MiguelPeralvo/wkmigrate", "default_branch": "alpha"},
            {"url": "https://github.com/ghanse/wkmigrate", "default_branch": "main"},
        ],
        "active_repo": "https://github.com/MiguelPeralvo/wkmigrate",
        "active_branch": "alpha",
    }

    @app.get("/api/config/wkmigrate")
    def get_wkmigrate_config() -> dict[str, Any]:
        """Return the current wkmigrate repo/branch configuration."""
        return _wkmigrate_config

    @app.post("/api/config/wkmigrate")
    def set_wkmigrate_config(request: dict[str, Any]) -> dict[str, Any]:
        """Update the active wkmigrate repo and/or branch.

        Note: changing the repo/branch stores the selection but does NOT
        hot-swap the running wkmigrate. A server restart with the new
        package installed is required for changes to take effect.
        """
        if "active_repo" in request:
            _wkmigrate_config["active_repo"] = request["active_repo"]
        if "active_branch" in request:
            _wkmigrate_config["active_branch"] = request["active_branch"]
        if "repos" in request:
            _wkmigrate_config["repos"] = request["repos"]
        return _wkmigrate_config

    @app.get("/api/config/wkmigrate/branches")
    def get_wkmigrate_branches(repo_url: str = Query(...)) -> list[dict[str, Any]]:
        """Fetch branches for a GitHub repo, sorted by most recent commit.

        Example: ``/api/config/wkmigrate/branches?repo_url=https://github.com/MiguelPeralvo/wkmigrate``
        """
        from urllib.request import Request, urlopen
        from urllib.error import URLError

        # Parse owner/repo from URL
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            raise HTTPException(status_code=422, detail="Invalid repo URL")
        owner, repo = parts[-2], parts[-1]

        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo}/branches?per_page=100"
            req = Request(api_url, headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "LMV"})
            with urlopen(req, timeout=10) as resp:
                branches = _json.loads(resp.read().decode("utf-8"))
        except (URLError, Exception) as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch branches: {exc}") from exc

        # Sort by commit date (most recent first)
        for b in branches:
            sha = b.get("commit", {}).get("sha", "")
            b["_sha"] = sha
        # Fetch commit dates for sorting (batch — just use the sha order as proxy)
        # GitHub branches API doesn't include commit dates, so we fetch each commit
        # For performance, just return as-is and let the frontend sort if needed
        return [
            {"name": b["name"], "sha": b.get("_sha", "")[:8], "protected": b.get("protected", False)}
            for b in branches
        ]

    # ------------------------------------------------------------------
    # Synthetic run history (list past batch directories)
    # ------------------------------------------------------------------
    @app.get("/api/synthetic/runs")
    def get_synthetic_runs() -> list[dict[str, Any]]:
        """List past synthetic generation runs from the temp directory."""
        base = Path(tempfile.gettempdir()) / "lmv_synthetic"
        if not base.is_dir():
            return []
        runs = []
        for d in sorted(base.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            suite_file = d / "suite.json"
            pipeline_count = 0
            if suite_file.exists():
                try:
                    with open(suite_file, encoding="utf-8") as f:
                        data = _json.load(f)
                    pipeline_count = len(data.get("pipelines", []))
                except Exception:
                    pass
            # Count pipeline subfolders
            subfolders = [p for p in d.iterdir() if p.is_dir()]
            runs.append({
                "path": str(d),
                "name": d.name,
                "pipeline_count": pipeline_count,
                "subfolder_count": len(subfolders),
                "has_suite": suite_file.exists(),
            })
        return runs

    @app.get("/api/synthetic/templates")
    def get_synthetic_templates() -> list[dict[str, str]]:
        from lakeflow_migration_validator.synthetic.prompt_templates import list_templates
        return list_templates()

    @app.post("/api/synthetic/resolve-template")
    def post_resolve_template(request: dict[str, Any]) -> dict[str, str]:
        from lakeflow_migration_validator.synthetic.prompt_templates import resolve_template
        base = resolve_template(
            request.get("preset", "complex_expressions"),
            count=request.get("count", 10),
            max_activities=request.get("max_activities", 10),
        )
        # Append extra params so the spec reflects all user choices
        extras: list[str] = []
        difficulty = request.get("difficulty")
        if difficulty and difficulty != "medium":
            extras.append(f"Target difficulty: {difficulty}.")
        if request.get("generate_test_data"):
            extras.append("Also generate parallel test data (CSV source files + SQL seed scripts) for each pipeline.")
        if extras:
            base += "\n\n" + " ".join(extras)
        return {"prompt": base}

    @app.post("/api/synthetic/spec")
    def post_synthetic_spec(request: dict[str, Any]) -> dict[str, Any]:
        """Generate an editable spec from prompt + options, without generating pipelines."""
        req_count = int(request.get("count", 10))
        req_mode = request.get("mode", "template")
        req_preset = request.get("preset")
        req_prompt = request.get("custom_prompt", "")
        req_difficulty = request.get("difficulty", "medium")
        req_max_activities = int(request.get("max_activities", 20))

        if req_mode in ("llm", "custom") and judge_provider is not None:
            from lakeflow_migration_validator.synthetic.agent_generator import (
                AgentPipelineGenerator,
                GenerationConfig,
            )
            weak_spots = _PRESET_WEAK_SPOTS.get(req_preset or "", ("nested_expressions",))
            config = GenerationConfig(
                target_weak_spots=weak_spots,
                extra_instructions=req_prompt,
            )
            agent = AgentPipelineGenerator(judge_provider=judge_provider)
            plan = agent._create_plan(req_count, config)
            return {
                "count": plan.count,
                "pipelines": [
                    {
                        "name": s.name,
                        "activity_count": s.activity_count,
                        "activity_types": list(s.activity_types),
                        "stress_area": s.stress_area,
                        "expression_complexity": s.expression_complexity,
                        "parameters": list(s.parameters),
                    }
                    for s in plan.specs
                ],
            }
        # Template / fallback: deterministic spec
        from lakeflow_migration_validator.synthetic.pipeline_generator import _DEFAULT_ACTIVITY_TYPES
        specs = []
        for i in range(req_count):
            specs.append({
                "name": f"synthetic_pipeline_{i:03d}",
                "activity_count": 1 + (i % req_max_activities),
                "activity_types": list(_DEFAULT_ACTIVITY_TYPES),
                "stress_area": req_difficulty,
                "expression_complexity": "mixed",
                "parameters": ["param1", "param2"],
            })
        return {"count": req_count, "pipelines": specs}

    _PRESET_WEAK_SPOTS: dict[str, tuple[str, ...]] = {
        "complex_expressions": ("nested_expressions", "math_on_params"),
        "deep_nesting": ("deep_nesting", "complex_conditions"),
        "activity_mix": ("activity_output_chaining", "unsupported_types"),
        "math_on_params": ("math_on_params",),
        "unsupported_types": ("unsupported_types",),
        "pipeline_invocation": ("activity_output_chaining", "deep_nesting"),
        "full_coverage": ("nested_expressions", "math_on_params", "deep_nesting", "complex_conditions"),
    }

    def _persist_suite(suite: GroundTruthSuite, output_path: str | None = None) -> str:
        """Persist suite to disk with per-pipeline subfolders.

        Structure::

            {batch_dir}/
                suite.json                          # full suite (for batch validation)
                000_pipeline_name/
                    adf_pipeline.json               # raw ADF JSON
                001_other_pipeline/
                    adf_pipeline.json
        """
        if output_path:
            suite.to_json(output_path)
            return output_path
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        batch_dir = Path(tempfile.gettempdir()) / "lmv_synthetic" / ts
        batch_dir.mkdir(parents=True, exist_ok=True)

        # Full suite JSON (loadable by batch validation)
        suite.to_json(str(batch_dir / "suite.json"))

        # Individual pipeline subfolders
        for i, pipeline in enumerate(suite.pipelines):
            name = pipeline.adf_json.get("name", f"pipeline_{i:03d}")
            safe = f"{i:03d}_{name.replace('/', '_').replace(' ', '_')[:60]}"
            pipe_dir = batch_dir / safe
            pipe_dir.mkdir(parents=True, exist_ok=True)
            with open(pipe_dir / "adf_pipeline.json", "w", encoding="utf-8") as fh:
                _json.dump(pipeline.adf_json, fh, indent=2)

        return str(batch_dir)

    def _build_result(
        suite: GroundTruthSuite,
        persist_path: str,
        fallback_note: str | None,
        generate_test_data: bool,
    ) -> dict[str, Any]:
        pipelines_payload = [
            {
                "name": p.adf_json.get("name", "<unknown>"),
                "adf_json": p.adf_json,
                "description": p.description,
                "difficulty": p.difficulty,
            }
            for p in suite.pipelines
        ]
        result: dict[str, Any] = {
            "count": len(suite.pipelines),
            "pipelines": pipelines_payload,
            "output_path": persist_path,
        }
        if fallback_note:
            result["fallback_note"] = fallback_note
        if generate_test_data:
            from lakeflow_migration_validator.synthetic.test_data_generator import TestDataGenerator
            gen = TestDataGenerator()
            test_data = gen.generate_for_suite([p.adf_json for p in suite.pipelines])
            result["test_data"] = [td.to_dict() for td in test_data]
        return result

    def _generate_stream(request: SyntheticGenerateRequest):
        """Yield NDJSON lines with per-pipeline progress."""
        mode = request.mode
        fallback_note: str | None = None

        if mode in ("llm", "custom") and judge_provider is None:
            fallback_note = f"Mode '{mode}' requires an LLM provider; using 'template' mode."
            mode = "template"

        suite = None

        if mode in ("llm", "custom") and judge_provider is not None:
            try:
                from lakeflow_migration_validator.synthetic.agent_generator import (
                    AgentPipelineGenerator,
                    GenerationConfig,
                )
                weak_spots = _PRESET_WEAK_SPOTS.get(request.preset or "", ("nested_expressions",))
                config = GenerationConfig(
                    target_weak_spots=weak_spots,
                    extra_instructions=request.custom_prompt or "",
                )
                agent_gen = AgentPipelineGenerator(judge_provider=judge_provider)
                # Build pre-built plan from spec if provided
                pre_plan = None
                if request.spec and "pipelines" in request.spec:
                    from lakeflow_migration_validator.synthetic.agent_generator import (
                        GenerationPlan,
                        PipelineSpec,
                    )
                    pre_specs = []
                    for item in request.spec["pipelines"]:
                        pre_specs.append(PipelineSpec(
                            name=item.get("name", f"pipeline_{len(pre_specs):03d}"),
                            activity_count=int(item.get("activity_count", 5)),
                            activity_types=tuple(item.get("activity_types", ("SetVariable", "DatabricksNotebook"))),
                            stress_area=item.get("stress_area", "nested_expressions"),
                            expression_complexity=item.get("expression_complexity", "nested"),
                            parameters=tuple(item.get("parameters", ("env",))),
                        ))
                    pre_plan = GenerationPlan(
                        count=len(pre_specs),
                        specs=tuple(pre_specs),
                        raw_plan=request.spec,
                    )
                collected = []
                for ev in agent_gen.generate_stream(
                    count=request.count, config=config, plan=pre_plan,
                ):
                    if ev["type"] == "plan":
                        plan = ev["plan"]
                        plan_specs = [
                            {"name": s.name, "stress_area": s.stress_area,
                             "activity_count": s.activity_count}
                            for s in plan.specs
                        ]
                        yield _json.dumps({
                            "type": "plan",
                            "count": plan.count,
                            "specs": plan_specs,
                        }) + "\n"
                    elif ev["type"] == "stage":
                        stage_event: dict[str, Any] = {
                            "type": "stage",
                            "pipeline_index": ev["pipeline_index"],
                            "pipeline_name": ev["pipeline_name"],
                            "stage": ev["stage"],
                            "pct": ev.get("pct", 0),
                            "total": ev["total"],
                        }
                        if ev.get("attempt"):
                            stage_event["attempt"] = ev["attempt"]
                            stage_event["max_attempts"] = ev.get("max_attempts", 1)
                        if ev.get("error"):
                            stage_event["error"] = ev["error"]
                        yield _json.dumps(stage_event) + "\n"
                    elif ev["type"] == "pipeline":
                        pipeline = ev.get("pipeline")
                        name = pipeline.adf_json.get("name") if pipeline else ev.get("spec_name")
                        event: dict[str, Any] = {
                            "type": "progress",
                            "completed": ev["completed"],
                            "total": ev["total"],
                            "pipeline_name": name,
                            "ok": pipeline is not None,
                        }
                        if ev.get("error"):
                            event["error"] = ev["error"]
                        yield _json.dumps(event) + "\n"
                        if pipeline:
                            collected.append(pipeline)

                if collected:
                    suite = GroundTruthSuite(pipelines=tuple(collected))
                    if len(collected) < plan.count:
                        fallback_note = f"LLM generated {len(collected)}/{plan.count} pipelines."
                else:
                    fallback_note = "LLM produced no valid pipelines; using template mode."
                    mode = "template"
            except Exception as exc:
                logger.exception("LLM generation failed in streaming path")
                fallback_note = "LLM generation failed; using template mode."
                mode = "template"

        if mode == "template":
            suite = GroundTruthSuite.generate(
                count=request.count,
                difficulty=request.difficulty,
                max_activities=request.max_activities,
                mode="template",
            )
            yield _json.dumps({
                "type": "progress",
                "completed": len(suite.pipelines),
                "total": request.count,
                "pipeline_name": None,
                "ok": True,
            }) + "\n"

        persist_path = _persist_suite(suite, request.output_path)
        result = _build_result(suite, persist_path, fallback_note, request.generate_test_data)
        yield _json.dumps({"type": "complete", "result": result}) + "\n"

    @app.post("/api/synthetic/generate")
    def post_synthetic_generate(
        request: SyntheticGenerateRequest,
        stream: bool = Query(False),
    ):
        if stream:
            return StreamingResponse(
                _generate_stream(request),
                media_type="application/x-ndjson",
            )
        mode = request.mode
        fallback_note: str | None = None

        if mode in ("llm", "custom") and judge_provider is None:
            fallback_note = f"Mode '{mode}' requires an LLM provider; using 'template' mode."
            mode = "template"

        if mode in ("llm", "custom") and judge_provider is not None:
            try:
                from lakeflow_migration_validator.synthetic.agent_generator import (
                    AgentPipelineGenerator,
                    GenerationConfig,
                )
                weak_spots = _PRESET_WEAK_SPOTS.get(request.preset or "", ("nested_expressions",))
                config = GenerationConfig(
                    target_weak_spots=weak_spots,
                    extra_instructions=request.custom_prompt or "",
                )
                agent_gen = AgentPipelineGenerator(judge_provider=judge_provider)
                pre_plan = None
                if request.spec and "pipelines" in request.spec:
                    from lakeflow_migration_validator.synthetic.agent_generator import (
                        GenerationPlan,
                        PipelineSpec,
                    )
                    pre_specs = []
                    for item in request.spec["pipelines"]:
                        pre_specs.append(PipelineSpec(
                            name=item.get("name", f"pipeline_{len(pre_specs):03d}"),
                            activity_count=int(item.get("activity_count", 5)),
                            activity_types=tuple(item.get("activity_types", ("SetVariable", "DatabricksNotebook"))),
                            stress_area=item.get("stress_area", "nested_expressions"),
                            expression_complexity=item.get("expression_complexity", "nested"),
                            parameters=tuple(item.get("parameters", ("env",))),
                        ))
                    pre_plan = GenerationPlan(
                        count=len(pre_specs),
                        specs=tuple(pre_specs),
                        raw_plan=request.spec,
                    )
                pipelines = [
                    p for ev in agent_gen.generate_stream(count=request.count, config=config, plan=pre_plan)
                    if ev["type"] == "pipeline" and ev.get("pipeline")
                    for p in [ev["pipeline"]]
                ]
                if pipelines:
                    suite = GroundTruthSuite(pipelines=tuple(pipelines))
                    if len(pipelines) < request.count:
                        fallback_note = f"LLM generated {len(pipelines)}/{request.count} pipelines."
                else:
                    fallback_note = "LLM produced no valid pipelines; using template mode."
                    mode = "template"
            except Exception as exc:
                logger.exception("LLM generation failed in non-streaming path")
                fallback_note = "LLM generation failed; using template mode."
                mode = "template"

        if mode == "template":
            suite = GroundTruthSuite.generate(
                count=request.count,
                difficulty=request.difficulty,
                max_activities=request.max_activities,
                mode="template",
            )

        persist_path = _persist_suite(suite, request.output_path)
        return _build_result(suite, persist_path, fallback_note, request.generate_test_data)

    @app.post("/api/parallel/run")
    def post_parallel_run(request: ParallelRunRequest) -> dict[str, Any]:
        if parallel_runner is None:
            raise HTTPException(status_code=503, detail="parallel_runner is not configured")
        snapshot = convert(request.snapshot) if request.snapshot is not None else None
        result = parallel_runner.run(
            request.pipeline_name,
            parameters=request.parameters,
            snapshot=snapshot,
        )
        return result.to_dict()

    return app


def _resolve_snapshot(
    request: ValidateRequest,
    convert_fn: Callable[[dict], ConversionSnapshot],
) -> ConversionSnapshot:
    if request.snapshot is not None:
        return convert_fn(request.snapshot)
    if request.adf_yaml is not None:
        try:
            import yaml
            parsed = yaml.safe_load(request.adf_yaml)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=422, detail="YAML must parse to an object (dict)")
        return convert_fn(parsed)
    if request.adf_json is not None:
        return convert_fn(request.adf_json)
    raise HTTPException(status_code=422, detail="provide one of: adf_json, adf_yaml, or snapshot")
