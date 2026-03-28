# Agent-Backed Synthetic Pipeline Generator

> **Priority:** 1 (highest remaining)
> **Depends on:** FMAPI provider (done), evaluate() (done)
> **Produces:** Calibration data for DSPy judge optimization (Priority 3)

---

## Problem

The current synthetic generator is template-based — it cycles through canned expression
pairs and wraps them in pipeline JSON. It produces ~30 unique patterns that repeat.
It doesn't produce realistic ADF pipelines that would stress-test wkmigrate in ways
that matter.

## What the agent generator must do

### 1. Understand ADF's real pipeline model

The generator must produce **valid ADF pipeline JSON** that a real ADF instance would
accept. This means:

- Valid activity type combinations (not every type can appear everywhere)
- Realistic dependency chains (not just linear A→B→C)
- Parameter references that cross activities (SetVariable sets, downstream reads)
- Expressions that reference upstream activity outputs (`@activity('X').output.firstRow.col`)
- Nested control flow (ForEach containing IfCondition containing Notebook)
- Linked service references for Copy/Lookup activities
- Dataset definitions with realistic schemas

### 2. Target wkmigrate's known weak spots

The generator should produce pipelines that stress areas where wkmigrate has partial
support or known bugs:

| Weak spot | Example | Why it matters |
|---|---|---|
| Complex nested expressions | `@concat(formatDateTime(utcNow(),'yyyy-MM-dd'), '/', pipeline().parameters.env, '/', activity('Lookup').output.firstRow.path)` | Multiple function nesting + cross-activity refs |
| Math on pipeline parameters | `@add(mul(pipeline().parameters.count, 2), 1)` | `widgets.get` returns string — the coercion bug we found |
| ForEach with expression items | `@createArray(concat('a', pipeline().parameters.suffix), concat('b', pipeline().parameters.suffix))` | Items are expressions, not literals |
| IfCondition with complex predicates | `@and(greater(pipeline().parameters.threshold, 50), not(equals(pipeline().parameters.env, 'prod')))` | Multiple logical operators |
| Copy with parameterized paths | Source path built from `@concat(pipeline().parameters.container, '/', formatDateTime(utcNow(), 'yyyy/MM/dd'))` | Expression in file path |
| Lookup + downstream consumption | Lookup → SetVariable that uses `@activity('Lookup').output.firstRow.config` | Activity output chaining |
| Unsupported activity types | AzureFunction, ExecuteSSISPackage, Wait | Should produce placeholder, not crash |
| Deep nesting | ForEach → IfCondition → ForEach → Notebook | 3+ levels of control flow |

### 3. Produce verifiable ground truth

For each generated pipeline, the generator must produce:

- **Expected CCS range** — based on which activity types and expressions are used
- **Expected dimension scores** — e.g., if it contains an unsupported activity, `activity_coverage` should be < 1.0
- **Expected expression translations** — for each ADF expression, the Python code wkmigrate should emit
- **Expected failure modes** — which dimensions should fail and why

### 4. Learn from failures (DSPy feedback loop)

When wkmigrate fails on a generated pipeline:
1. Record the failure (which dimension, what error)
2. Use DSPy `Refine` to generate variations that explore the failure neighborhood
3. Use GEPA's `optimize_anything` to optimize the generator prompt for maximum failure discovery rate
4. Track the failure rate over time — it should increase as the generator gets smarter

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentPipelineGenerator                     │
│                                                               │
│  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │  TemplateGen │     │   LLMGen     │     │ AdversarialGen│ │
│  │  (existing)  │     │  (FMAPI)     │     │  (DSPy)      │ │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘ │
│         └──────────────┬─────┘──────────────┘               │
│                        │                                     │
│              ┌─────────▼──────────┐                         │
│              │  PipelineValidator  │                         │
│              │  (JSON schema +    │                         │
│              │   ADF structure)   │                         │
│              └─────────┬──────────┘                         │
│                        │                                     │
│              ┌─────────▼──────────┐                         │
│              │ GroundTruthBuilder  │                         │
│              │ (expected CCS,     │                         │
│              │  dim scores,       │                         │
│              │  translations)     │                         │
│              └─────────┬──────────┘                         │
│                        │                                     │
│              ┌─────────▼──────────┐                         │
│              │ ConversionTester   │                         │
│              │ (run wkmigrate,    │                         │
│              │  score, compare)   │                         │
│              └─────────┬──────────┘                         │
│                        │                                     │
│              ┌─────────▼──────────┐                         │
│              │ FailureFeedback    │                         │
│              │ (DSPy Refine,      │                         │
│              │  GEPA optimize)   │                         │
│              └────────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation

### `synthetic/agent_generator.py`

