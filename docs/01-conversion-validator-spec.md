# Detailed Spec: Lakeflow Migration Validator (`lakeflow-migration-validator`)

> **Package:** `lakeflow_migration_validator` (alias: `lmv`)
> **Scope:** Full technical design for the Lakeflow Migration Validator (System 1),
> written so that every class is extractable into the Validator Factory (System 3).
>
> **LLM backend:** Databricks FMAPI
> - **Opus 4.6** (`claude-opus-4-6`): semantic equivalence judge (calibration, nightly), fix suggestions, DSPy optimization
> - **ChatGPT 5.4** (`chatgpt-5-4`): semantic equivalence judge (batch CI), synthetic test generation

---

## 1. Architecture

### Module layout

### Layered architecture

```
┌───────────────────────────────────────────────────────────────┐
│                    SURFACE LAYER (how users interact)          │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ Databricks│  │   MCP    │  │ REST API │  │   CLI    │     │
│  │    App    │  │  Server  │  │ (FastAPI)│  │ (Typer)  │     │
│  │ (primary) │  │          │  │          │  │(secondary│     │
│  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│        └──────────────┴─────────────┴──────────────┘          │
│                            │                                   │
│                    ┌───────▼──────┐                            │
│                    │  Python API  │ evaluate_pipeline()        │
│                    │   (core)     │ evaluate_batch()           │
│                    └───────┬──────┘ regression_check()         │
│                            │                                   │
├────────────────────────────┼───────────────────────────────────┤
│                    DIMENSION LAYER (scoring logic)             │
│                            │                                   │
│  ┌─────────────────────────▼─────────────────────────┐        │
│  │ Tiers 1-2: Programmatic + Structural (8 dims)     │        │
│  │ Tier 3:    LLM Judge — FMAPI (Opus 4.6/GPT 5.4)  │        │
│  │ Tier 4:    Execution — Databricks Jobs API        │        │
│  └───────────────────────────────────────────────────┘        │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│                    INFRASTRUCTURE LAYER                        │
│                                                               │
│  MLflow (tracking)  │  FMAPI (LLM)  │  Databricks (execution)│
└───────────────────────────────────────────────────────────────┘
```

### Module layout

```
src/wkmigrate/
  validation/                           # Core library (Python API)
    __init__.py                         # Public API: evaluate_pipeline, ConversionScorecard
    dimensions/
      __init__.py                       # Dimension protocol + DimensionResult
      programmatic.py                   # ProgrammaticCheck base class
      llm_judge.py                      # LLMJudge base class + JudgeProvider protocol
      execution.py                      # ExecutionDimension base class + ExecutionRunner protocol
      # --- Concrete dimensions (deterministic, Tiers 1-2) ---
      activity_coverage.py              # compute_activity_coverage()
      expression_coverage.py            # compute_expression_coverage()
      dependency_preservation.py        # compute_dependency_preservation()
      notebook_validity.py              # compute_notebook_validity()
      parameter_completeness.py         # compute_parameter_completeness()
      secret_completeness.py            # compute_secret_completeness()
      not_translatable_ratio.py         # compute_not_translatable_ratio()
      control_flow_fidelity.py          # compute_control_flow_fidelity()
      # --- Agentic dimensions (LLM-powered, Tier 3) ---
      semantic_equivalence.py           # LLMJudge: ADF expr ↔ Python semantic comparison
      # --- Execution dimensions (Tier 4) ---
      runtime_success.py                # ExecutionDimension: Databricks job run
    providers/
      __init__.py                       # Provider protocols
      fmapi.py                          # FMAPIJudgeProvider (Opus 4.6 + ChatGPT 5.4)
      databricks_runner.py              # DatabricksJobRunner (ExecutionRunner impl)
    optimization/                       # DSPy-powered components (opt-in)
      __init__.py
      judge_optimizer.py                # DSPy MIPROv2/SIMBA judge prompt optimization
      synthetic_generator.py            # LLM-based ADF expression generation
      fix_suggester.py                  # dspy.Refine fix suggestion agent
    scorecard.py                        # Scorecard + CCS computation
    golden_set.py                       # GoldenSet loader
    report.py                           # Report + regression checking
    tracking.py                         # MLflow integration

apps/lmv/                              # Databricks App (primary surface)
  backend/
    main.py                             # FastAPI: /api/validate, /api/history, etc.
    models.py                           # Request/response Pydantic models
  frontend/
    src/
      pages/
        Validate.tsx                    # Upload ADF JSON → scorecard dashboard
        History.tsx                     # Compare scorecards over time
        ExpressionDetail.tsx            # Per-expression semantic judge drill-down
      components/
        ScorecardCard.tsx               # CCS gauge + per-dimension score bars
        DimensionDrilldown.tsx          # Expandable details per dimension
        NotebookViewer.tsx              # Syntax-highlighted generated notebook source
  app.yaml                              # Databricks App deployment config

  mcp_server.py                         # MCP surface: validate_pipeline, judge_expression, etc.
  cli.py                                # CLI surface: lmv evaluate, lmv judge-expression, etc.
```

