# System 3: Validator Factory

> **Purpose:** A configuration-driven Python library that produces domain-specific validators
> from declarative specifications of quality dimensions, judges, golden sets, and scorecards.
> **Relationship to other systems:** Extracted from the Conversion Validator (System 1).
> Consumed by the Demo Factory Validator (System 2) and future validators.

---

## Problem statement

Building a validator from scratch requires repeated work: defining quality dimensions,
implementing scorers (programmatic + LLM), managing golden sets, computing aggregate scores,
tracking results in MLflow, and wiring into CI. Systems 1 and 2 share 80% of this
infrastructure. The factory extracts the common 80% so that producing a new validator is a
configuration task, not a development task.

---

## What the factory produces

Given a domain specification, the factory produces a `Validator` object:

```python
validator = factory.create(
    name="adf_to_lakeflow",
    dimensions=[...],
    scorecard=Scorecard(weights={...}),
    golden_set=GoldenSet.from_json("..."),
)

# Usage
scorecard = validator.evaluate(input=adf_pipeline, output=prepared_workflow)
report = validator.evaluate_batch(pairs=golden_set.pairs)
passed = validator.regression_check(current=report, baseline=baseline_report)
validator.track(experiment_name="conversion-quality")
```

A `Validator` has four operations:
- **`evaluate(input, output) -> Scorecard`** — run all dimensions on a single input/output pair
- **`evaluate_batch(pairs) -> Report`** — run on a corpus, compute aggregates and per-pair details
- **`regression_check(current, baseline) -> bool`** — compare reports, return True if no regression
- **`track(experiment_name)`** — log the latest report to MLflow

---

## Core abstractions

### Dimension (base)

Every quality dimension implements a common interface:

```python
@dataclass(frozen=True)
class DimensionResult:
    name: str
    score: float          # 0.0-1.0
    passed: bool          # score >= threshold
    details: dict         # dimension-specific metadata

class Dimension(Protocol):
    name: str
    threshold: float      # minimum acceptable score

    def evaluate(self, input: Any, output: Any) -> DimensionResult: ...
```

### ProgrammaticCheck

Wraps a Python function:

```python
class ProgrammaticCheck(Dimension):
    def __init__(self, name: str, check_fn: Callable[[Any, Any], float], threshold: float = 0.0):
        ...

    def evaluate(self, input, output) -> DimensionResult:
        score = self.check_fn(input, output)
        return DimensionResult(name=self.name, score=score, passed=score >= self.threshold, details={})
```

Covers: activity coverage, notebook validity, parameter completeness, secret completeness,
dependency preservation, cross-artifact consistency, etc.

### LLMJudge

Wraps an LLM-as-judge evaluation:

```python
class LLMJudge(Dimension):
    def __init__(
        self,
        name: str,
        criteria: str,                           # NL description of what "good" means
        input_template: str,                     # format string with {input} and {output} placeholders
        model: str = "claude-sonnet-4-6",        # or any FMAPI model
        calibration_examples: list[dict] = None, # few-shot examples for the judge
        threshold: float = 0.7,
        provider: str = "databricks_fmapi",      # or "anthropic", "openai"
    ): ...

    def evaluate(self, input, output) -> DimensionResult:
        prompt = self._build_judge_prompt(input, output)
        response = self._call_llm(prompt)
        score = self._parse_score(response)
        return DimensionResult(name=self.name, score=score, passed=score >= self.threshold,
                               details={"reasoning": response.reasoning})
```

Covers: semantic equivalence, spec-prompt alignment, artifact-spec alignment.

### ExecutionDimension

Wraps a live execution test:

```python
class ExecutionDimension(Dimension):
    def __init__(
        self,
        name: str,
        runner: ExecutionRunner,     # protocol with run(output, params) -> dict[str, TaskResult]
        threshold: float = 1.0,
    ): ...

    def evaluate(self, input, output) -> DimensionResult:
        results = self.runner.run(output, params=self._get_test_params(input))
        success_rate = sum(1 for r in results.values() if r.success) / len(results)
        return DimensionResult(name=self.name, score=success_rate,
                               passed=success_rate >= self.threshold,
                               details={"task_results": results})
```

Covers: runtime success on Databricks.

### Scorecard

Weighted aggregation of dimension results:

```python
@dataclass(frozen=True)
class Scorecard:
    weights: dict[str, float]  # dimension_name -> weight (must sum to 1.0)

    def compute(self, results: dict[str, DimensionResult]) -> float:
        return sum(
            results[name].score * weight
            for name, weight in self.weights.items()
            if name in results
        ) * 100
```

### GoldenSet

Test corpus with known-good input/output pairs:

