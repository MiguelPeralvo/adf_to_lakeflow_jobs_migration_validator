# Lakeflow Migration Validator (`lmv`)

Evaluates the fidelity, correctness, and completeness of ADF-to-Databricks Lakeflow Jobs conversions produced by [wkmigrate](https://github.com/ghanse/wkmigrate).

## What it does

Given an ADF pipeline and its wkmigrate-produced `PreparedWorkflow`, the validator scores the conversion across 10 quality dimensions and produces a **Conversion Confidence Score (CCS)**:

| Tier | Dimensions | How |
|---|---|---|
| **Tier 1** (every commit) | Activity coverage, expression coverage, dependency preservation, notebook validity, parameter completeness, secret completeness, not-translatable ratio | Deterministic Python checks |
| **Tier 2** (nightly) | Control flow fidelity | Structural analysis |
| **Tier 3** (nightly) | Semantic equivalence | LLM-as-judge via Databricks FMAPI (Opus 4.6 / ChatGPT 5.4) |
| **Tier 4** (on-demand) | Runtime success | Deploy + run on a real Databricks cluster |

```
CCS = activity_coverage * 0.25 + expression_coverage * 0.20 + dependency_preservation * 0.15
    + notebook_validity * 0.15 + parameter_completeness * 0.10 + secret_completeness * 0.10
    + (1 - not_translatable_ratio) * 0.05
```

| CCS | Label | Action |
|---|---|---|
| 90-100 | `HIGH_CONFIDENCE` | Auto-deploy eligible |
| 70-89 | `REVIEW_RECOMMENDED` | Human reviews gaps |
| < 70 | `MANUAL_INTERVENTION` | Significant unsupported activities or expressions |

## Surfaces

The validator is accessible through four interfaces:

1. **Databricks App** (primary) — React + FastAPI dashboard with scorecard visualization, per-dimension drill-down, expression-level semantic judge reasoning, and run history
2. **MCP Server** — tools for Claude and other LLM agents: `validate_pipeline`, `validate_expression`, `suggest_fix`, etc.
3. **REST API** — the same FastAPI backend, callable from CI/CD pipelines and notebooks
4. **CLI** — `lmv evaluate`, `lmv evaluate-batch`, `lmv regression-check` for local dev

## Quick start

```python
from lakeflow_migration_validator import evaluate_pipeline

scorecard = evaluate_pipeline(source_adf_pipeline, prepared_workflow)
print(f"CCS: {scorecard.score:.0f}/100 ({scorecard.label})")
for name, result in scorecard.results.items():
    print(f"  {name}: {result.score:.2f} {'PASS' if result.passed else 'FAIL'}")
```

## Architecture

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Databricks│  │   MCP    │  │ REST API │  │   CLI    │
│    App    │  │  Server  │  │ (FastAPI)│  │ (Typer)  │
└─────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
      └──────────────┴─────────────┴──────────────┘
                         │
                 ┌───────▼──────┐
                 │  Python API  │  evaluate_pipeline()
                 │   (core)     │  evaluate_batch()
                 └───────┬──────┘  regression_check()
                         │
   ┌─────────────────────▼─────────────────────────┐
   │ Tiers 1-2: Programmatic + Structural (8 dims) │
   │ Tier 3:    LLM Judge — FMAPI (Opus/GPT)       │
   │ Tier 4:    Execution — Databricks Jobs API     │
   └───────────────────────────────────────────────┘
                         │
   MLflow (tracking)  │  FMAPI (LLM)  │  Databricks (execution)
```

## Project structure

```
src/lakeflow_migration_validator/
  dimensions/           # 10 quality dimensions
    programmatic.py     # ProgrammaticCheck base (factory-extractable)
    llm_judge.py        # LLMJudge base — FMAPI with Opus 4.6 + ChatGPT 5.4
    execution.py        # ExecutionDimension base — Databricks Jobs API
    activity_coverage.py, notebook_validity.py, ...  # concrete dimensions
  providers/
    fmapi.py            # FMAPIJudgeProvider (Opus 4.6 for calibration, ChatGPT 5.4 for batch)
    databricks_runner.py # DatabricksJobRunner
  optimization/         # DSPy-powered (opt-in)
    judge_optimizer.py  # MIPROv2/SIMBA judge prompt optimization
    synthetic_generator.py  # LLM-generated ADF expressions for stress testing
    fix_suggester.py    # dspy.Refine iterative fix suggestions
  scorecard.py          # Scorecard + CCS computation
  golden_set.py, report.py, tracking.py

apps/lmv/
  backend/              # FastAPI (REST API + App backend)
  frontend/             # React (Databricks App UI)
  mcp_server.py         # MCP tools for agentic workflows
  cli.py                # Typer CLI

tests/
  unit/validation/      # 56 TDD tests (9 passing, 47 skipped awaiting implementation)
  integration/          # Live ADF + Databricks tests
```

## Implementation status

The repo follows a TDD approach. Tests are written first, then implementation fills them in.

| Week | Scope | Status |
|---|---|---|
| **Week 1** | 7 programmatic dimensions + `evaluate_pipeline()` | Framework done, dimensions are stubs |
| **Week 2** | LLM judge (FMAPI) + execution dimension + CI | Base classes done, providers are stubs |
| **Week 3** | Databricks App + MCP + API + CLI | Directory structure + test stubs |

Current test status: **9 passed, 47 skipped**.

## Design docs

Detailed specs, architecture decisions, and implementation plans are in [`docs/`](docs/):

- [`01-conversion-validator.md`](docs/01-conversion-validator.md) — quality dimensions, CCS formula, agentic vs deterministic breakdown, cost model
- [`01-conversion-validator-spec.md`](docs/01-conversion-validator-spec.md) — full technical design, class hierarchy, TDD test specs, week-by-week plan
- [`03-validator-factory.md`](docs/03-validator-factory.md) — how this validator's abstractions extract into a reusable Validator Factory
- [`00-implementation-sequence.md`](docs/00-implementation-sequence.md) — why this validator is built first (before the factory and demo factory validator)

## Relationship to the Validator Factory

Every class in this repo is designed to be **factory-extractable**. The `Dimension` protocol, `ProgrammaticCheck`, `LLMJudge`, `ExecutionDimension`, `Scorecard`, `GoldenSet`, and `Report` are generic — no wkmigrate-specific imports. After this validator is complete, these abstractions are extracted into a standalone `validator-factory` library that can produce validators for other domains (e.g., the [demo factory](https://github.com/MiguelPeralvo/business-multi-domain-demo-factory) prompt-to-artifact pipeline).

## Development

```bash
# Install
python3.14 -m venv .venv && source .venv/bin/activate
pip install pytest

# Run tests
PYTHONPATH=src pytest tests/ -v

# Run only passing tests (skip TDD stubs)
PYTHONPATH=src pytest tests/ -v --no-header -q
```
