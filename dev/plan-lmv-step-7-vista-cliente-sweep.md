# Step 7 Plan — Vista Cliente Semantic Validation Sweep (lmv)

_Source: Google Doc `1zNokeWpHl-yWfCJd0rDrTo0sShdqVcP4pBEH7Awaul4` was inaccessible at execution time (ADC quota project missing for `docs.googleapis.com`). This document therefore summarizes the agent-reviewed plan at `<AGENT_PLANS_DIR>/tomando-en-cuenta-este-memoized-simon-agent-aa7d52dbb9cccd251.md`._

## Target state
- **Repo:** `<REPO_ROOT>`
- **wkmigrate SHA pinned:** `cfb49e6` (`pr/27-4-integration-tests`)
- **Branch:** `feature/step-7-vista-cliente-sweep` off `main` (`f616be3`)
- **Date:** 2026-04-23
- **VC corpus:** `<CORPUS_DIR>/` — 327 pipelines

## Motivation
After Step 6 landed CRP0001 baseline X-1 = 0.8317, we need a second real-corpus datapoint to verify the resolution-rate KPI generalizes. Vista Cliente (VC) is the next ADF corpus in scope and has 212 IfCondition activities across 119 pipelines with complex compound predicates.

## Golden set shape
- Path: `golden_sets/vista_cliente_expressions.json`
- Structure: `{count, expressions:[{adf_expression, category (canonical 6), vc_category (9 VC buckets), expected_python (nullable), source:{pipeline, activity_name, depth}}]}`
- Sampling: stratified across 9 VC buckets (`compound_and`, `compound_or`, `nested_predicate`, `equals_binary`, `contains_intersection_empty`, `bare_activity_output`, `variables_ref`, `concat_string`, `pipeline_param_ref`), min floor 12/bucket, total ≥ 200.
- VC→canonical category mapping preserves X-6 per-category KPI compatibility.

## Primitives used
- `uv run lmv sweep-activity-contexts --contexts if_condition` for the primary X-1 resolution-rate sweep.
- `uv run lmv batch --threshold 75` for X-2 semantic_equivalence on hand-seeded subset (requires `DATABRICKS_HOST` for judge — probe first, otherwise mark BLOCKED).
- `uv run lmv sweep-activity-contexts` (all contexts) as an informational secondary run.
- `lmv batch-expressions` does NOT exist (L-8 backlog); this plan uses the two above instead.

## KPIs / Gates
- **X-1 expression_coverage ≥ 0.80** — primary.
- **X-2 semantic_equivalence ≥ 0.75** — partial on VC (hand-seeded subset).
- **X-6 per-canonical-category ≥ 0.70** — 6 canonical categories × 2 corpora.
- **Hard gate:** CRP0001 replay at same SHA must be within ±5% of 0.8317. Flag (not abort) if violated.
- **L-series hard gates:** LR-1/LR-2/LA-1/LA-2/LT-3 — zero tolerance. Stop session if tripped.

## Deliverables (all in this branch)
1. `dev/plan-lmv-step-7-vista-cliente-sweep.md` (this file)
2. `scripts/extract_vista_cliente_expressions.py` — the VC corpus extractor
3. `scripts/compute_step7_kpis.py` — KPI aggregator
4. `golden_sets/vista_cliente_expressions.json` — 200+ stratified sample
5. `dev/findings/vista-cliente-category-histogram-2026-04-23.json` — full bucket histogram
6. `dev/results/step-7-vista-cliente/` — primary/secondary/CRP0001-replay sweep JSONs
7. `dev/autodev-sessions/LMV-AUTODEV-STEP-7-2026-04-23.md` — session ledger (Register 1/2/3)
8. `dev/reports/step-7-vista-cliente-findings-2026-04-23.md` — findings report

## Execution order
§1 branch → §2 pre-flight → §3 golden set → §4 sweeps → §5 KPI compute → §6 ledger → §7 findings → §8 commit+push.
