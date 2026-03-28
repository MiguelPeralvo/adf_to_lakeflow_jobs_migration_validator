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

_GENERATION_PROMPT = """You are an Azure Data Factory expert. Generate a realistic ADF pipeline JSON
definition that would stress-test an ADF-to-Databricks migration tool.

Requirements:
- Valid ADF pipeline JSON: {{"name": "...", "properties": {{"parameters": {{...}}, "variables": {{...}}, "activities": [...]}}}}
- Include {activity_count} activities using these types: {activity_types}
- Include dependency chains between activities (depends_on with Succeeded conditions)
- Use these ADF expression patterns in activity properties: {expression_patterns}
- Include pipeline parameters: {parameters}
- Target this stress area: {target_description}
{extra_instructions}

CRITICAL: Output ONLY valid JSON. No markdown, no explanation, no code blocks. Just the JSON object."""

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
        model: str = "chatgpt-5-4",
        max_retries: int = 2,
    ):
        self._provider = judge_provider
        self._model = model
        self._max_retries = max_retries

    def generate(
        self,
        count: int = 10,
        config: GenerationConfig | None = None,
    ) -> list[SyntheticPipeline]:
        """Generate synthetic pipelines using the LLM."""
        cfg = config or GenerationConfig()
        pipelines: list[SyntheticPipeline] = []

        for i in range(count):
            # Rotate through weak spots
            weak_spot_key = cfg.target_weak_spots[i % len(cfg.target_weak_spots)]
            target_desc = _WEAK_SPOTS.get(weak_spot_key, weak_spot_key)

            activity_types = list(cfg.activity_types)
            if cfg.include_unsupported and i % 3 == 0:
                activity_types.append("AzureFunctionActivity")

            prompt = _GENERATION_PROMPT.format(
                activity_count=cfg.activity_count + (i % 3),
                activity_types=", ".join(activity_types),
                expression_patterns=target_desc,
                parameters=", ".join(cfg.parameters),
                target_description=target_desc,
                extra_instructions=cfg.extra_instructions,
            )

            adf_json = self._generate_one(prompt, pipeline_index=i)
            if adf_json is None:
                continue

            snapshot = _build_expected_snapshot(adf_json)

            pipelines.append(SyntheticPipeline(
                adf_json=adf_json,
                expected_snapshot=snapshot,
                description=f"LLM-generated pipeline targeting {weak_spot_key} (#{i})",
                difficulty="llm",
            ))

        return pipelines

    def _generate_one(self, prompt: str, pipeline_index: int) -> dict | None:
        """Call LLM and parse JSON response, with retries."""
        for attempt in range(self._max_retries + 1):
            try:
                response = self._provider.judge(prompt, model=self._model)
                raw_text = response.get("reasoning", "")
                adf_json = _extract_json(raw_text)
                if adf_json is None:
                    continue  # retry — LLM returned non-JSON
                if not _is_adf_pipeline(adf_json):
                    continue  # retry — JSON is not an ADF pipeline
                if "name" not in adf_json:
                    adf_json["name"] = f"llm_pipeline_{pipeline_index:03d}"
                return adf_json
            except Exception:
                continue
        return None

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
    """Extract a JSON object from LLM output, handling markdown code blocks."""
    if not text:
        return None
    # Strip markdown code blocks
    text = re.sub(r"```json?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                obj = json.loads(match.group())
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
    return None


def _estimate_ground_truth(adf_json: dict) -> dict:
    """Estimate ground truth without LLM — deterministic fallback."""
    activities = adf_json.get("properties", {}).get("activities", [])
    if not activities:
        activities = adf_json.get("activities", [])

    total = max(len(activities), 1)
    supported = sum(1 for a in activities if a.get("type") in _SUPPORTED_TYPES)
    unsupported = total - supported

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

    expected_outputs = {
        t.task_key: f"expected_output_{i}"
        for i, t in enumerate(tasks)
        if not t.is_placeholder
    }

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
