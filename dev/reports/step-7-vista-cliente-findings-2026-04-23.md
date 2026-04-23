# Step 7 — Vista Cliente Semantic Validation Sweep: Findings

**Date:** 2026-04-23
**Branch:** `feature/step-7-vista-cliente-sweep`
**wkmigrate SHA:** `cfb49e6`
**lmv base SHA:** `f616be3` (main)
**Session ledger:** `dev/autodev-sessions/LMV-AUTODEV-STEP-7-2026-04-23.md`

## TL;DR

Vista Cliente (VC) X-1 resolution rate for `if_condition` is **1.0000** (200/200)
at wkmigrate `cfb49e6` — above the 0.80 target and above the 0.8317 CRP0001
historical baseline by +16.83 pp. The same replay on the CRP0001 golden set at
the same SHA also returns **1.0000**, which trips the ±5% hard-gate relative to
the historical baseline — attribution is wkmigrate advancement, not lmv, and
the 0.8317 baseline number should be re-pinned. X-2 semantic-equivalence is
BLOCKED for both corpora (`DATABRICKS_HOST` unset; VC has no `expected_python`
oracle). The all-contexts secondary sweep uncovered a high-severity systemic
failure on the `for_each` synthetic context (0/200 resolved, 200 placeholders),
which is the primary candidate wkmigrate issue from this sweep.

## Table 1 — X-1 / X-2 / X-6 (CRP0001 baseline vs CRP0001 replay vs VC)

### X-1 Expression Coverage (if_condition)

| Corpus | Resolved | Total | Coverage | Δ vs 0.8317 baseline | Status |
|---|---|---|---|---|---|
| CRP0001 baseline (historical) | — | — | 0.8317 | 0 | reference |
| CRP0001 replay @ `cfb49e6` | 208 | 208 | **1.0000** | +0.1683 | **hard-gate flag** |
| Vista Cliente @ `cfb49e6` | 200 | 200 | **1.0000** | +0.1683 | pass |

### X-2 Semantic Equivalence (if_condition)

| Corpus | Status |
|---|---|
| CRP0001 replay | BLOCKED — `DATABRICKS_HOST` unset |
| Vista Cliente | BLOCKED — `DATABRICKS_HOST` unset + `expected_python` null |

### X-6 Per-canonical-category Coverage (target ≥ 0.70)

| Category | CRP0001 cov | VC cov | Δ | VC pass |
|---|---|---|---|---|
| collection | 1.0000 | — | — | n/a |
| datetime | 1.0000 | — | — | n/a |
| logical | 1.0000 | 1.0000 | 0.0000 | yes |
| math | 1.0000 | — | — | n/a |
| nested | 1.0000 | 1.0000 | 0.0000 | yes |
| string | 1.0000 | — | — | n/a |

## Table 2 — Secondary sweep (VC all 7 contexts)

| Context | Coverage | not_translatable | Note |
|---|---|---|---|
| copy_query | 1.0000 | 36 | clean |
| **for_each** | **0.0000** | **200** | **placeholder substitution for all 200** |
| if_condition | 1.0000 | 194 | clean (taskValues warnings) |
| lookup_query | 1.0000 | 200 | every pipeline emits not_translatable — CRP-28 pattern |
| notebook_base_param | 1.0000 | 36 | clean |
| set_variable | 1.0000 | 36 | clean |
| web_body | 1.0000 | 36 | clean |

## Top divergent categories (X-6 Δ analysis)

VC X-6 is tied with CRP0001 on the 2 shared categories (`logical`, `nested`),
so there are **no divergent canonical categories** within the if_condition
primary sweep. Divergence surfaces only in the secondary all-contexts sweep,
where VC expressions fail on 2 contexts that are not in-scope for X-1.

### Top 5 divergent categories (reading across corpus + context pairs)

