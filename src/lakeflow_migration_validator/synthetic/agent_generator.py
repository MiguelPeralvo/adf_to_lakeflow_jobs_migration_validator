"""LLM-powered ADF pipeline generator for stress testing wkmigrate.

Three modes:
- ``template``: existing deterministic templates (fast, no LLM)
- ``llm``: single-shot LLM generation via FMAPI (creative, varied)
- ``adversarial``: DSPy-optimized generation targeting converter weak spots

The ``llm`` and ``adversarial`` modes use an LLM to generate realistic ADF
pipeline JSON that exercises activity types, expression patterns, dependency
chains, and edge cases that the template generator cannot produce.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    DependencyRef,
    ExpressionPair,
    NotebookSnapshot,
    SecretRef,
    TaskSnapshot,
)
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.synthetic.pipeline_generator import (
    SyntheticPipeline,
    _DEFAULT_ACTIVITY_TYPES,
)

# Max tokens for LLM pipeline generation.  Complex ADF pipelines with deeply
# nested expressions can exceed 10 K tokens, so we set a generous ceiling.
# Adjust downward if your serving endpoint has a lower limit or you want to
# reduce cost; 8192 is the practical minimum for non-trivial pipelines.
MAX_GENERATION_TOKENS: int = 65_536

# Canonical supported types — derived from the shared pipeline_generator constant
# to avoid drift. Control-flow types (ForEach, IfCondition) are also supported.
_SUPPORTED_TYPES: frozenset[str] = frozenset(_DEFAULT_ACTIVITY_TYPES) | {
    "DatabricksSparkJar", "DatabricksSparkPython", "DatabricksJob",
}

_WEAK_SPOTS = {
    "nested_expressions": "Use deeply nested ADF expressions (3+ levels): concat(formatDateTime(utcNow(),'yyyy-MM-dd'), '/', pipeline().parameters.env, '/', activity('Lookup').output.firstRow.path)",
    "math_on_params": "Use math functions on pipeline parameters: add(mul(pipeline().parameters.count, 2), 1) — dbutils.widgets.get returns strings so math fails without coercion",
    "foreach_expression_items": "Use expressions as ForEach items: createArray(concat('a', pipeline().parameters.suffix), concat('b', pipeline().parameters.suffix))",
    "complex_conditions": "Use complex IfCondition predicates: and(greater(pipeline().parameters.threshold, 50), not(equals(pipeline().parameters.env, 'prod')))",
    "parameterized_paths": "Use expressions in Copy source paths: concat(pipeline().parameters.container, '/', formatDateTime(utcNow(), 'yyyy/MM/dd'))",
    "activity_output_chaining": "Reference upstream activity outputs: activity('Lookup').output.firstRow.config_value in a SetVariable downstream",
    "unsupported_types": "Include unsupported activity types (AzureFunction, Wait) that should produce placeholder notebooks",
    "deep_nesting": "Use 3+ levels of control flow nesting: ForEach → IfCondition → ForEach → Notebook",
}

_PLAN_PROMPT = """You are an Azure Data Factory expert planning a synthetic test suite.

User request:
{user_request}

Analyze the request and produce a generation plan as JSON:
{{
  "count": <number of pipelines to generate>,
  "pipelines": [
    {{
      "name": "<descriptive_pipeline_name>",
      "activity_count": <3-10>,
      "activity_types": ["SetVariable", "DatabricksNotebook", ...],
      "stress_area": "<what this pipeline tests>",
      "expression_complexity": "<simple|nested|deeply_nested>",
      "parameters": ["env", "batch_id", ...]
    }}
  ]
}}

Rules:
- Each pipeline must have a unique name and distinct stress focus
- Activity types: SetVariable, IfCondition, DatabricksNotebook, Copy, Lookup, WebActivity, ForEach
- Match the user's intent for count, complexity, and coverage
- If the user didn't specify a count, default to 10

Output ONLY valid JSON. No markdown, no explanation."""

_GENERATION_PROMPT = """You are an Azure Data Factory expert. Generate exactly ONE realistic ADF pipeline JSON.

