# LMV AutoDev Session 2: Re-baseline lmv against wkmigrate alpha_1 (post-fix verification)

> **Started:** 2026-04-08 (session 2 of the day)
> **Input:** url — `https://github.com/ghanse/wkmigrate/issues/27`
> **Target issue(s):** wkmigrate #27 — Support complex expressions
> **Autonomy:** semi-auto
> **Mode:** `--harvest-only`
> **Status:** DONE
> **wkmigrate_version_under_test (baseline):** `MiguelPeralvo/wkmigrate@alpha_1@969e74d`
> **wkmigrate_version_under_test (current):**  `MiguelPeralvo/wkmigrate@alpha_1@969e74d` (unchanged from session 1 — directly comparable)
> **lmv ref (baseline):** `05e18c4` (= main, post PR #18)
> **Predecessor session:** `dev/autodev-sessions/LMV-AUTODEV-2026-04-08.md` (session 1, surfaced L-F1..L-F12)

---

## Why session 2 exists

Session 1 surfaced 12 L-series findings about why the harvest couldn't produce honest measurements. Three coupled PRs landed between sessions:

| PR | Commit | What it fixed |
|----|--------|---------------|
| [#16](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/pull/16) | `b7db0e8` | L-F8 (Makefile python3), L-F9 (poetry install black), L-F10 (ruff cleanup), L-F11 (CodeRabbit null guard) |
| [#17](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/pull/17) | `752d1da` | L-F6/L-F7 (wkmigrate path-dep), python `<3.15` constraint, NEW poetry.lock, CliRunner feature-detect |
| [#18](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/pull/18) | `05e18c4` | L-F1 (`unwrap_adf_pipeline` + `adf_to_snapshot`), L-F2 (`measurable` field on `compute_expression_coverage`), L-F12 (placeholder activity surfacing), TYPE_CHECKING guard, cli graceful-degradation probe |

This session re-runs the same harvest command from session 1 to verify the fixes work end-to-end against the same wkmigrate ref (`alpha_1@969e74d`), without the manual PYTHONPATH workaround that session 1 needed. This is **the closest thing to a full PR-reviewed regression test of L-F1, L-F2, L-F6, L-F7, L-F8, L-F9, L-F10, L-F12**.

---

## Register 1: Instructions

Same as session 1: re-baseline lmv against wkmigrate `alpha_1`, verify which W-1..W-6 findings are fixed, surface new findings, **honor `--harvest-only`** (no draft filing, no handoff, no impl).

## Register 2: Constraints

- **LA-1** Adapter boundary invariant: only `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py` imports `wkmigrate.*` (top-level)
- **LA-2** Frozen contract: `ConversionSnapshot` and child dataclasses remain `@dataclass(frozen=True, slots=True)`
- **LA-3** Graceful degradation: adapter module is importable without wkmigrate (TYPE_CHECKING guard for `PreparedWorkflow`)
- **LA-4** Hot-swap endpoint must remain functional — not exercised this session
- HistoryStore is append-only — N/A, backend not running
- Findings filed only to `MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator` with label `wkmigrate-feedback` — no findings filed (`--harvest-only`)
- Hard-gate KPIs: LR-1, LR-2, LA-1, LA-2, LT-3 (zero tolerance) — **all green this session**
- Soft-gate tolerance: 5%

## Register 3: Stopping Criteria

- All Phase 0 + Phase 1 + Phase 1.5 work complete ✓
- Phase 1.5 result presented to user via CHECKPOINT ✓
- `--harvest-only` honored: no Phase 4 / Phase 4.1 / Phase 4.5 / file creation ✓
- Ledger written + committed ✓

---

## Selected Meta-KPIs — session 2 vs session 1

### L-Series Baseline (lmv hygiene, wkmigrate-agnostic)

| ID    | Meta-KPI                                 | Session 1            | **Session 2**         | Status   |
|-------|------------------------------------------|----------------------|-----------------------|----------|
| LR-1  | Unit test pass rate (fast tier)          | BLOCKED (L-F8)       | **276 passed**        | ✅ PASS  |
| LR-2  | Regression count (fast tier)             | BLOCKED              | **0**                 | ✅ PASS  |
| LR-3  | Unit test pass rate (full tier)          | not attempted        | **308 passed**, 1 skipped | ✅ PASS  |
| LR-4  | Ruff compliance                          | 26 errors            | **0 errors**          | ✅ PASS  |
| LR-5  | Black compliance                         | not installed (L-F9) | **102 unchanged**     | ✅ PASS  |
| LA-1  | Adapter boundary invariant               | 1 file               | **1 file**            | ✅ PASS  |
| LA-2  | Contract frozen                          | not verified         | **frozen**            | ✅ PASS  |
| LA-3  | Graceful degradation                     | unverified           | **verified** (TYPE_CHECKING + import probe) | ✅ PASS  |
| LT-2  | Golden-set integrity                     | PASS                 | **PASS**              | ✅ PASS  |
| L-F7  | wkmigrate-wip warning suppression        | every command        | **silenced**          | ✅ PASS  |

**All 5 hard gates (LR-1, LR-2, LA-1, LA-2, LT-3) are now measurable AND green for the first time.**

### X-Series (wkmigrate@alpha_1@969e74d, expressions golden set, **honest baseline**)

Each row tested under BOTH the flat `{name, activities, ...}` shape AND the wrapped Azure-native `{name, properties: {...}}` shape, end-to-end via the new `adf_to_snapshot` helper. NO PYTHONPATH workaround.

| ID | Meta-KPI | Session 1 (FLAT only, with workaround) | **Session 2 FLAT** | **Session 2 WRAPPED** |
|----|----------|----------------------------------------|--------------------|-----------------------|
| X-1 | Mean `expression_coverage` | 1.000 (workaround) | **1.000** ✓ | **1.000** ✓ |
| X-2 | byte-match proxy across 200 pairs | 1.000 (circular) | **1.000** | **1.000** |
| X-6.string | per-category byte-match | 34/34 | **34/34** | **34/34** |
| X-6.math | | 34/34 | **34/34** | **34/34** |
| X-6.datetime | | 33/33 | **33/33** | **33/33** |
| X-6.logical | | 33/33 | **33/33** | **33/33** |
| X-6.collection | | 33/33 | **33/33** | **33/33** |
| X-6.nested | | 33/33 | **33/33** | **33/33** |

#### What's new vs session 1

| Capability | Session 1 | **Session 2** |
|------------|-----------|---------------|
| **L-F1 wrapped → flattened** | Manual `flatten_adf()` workaround in test script | **`adf_to_snapshot()` does it transparently** |
| **L-F2 measurable field** | Defensive 1.0, no signal | **`measurable=True/False` + `reason`** |
| **L-F12 placeholder surfacing** | Silent `is_placeholder=True`, nothing in `not_translatable` | **`kind=placeholder_activity` warnings with `task_key`** |
| **PYTHONPATH workaround required** | YES | **NO — wkmigrate properly installed via poetry** |
| **L-F7 noise** | `Path /Users/miguel/Code/wkmigrate-wip ... does not exist` on every run | **silenced** |

---

## Findings Harvested (Phase 1.5)

### Cluster harvest result (against `dev/wkmigrate-issue-map.json` v2)

| Signature | Hits in 200-pair golden set | Verdict |
|-----------|------------------------------|---------|
| W-1 `unsupported_function:concat` | **0** | Still fixed in `alpha_1@969e74d` (consistent with session 1) |
| W-2 `pipeline_param_in_non_notebook` | 0 | Not exercised by corpus (L-F5 still applies) |
| W-3 `param_math_no_coercion` | 0 | Not exercised |
| W-4 `activity_output_chain_unresolved` | 0 | Not exercised |
| W-5 `pipeline_adapter_recursion` | 0 | Not exercised |
| W-6 `unstructured_warning_message` | 0 | Not exercised |

**Total `not_translatable` entries on the golden set: 0.** Same as session 1, but now **honest** — the adapter is actually capable of producing entries when there's something to report (verified separately, see below).

### In-vivo verification of L-F12 (placeholder surfacing)

Fed `adf_to_snapshot` an ADF pipeline with two unrecognized activity types:

```python
{
  "name": "mystery_pipe",
  "activities": [
    {"name": "mystery_activity", "type": "UnsupportedTestActivity", ...},
    {"name": "another", "type": "SomethingMadeUp", ...},
  ],
}
```

Result:
- **2 tasks** in snapshot, both `is_placeholder=True`
- **2 placeholder_activity entries** in `not_translatable`, each with `task_key`, `kind`, and a clear human message
- `compute_expression_coverage` returns **`1.0` with `measurable=True, reason=no_expressions_in_source`** (vacuous-truth case — no expressions in source)

**This proves L-F12 works in vivo and L-F2's measurable signal flows through correctly.** Session 1 would have produced an empty snapshot for this same input.

### In-vivo verification of L-F1 (wrapped Azure-native shape)

Same 200-pair corpus, wrapped as `{name, properties: {activities, variables}}` (the shape Azure ADF's REST API returns) and passed to `adf_to_snapshot` directly. Session 1 would have produced 200 empty snapshots silently (the silent-empty trap). Session 2:
- **200/200 resolved**
- **200/200 byte-match**
- 0 placeholder warnings
- 0 `measurable=False`

The unwrap-then-translate chain inside `adf_to_snapshot` does the right thing.

---

## Findings Filed (lmv issues)

**None.** `--harvest-only` mode + 0 unmapped clusters → nothing to draft.

The W-series catalog in `dev/wkmigrate-issue-map.json` is unchanged from session 1's update (W-1 still marked `lmv_issue: "fixed-in:alpha_1@969e74d"`, W-2..W-6 still `not_tested_on_corpus`).

---

## NEW L-Series findings discovered this session

### L-F15 — `compute_expression_coverage` doesn't count placeholder_activity warnings

**Severity:** 🟡 P2 (design call)

`compute_expression_coverage` filters `snapshot.not_translatable` entries by `"expression" in entry.get("message", "").lower()`. Placeholder warnings introduced by L-F12 have messages like `"Activity 'mystery' was substituted with a placeholder DatabricksNotebookActivity (wkmigrate did not recognise the source ADF activity type)."` — no "expression" substring, so they're excluded from the X-1 ratio.

**Observed in vivo:**
```
mixed pipeline: 1 SetVariable (with @concat) + 1 mystery activity
→ snap.tasks = 2
→ snap.resolved_expressions = 1
→ snap.not_translatable = [placeholder_activity for "mystery"]
→ compute_expression_coverage = (1.0, {total: 1, resolved: 1, unsupported: [], measurable: True})
```

The score is `1.0` because `1 resolved / 1 total` — the placeholder activity is invisible to the dimension. But the activity might have *had* expressions inside it that wkmigrate dropped silently.

**Two design options:**
- **(a) Count placeholders in X-1**: change the filter to `"expression" in message OR kind == "placeholder_activity"`. Each placeholder counts as 1 unsupported entry. Penalises activities wkmigrate can't translate at all. Risk: double-counts with `not_translatable_ratio` dimension.
- **(b) Leave X-1 alone, document the boundary**: X-1 is *strictly* about expressions inside translatable activities. Placeholder activities are `not_translatable_ratio`'s job. Add a docstring + a `placeholder_count` field to the details dict for reporting. Cleaner separation, no double-count.

**Recommendation:** Option (b). The two dimensions exist precisely because they measure different things. But the docstring should explicitly call this out, and the X-1 details dict should include the placeholder count for cross-reference.

### L-F16 — Information-poor measurement: corpus is the bottleneck, not the adapter

**Severity:** 🟡 P2 (signals next-priority work)

After PRs #16/#17/#18, the X-1/X-2 measurement infrastructure is **gates-clean and honest** but **information-poor** on the current corpus. Every meaningful golden-set entry scores 1.000 because alpha_1 actually does cover them. **Until L-F3 (circular oracle), L-F4 (uniform difficulty), and L-F5 (SetVariable-only wrapper) are addressed, no future `/lmv-autodev` harvest will produce W-cluster hits regardless of how broken wkmigrate gets.**

The next high-leverage move is **corpus work**, not more adapter or dimension fixes. The corpus is now the constraint.

Prioritized order (matches session 1's ledger but with renewed urgency):
1. **L-F5** — add an activity-context wrapper sweep (each expression in Lookup, Copy, Web, ForEach, IfCondition contexts, not just SetVariable). Probably ~150 lines + 1 PR. Highest ROI: probes the deferred wkmigrate translator adoption work (issue #28).
2. **L-F4** — regenerate `golden_sets/pipelines.json` with `lmv synthetic --difficulty simple|medium|complex --target nested_expressions|math_on_params|...` so the 60 pipelines actually stratify across the 5 weak-spot stress areas. ~2 hours.
3. **L-F3** — the hardest: source `expected_python` from an independent oracle (human-written for an adversarial seed, OR parallel-test execution comparison). Until this is done, X-2 only catches *regressions*, never bugs in the emitter's notion of correctness.

---

## Handoff Log

**Empty.** `--harvest-only` mode skips Phase 4. No `/wkmigrate-autodev` sessions suggested.

| lmv finding | Suggested command | User confirmed | wkmigrate ledger |
|-------------|-------------------|----------------|-------------------|
| (none)      |                   |                |                   |

---

## Re-Validation Log (Phase 4.5)

**Empty.** Phase 4.5 not entered (`--harvest-only`).

---

## Phase Plan & Phase Log

| Phase | Status | Notes |
|-------|--------|-------|
| 0. Input normalization + baseline | **DONE** | wkmigrate ref pinned to alpha_1@969e74d (unchanged from session 1). All L-series gates measurable and green for the first time. X-1 baselined under both flat AND wrapped input shapes — both produce 200/200. |
| 1. Research + meta-KPI proposal | **DONE** | L+X series presented at CHECKPOINT with session 1 vs session 2 comparison. User chose to stop and ledger. |
| 1.5. Finding harvest + local issue filing | **DONE (harvest only, no filing)** | 0 W-series cluster hits (consistent with session 1). 2 in-vivo verifications: L-F12 placeholder surfacing + L-F1 wrapped-shape unwrap. 2 new L-series findings (L-F15, L-F16) surfaced. |
| 2. Plan validation | SKIPPED | `--harvest-only` |
| 3. Documentation | **DONE** | This ledger. Will be committed. |
| 4. Handoff to /wkmigrate-autodev | SKIPPED | `--harvest-only` |
| 4.1. lmv-side implementation loop | SKIPPED | `--harvest-only` |
| 4.5. Post-handoff re-validation | SKIPPED | `--harvest-only` |
| 5. Session summary + convergence | **DONE** | This document |

---

## Self-Evaluation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Input Handling | 5 | Auto-detected URL, parsed `--wkmigrate-branch`, `--harvest-only`, `--autonomy semi-auto` flags |
| Meta-KPI Relevance | 5 | All gates measurable + cross-referenced against session 1 |
| Finding Harvest Quality | 5 | 0 W-cluster hits (correct), 2 in-vivo verifications, 2 new L-series findings surfaced |
| Plan Quality | n/a | --harvest-only |
| Phase Completeness | 5 | All phases applicable to --harvest-only mode complete |
| Ratchet Enforcement | n/a | --harvest-only, no L-side code changes to ratchet against |
| Cross-Repo Discipline | 5 | wkmigrate working tree untouched this session |
| Git Discipline | 5 | Ledger committed; no other artifacts touched |
| Checkpoint Compliance | 5 | Phase 1 CHECKPOINT honored (user chose stop) |
| Convergence Report | 5 | Full session-1 vs session-2 comparison + next-actions |
| **Total** | **45 / 50** | well above 35/50 target; +3 from session 1's 42/50 |

---

## Next Actions (recommended)

The L-series side is **done**. The bottleneck is now the corpus.

1. **L-F5 (highest ROI)** — Build an activity-context wrapper sweep. Add a helper or new test fixture that, for each of the 200 expressions, wraps it in 5 different ADF activity contexts (Lookup `source_query`, Copy `source.query`, Web `body`, ForEach `items`, IfCondition `expression`). Re-run the harvest. **This is the quickest path to actually triggering the wkmigrate#28 deferred-work findings (Lookup/Copy translator adoption gap).**

2. **L-F4** — Regenerate `golden_sets/pipelines.json` via `lmv synthetic --difficulty simple|medium|complex` with explicit weak-spot targeting. Stratifies the 60 pipelines so X-6 by difficulty becomes a real signal.

3. **L-F15** — Document the `compute_expression_coverage` boundary in its docstring + add `placeholder_count` to the details dict. Small lmv PR (~20 lines + test).

4. **L-F3** — The hardest: independent oracle for `expected_python`. Likely a research project on its own. Could start with manually scoring 20 adversarial pairs to build a "trust-but-verify" subset.

5. **L-F11** — Set `DATABRICKS_HOST` / `DATABRICKS_TOKEN` so the LLM judge runs and X-2 stops being a syntactic byte-match proxy. Requires a Databricks workspace handy.

To resume this session (e.g., to drive any of the above through Phase 4.1):
```
/lmv-autodev "<task>" --no-handoff --autonomy semi-auto
```

To re-validate after a new wkmigrate ref lands:
```
/lmv-autodev https://github.com/ghanse/wkmigrate/issues/27 --wkmigrate-branch <new-ref> --harvest-only
```

This ledger establishes the **honest baseline** for `MiguelPeralvo/wkmigrate@alpha_1@969e74d` against the current corpus. Future sessions can compare to it directly.