```python
class GoldenSet:
    pairs: list[dict]  # each dict has "input", "output", and optional "expected_scores"

    @classmethod
    def from_json(cls, path: str) -> GoldenSet: ...

    @classmethod
    def from_mlflow(cls, experiment_name: str, run_id: str) -> GoldenSet: ...

    def add_failure(self, input, output, failure_details: dict) -> None:
        """Add a production failure to the golden set (grows from failures)."""
        ...
```

### Report

Batch evaluation output:

```python
@dataclass(frozen=True)
class Report:
    timestamp: str
    validator_name: str
    aggregate_score: float
    per_dimension: dict[str, float]            # dimension_name -> mean score
    per_pair: list[dict[str, DimensionResult]]  # per golden-set pair
    regressions: list[str]                      # dimensions that regressed vs baseline
```

---

## Factory API

```python
class ValidatorFactory:
    def __init__(
        self,
        tracking_backend: str = "mlflow",       # "mlflow", "braintrust", "console"
        llm_provider: JudgeProvider | None = None,
    ): ...

    def create(
        self,
        name: str,
        dimensions: list[Dimension],
        scorecard: Scorecard,
        golden_set: GoldenSet | None = None,
    ) -> Validator: ...
```

Default LLM provider when `llm_provider=None`:

```python
from validator_factory.providers.fmapi import FMAPIJudgeProvider

default_provider = FMAPIJudgeProvider(
    endpoint=os.environ["DATABRICKS_HOST"] + "/serving-endpoints",
    high_stakes_model="claude-opus-4-6",   # Opus 4.6 for calibration, nightly, optimization
    batch_model="chatgpt-5-4",             # ChatGPT 5.4 for CI batch scoring
)
```

The factory configures the tracking backend and LLM provider once. Individual `LLMJudge`
dimensions inherit the provider. This avoids repeating FMAPI configuration per dimension.

---

## How Systems 1 and 2 use the factory

### System 1: Lakeflow Migration Validator

```python
factory = ValidatorFactory(tracking_backend="mlflow")

lmv = factory.create(
    name="lakeflow_migration_validator",
    dimensions=[
        ProgrammaticCheck("activity_coverage", check_fn=compute_activity_coverage),
        ProgrammaticCheck("expression_coverage", check_fn=compute_expression_coverage),
        ProgrammaticCheck("dependency_preservation", check_fn=compute_dependency_preservation),
        ProgrammaticCheck("notebook_validity", check_fn=compute_notebook_validity),
        ProgrammaticCheck("parameter_completeness", check_fn=compute_parameter_completeness),
        ProgrammaticCheck("secret_completeness", check_fn=compute_secret_completeness),
        ProgrammaticCheck("not_translatable_ratio", check_fn=compute_not_translatable_ratio),
        LLMJudge(
            "semantic_equivalence",
            criteria="Does the Python expression produce the same result as the ADF expression?",
            input_template="ADF expression: {adf_expr}\nGenerated Python: {python_code}",
            calibration_examples=load_expression_golden_pairs(),
        ),
        ExecutionDimension("runtime_success", runner=DatabricksJobRunner(workspace_store)),
    ],
    scorecard=Scorecard(weights={
        "activity_coverage": 0.25, "expression_coverage": 0.20,
        "dependency_preservation": 0.15, "notebook_validity": 0.15,
        "parameter_completeness": 0.10, "secret_completeness": 0.10,
        "not_translatable_ratio": 0.05,
    }),
    golden_set=GoldenSet.from_json("tests/resources/golden_pipelines.json"),
)
```

### System 2: Demo Factory Validator

```python
demo_validator = factory.create(
    name="prompt_to_artifact",
    dimensions=[
        LLMJudge(
            "spec_prompt_alignment",
            criteria="Does the DomainSpec capture every entity and surface from the prompt?",
            input_template="User prompt: {prompt}\nGenerated spec:\n{spec_yaml}",
            calibration_examples=load_seed_prompt_spec_pairs(),
            threshold=0.8,
        ),
        LLMJudge(
            "artifact_spec_alignment",
            criteria="Does the artifact match the spec's table list and page descriptions?",
            input_template="Spec tables: {spec_tables}\nArtifact: {artifact_json}",
            threshold=0.75,
        ),
        ProgrammaticCheck(
            "cross_artifact_consistency",
            check_fn=compute_cross_artifact_table_consistency,
            threshold=0.9,
        ),
        ProgrammaticCheck(
            "existing_quality_gate",
            check_fn=lambda input, output: run_existing_quality_gate(output),
        ),
    ],
    scorecard=Scorecard(weights={
        "spec_prompt_alignment": 0.30, "artifact_spec_alignment": 0.35,
        "cross_artifact_consistency": 0.15, "existing_quality_gate": 0.20,
    }),
    golden_set=GoldenSet.from_json("seed_library/golden_seeds.json"),
)
```