Pipeline spec:
- Name: {pipeline_name}
- Include {activity_count} activities using types: {activity_types}
- Include dependency chains (dependsOn with Succeeded conditions)
- Use these ADF expression patterns: {expression_patterns}
- Include pipeline parameters: {parameters}
- Stress area: {target_description}
{extra_instructions}

Output format — a single JSON object:
{{"name": "{pipeline_name}", "properties": {{"parameters": {{...}}, "variables": {{...}}, "activities": [...]}}}}

CRITICAL: Output ONLY the single JSON object. No arrays, no markdown, no explanation, no code blocks."""

_GROUND_TRUTH_PROMPT = """Analyze this ADF pipeline JSON and predict what a migration validator would score.

Pipeline:
{pipeline_json}

For each quality dimension, predict a score from 0.0 to 1.0:
- activity_coverage: fraction of activities that can be translated (supported types / total)
- expression_coverage: fraction of ADF expressions that can be translated to Python
- dependency_preservation: fraction of depends_on relationships that survive translation
- notebook_validity: will generated notebooks compile without SyntaxError (1.0 or lower)
- parameter_completeness: will all dbutils.widgets.get references match defined parameters
- secret_completeness: will secret references match instructions (1.0 for pipelines without secrets)
- not_translatable_ratio: inverse of warning count vs property count

