"""FastAPI surface for validation, harness, and synthetic workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
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

    @app.get("/api/synthetic/templates")
    def get_synthetic_templates() -> list[dict[str, str]]:
        from lakeflow_migration_validator.synthetic.prompt_templates import list_templates
        return list_templates()

    @app.post("/api/synthetic/resolve-template")
    def post_resolve_template(request: dict[str, Any]) -> dict[str, str]:
        from lakeflow_migration_validator.synthetic.prompt_templates import resolve_template
        return {
            "prompt": resolve_template(
                request.get("preset", "complex_expressions"),
                count=request.get("count", 10),
                max_activities=request.get("max_activities", 10),
            )
        }

    @app.post("/api/synthetic/generate")
    def post_synthetic_generate(request: SyntheticGenerateRequest) -> dict[str, Any]:
        suite = GroundTruthSuite.generate(
            count=request.count,
            difficulty=request.difficulty,
            max_activities=request.max_activities,
            mode=request.mode,
        )
        if request.output_path:
            suite.to_json(request.output_path)

        result: dict[str, Any] = {
            "count": len(suite.pipelines),
            "pipelines": [pipeline.adf_json.get("name", "<unknown>") for pipeline in suite.pipelines],
            "output_path": request.output_path,
        }

        # Optionally generate test data for parallel testing
        if request.generate_test_data:
            from lakeflow_migration_validator.synthetic.test_data_generator import TestDataGenerator
            gen = TestDataGenerator()
            test_data = gen.generate_for_suite([p.adf_json for p in suite.pipelines])
            result["test_data"] = [td.to_dict() for td in test_data]

        return result

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