### Design constraints (factory-extractable)

Every class in `validation/` must follow these rules:

1. **No wkmigrate-specific imports in the base protocols.** `Dimension`, `DimensionResult`,
   `Scorecard`, `GoldenSet`, `Report` must be generic. wkmigrate-specific logic lives only
   in the concrete dimension implementations (e.g., `activity_coverage.py`).

2. **Dependency injection for externals.** LLM calls go through a `JudgeProvider` protocol.
   MLflow tracking goes through a `TrackingBackend` protocol. Databricks execution goes
   through an `ExecutionRunner` protocol. No direct imports of `mlflow`, `databricks.sdk`,
   or LLM SDKs in the dimension implementations.

3. **Frozen dataclasses for results.** `DimensionResult`, `Scorecard`, `Report` are
   `@dataclass(frozen=True, slots=True)` — immutable, serializable, testable.

4. **Pure functions for checks.** Each programmatic dimension exposes a top-level function
   `compute_<dimension>(source_pipeline, prepared_workflow) -> float` that can be tested
   independently of the validator framework.

---

## 2. Technical Design

### 2.1 Core protocols (factory-extractable)

```python
# validation/dimensions/__init__.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class DimensionResult:
    """Result of evaluating a single quality dimension."""
    name: str
    score: float                          # 0.0 - 1.0
    passed: bool                          # score >= threshold
    details: dict[str, Any] = field(default_factory=dict)


class Dimension(Protocol):
    """Protocol for a quality dimension that can evaluate an input/output pair."""
    name: str
    threshold: float

    def evaluate(self, input: Any, output: Any) -> DimensionResult: ...
```

### 2.2 ProgrammaticCheck

```python
# validation/dimensions/programmatic.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from wkmigrate.validation.dimensions import Dimension, DimensionResult


@dataclass(frozen=True, slots=True)
class ProgrammaticCheck:
    """A dimension computed by a pure Python function."""
    name: str
    check_fn: Callable[[Any, Any], float | tuple[float, dict[str, Any]]]
    threshold: float = 0.0

    def evaluate(self, input: Any, output: Any) -> DimensionResult:
        result = self.check_fn(input, output)
        if isinstance(result, tuple):
            score, details = result
        else:
            score, details = result, {}
        return DimensionResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            details=details,
        )
```

### 2.3 Concrete programmatic dimensions

Each dimension is a module with a single public function:

```python
# validation/dimensions/activity_coverage.py

from __future__ import annotations
from wkmigrate.models.workflows.artifacts import PreparedWorkflow

_PLACEHOLDER_PATH = "/UNSUPPORTED_ADF_ACTIVITY"


def compute_activity_coverage(source: dict, prepared: PreparedWorkflow) -> tuple[float, dict]:
    """Fraction of tasks that are not placeholder activities."""
    total = len(prepared.activities)
    if total == 0:
        return 1.0, {"total": 0, "covered": 0, "placeholders": []}

    placeholders = []
    for activity in prepared.activities:
        notebook_task = activity.task.get("notebook_task", {})
        if notebook_task.get("notebook_path") == _PLACEHOLDER_PATH:
            placeholders.append(activity.task.get("task_key", "unknown"))

    covered = total - len(placeholders)
    return covered / total, {
        "total": total,
        "covered": covered,
        "placeholders": placeholders,
    }
```

