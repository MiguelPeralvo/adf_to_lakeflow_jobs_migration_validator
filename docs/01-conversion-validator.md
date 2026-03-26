# System 1: Lakeflow Migration Validator (`lakeflow-migration-validator`)

> **Package:** `lakeflow_migration_validator` (alias: `lmv`)
> **Domain:** wkmigrate — translates Azure Data Factory pipelines into Databricks Lakeflow Jobs
> **Validates:** The fidelity, correctness, and completeness of ADF-to-Lakeflow conversions
> **Relationship to other systems:** Seeds the patterns that become the Validator Factory (System 3).
> Shares the evaluation layering model with the Demo Factory Validator (System 2).
>
> **LLM backend:** Databricks Foundation Model API (FMAPI)
> - **High-stakes judgments** (calibration, nightly eval): Claude Opus 4.6 (`claude-opus-4-6`)
> - **Batch scoring** (CI, high-throughput): ChatGPT 5.4 (`chatgpt-5-4`)
> - **Judge optimization:** DSPy 3.x with MIPROv2/SIMBA, LLM calls via FMAPI

---

## Purpose

wkmigrate converts ADF pipelines through a three-layer pipeline:
`ADF JSON → Translator → IR (Pipeline/Activity) → Preparer → PreparedWorkflow → Databricks Job`.
Today, conversion quality is validated by unit tests (IR field assertions), integration tests
(real ADF → IR), and execution tests (real Databricks cluster). But there is no **unified
quality model** that scores a conversion holistically and no **automated feedback loop** that
uses evaluation results to improve the converter.

The Conversion Validator fills both gaps: it produces a **Conversion Scorecard** per pipeline
and, over time, feeds failures into an improvement loop via DSPy-optimized judges and
synthetic test generation.

---

## Quality Dimensions

### Tier 1: Programmatic assertions (deterministic, every commit)

| # | Dimension | Input | Computation | Output |
|---|---|---|---|---|
| 1 | **Activity coverage** | `PreparedWorkflow` | Count tasks with real notebook paths vs total tasks. Tasks pointing to `/UNSUPPORTED_ADF_ACTIVITY` are uncovered. | `float` 0.0-1.0 |
| 2 | **Expression coverage** | Translation trace | Count successful `get_literal_or_expression()` calls vs total expression properties encountered. Requires instrumentation in the parser. | `float` 0.0-1.0 |
| 3 | **Dependency preservation** | Source ADF pipeline + IR Pipeline | For each `depends_on` in the ADF payload, check that a corresponding `Dependency` exists in the IR. Unsupported conditions (non-Succeeded) count as misses. | `float` 0.0-1.0 |
| 4 | **Notebook syntax validity** | `PreparedWorkflow.all_notebooks` | `compile(nb.content, '<generated>', 'exec')` per `NotebookArtifact`. Any `SyntaxError` is a failure. | `float` 0.0-1.0 |
| 5 | **Parameter completeness** | IR Pipeline + all notebook contents | Extract every `dbutils.widgets.get('X')` reference from notebook source. Check that `X` exists in `pipeline.parameters`. | `float` 0.0-1.0 |
| 6 | **Secret completeness** | All notebook contents + `PreparedWorkflow.all_secrets` | Extract every `dbutils.secrets.get(scope=..., key=...)` reference. Check that each (scope, key) pair has a matching `SecretInstruction`. | `float` 0.0-1.0 |
| 7 | **Not-translatable ratio** | IR Pipeline | `1 - (len(pipeline.not_translatable) / max(total_properties, 1))`. A pipeline with many not-translatable warnings has lower quality. | `float` 0.0-1.0 |

### Tier 2: Structural analysis (deterministic, nightly)

| # | Dimension | Input | Computation | Output |
|---|---|---|---|---|
| 8 | **Control flow fidelity** | Source ADF pipeline + IR Pipeline | Verify: (a) ForEach items match ADF items expression count, (b) IfCondition branches produce the right number of child activities with correct outcomes, (c) nested structures are preserved. | `dict[str, bool]` per check |

### Tier 3: Semantic analysis (LLM-as-judge, nightly)

| # | Dimension | Input | Computation | Output |
|---|---|---|---|---|
| 9 | **Semantic equivalence** | (ADF expression string, generated Python string) pairs | LLM judge: "Given these inputs, would the Python code produce the same result as the ADF expression for all valid parameter values?" Calibrated against golden pairs. | `float` 0.0-1.0 per pair, aggregated |

