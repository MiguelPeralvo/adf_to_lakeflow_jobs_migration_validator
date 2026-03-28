# Implementation Status & Remaining Work

> **Updated:** 2026-03-28
> **Repo:** https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator

---

## What's Done (Weeks 1-5, merged to main)

### Week 1: Core Dimensions + Adapter (PR #1)
- [x] `contract.py` — ConversionSnapshot + 6 child dataclasses
- [x] `adapters/wkmigrate_adapter.py` — from_wkmigrate() mapping
- [x] 7 programmatic dimensions (activity_coverage, notebook_validity, parameter_completeness, secret_completeness, dependency_preservation, expression_coverage, not_translatable_ratio)
- [x] `scorecard.py` — Scorecard with CCS computation
- [x] `evaluate()` + `evaluate_from_wkmigrate()` entry points
- [x] 53 unit tests passing

### Week 2: Synthetic Generation (PR #2)
- [x] `synthetic/expression_generator.py` — template-based ADF expression + Python pairs
- [x] `synthetic/pipeline_generator.py` — parameterized ADF pipeline JSON templates
- [x] `synthetic/ground_truth.py` — GroundTruthSuite with evaluate_converter()
- [x] `synthetic/runner.py` — run_synthetic_workflow() with triage
- [x] `golden_sets/expressions.json` (200 pairs), `pipelines.json`, `regression_pipelines.json`
- [x] 90 unit tests passing

### Week 3: Agentic Dimensions + CI (PR #3)
- [x] `providers/fmapi.py` — FMAPIJudgeProvider (Opus 4.6 + ChatGPT 5.4)
- [x] `providers/databricks_runner.py` — DatabricksJobRunner
- [x] `dimensions/semantic_equivalence.py` — LLMJudge dimension
- [x] `dimensions/runtime_success.py` — ExecutionDimension
- [x] `evaluate_full()` — with optional agentic dimensions
- [x] CI score gate (`tests/integration/test_score_gate.py`)
- [x] Regression baseline (`golden_sets/regression_pipelines.json`)
- [x] 127 unit tests passing

### Week 4: Harness + Surfaces (PR #4)
- [x] `harness/harness_runner.py` — HarnessRunner orchestration
- [x] `harness/adf_connector.py` — ADFConnector with DI + from_credentials stub
- [x] `harness/fix_loop.py` — FixLoop with judge-powered suggestions
- [x] `api.py` — FastAPI with 7 endpoints
- [x] `mcp_server.py` — LMVMCPServer + create_mcp_server()
- [x] `cli.py` — Typer CLI with 6 commands
- [x] `serialization.py` — ConversionSnapshot JSON round-trip
- [x] 162 unit tests passing

### Week 5: Parallel Testing + App (PR #5)
- [x] `parallel/adf_runner.py` — ADFExecutionRunner
- [x] `parallel/comparator.py` — OutputComparator with type normalization
- [x] `parallel/parallel_test_runner.py` — ParallelTestRunner
- [x] `dimensions/parallel_equivalence.py` — Dimension 11
- [x] `apps/lmv/` — Databricks App scaffold (backend + frontend)
- [x] `app.yaml` — Databricks Apps deployment config
- [x] 205 unit tests passing