```python
# validation/dimensions/notebook_validity.py

from __future__ import annotations
from wkmigrate.models.workflows.artifacts import PreparedWorkflow


def compute_notebook_validity(source: dict, prepared: PreparedWorkflow) -> tuple[float, dict]:
    """Fraction of generated notebooks that compile without SyntaxError."""
    notebooks = list(prepared.all_notebooks)
    if not notebooks:
        return 1.0, {"total": 0, "valid": 0, "errors": []}

    errors = []
    for nb in notebooks:
        try:
            compile(nb.content, nb.file_path, "exec")
        except SyntaxError as e:
            errors.append({"file_path": nb.file_path, "error": str(e)})

    valid = len(notebooks) - len(errors)
    return valid / len(notebooks), {
        "total": len(notebooks),
        "valid": valid,
        "errors": errors,
    }
```

```python
# validation/dimensions/parameter_completeness.py

from __future__ import annotations
import re
from wkmigrate.models.workflows.artifacts import PreparedWorkflow
from wkmigrate.models.ir.pipeline import Pipeline

_WIDGET_GET_PATTERN = re.compile(r"dbutils\.widgets\.get\(['\"](\w+)['\"]\)")


def compute_parameter_completeness(source: dict, prepared: PreparedWorkflow) -> tuple[float, dict]:
    """Fraction of dbutils.widgets.get references that have matching job parameters."""
    pipeline: Pipeline = prepared.pipeline
    defined_params = set()
    if pipeline.parameters:
        for param in pipeline.parameters:
            defined_params.add(param.get("name", ""))

    referenced_params = set()
    for nb in prepared.all_notebooks:
        for match in _WIDGET_GET_PATTERN.finditer(nb.content):
            referenced_params.add(match.group(1))

    if not referenced_params:
        return 1.0, {"defined": sorted(defined_params), "referenced": [], "missing": []}

    missing = referenced_params - defined_params
    score = (len(referenced_params) - len(missing)) / len(referenced_params)
    return score, {
        "defined": sorted(defined_params),
        "referenced": sorted(referenced_params),
        "missing": sorted(missing),
    }
```

```python
# validation/dimensions/secret_completeness.py

from __future__ import annotations
import re
from wkmigrate.models.workflows.artifacts import PreparedWorkflow

_SECRET_GET_PATTERN = re.compile(
    r'dbutils\.secrets\.get\(\s*scope=["\']([^"\']+)["\'],\s*key=["\']([^"\']+)["\']\)'
)


def compute_secret_completeness(source: dict, prepared: PreparedWorkflow) -> tuple[float, dict]:
    """Fraction of dbutils.secrets.get references that have matching SecretInstructions."""
    secret_instructions = {(s.scope, s.key) for s in prepared.all_secrets}

    referenced_secrets = set()
    for nb in prepared.all_notebooks:
        for match in _SECRET_GET_PATTERN.finditer(nb.content):
            referenced_secrets.add((match.group(1), match.group(2)))

    if not referenced_secrets:
        return 1.0, {"defined": [], "referenced": [], "missing": []}

    missing = referenced_secrets - secret_instructions
    score = (len(referenced_secrets) - len(missing)) / len(referenced_secrets)
    return score, {
        "defined": sorted(str(s) for s in secret_instructions),
        "referenced": sorted(str(s) for s in referenced_secrets),
        "missing": sorted(str(s) for s in missing),
    }
```

```python
# validation/dimensions/dependency_preservation.py

from __future__ import annotations
from wkmigrate.models.workflows.artifacts import PreparedWorkflow


def compute_dependency_preservation(source: dict, prepared: PreparedWorkflow) -> tuple[float, dict]:
    """Fraction of ADF depends_on entries that have corresponding Databricks task dependencies."""
    adf_activities = source.get("activities") or source.get("properties", {}).get("activities", [])
    total_deps = 0
    preserved_deps = 0
    missing = []

    ir_task_keys = {task.task_key for task in prepared.pipeline.tasks}

    for adf_activity in adf_activities:
        for dep in adf_activity.get("depends_on", []):
            dep_name = dep.get("activity")
            if dep_name:
                total_deps += 1
                if dep_name in ir_task_keys:
                    preserved_deps += 1
                else:
                    missing.append({"activity": adf_activity.get("name"), "depends_on": dep_name})

    if total_deps == 0:
        return 1.0, {"total": 0, "preserved": 0, "missing": []}

    return preserved_deps / total_deps, {
        "total": total_deps,
        "preserved": preserved_deps,
        "missing": missing,
    }
```

