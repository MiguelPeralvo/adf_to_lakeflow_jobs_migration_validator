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

## Prompt Customization (User-Editable Generation)

### Problem

The current generator uses a hardcoded prompt template. Implementation teams need to:
1. Focus generation on specific patterns (e.g., "50 pipelines with complex expressions only")
2. Edit the prompt before generation to add domain-specific constraints
3. Choose from preset templates for common scenarios
4. Write completely custom prompts for edge-case testing

### UI Flow

The Synthetic page should have a **prompt editor** with:

```
┌──────────────────────────────────────────────────────────┐
│  Generation Mode:  [Template ▾]  [LLM ▾]  [Custom]      │
│                                                          │
│  Preset Templates:                                        │
│  [Complex Expressions] [Deep Nesting] [Activity Mix]     │
│  [Math on Params] [Unsupported Types] [Full Coverage]    │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Prompt (editable):                                 │  │
│  │                                                    │  │
│  │ Generate 50 realistic ADF pipelines that stress    │  │
│  │ complex nested expressions. Each pipeline should:  │  │
│  │ - Use concat, formatDateTime, and pipeline()       │  │
│  │   .parameters references nested 3+ levels deep     │  │
│  │ - Include at least one activity that references an │  │
│  │   upstream activity's output via @activity()       │  │
│  │ - Have 5-10 activities with dependency chains      │  │
│  │                                                    │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  Count: [50]  Max Activities: [10]                       │
│                                                          │
│  [Generate Suite]                                        │
└──────────────────────────────────────────────────────────┘
```

### Preset Templates

Each template generates a prompt focused on a specific testing scenario:

```python
PROMPT_TEMPLATES: dict[str, str] = {
    "complex_expressions": """Generate {count} ADF pipelines that stress-test complex
nested ADF expressions. Each pipeline should use expressions nested 3+ levels deep
combining concat, formatDateTime, utcNow, pipeline().parameters, and activity().output
references. Include SetVariable activities that consume upstream Lookup outputs.
Include pipeline parameters: env, prefix, threshold, date_override.""",

    "deep_nesting": """Generate {count} ADF pipelines with deeply nested control flow:
ForEach containing IfCondition containing another ForEach or nested IfCondition.
Inner activities should be DatabricksNotebook with expression-valued parameters.
The ForEach items should be expression-generated arrays, not static.""",

    "activity_mix": """Generate {count} ADF pipelines using ALL supported activity
types: DatabricksNotebook, Copy, Lookup, WebActivity, SetVariable, ForEach,
IfCondition. Each pipeline should use at least 4 different activity types with
realistic dependency chains between them.""",

    "math_on_params": """Generate {count} ADF pipelines that use math functions
(add, mul, sub, div, mod) on pipeline parameters. Include expressions like
@add(mul(pipeline().parameters.count, 2), 1). These stress-test the numeric
coercion logic since dbutils.widgets.get returns strings.""",

    "unsupported_types": """Generate {count} ADF pipelines that include a mix of
supported and unsupported activity types (AzureFunction, ExecuteSSISPackage,
Wait, ExecutePipeline, Switch, Until). This tests placeholder generation and
activity_coverage scoring.""",

    "full_coverage": """Generate {count} ADF pipelines that exercise ALL dimensions
of the Lakeflow Migration Validator: activity coverage, expression coverage,
dependency preservation, notebook validity, parameter completeness, secret
completeness, and translatable ratio. Each pipeline should have deliberate
weaknesses in 1-2 dimensions for targeted testing.""",
}
```

### API Changes

```python
# POST /api/synthetic/generate — updated request model
class SyntheticGenerateRequest(BaseModel):
    count: int = 10
    mode: str = "template"              # "template", "llm", "custom"
    preset: str | None = None           # key from PROMPT_TEMPLATES
    custom_prompt: str | None = None    # user-edited or fully custom prompt
    max_activities: int = 20
    difficulty: str = "medium"
    output_path: str | None = None
```

When `mode="llm"` and `preset` is set, the preset template is used as the base prompt.
When `mode="custom"`, `custom_prompt` is used directly.
The UI always shows the effective prompt in the editor, allowing the user to modify it
before clicking Generate.

---

## Synthetic Test Data Generation (for Parallel Testing)

### Problem

Parallel testing compares ADF pipeline execution outputs with Databricks job outputs.
But running real ADF pipelines requires real data in the source systems (Azure SQL,
Blob Storage, etc.). The generator should be able to produce test data alongside
the pipeline definitions.

### What the data generator needs to produce

For each generated pipeline that includes data-reading activities (Copy, Lookup):

1. **Source data files** — CSV/JSON/Parquet files with synthetic rows matching the
   pipeline's dataset schema
2. **Database seed scripts** — SQL INSERT statements for Lookup activities that query
   SQL databases
3. **Expected output data** — what the pipeline should produce given the seed data
   (for comparison in parallel testing)

### Data Generation Strategy

```python
@dataclass(frozen=True, slots=True)
class SyntheticTestData:
    """Test data generated alongside a synthetic pipeline."""
    pipeline_name: str
    source_files: dict[str, str]          # file_path → CSV/JSON content
    seed_sql: list[str]                   # SQL statements to seed lookup sources
    expected_outputs: dict[str, str]      # activity_name → expected output value
    setup_instructions: str               # human-readable setup guide


class TestDataGenerator:
    """Generate test data that matches a pipeline's data requirements."""

    def __init__(self, judge_provider: JudgeProvider | None = None):
        self._provider = judge_provider

    def generate_for_pipeline(self, adf_json: dict) -> SyntheticTestData:
        """Analyze the pipeline and generate matching test data."""
        ...

    def generate_for_suite(self, suite: list[SyntheticPipeline]) -> list[SyntheticTestData]:
        """Generate test data for all pipelines in a suite."""
        ...
```

### Integration with Parallel Testing

The parallel test runner should optionally accept test data:

```python
# Updated parallel test flow:
# 1. Generate synthetic pipeline + test data
# 2. Seed the test data into ADF source systems
# 3. Run the ADF pipeline → collect outputs
# 4. Run the converted Lakeflow Job with same data → collect outputs
# 5. Compare outputs
```

### UI Changes

The Synthetic page should have a "Generate Test Data" toggle that:
- Shows a preview of generated source files and SQL scripts
- Offers a "Deploy Test Data" button that uploads files to Azure storage
  and runs seed SQL against the configured database
- Shows setup instructions for manual deployment

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