---

## Optional extensions

### DSPy judge optimization

Any `LLMJudge` can be optionally optimized via DSPy:

```python
optimized_judge = factory.optimize_judge(
    judge=semantic_equiv_judge,
    calibration_data=human_labeled_pairs,
    optimizer="MIPROv2",  # or "SIMBA"
    metric=judge_human_agreement,
)
```

This wraps the judge as a DSPy module, runs optimization, and returns an improved judge
with better instructions/demonstrations. The original judge is replaced in the validator.

### Synthetic test generation

The factory can generate new test cases for any validator:

```python
new_tests = factory.generate_tests(
    validator=conversion_validator,
    strategy="adversarial",  # or "coverage", "boundary"
    count=50,
)
golden_set.extend(new_tests)
```

Uses an LLM to generate inputs that are likely to stress the validator's dimensions.

---

## Relationship to existing frameworks

| Factory component | Backed by | Alternative |
|---|---|---|
| `LLMJudge` | MLflow Tunable Judges | Braintrust Loop, DeepEval G-Eval |
| `ProgrammaticCheck` | Plain Python | DeepEval custom metrics |
| `ExecutionDimension` | Databricks Jobs API | Custom runners |
| `Scorecard` | Custom aggregation | MLflow evaluate |
| `GoldenSet` | JSON files + MLflow artifacts | Braintrust datasets |
| Tracking | MLflow experiments | Braintrust, LangSmith |
| Judge optimization | DSPy MIPROv2/SIMBA | Manual prompt engineering |
| Test generation | LLM-based | Agent Bricks, Bloom |

The factory is **not a framework** — it produces plain Python objects. Validators can be used
in pytest, CI pipelines, Databricks notebooks, or production monitoring without imposing
architectural constraints on the validated systems.

---

## Surface layer scaffolding

The factory optionally scaffolds the four interaction surfaces for any validator it produces.
This is extracted from the reference implementations built in System 1 (lakeflow migration
validator).

### What the factory can scaffold

```python
factory.scaffold_surfaces(
    validator=lmv,
    output_dir="apps/lmv/",
    surfaces=["app", "mcp", "api", "cli"],  # pick any subset
    app_name="lakeflow-migration-validator",
)
```

This generates:

| Surface | Generated files | Requires |
|---|---|---|
| **Databricks App** | `app.yaml`, `backend/main.py` (FastAPI routes), `frontend/` (React scaffold) | Databricks Apps runtime |
| **MCP Server** | `mcp_server.py` with one tool per dimension + `validate`, `suggest_fix` | MCP-compatible agent (Claude, etc.) |
| **REST API** | `backend/main.py` (same as app, deployable standalone) | Any Python host |
| **CLI** | `cli.py` with `evaluate`, `evaluate-batch`, `regression-check` commands | Python + Typer |

Each surface wraps the same Python API (`validator.evaluate()`, `validator.evaluate_batch()`,
`validator.regression_check()`). The scaffolded code is **fully editable** — it's generated
once and then maintained by the developer, not regenerated on every factory call.

### Surface configuration in the factory

```python
class ValidatorFactory:
    def create(
        self,
        name: str,
        dimensions: list[Dimension],
        scorecard: Scorecard,
        golden_set: GoldenSet | None = None,
    ) -> Validator: ...

    def scaffold_surfaces(
        self,
        validator: Validator,
        output_dir: str,
        surfaces: list[str] = ["app", "mcp", "api", "cli"],
        app_name: str | None = None,
        app_framework: str = "databricks",  # or "standalone" (no Databricks dependency)
    ) -> None:
        """Generate boilerplate code for the selected interaction surfaces.

        The generated code imports and calls the validator's Python API. It is
        editable and does not need to be regenerated when dimensions change.
        """
        ...
```

### How System 2 uses this

The demo factory validator does **not** scaffold a standalone app — it integrates into the
existing Demo Composer app. Instead, it scaffolds only the MCP tools and CLI commands:

```python
factory.scaffold_surfaces(
    validator=demo_validator,
    output_dir="src/demo_factory/evaluation/",
    surfaces=["mcp", "cli"],  # no separate app — integrates into existing UI
)
```

The scaffolded MCP tools are then manually merged into `demo_factory/mcp_server.py`,
and the CLI commands into `demo_factory/cli.py`.

### LLM backend for all surfaces

All surfaces delegate to the same `FMAPIJudgeProvider` configured at factory creation time.
The provider handles model routing (Opus 4.6 for high-stakes, ChatGPT 5.4 for batch) —
surfaces don't need to know about model selection.