```python
# validation/dimensions/expression_coverage.py

from __future__ import annotations
from wkmigrate.models.ir.pipeline import Pipeline


def compute_expression_coverage(source: dict, prepared) -> tuple[float, dict]:
    """Fraction of ADF expression properties that were successfully resolved."""
    pipeline: Pipeline = prepared.pipeline
    total_expressions = 0
    resolved_expressions = 0
    unsupported = []

    # Count not_translatable entries related to expressions
    for entry in pipeline.not_translatable:
        if "expression" in entry.get("message", "").lower() or "unsupported" in entry.get("message", "").lower():
            total_expressions += 1
            unsupported.append(entry)

    # Count resolved expressions (activities that are NOT placeholders)
    for task in pipeline.tasks:
        if hasattr(task, "variable_value"):
            total_expressions += 1
            resolved_expressions += 1

    total = total_expressions + resolved_expressions if total_expressions > 0 else resolved_expressions
    if total == 0:
        return 1.0, {"total": 0, "resolved": 0, "unsupported": []}

    score = resolved_expressions / total if total > 0 else 1.0
    return score, {
        "total": total,
        "resolved": resolved_expressions,
        "unsupported": unsupported,
    }
```

```python
# validation/dimensions/not_translatable_ratio.py

from __future__ import annotations
from wkmigrate.models.workflows.artifacts import PreparedWorkflow


def compute_not_translatable_ratio(source: dict, prepared: PreparedWorkflow) -> tuple[float, dict]:
    """Inverse ratio of not-translatable warnings to total properties."""
    count = len(prepared.pipeline.not_translatable)
    # Estimate total properties from activity count * average properties per activity
    total_tasks = len(prepared.pipeline.tasks)
    estimated_properties = max(total_tasks * 5, 1)  # rough estimate
    ratio = count / estimated_properties
    score = max(0.0, 1.0 - ratio)
    return score, {
        "not_translatable_count": count,
        "estimated_total_properties": estimated_properties,
        "entries": prepared.pipeline.not_translatable,
    }
```

### 2.4 LLMJudge

```python
# validation/dimensions/llm_judge.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from wkmigrate.validation.dimensions import Dimension, DimensionResult


class JudgeProvider(Protocol):
    """Protocol for calling an LLM judge via Databricks FMAPI."""
    def judge(self, prompt: str, model: str | None = None) -> dict[str, Any]:
        """Returns {"score": float, "reasoning": str}.

        Args:
            prompt: The judge prompt.
            model: Optional model override. If None, uses the provider's default.
        """
        ...


class FMAPIJudgeProvider:
    """JudgeProvider backed by Databricks Foundation Model API.

    Supports model routing: high-stakes judgments use Opus 4.6 for maximum
    reasoning quality; batch scoring uses ChatGPT 5.4 for throughput/cost.
    """
    def __init__(
        self,
        endpoint: str,                              # FMAPI serving endpoint URL
        high_stakes_model: str = "claude-opus-4-6",  # calibration, nightly eval
        batch_model: str = "chatgpt-5-4",            # CI, large corpora
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ): ...

    def judge(self, prompt: str, model: str | None = None) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class LLMJudge:
    """A dimension evaluated by an LLM judge via Databricks FMAPI.

    Uses Opus 4.6 for high-stakes calibration and nightly eval.
    Uses ChatGPT 5.4 for batch CI scoring.
    """
    name: str
    criteria: str
    input_template: str
    provider: JudgeProvider
    calibration_examples: tuple[dict, ...] = ()
    threshold: float = 0.7
    model: str = "claude-opus-4-6"  # default to Opus for highest quality

    def evaluate(self, input: Any, output: Any) -> DimensionResult:
        prompt = self._build_prompt(input, output)
        response = self.provider.judge(prompt)
        score = response.get("score", 0.0)
        return DimensionResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            details={"reasoning": response.get("reasoning", ""), "model": self.model},
        )

    def _build_prompt(self, input: Any, output: Any) -> str:
        examples_block = ""
        if self.calibration_examples:
            examples_block = "Examples:\n" + "\n".join(
                f"- Input: {ex['input']}\n  Output: {ex['output']}\n  Score: {ex['score']}"
                for ex in self.calibration_examples
            ) + "\n\n"

        return (
            f"You are an evaluation judge. Score the following output on a scale of 0.0 to 1.0.\n\n"
            f"Criteria: {self.criteria}\n\n"
            f"{examples_block}"
            f"{self.input_template.format(input=input, output=output)}\n\n"
            f"Respond with JSON: {{\"score\": <float>, \"reasoning\": \"<explanation>\"}}"
        )
```