Output JSON: {{"activity_coverage": 0.X, "expression_coverage": 0.X, ...}}
ONLY valid JSON, no explanation."""


@dataclass(frozen=True, slots=True)
class PipelineSpec:
    """Spec for a single pipeline from the generation plan."""
    name: str
    activity_count: int = 5
    activity_types: tuple[str, ...] = ("SetVariable", "DatabricksNotebook", "Lookup", "IfCondition")
    stress_area: str = "nested_expressions"
    expression_complexity: str = "nested"
    parameters: tuple[str, ...] = ("env", "batch_id", "output_path")


@dataclass(frozen=True, slots=True)
class GenerationPlan:
    """An LLM-produced plan describing the full test suite to generate."""
    count: int
    specs: tuple[PipelineSpec, ...]
    raw_plan: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    """Configuration for a single generation run."""
    activity_count: int = 5
    activity_types: tuple[str, ...] = ("SetVariable", "DatabricksNotebook", "Lookup", "IfCondition")
    parameters: tuple[str, ...] = ("env", "batch_id", "output_path")
    target_weak_spots: tuple[str, ...] = ("nested_expressions",)
    include_unsupported: bool = False
    extra_instructions: str = ""


class AgentPipelineGenerator:
    """LLM-powered ADF pipeline generator.

    Uses FMAPI to generate realistic, varied ADF pipelines that stress-test
    wkmigrate's translation capabilities.
    """

    def __init__(
        self,
        judge_provider: JudgeProvider,
        model: str | None = None,
        max_retries: int = 2,
    ):
        self._provider = judge_provider
        self._model = model  # None → provider picks its default
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        count: int = 10,
        config: GenerationConfig | None = None,
    ) -> list[SyntheticPipeline]:
        """Generate synthetic pipelines using the LLM."""
        return [p for ev in self.generate_stream(count, config) if ev["type"] == "pipeline" and ev.get("pipeline") for p in [ev["pipeline"]]]

    def generate_stream(
        self,
        count: int = 10,
        config: GenerationConfig | None = None,
        plan: GenerationPlan | None = None,
    ):
        """Yield event dicts for streaming: plan, pipeline progress, errors.

        Event types:
          {"type": "plan", "plan": GenerationPlan}
          {"type": "pipeline", "completed": int, "total": int,
           "pipeline": SyntheticPipeline | None, "error": str | None}
        """
        cfg = config or GenerationConfig()

        # Phase 1: Plan (skip if pre-built plan provided)
        if plan is None:
            plan = self._create_plan(count, cfg)
        yield {"type": "plan", "plan": plan}

        # Phase 2: Execute per spec with per-pipeline stage events
        total = plan.count
        for i, spec in enumerate(plan.specs):
            target_desc = _WEAK_SPOTS.get(spec.stress_area, spec.stress_area)
            prompt = _GENERATION_PROMPT.format(
                pipeline_name=spec.name,
                activity_count=spec.activity_count,
                activity_types=", ".join(spec.activity_types),
                expression_patterns=target_desc,
                parameters=", ".join(spec.parameters),
                target_description=target_desc,
                extra_instructions=cfg.extra_instructions,
            )
            pipeline = None
            error = None
            for stage_ev in self._generate_one_staged(prompt, spec.name, spec.stress_area):
                yield {
                    "type": "stage",
                    "pipeline_index": i,
                    "pipeline_name": spec.name,
                    "total": total,
                    **stage_ev,
                }
                if stage_ev["stage"] == "complete":
                    pipeline = stage_ev["pipeline"]
                elif stage_ev["stage"] == "failed":
                    error = stage_ev.get("error")

            yield {
                "type": "pipeline",
                "completed": i + 1,
                "total": total,
                "pipeline": pipeline,
                "error": error,
                "spec_name": spec.name,
            }

    # Keep old name as alias for backward compat
    def generate_iter(self, count: int = 10, config: GenerationConfig | None = None):
        """Yield ``(completed, total, pipeline | None, error | None)``."""
        for ev in self.generate_stream(count, config):
            if ev["type"] == "pipeline":
                yield (ev["completed"], ev["total"], ev.get("pipeline"), ev.get("error"))

    # ------------------------------------------------------------------
    # Phase 1: Planning
    # ------------------------------------------------------------------

    def _create_plan(self, count: int, cfg: GenerationConfig) -> GenerationPlan:
        """Ask the LLM to produce a generation plan, or build a deterministic fallback."""
        user_request = cfg.extra_instructions or f"Generate {count} ADF pipelines targeting: {', '.join(cfg.target_weak_spots)}"
        prompt = _PLAN_PROMPT.format(user_request=user_request)

        try:
            raw_text = self._complete(prompt, max_tokens=16_384)
            plan_json = _extract_json(raw_text)
            if plan_json and "pipelines" in plan_json:
                specs = []
                for item in plan_json["pipelines"]:
                    if not isinstance(item, dict):
                        continue
                    specs.append(PipelineSpec(
                        name=item.get("name", f"llm_pipeline_{len(specs):03d}"),
                        activity_count=int(item.get("activity_count", cfg.activity_count)),
                        activity_types=tuple(item.get("activity_types", cfg.activity_types)),
                        stress_area=item.get("stress_area", cfg.target_weak_spots[0]),
                        expression_complexity=item.get("expression_complexity", "nested"),
                        parameters=tuple(item.get("parameters", cfg.parameters)),
                    ))
                if specs:
                    return GenerationPlan(
                        count=len(specs),
                        specs=tuple(specs),
                        raw_plan=plan_json,
                    )
        except Exception:
            pass  # fall through to deterministic plan

        # Deterministic fallback
        specs = []
        for i in range(count):
            weak_spot = cfg.target_weak_spots[i % len(cfg.target_weak_spots)]
            specs.append(PipelineSpec(
                name=f"llm_pipeline_{i:03d}",
                activity_count=cfg.activity_count + (i % 3),
                activity_types=cfg.activity_types,
                stress_area=weak_spot,
                parameters=cfg.parameters,
            ))
        return GenerationPlan(count=count, specs=tuple(specs))

    # ------------------------------------------------------------------
    # Phase 2: Single pipeline generation
    # ------------------------------------------------------------------

    def _generate_one_staged(self, prompt: str, pipeline_name: str, stress_area: str = ""):
        """Yield stage events during single pipeline generation.

        Stages: preparing → generating → parsing → validating → complete/failed.
        Each event is a dict with ``stage``, ``pct`` (0-100), and optional metadata.
        """
        max_attempts = self._max_retries + 1
        yield {"stage": "preparing", "pct": 0}

        last_error: str | None = None
        for attempt in range(max_attempts):
            yield {"stage": "generating", "pct": 10, "attempt": attempt + 1, "max_attempts": max_attempts}
            try:
                raw_text = self._complete(prompt, max_tokens=MAX_GENERATION_TOKENS)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                yield {"stage": "retry", "pct": 10, "attempt": attempt + 1, "max_attempts": max_attempts, "error": last_error}
                continue

            yield {"stage": "parsing", "pct": 70}
            adf_json = _extract_json(raw_text)
            if adf_json is None:
                last_error = f"LLM returned non-JSON (attempt {attempt + 1}/{max_attempts})"
                yield {"stage": "retry", "pct": 75, "attempt": attempt + 1, "max_attempts": max_attempts, "error": last_error}
                continue

            yield {"stage": "validating", "pct": 85}
            if not _is_adf_pipeline(adf_json):
                last_error = f"Not a valid ADF pipeline (attempt {attempt + 1}/{max_attempts})"
                yield {"stage": "retry", "pct": 88, "attempt": attempt + 1, "max_attempts": max_attempts, "error": last_error}
                continue

            if "name" not in adf_json:
                adf_json["name"] = pipeline_name

            yield {"stage": "building_snapshot", "pct": 92}
            snapshot = _build_expected_snapshot(adf_json)
            pipeline = SyntheticPipeline(
                adf_json=adf_json,
                expected_snapshot=snapshot,
                description=f"LLM pipeline: {pipeline_name} ({stress_area})" if stress_area else f"LLM pipeline: {pipeline_name}",
                difficulty="llm",
            )
            yield {"stage": "complete", "pct": 100, "pipeline": pipeline}
            return

        yield {"stage": "failed", "pct": 100, "error": last_error}

    def _generate_one(self, prompt: str, pipeline_name: str) -> tuple[dict | None, str | None]:
        """Non-streaming single pipeline generation. Returns (result, error)."""
        pipeline = None
        error = None
        for ev in self._generate_one_staged(prompt, pipeline_name):
            if ev["stage"] == "complete":
                pipeline = ev["pipeline"]
            elif ev["stage"] == "failed":
                error = ev.get("error")
        if pipeline:
            return pipeline.adf_json, None
        return None, error

    def _complete(self, prompt: str, max_tokens: int = MAX_GENERATION_TOKENS) -> str:
        """Call the LLM provider for raw text completion."""
        if hasattr(self._provider, "complete"):
            return self._provider.complete(prompt, model=self._model, max_tokens=max_tokens)
        response = self._provider.judge(prompt, model=self._model)
        return response.get("reasoning", "")

    def _predict_ground_truth(self, adf_json: dict) -> dict:
        """Use LLM to predict expected dimension scores."""
        prompt = _GROUND_TRUTH_PROMPT.format(
            pipeline_json=json.dumps(adf_json, indent=2)[:4000],
        )
        try:
            response = self._provider.judge(prompt, model=self._model)
            return _extract_json(response.get("reasoning", "")) or {}
        except Exception:
            return _estimate_ground_truth(adf_json)


@dataclass(frozen=True, slots=True)
class FailureRecord:
    """A recorded failure from running wkmigrate on a generated pipeline."""
    pipeline_name: str
    dimension: str
    score: float
    error: str
    adf_json: dict = field(default_factory=dict)


class FailureFeedback:
    """Learn from converter failures to generate more targeted test cases."""

    def __init__(self):
        self.failures: list[FailureRecord] = []

    def record(self, record: FailureRecord) -> None:
        self.failures.append(record)

    def suggest_config(self) -> GenerationConfig:
        """Analyze failures and suggest generation config targeting weak areas."""
        if not self.failures:
            return GenerationConfig()

        # Count failures by dimension
        dim_counts: dict[str, int] = {}
        for f in self.failures:
            dim_counts[f.dimension] = dim_counts.get(f.dimension, 0) + 1

        # Target the most-failing dimensions
        worst_dims = sorted(dim_counts, key=dim_counts.get, reverse=True)[:3]

        weak_spots = []
        for dim in worst_dims:
            if dim == "expression_coverage":
                weak_spots.extend(["nested_expressions", "math_on_params"])
            elif dim == "activity_coverage":
                weak_spots.append("unsupported_types")
            elif dim == "dependency_preservation":
                weak_spots.append("deep_nesting")
            elif dim == "notebook_validity":
                weak_spots.append("parameterized_paths")
            else:
                weak_spots.append("nested_expressions")

        return GenerationConfig(
            target_weak_spots=tuple(weak_spots[:4]) or ("nested_expressions",),
            include_unsupported="unsupported_types" in weak_spots,
            extra_instructions=f"Focus on patterns that cause failures in: {', '.join(worst_dims)}",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from LLM output.

    Handles markdown code blocks, JSON arrays, and structurally broken JSON
    (e.g. unescaped quotes in ADF SQL expressions) using ``json_repair``.
    """
    if not text:
        return None
    # Strip markdown code blocks
    text = re.sub(r"```json?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # Fast path: try direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    return item
    except json.JSONDecodeError:
        pass

    # Repair path: use json_repair for LLM-generated malformed JSON
    # (handles unescaped quotes, missing commas, trailing commas, etc.)
    try:
        from json_repair import repair_json
        repaired = repair_json(text, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
        if isinstance(repaired, list):
            for item in repaired:
                if isinstance(item, dict):
                    return item
    except Exception:
        pass

    # Last resort: find a JSON object substring
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            obj = json.loads(match.group())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                repaired = repair_json(match.group(), return_objects=True)
                if isinstance(repaired, dict):
                    return repaired
            except Exception:
                pass
    return None


def _estimate_ground_truth(adf_json: dict) -> dict:
    """Estimate ground truth without LLM — deterministic fallback."""
    activities = adf_json.get("properties", {}).get("activities", [])
    if not activities:
        activities = adf_json.get("activities", [])

    total = max(len(activities), 1)
    supported = sum(1 for a in activities if a.get("type") in _SUPPORTED_TYPES)
    unsupported = len(activities) - supported

    return {
        "activity_coverage": supported / total,
        "expression_coverage": 0.8,  # conservative estimate
        "dependency_preservation": 1.0,
        "notebook_validity": 1.0 if unsupported == 0 else 0.9,
        "parameter_completeness": 1.0,
        "secret_completeness": 1.0,
        "not_translatable_ratio": max(0.5, 1.0 - unsupported * 0.1),
    }


def _is_adf_pipeline(obj: dict) -> bool:
    """Check if a JSON object looks like an ADF pipeline definition."""
    # Must have activities (either at top level or under properties)
    props = obj.get("properties", obj)
    activities = props.get("activities")
    if isinstance(activities, list) and len(activities) > 0:
        # At least one activity should have a "type" field
        return any(isinstance(a, dict) and "type" in a for a in activities)
    return False


def _extract_parameters(adf_json: dict) -> tuple[str, ...]:
    """Extract parameter names from the generated pipeline JSON."""
    params = adf_json.get("properties", {}).get("parameters", {})
    if isinstance(params, dict):
        return tuple(params.keys())
    if isinstance(params, list):
        return tuple(p.get("name", "") for p in params if isinstance(p, dict) and p.get("name"))
    return ()


def _build_expected_snapshot(
    adf_json: dict,
) -> ConversionSnapshot:
    """Build an expected ConversionSnapshot from the generated pipeline."""
    activities = adf_json.get("properties", {}).get("activities", [])
    if not activities:
        activities = adf_json.get("activities", [])

    tasks = tuple(
        TaskSnapshot(
            task_key=a.get("name", f"task_{i}"),
            is_placeholder=a.get("type") not in _SUPPORTED_TYPES,
        )
        for i, a in enumerate(activities)
    )

    # Derive parameters from the pipeline, not from config
    parameters = _extract_parameters(adf_json)

    # Store both task-level expected outputs and predicted dimension scores
    expected_outputs = {
        t.task_key: f"expected_output_{i}"
        for i, t in enumerate(tasks)
        if not t.is_placeholder
    }
    # Include deterministic ground-truth estimates as metadata
    gt = _estimate_ground_truth(adf_json)
    if gt:
        expected_outputs["__predicted_dimensions__"] = json.dumps(gt)

    return ConversionSnapshot(
        tasks=tasks,
        notebooks=(),
        secrets=(),
        parameters=parameters,
        dependencies=(),
        not_translatable=(),
        resolved_expressions=(),
        source_pipeline=adf_json,
        total_source_dependencies=sum(
            len(a.get("depends_on", a.get("dependsOn", [])))
            for a in activities
        ),
        expected_outputs=expected_outputs,
    )
