# L-F20 — Adapter surfaces CRP-11 wrapper body for IfCondition predicates

> **Session:** LMV-AUTODEV-2026-04-17-kpi-convergence
> **Input:** `kpi:X-1>=0.90,X-2>=0.90,X-6.logical>=0.95,X-6.nested>=0.90,X-6.collection>=0.95`
> **Autonomy:** semi-auto
> **Status:** IMPLEMENTED — awaiting push/PR approval

## Problem

Post-CRP-11 (wkmigrate PR #19 merge into `pr/27-4-integration-tests@e21c1e3`),
compound IfCondition predicates no longer live on `condition_task`:

- `IfConditionActivity.left`  = `"{{tasks.<wrap>.values.branch}}"`
- `IfConditionActivity.right` = `"True"`
- Real predicate body        = `IfConditionActivity.wrapper_notebook_content`
  (`_branch = bool(<python_expression>)`)

The L-F17 walker in `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py`
routed this new shape through the legacy `(left op right)` path, producing
`({{tasks.if_cond__crp11_wrap.values.branch}} == True)` as the "resolved
python_code". All 195/208 compound if_condition golden-set expressions
collapsed to this template reference — unusable for X-2 semantic equivalence.

## Evidence (pre-fix)

`lmv sweep-activity-contexts --golden-set golden_sets/expressions.json` on
wkmigrate@`e21c1e3`:

| Context | Resolved | Wrapper-template collapse | Real Python |
|---|---|---|---|
| if_condition | 208/208 | 195 | 13 (native INV-1 binary cases) |

Per-category X-6 shape (if_condition context):

| Category    | Total | Native-Python pre-fix |
|-------------|:-----:|:---------------------:|
| collection  | 41 | 0 |
| datetime    | 33 | 0 |
| logical     | 33 | 13 |
| math        | 34 | 0 |
| nested      | 33 | 0 |
| string      | 34 | 0 |

## Fix

`src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py`:

1. New helper `_extract_wrapper_branch_expression(content) -> str | None`.
   Scans the deterministic wrapper body for the line starting with
   `_branch = bool(` and returns the parenthesised payload, or `None` for
   the INV-5 `raise NotImplementedError` path.
2. In `_extract_resolved_expression_pairs` IfCondition branch:
   - If `wrapper_notebook_key` is set: extract via helper; emit real-Python
     pair when successful, otherwise emit **no pair** (not_translatable
     already captures the failure; emitting the template ref would mislead
     the judge).
   - If not set: keep the existing binary / pre-CRP-11 compound branches
     untouched (backward-compat with IR produced on older wkmigrate refs).

## Tests (all added to `tests/unit/validation/test_wkmigrate_adapter_lf17.py`)

| Test | Verifies |
|------|----------|
| `test_lf20_adapter_extracts_wrapper_body_for_compound_if_condition` | Happy path: `_branch = bool(...)` becomes the resolved python_code |
| `test_lf20_adapter_preserves_native_binary_when_no_wrapper` | INV-1 native binary path unaffected |
| `test_lf20_adapter_skips_if_condition_when_wrapper_body_malformed` | INV-5 `raise NotImplementedError` wrapper body emits no pair |
| `test_lf20_wrapper_extractor_unit` | Direct unit coverage: nested parens, empty, None, malformed |

## Evidence (post-fix, same wkmigrate ref)

- Unit tests: **421/421 passed** (was 417 pre-fix; +4 new L-F20 tests).
- Ruff clean. Black clean on touched files.
- `lmv sweep-activity-contexts` post-fix: if_condition **0 wrapper-template collapses**, 208/208 real Python.
- wkmigrate's `scripts/check_wrapper_semantic_equivalence.py --golden golden_sets/expressions.json` reports **208/208 eval match (100%)** on the full 208-pair corpus. Wrapper-relevant subset (collection + logical + nested = 107): **107/107 = 100%**.

## KPI snapshot

| KPI | Target | Pre-fix | Post-fix | Status |
|---|:---:|:---:|:---:|:---:|
| LR-1 unit tests | 100% | 417/417 | 421/421 | PASS |
| LR-2 regression count | 0 | 0 | 0 | PASS |
| LR-4 ruff | clean | clean | clean | PASS |
| LA-1 adapter boundary | 1 file | OK | OK | PASS |
| LA-2 contract frozen | 100% | OK | OK | PASS |
| **X-1** mean expression_coverage | ≥0.90 | 0.86 (weighted across 7 contexts) | 0.86 | signal (ForEach W-10 bounds X-1; CRP-11-related collapse resolved) |
| **X-2** mean semantic_equivalence (eval proxy) | ≥0.90 | collapsed on 195 cases | **1.00** (208/208) | PASS |
| **X-6.logical** | ≥0.95 | 0.39 (13/33) | 1.00 | PASS |
| **X-6.nested** | ≥0.90 | 0.00 (0/33) | 1.00 | PASS |
| **X-6.collection** | ≥0.95 | 0.00 (0/41) | 1.00 | PASS |

X-1 still sits at 0.86 because the `for_each` context remains at 8/208 —
this is the long-standing W-10 gap (ForEach items silent placeholder), not
CRP-11 territory. Re-validated this session with `last_tested` update in
`dev/wkmigrate-issue-map.json`. The five session targets that *are* tied to
CRP-11 (X-2 and X-6.logical/nested/collection) all converge.

## Next actions

1. Commit + push on a feature branch.
2. Open PR against `main` with L-F20 label.
3. Optional follow-up: resolve ForEach items (W-10) upstream in wkmigrate to push X-1 past 0.95 across all 7 contexts.
4. Post-merge: file `L-F20` as a GitHub issue on `MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator` closing out the harvest draft.