### 2.5 ExecutionDimension

```python
# validation/dimensions/execution.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from wkmigrate.validation.dimensions import Dimension, DimensionResult


class ExecutionRunner(Protocol):
    """Protocol for running a prepared workflow and collecting results."""
    def run(self, output: Any, params: dict[str, str]) -> dict[str, Any]:
        """Returns {task_key: {"success": bool, "error": str | None}}."""
        ...


@dataclass(frozen=True, slots=True)
class ExecutionDimension:
    """A dimension that deploys and runs the output on a real environment."""
    name: str
    runner: ExecutionRunner
    test_params: dict[str, str] = ()
    threshold: float = 1.0

    def evaluate(self, input: Any, output: Any) -> DimensionResult:
        results = self.runner.run(output, params=dict(self.test_params))
        if not results:
            return DimensionResult(name=self.name, score=0.0, passed=False,
                                   details={"error": "no tasks returned"})
        successes = sum(1 for r in results.values() if r.get("success"))
        score = successes / len(results)
        return DimensionResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            details={"task_results": results},
        )
```

### 2.6 Scorecard

```python
# validation/scorecard.py

from __future__ import annotations
from dataclasses import dataclass, field
from wkmigrate.validation.dimensions import DimensionResult


@dataclass(frozen=True, slots=True)
class Scorecard:
    """Weighted aggregation of dimension results into a single score."""
    weights: dict[str, float]
    results: dict[str, DimensionResult] = field(default_factory=dict)
    score: float = 0.0

    @classmethod
    def compute(cls, weights: dict[str, float], results: dict[str, DimensionResult]) -> Scorecard:
        total_weight = sum(weights.get(name, 0) for name in results)
        if total_weight == 0:
            return cls(weights=weights, results=results, score=0.0)
        raw = sum(
            results[name].score * weights.get(name, 0)
            for name in results
            if name in weights
        )
        score = (raw / total_weight) * 100
        return cls(weights=weights, results=results, score=score)

    @property
    def label(self) -> str:
        if self.score >= 90:
            return "HIGH_CONFIDENCE"
        if self.score >= 70:
            return "REVIEW_RECOMMENDED"
        return "MANUAL_INTERVENTION"

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results.values())

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "label": self.label,
            "dimensions": {
                name: {"score": r.score, "passed": r.passed, "details": r.details}
                for name, r in self.results.items()
            },
        }
```

### 2.7 ConversionScorecard (wkmigrate-specific entry point)

```python
# validation/__init__.py

from __future__ import annotations
from typing import Any
from wkmigrate.models.ir.pipeline import Pipeline
from wkmigrate.models.workflows.artifacts import PreparedWorkflow
from wkmigrate.validation.dimensions import DimensionResult
from wkmigrate.validation.dimensions.programmatic import ProgrammaticCheck
from wkmigrate.validation.dimensions.activity_coverage import compute_activity_coverage
from wkmigrate.validation.dimensions.notebook_validity import compute_notebook_validity
from wkmigrate.validation.dimensions.parameter_completeness import compute_parameter_completeness
from wkmigrate.validation.dimensions.secret_completeness import compute_secret_completeness
from wkmigrate.validation.dimensions.dependency_preservation import compute_dependency_preservation
from wkmigrate.validation.dimensions.expression_coverage import compute_expression_coverage
from wkmigrate.validation.dimensions.not_translatable_ratio import compute_not_translatable_ratio
from wkmigrate.validation.scorecard import Scorecard

_DEFAULT_WEIGHTS = {
    "activity_coverage": 0.25,
    "expression_coverage": 0.20,
    "dependency_preservation": 0.15,
    "notebook_validity": 0.15,
    "parameter_completeness": 0.10,
    "secret_completeness": 0.10,
    "not_translatable_ratio": 0.05,
}

_DIMENSIONS = [
    ProgrammaticCheck("activity_coverage", compute_activity_coverage),
    ProgrammaticCheck("expression_coverage", compute_expression_coverage),
    ProgrammaticCheck("dependency_preservation", compute_dependency_preservation),
    ProgrammaticCheck("notebook_validity", compute_notebook_validity),
    ProgrammaticCheck("parameter_completeness", compute_parameter_completeness),
    ProgrammaticCheck("secret_completeness", compute_secret_completeness),
    ProgrammaticCheck("not_translatable_ratio", compute_not_translatable_ratio),
]


def evaluate_pipeline(source_pipeline: dict, prepared_workflow: PreparedWorkflow) -> Scorecard:
    """Evaluate a conversion and return a Scorecard with the Conversion Confidence Score."""
    results: dict[str, DimensionResult] = {}
    for dim in _DIMENSIONS:
        results[dim.name] = dim.evaluate(source_pipeline, prepared_workflow)
    return Scorecard.compute(_DEFAULT_WEIGHTS, results)
```