### Tier 4: Execution validation (on-demand)

| # | Dimension | Input | Computation | Output |
|---|---|---|---|---|
| 10 | **Runtime success** | Deployed Databricks job | Run job with test parameters, collect per-task `result_state`. | `float` (successful_tasks / total_tasks) |

---

## Conversion Confidence Score

```
CCS = (
    activity_coverage     * 0.25
  + expression_coverage   * 0.20
  + dependency_preservation * 0.15
  + notebook_validity     * 0.15
  + parameter_completeness * 0.10
  + secret_completeness   * 0.10
  + (1 - not_translatable_ratio) * 0.05
) * 100
```

| Range | Label | Action |
|---|---|---|
| 90-100 | High confidence | Auto-deploy eligible |
| 70-89 | Review recommended | Human reviews not-translatable items and placeholder activities |
| < 70 | Manual intervention | Significant gaps — likely unsupported activity types or expressions |

---

## Agentic vs Deterministic Components

8 of 11 scoring dimensions are **fully deterministic** — no LLM calls, no cost, run on every
commit in CI. The agentic components are opt-in and additive:

### What's deterministic (Tiers 1-2, always on)

Dimensions 1-8: pure Python functions that inspect the `ConversionSnapshot` (the validator's
tool-agnostic contract). No wkmigrate imports, no external dependencies. These compute the
Conversion Confidence Score.

### What uses LLMs (Tier 3, nightly)

**Semantic equivalence judge** — given `(ADF expression, generated Python)` pairs, an LLM
determines whether they produce the same result. Runs via **Databricks FMAPI**:

| Use case | Model | Why |
|---|---|---|
| Calibration runs + nightly eval | **Claude Opus 4.6** (`claude-opus-4-6` via FMAPI) | Highest reasoning quality for nuanced ADF/Python semantic comparison |
| Batch CI scoring (high throughput) | **ChatGPT 5.4** (`chatgpt-5-4` via FMAPI) | Faster, cheaper for large expression corpora |

FMAPI configuration:
```python
judge_provider = FMAPIJudgeProvider(
    endpoint=os.environ["DATABRICKS_HOST"] + "/serving-endpoints",
    high_stakes_model="claude-opus-4-6",       # nightly, calibration
    batch_model="chatgpt-5-4",                 # CI, large corpora
    timeout_seconds=30,
    max_retries=2,
)
```

### What uses DSPy (optimization, periodic)

**Judge optimization** — DSPy MIPROv2 or SIMBA optimizes the semantic equivalence judge's
prompt (instructions + few-shot demonstrations) by maximizing agreement with human-labeled
calibration pairs. LLM calls go through FMAPI. Runs weekly or on-demand, not per evaluation.

**Synthetic test generation (template mode)** — deterministic, no LLM. Generates parameterized
ADF pipelines and expression pairs with known-correct expected outputs. Runs through wkmigrate
+ `evaluate()`. Any CCS < 90 or expression mismatch = wkmigrate bug. This is the primary
mechanism for finding converter bugs — it's how we discovered the `div` floor-division and
`widgets.get` string-coercion issues.

**Synthetic test generation (LLM mode)** — uses FMAPI to generate novel, creative ADF
expressions designed to stress the converter. GEPA's `optimize_anything` can optimize the
generator prompt to maximize the discovery rate of converter failures.

**Fix suggestion agent** — when a dimension fails, `dspy.Refine` iteratively generates
code fix suggestions, validates them against the failing dimension, and returns the first
passing suggestion. Uses Opus 4.6 via FMAPI for the reasoning-heavy refinement loop.

### Cost model

| Component | Frequency | Estimated cost |
|---|---|---|
| Tiers 1-2 (deterministic) | Every commit | $0 |
| Synthetic generation (template mode) | Every commit / nightly | $0 (no LLM) |
| Synthetic generation (LLM mode) | Monthly | ~$5-10/run |
| Tier 3 (semantic judge, batch) | Nightly, ~100 expression pairs | ~$0.50/run (ChatGPT 5.4) |
| Tier 3 (semantic judge, calibration) | Weekly, ~30 pairs | ~$1.00/run (Opus 4.6) |
| Tier 4 (execution) | On-demand | ~$0.25/run (Databricks cluster) |
| Tier 5 (parallel testing) | On-demand | ~$0.50/run (ADF + Databricks) |
| DSPy judge optimization | Monthly or on-demand | ~$20-50/run (thousands of LLM calls) |