```python
class AgentPipelineGenerator:
    """LLM-powered ADF pipeline generator.

    Modes:
    - template: existing deterministic templates (fast, no LLM)
    - llm: single-shot LLM generation via FMAPI (creative, varied)
    - adversarial: DSPy-optimized generation targeting converter weak spots
    """

    def __init__(
        self,
        judge_provider: JudgeProvider,
        mode: str = "llm",
        model: str = "chatgpt-5-4",            # fast model for generation
        adversarial_optimizer: str = "MIPROv2",  # DSPy optimizer for adversarial mode
    ): ...

    def generate(
        self,
        count: int = 10,
        target_weak_spots: list[str] | None = None,  # e.g., ["nested_expressions", "math_params"]
        min_activities: int = 2,
        max_activities: int = 15,
        include_unsupported: bool = True,
    ) -> list[SyntheticPipeline]: ...

    def generate_adversarial(
        self,
        count: int = 10,
        failure_history: list[dict] | None = None,  # past failures to learn from
    ) -> list[SyntheticPipeline]: ...
```

### LLM Generation Prompt

```
You are an Azure Data Factory expert. Generate a realistic ADF pipeline JSON
definition that would stress-test an ADF-to-Databricks migration tool.

Requirements:
- Valid ADF pipeline JSON structure (name, properties.activities)
- Include {activity_count} activities of types: {activity_types}
- Include dependencies between activities (not all independent)
- Use these ADF expressions in activity properties:
  {expression_patterns}
- Include at least one activity that references an upstream activity's output
- Pipeline parameters: {parameters}
- Target weak spot: {target_weak_spot_description}

Output ONLY valid JSON, no explanation.
```

### Ground Truth Builder

For each generated pipeline, automatically compute expected outcomes:

```python
class GroundTruthBuilder:
    """Compute expected validation outcomes for a generated pipeline."""

    def build(self, adf_json: dict) -> dict:
        """Analyze the pipeline and predict what evaluate() should produce."""
        activities = adf_json.get("properties", {}).get("activities", [])

        # Count supported vs unsupported activity types
        supported = {"DatabricksNotebook", "DatabricksSparkJar", ...}
        unsupported = [a for a in activities if a["type"] not in supported]
        expected_activity_coverage = (len(activities) - len(unsupported)) / max(len(activities), 1)

        # Count expressions that wkmigrate can handle
        expressions = self._extract_expressions(activities)
        resolvable = [e for e in expressions if self._is_resolvable(e)]
        expected_expression_coverage = len(resolvable) / max(len(expressions), 1)

        # ...etc for each dimension

        return {
            "expected_ccs_range": (min_ccs, max_ccs),
            "expected_dimensions": {
                "activity_coverage": expected_activity_coverage,
                "expression_coverage": expected_expression_coverage,
                ...
            },
            "expected_expression_translations": [...],
        }
```

### Failure Feedback Loop (DSPy)

```python
class FailureFeedback:
    """Learn from converter failures to generate more targeted test cases."""

    def __init__(self, optimizer: str = "MIPROv2"):
        self.failure_history: list[dict] = []

    def record_failure(self, pipeline: SyntheticPipeline, scorecard: Scorecard, errors: list[str]):
        self.failure_history.append({
            "pipeline": pipeline,
            "scorecard": scorecard,
            "errors": errors,
        })

    def suggest_next_generation(self) -> dict:
        """Analyze failures and suggest generation parameters for next round."""
        # Cluster failures by dimension
        # Identify which expression patterns / activity combos cause failures
        # Return generation config that targets those patterns
        ...
```

---

## Test Plan

### Unit tests (no LLM calls)

```
test_agent_generator_llm_mode_calls_provider
test_agent_generator_validates_output_json
test_agent_generator_rejects_invalid_llm_output
test_agent_generator_retries_on_invalid_json
test_ground_truth_builder_computes_activity_coverage
test_ground_truth_builder_computes_expression_coverage
test_ground_truth_builder_identifies_unsupported_types
test_failure_feedback_records_failures
test_failure_feedback_suggests_targeted_generation
```

### Integration tests (with LLM)

```
test_llm_generates_valid_adf_json
test_llm_generated_pipeline_has_dependencies
test_llm_generated_pipeline_includes_expressions
test_generated_pipeline_runs_through_wkmigrate_without_crash
test_adversarial_mode_finds_more_failures_than_template
```

---

## Implementation Sequence

| Step | What | Depends on |
|---|---|---|
| 1 | `GroundTruthBuilder` — predict expected outcomes from ADF JSON | Nothing |
| 2 | `AgentPipelineGenerator` (llm mode) — single-shot LLM generation | FMAPI provider |
| 3 | `PipelineValidator` — validate generated JSON is structurally valid ADF | Nothing |
| 4 | `ConversionTester` — run wkmigrate + evaluate(), compare vs expected | wkmigrate, evaluate() |
| 5 | `FailureFeedback` — record failures, suggest next generation params | Step 4 |
| 6 | Adversarial mode with DSPy — optimize generator prompt | DSPy 3.x, Step 5 |
| 7 | UI integration — show generation quality, failure patterns | Steps 1-5 |