---

## 3. Test Suite (TDD)

Tests are written **before implementation**. Each test file corresponds to a dimension or
component. All tests use pytest and follow wkmigrate's existing patterns.

### 3.1 Test file layout

```
tests/unit/validation/
    __init__.py
    test_activity_coverage.py
    test_expression_coverage.py
    test_dependency_preservation.py
    test_notebook_validity.py
    test_parameter_completeness.py
    test_secret_completeness.py
    test_not_translatable_ratio.py
    test_scorecard.py
    test_evaluate_pipeline.py
```

### 3.2 Test specifications

#### `test_activity_coverage.py`

```python
"""TDD tests for the activity coverage dimension."""

def test_all_activities_translated_returns_1():
    """A workflow with no placeholder activities scores 1.0."""

def test_all_activities_placeholder_returns_0():
    """A workflow where every task points to /UNSUPPORTED_ADF_ACTIVITY scores 0.0."""

def test_mixed_activities_returns_fraction():
    """3 real + 1 placeholder = 0.75."""

def test_empty_workflow_returns_1():
    """A workflow with no activities scores 1.0 (vacuously true)."""

def test_details_list_placeholder_task_keys():
    """The details dict lists the task_keys of placeholder activities."""
```

#### `test_notebook_validity.py`

```python
"""TDD tests for the notebook validity dimension."""

def test_valid_notebook_scores_1():
    """A single syntactically valid notebook scores 1.0."""

def test_invalid_notebook_scores_0():
    """A single notebook with a SyntaxError scores 0.0."""

def test_mixed_notebooks_returns_fraction():
    """2 valid + 1 invalid = 0.667."""

def test_no_notebooks_scores_1():
    """A workflow with no notebooks scores 1.0."""

def test_details_list_error_file_paths():
    """The details dict lists file_path and error for each invalid notebook."""
```

#### `test_parameter_completeness.py`

```python
"""TDD tests for the parameter completeness dimension."""

def test_all_params_defined_scores_1():
    """Every dbutils.widgets.get reference has a matching JobParameterDefinition."""

def test_missing_param_lowers_score():
    """A notebook references param 'X' but pipeline.parameters has no 'X' -> score < 1.0."""

def test_no_widget_references_scores_1():
    """A notebook with no dbutils.widgets.get calls scores 1.0."""

def test_details_list_missing_params():
    """The details dict lists the missing parameter names."""

def test_multiple_notebooks_aggregate_references():
    """References across all notebooks are collected, not just the first."""
```

#### `test_secret_completeness.py`

```python
"""TDD tests for the secret completeness dimension."""

def test_all_secrets_defined_scores_1():
    """Every dbutils.secrets.get reference has a matching SecretInstruction."""

def test_missing_secret_lowers_score():
    """A notebook references (scope, key) not in secrets -> score < 1.0."""

def test_no_secret_references_scores_1():
    """A notebook with no dbutils.secrets.get calls scores 1.0."""

def test_details_list_missing_scope_key_pairs():
    """The details dict lists the missing (scope, key) pairs."""
```

#### `test_dependency_preservation.py`

```python
"""TDD tests for the dependency preservation dimension."""

def test_all_deps_preserved_scores_1():
    """Every ADF depends_on entry has a corresponding IR Dependency."""

def test_missing_dep_lowers_score():
    """An ADF depends_on entry with no matching IR task_key -> score < 1.0."""

def test_no_deps_scores_1():
    """A pipeline with no depends_on entries scores 1.0."""

def test_details_list_missing_deps():
    """The details dict lists which activities lost which dependencies."""
```