### Post-Week 5: App + Stitch Integration
- [x] Single-process backend serving frontend + API + MCP
- [x] Environment-based dependency injection
- [x] React frontend with 7 pages (Validate, Expression, Harness, Parallel, Batch, Synthetic, History)
- [x] Stitch design system applied (dark M3 theme, Material icons, Tailwind v4)
- [x] YAML input support for /api/validate
- [x] Hash-based routing (#/validate, #/expression, etc.)
- [x] Stitch design prompts + 8 generated screens downloaded

---

## What's Left

### Priority 1: Agent-Backed Synthetic Generator
**Status:** Template-only. `mode="llm"` and `mode="adversarial"` raise NotImplementedError.

**What's needed:**
- LLM-powered pipeline generation via FMAPI that understands ADF's real pipeline model
- Valid activity type combinations, realistic dependency chains, parameter cross-references
- Targeting wkmigrate's known weak spots (nested expressions, partial activity support)
- DSPy optimization of the generator prompt to maximize converter failure discovery rate
- Feedback loop: when wkmigrate fails, generate more cases in that failure neighborhood
- UI integration: Synthetic page should show generation quality, not just pipeline names

**Files:** `synthetic/pipeline_generator.py`, `synthetic/expression_generator.py`, new `synthetic/agent_generator.py`
**Tests:** `tests/unit/synthetic/test_agent_generator.py`
**Depends on:** FMAPI provider (done), DSPy (new dep)

### Priority 2: ADFConnector Real Implementation
**Status:** `from_credentials()` raises NotImplementedError.

**What's needed:**
- Import wkmigrate's `FactoryClient` + `FactoryDefinitionStore`
- Implement `list_pipelines()`, `fetch_pipeline()`, `translate_and_prepare()`
- Wire into HarnessRunner so the Harness page actually works
- Handle authentication (service principal via env vars)

**Files:** `adapters/wkmigrate_adapter.py` (extend), `harness/adf_connector.py`
**Tests:** `tests/unit/validation/test_adf_connector.py` (new), integration test with real ADF
**Depends on:** wkmigrate installed

### Priority 3: DSPy Judge Calibration
**Status:** Semantic equivalence judge uses uncalibrated prompt. No DSPy optimization.

**What's needed:**
- `optimization/judge_optimizer.py` — wrap LLMJudge as DSPy module
- MIPROv2 or SIMBA optimization against human-labeled calibration pairs
- Golden expression pairs from synthetic generator as calibration data
- Track optimization runs in MLflow
- Calibrated judge should improve from ~0.7 to ~0.9 human agreement

**Files:** `optimization/judge_optimizer.py`, `optimization/synthetic_generator.py`
**Tests:** `tests/unit/validation/test_judge_optimizer.py`
**Depends on:** DSPy 3.x, golden set data (from Priority 1)

### Priority 4: Frontend Polish (Stitch Design Fidelity)
**Status:** Stitch designs applied but rough. Missing glass panels, gradient effects, proper spacing.

**What's needed:**
- Full conversion of 8 Stitch HTML screens to React (currently partial)
- Bento grid dimension cards on Harness page
- Glass panel effects on results
- Traffic-light dots on code editors
- Top header bar with search, notifications, settings
- Capability status bar in sidebar (done)
- Responsive layout fixes

**Files:** `apps/lmv/frontend/src/pages/*.tsx`, `apps/lmv/frontend/src/components/*.tsx`
**Depends on:** Nothing — purely frontend

### Priority 5: CI Workflow for Integration Tests
**Status:** No GitHub Actions workflow runs integration tests.

**What's needed:**
- `.github/workflows/integration.yml` — runs on merge to main
- Uses existing GitHub secrets (AZURE_*, DATABRICKS_*)
- Runs `pytest -m integration` (ADF tests) and optionally `pytest -m databricks`
- Databricks tests only on manual trigger (cost control)

**Files:** `.github/workflows/integration.yml`
**Depends on:** Nothing

### Priority 6: Fix Loop with Real Advance Function
**Status:** FixLoop breaks after first suggestion without advance_fn.

**What's needed:**
- Implement `advance_fn` that re-runs wkmigrate translate+prepare after applying a fix
- Wire into HarnessRunner so `max_iterations > 1` actually iterates
- Requires ADFConnector (Priority 2) to re-translate

**Files:** `harness/fix_loop.py`, `harness/harness_runner.py`
**Depends on:** Priority 2 (ADFConnector)

### Priority 7: Configurable Expression Emission
**Status:** Documented in `dev/configurable-expression-emission.md`. Not implemented.

**What's needed:**
- `EmissionConfig` dataclass in wkmigrate
- Pluggable function registry (allow runtime registration)
- Per-context emission strategy routing
- This is a **wkmigrate** change, not an lmv change

**Files:** wkmigrate `src/wkmigrate/parsers/expression_functions.py`, `expression_emitter.py`
**Depends on:** Proposal to @ghanse

---

## Implementation Sequence

```
Priority 1 (Agent Synthetic) ──→ Priority 3 (DSPy Judge) ──→ Priority 6 (Fix Loop)
Priority 2 (ADFConnector)     ──→ Priority 6 (Fix Loop)
Priority 4 (Frontend)         (independent)
Priority 5 (CI Workflow)      (independent)
Priority 7 (Emission Config)  (wkmigrate scope, separate)
```

Parallel branches:
- `feature/agent-synthetic-generator` — Priorities 1 + 3
- `feature/adf-connector-impl` — Priority 2
- `feature/frontend-stitch-polish` — Priority 4
- `feature/ci-integration-workflow` — Priority 5