---

## Relationship to System 3 (Validator Factory)

This validator is the **first concrete instance** from which the factory's abstractions are
extracted. Specifically:

- The `ProgrammaticCheck(name, check_fn)` factory primitive is derived from dimensions 1-7
- The `LLMJudge(name, criteria, calibration_set)` primitive is derived from dimension 9
- The `ExecutionDimension(name, runner)` primitive is derived from dimension 10
- The `Scorecard(weights)` primitive is derived from the CCS formula
- The `GoldenSet.from_json()` pattern is derived from `set_variable_activities.json` fixtures

When building this validator, every class should be designed as if it will be extracted into
a library — clean interfaces, no wkmigrate-specific imports in the scoring logic, dependency
injection for the LLM provider and tracking backend.

## Relationship to System 2 (Demo Factory Validator)

Both validators share:
- The three-tier evaluation model (programmatic → LLM judge → execution)
- MLflow as the tracking backend
- The "golden set grows from failures" pattern
- The Scorecard aggregation concept

They differ in:
- System 1's quality dimensions are mostly programmatic (7/10); System 2's are mostly
  LLM-judge-based (2/3 new dimensions are semantic)
- System 1 validates a deterministic translation; System 2 validates an LLM-generated pipeline
- System 1's golden set is small (expression pairs); System 2's is larger (16 curated seeds)

---

## Data flow

```
                    ┌──────────────┐
                    │ ADF Pipeline │
                    │   (JSON)     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  wkmigrate   │
                    │  translate   │
                    │  + prepare   │
                    └──────┬───────┘
                           │
              ┌────────────▼────────────┐
              │    PreparedWorkflow     │
              │  (tasks, notebooks,     │
              │   secrets, pipelines)   │
              └────────────┬────────────┘
                           │
          ┌────────────────▼────────────────┐
          │     Conversion Validator         │
          │                                  │
          │  Tier 1: Programmatic checks     │
          │    ├─ activity_coverage           │
          │    ├─ expression_coverage         │
          │    ├─ dependency_preservation     │
          │    ├─ notebook_validity           │
          │    ├─ parameter_completeness      │
          │    ├─ secret_completeness         │
          │    └─ not_translatable_ratio      │
          │                                  │
          │  Tier 2: Structural checks       │
          │    └─ control_flow_fidelity       │
          │                                  │
          │  Tier 3: Semantic checks         │
          │    └─ semantic_equivalence        │
          │                                  │
          │  Tier 4: Execution checks        │
          │    └─ runtime_success             │
          │                                  │
          └────────────────┬────────────────┘
                           │
              ┌────────────▼────────────┐
              │   Conversion Scorecard   │
              │  ┌─────────────────┐    │
              │  │ CCS: 87/100     │    │
              │  │ activity: 0.90  │    │
              │  │ expression: 0.85│    │
              │  │ notebook: 1.00  │    │
              │  │ ...             │    │
              │  └─────────────────┘    │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │    MLflow Experiment     │
              │  (tracking, regression,  │
              │   judge calibration)     │
              └─────────────────────────┘
```

---

## Surface layer: how users interact with the validator

The validator core (`evaluate_pipeline`, `Scorecard`, dimensions) is a Python library. It is
exposed through four surfaces, in priority order:

### 1. Databricks App (primary)

A Databricks App with a React frontend and FastAPI backend, deployed via DAB.

**User flow:**
1. User uploads an ADF pipeline JSON (or pastes a URL to the ADF factory).
2. App calls wkmigrate to translate + prepare the pipeline.
3. App runs the validator against the `PreparedWorkflow`.
4. Dashboard shows the Conversion Scorecard: overall CCS, per-dimension scores,
   drill-down into failures (which activities are placeholders, which notebooks
   have syntax errors, which expressions are unsupported).
5. For Tier 3 (semantic judge): user can trigger on-demand LLM evaluation and
   see per-expression reasoning from Opus 4.6.
6. For Tier 4 (execution): user can trigger a live Databricks run and watch
   per-task status in real time.
7. History view: compare scorecards across pipeline versions or converter releases.

**Tech stack:**
- Backend: FastAPI + `lakeflow_migration_validator` Python API
- Frontend: React (Vite + TypeScript) — scorecard dashboard, dimension drill-down,
  expression-level detail, run history