#### `test_expression_coverage.py`

```python
"""TDD tests for the expression coverage dimension."""

def test_all_expressions_resolved_scores_1():
    """A pipeline with only SetVariableActivity tasks (all resolved) scores 1.0."""

def test_unsupported_expressions_lower_score():
    """not_translatable entries mentioning 'expression' reduce the score."""

def test_no_expressions_scores_1():
    """A pipeline with no expression properties scores 1.0."""
```

#### `test_not_translatable_ratio.py`

```python
"""TDD tests for the not-translatable ratio dimension."""

def test_no_warnings_scores_1():
    """An empty not_translatable list scores 1.0."""

def test_many_warnings_lowers_score():
    """A pipeline with many not_translatable entries scores below 1.0."""

def test_details_include_entries():
    """The details dict includes the not_translatable list."""
```

#### `test_scorecard.py`

```python
"""TDD tests for the Scorecard aggregation."""

def test_perfect_scores_produce_100():
    """All dimensions at 1.0 with any weights -> score 100."""

def test_zero_scores_produce_0():
    """All dimensions at 0.0 -> score 0."""

def test_weighted_aggregation_is_correct():
    """Specific dimension scores with known weights produce expected aggregate."""

def test_label_high_confidence_above_90():
    """Score >= 90 -> 'HIGH_CONFIDENCE'."""

def test_label_review_recommended_70_to_89():
    """Score 70-89 -> 'REVIEW_RECOMMENDED'."""

def test_label_manual_intervention_below_70():
    """Score < 70 -> 'MANUAL_INTERVENTION'."""

def test_all_passed_true_when_all_above_threshold():
    """all_passed is True when every dimension passes its threshold."""

def test_all_passed_false_when_any_below_threshold():
    """all_passed is False when any dimension is below its threshold."""

def test_to_dict_is_serializable():
    """to_dict() returns a JSON-serializable dict."""
```

#### `test_evaluate_pipeline.py`

```python
"""TDD tests for the top-level evaluate_pipeline function."""

def test_evaluate_returns_scorecard():
    """evaluate_pipeline returns a Scorecard instance."""

def test_evaluate_includes_all_7_dimensions():
    """The scorecard has results for all 7 programmatic dimensions."""

def test_evaluate_perfect_pipeline_scores_above_90():
    """A well-translated pipeline (no placeholders, valid notebooks, complete params) scores >= 90."""

def test_evaluate_degraded_pipeline_scores_below_70():
    """A pipeline with mostly placeholders and missing params scores < 70."""

def test_evaluate_works_with_real_fixtures():
    """Run evaluate_pipeline against the existing test_pipeline_integration fixtures."""
```

#### `test_api.py`

```python
"""TDD tests for the FastAPI REST surface."""

def test_post_validate_returns_scorecard():
    """POST /api/validate with ADF JSON returns a scorecard response."""

def test_post_validate_invalid_json_returns_422():
    """POST /api/validate with invalid JSON returns HTTP 422."""

def test_post_validate_expression_returns_judge_result():
    """POST /api/validate/expression returns score + reasoning."""

def test_get_history_returns_past_scorecards():
    """GET /api/history/{pipeline_name} returns a list of past scorecards."""

def test_post_validate_batch_returns_report():
    """POST /api/validate/batch with golden set returns a Report."""
```

#### `test_mcp_server.py`

```python
"""TDD tests for the MCP tool surface."""

def test_validate_pipeline_tool_returns_scorecard_dict():
    """MCP tool 'validate_pipeline' returns a serialized scorecard."""

def test_validate_expression_tool_returns_score_and_reasoning():
    """MCP tool 'validate_expression' returns {score, reasoning}."""

def test_suggest_fix_tool_returns_suggestion():
    """MCP tool 'suggest_fix' returns a code suggestion string."""

def test_missing_adf_json_returns_error():
    """MCP tool with empty input returns an error message, not an exception."""
```

#### `test_cli.py`

```python
"""TDD tests for the Typer CLI surface."""

def test_evaluate_writes_scorecard_json(tmp_path):
    """'lmv evaluate --adf-json ... --output ...' writes a valid JSON scorecard."""

def test_evaluate_batch_prints_report(capsys):
    """'lmv evaluate-batch --golden-set ...' prints aggregate scores."""

def test_regression_check_exits_0_on_pass():
    """'lmv regression-check' exits 0 when no regression detected."""

def test_regression_check_exits_1_on_regression():
    """'lmv regression-check' exits 1 when regression detected."""
```