| Rank | Category | CRP0001 | VC | Δ | Hypothesis |
|---|---|---|---|---|---|
| 1 | any × `for_each` | n/a | 0.0000 | — | Synthetic wrapper emits `type=ForEach` JSON that wkmigrate's ADF loader treats as unrecognized, producing a `DatabricksNotebookActivity` placeholder. Most likely a wrapper-contract bug (missing `typeProperties.items` / `isSequential`), not a wkmigrate translator gap. |
| 2 | any × `lookup_query` | n/a | 1.0000 (noisy) | — | 200/200 not_translatable warnings despite resolution — consistent with known wkmigrate #28 Lookup/Copy translator adoption gap called out at `cli.py:296`. |
| 3 | `logical` × `if_condition` | 1.0000 | 1.0000 | 0 | No divergence — VC compound `@and`/`@or` predicates resolve identically to CRP0001 synthetic logical. |
| 4 | `nested` × `if_condition` | 1.0000 | 1.0000 | 0 | No divergence — VC `pipeline().parameters.X` / `variables('X')` patterns resolve identically. |
| 5 | VC-bucket `compound_and` (N=14) | — | 1.0000 | — | `@and(variables('continue'), variables('testPassed'))` and `@and(..., pipeline().parameters.testing, variables('continue'))` all resolve; no 3+ level compound failures observed. |

## Candidate wkmigrate issues (list only; DO NOT file)

### Candidate 1 — `wkmigrate: ForEach activity emitted by synthetic-context wrapper treated as unknown type`
- **Signature:** Wrapping any expression inside a synthetic `ForEach` activity (as emitted by `synthetic/activity_context_wrapper.py` in the `for_each` context) triggers `placeholder_activity` substitution 100% of the time with the message: _"Activity 'foreach' (type: ForEach) was substituted with a placeholder DatabricksNotebookActivity (wkmigrate did not recognise the source ADF activity type)."_
- **VC prevalence:** 200/200 in the secondary sweep (every VC expression).
- **Severity:** HIGH — either a real wkmigrate translator gap or a wrapper-contract drift; either way it invalidates the `for_each` dimension of the sweep KPI.
- **Next step:** Diff what the wrapper emits against a real ADF ForEach JSON payload (from the VC corpus) to distinguish wrapper-bug from wkmigrate-bug.

### Candidate 2 — `wkmigrate: Lookup/Copy translator adoption gap (CRP-28) — every Lookup pipeline emits not_translatable warning`
- **Signature:** Any expression wrapped in a `Lookup` activity `source.query` returns a resolved Python translation BUT also emits a `not_translatable` entry.
- **VC prevalence:** 200/200 in the secondary `lookup_query` sweep.
- **Severity:** MEDIUM — already known (`cli.py:297` docstring, `dev/autodev-sessions/LMV-AUTODEV-2026-04-08-session2.md` L-F5). Confirmed still present at `cfb49e6`.
- **Next step:** Track CRP-28 landing.

### Candidate 3 — `wkmigrate: variables() reference inside IfCondition emits best-effort taskValues fallback with warning`
- **Signature:** `@and(variables('continue'), variables('testPassed'))` resolves to a `dbutils.jobs.taskValues.get(taskKey='set_variable_continue', key='continue')` pair, but emits the warning `"variables('continue') producer not in context cache; emitting best-effort taskKey='set_variable_continue'. Likely the SetVariable lives inside a multi-activity ForEach — the resulting lookup will fail"`.
- **VC prevalence:** Observed in every `variables_ref` expression (24/24 in the VC sample).
- **Severity:** MEDIUM — produces Python that compiles but may fail at runtime when the SetVariable producer is actually inside a ForEach. The warning is correct; the need is a fix for the ForEach-SetVariable producer resolution.

## Reproduction one-liner

```bash
cd /Users/miguel.peralvo/Code/adf_to_lakeflow_jobs_migration_validator && \
git checkout feature/step-7-vista-cliente-sweep && \
python3 scripts/extract_vista_cliente_expressions.py \
  --corpus ~/Downloads/DataFactory/pipeline \
  --out golden_sets/vista_cliente_expressions.json \
  --hist dev/findings/vista-cliente-category-histogram-2026-04-23.json && \
uv run lmv sweep-activity-contexts \
  --golden-set golden_sets/vista_cliente_expressions.json \
  --contexts if_condition \
  --output dev/results/step-7-vista-cliente/sweep-if-condition-2026-04-23.json && \
uv run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions.json \
  --contexts if_condition \
  --output dev/results/step-7-vista-cliente/crp0001-baseline-replay-2026-04-23.json && \
python3 scripts/compute_step7_kpis.py
```