- Deployment: Databricks Apps (`app.yaml`), same pattern as the demo factory app
- Persistence: MLflow experiments for scorecards, Lakebase or Delta for run history

**App layout:**
```
apps/lmv/
  backend/
    main.py                   # FastAPI: /api/validate, /api/history, /api/run-execution
    models.py                 # Request/response Pydantic models
  frontend/
    src/
      pages/
        Validate.tsx          # Upload + run + scorecard dashboard
        History.tsx           # Compare scorecards over time
        ExpressionDetail.tsx  # Per-expression semantic judge reasoning
      components/
        ScorecardCard.tsx     # CCS gauge + dimension bars
        DimensionDrilldown.tsx # Expandable per-dimension details
        NotebookViewer.tsx    # Syntax-highlighted generated notebook
  app.yaml                    # Databricks App config
```

### 2. MCP Server (for agentic workflows)

An MCP (Model Context Protocol) server that exposes the validator as tools for Claude or
other LLM agents. This allows agents to validate conversions as part of a larger workflow
(e.g., "translate this ADF pipeline and check quality before deploying").

**Tools exposed:**

| Tool | Description | Input | Output |
|---|---|---|---|
| `validate_pipeline` | Run all Tier 1-2 dimensions, return scorecard | `{adf_pipeline_json}` | `{scorecard}` |
| `validate_expression` | Run semantic equivalence judge on a single expression pair | `{adf_expr, python_expr}` | `{score, reasoning}` |
| `validate_batch` | Run against a golden set, return report | `{golden_set_path}` | `{report}` |
| `get_scorecard_history` | Retrieve past scorecards from MLflow | `{pipeline_name, limit}` | `{scorecards[]}` |
| `suggest_fix` | Run the fix suggestion agent for a failing dimension | `{dimension_name, failure_details}` | `{suggestion}` |
| `run_execution_validation` | Deploy + run + collect Tier 4 results | `{prepared_workflow}` | `{task_results}` |

**Implementation:**
```python
# mcp_server.py — extends the same pattern as demo factory's mcp_server.py
from mcp import Server
from lakeflow_migration_validator import evaluate_pipeline, Scorecard

server = Server("lakeflow-migration-validator")

@server.tool("validate_pipeline")
async def validate_pipeline_tool(adf_pipeline_json: str) -> dict:
    pipeline = json.loads(adf_pipeline_json)
    prepared = translate_and_prepare(pipeline)
    scorecard = evaluate_pipeline(pipeline, prepared)
    return scorecard.to_dict()
```

### 3. REST API (for CI/CD and programmatic access)

The FastAPI backend from the Databricks App doubles as the REST API. Can also be deployed
standalone (without the frontend) for headless CI/CD integration.

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/validate` | Upload ADF JSON, get scorecard |
| `POST` | `/api/validate/batch` | Upload golden set, get report |
| `POST` | `/api/validate/expression` | Single expression semantic check |
| `POST` | `/api/validate/execute` | Trigger Tier 4 execution run |
| `GET` | `/api/history/{pipeline_name}` | Scorecard history |
| `GET` | `/api/report/{run_id}` | Detailed report for a specific run |
| `POST` | `/api/suggest-fix` | Get fix suggestion for a failure |

**CI/CD integration** (GitHub Actions):
```yaml
- name: Validate conversion quality
  run: |
    curl -X POST $LMV_API_URL/api/validate \
      -H "Authorization: Bearer $DATABRICKS_TOKEN" \
      -d @prepared_workflow.json \
      | jq '.score >= 70'
```

### 4. CLI (secondary, for local dev)

A Typer CLI for local development and scripting. Lower priority than the other surfaces
but useful for quick checks.

```bash
# Evaluate a single pipeline
lmv evaluate --adf-json pipeline.json --output scorecard.json

# Evaluate against golden set
lmv evaluate-batch --golden-set tests/resources/golden_pipelines.json

# Run semantic judge on a single expression
lmv judge-expression --adf "@concat('a', 'b')" --python "str('a') + str('b')"

# Check regression
lmv regression-check --current scorecard.json --baseline baseline.json

# Trigger execution validation
lmv run --workspace-url $DATABRICKS_HOST --pipeline-name "my_pipeline"
```

**Implementation:** Typer CLI wrapping the same Python API. Same pattern as the demo
factory's `cli.py`.