---

## 4. Implementation Plan

### Week 1: Core library — programmatic dimensions + Scorecard

| Day | Task |
|---|---|
| 1 | Write all TDD test files (empty test functions with docstrings). Confirm all tests fail. |
| 2 | Implement `DimensionResult`, `Dimension` protocol, `ProgrammaticCheck` class. |
| 3 | Implement `activity_coverage`, `notebook_validity`, `parameter_completeness`, `secret_completeness`. Run tests — 4 dimension test files should pass. |
| 4 | Implement `dependency_preservation`, `expression_coverage`, `not_translatable_ratio`. Run tests — all 7 dimension test files should pass. |
| 5 | Implement `Scorecard`, `evaluate_pipeline`. Run all tests. Wire scorecard assertion into one existing integration test as a smoke test. |

### Week 2: Agentic dimensions + CI integration

| Day | Task |
|---|---|
| 6 | Implement `JudgeProvider` protocol, `FMAPIJudgeProvider` (Opus 4.6 + ChatGPT 5.4), and `LLMJudge` class. Write tests with a mock provider. |
| 7 | Implement `semantic_equivalence.py` dimension. Calibrate against expression pairs from `set_variable_activities.json`. Write tests. |
| 8 | Implement `ExecutionRunner` protocol and `ExecutionDimension` class. Wrap the existing `_run_job_and_wait` helper from `test_databricks_execution.py`. Write tests with a mock runner. |
| 9 | Wire `evaluate_pipeline` into CI: add a pytest fixture that computes the scorecard after each integration test run and asserts `scorecard.score >= 70`. |
| 10 | Curate golden set: 20-30 pipeline fixtures with expected score ranges. Write regression test: `evaluate_batch(golden_set)` scores should not regress from baseline. |

### Week 3: Surface layer — App, MCP, API, CLI

| Day | Task |
|---|---|
| 11 | Implement FastAPI backend (`apps/lmv/backend/main.py`): `/api/validate`, `/api/validate/batch`, `/api/validate/expression`, `/api/history`. Write `test_api.py`. |
| 12 | Implement MCP server (`apps/lmv/mcp_server.py`): `validate_pipeline`, `validate_expression`, `validate_batch`, `suggest_fix` tools. Write `test_mcp_server.py`. |
| 13 | Implement Typer CLI (`apps/lmv/cli.py`): `evaluate`, `evaluate-batch`, `judge-expression`, `regression-check` commands. Write `test_cli.py`. |
| 14 | Build React frontend: `ScorecardCard`, `DimensionDrilldown`, `Validate` page, `History` page. |
| 15 | Deploy as Databricks App (`app.yaml`). Test end-to-end: upload ADF JSON in UI → see scorecard. Verify MCP tools work from Claude. Verify CLI works locally. |

### Post-implementation: Extract into factory (Phase 2)

After Week 3, the lakeflow migration validator is complete with all four surfaces. The
following classes are ready for extraction into `validator-factory`:

| Class | Extracts as |
|---|---|
| `Dimension` protocol | `validator_factory.Dimension` |
| `DimensionResult` | `validator_factory.DimensionResult` |
| `ProgrammaticCheck` | `validator_factory.ProgrammaticCheck` |
| `LLMJudge` | `validator_factory.LLMJudge` |
| `JudgeProvider` protocol | `validator_factory.JudgeProvider` |
| `FMAPIJudgeProvider` | `validator_factory.providers.FMAPIJudgeProvider` |
| `ExecutionDimension` | `validator_factory.ExecutionDimension` |
| `ExecutionRunner` protocol | `validator_factory.ExecutionRunner` |
| `Scorecard` | `validator_factory.Scorecard` |
| `GoldenSet` | `validator_factory.GoldenSet` |
| `Report` | `validator_factory.Report` |

The surface layer code (FastAPI routes, MCP tools, CLI commands, React components) provides
**reference implementations** that the factory can optionally scaffold for new validators.
The concrete dimension functions (`compute_activity_coverage`, etc.) stay in wkmigrate —
they are wkmigrate-specific. The framework classes move to the factory.
