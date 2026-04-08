# LMV AutoDev Session: Re-baseline lmv against wkmigrate alpha_1 and harvest

> **Started:** 2026-04-08
> **Input:** url — `https://github.com/ghanse/wkmigrate/issues/27`
> **Target issue(s):** wkmigrate #27 — Support complex expressions
> **Autonomy:** semi-auto
> **Mode:** `--harvest-only` (stops after Phase 1.5; no draft filing, no handoff, no implementation)
> **Status:** DONE
> **wkmigrate_version_under_test (baseline):** `MiguelPeralvo/wkmigrate@alpha_1@969e74d`
> **wkmigrate_version_under_test (current):**  `MiguelPeralvo/wkmigrate@alpha_1@969e74d`
> **lmv ref (baseline):** uncommitted (dev/ artifacts only)

---

## Register 1: Instructions

Re-baseline lmv against wkmigrate `alpha_1` (sha `969e74d`), which contains the
fully merged 5-phase implementation of wkmigrate issue #27 (parser → emitter →
datetime helpers → translator adoption → integration tests). Verify which of
the seeded W-1..W-6 findings are now fixed; surface any new findings; produce
PR-review evidence (X-1 / X-2 journey table) for the polished `pr/27-0..4`
branches that ghanse will see upstream.

## Register 2: Constraints

- **LA-1** Adapter boundary invariant: only `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py` imports `wkmigrate.*` — verified
- **LA-2** Frozen contract: `ConversionSnapshot` and child dataclasses remain `@dataclass(frozen=True, slots=True)` — not mutated this session
- **LA-3** Graceful degradation: no provider may become required for startup
- **LA-4** Hot-swap endpoint must remain functional — N/A this session, backend not running
- HistoryStore is append-only — N/A, backend not running
- Findings filed only to `MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator` with label `wkmigrate-feedback` — no findings filed (`--harvest-only`)
- Hard-gate KPIs: LR-1, LR-2, LA-1, LA-2, LT-3 (zero tolerance)
- Soft-gate tolerance: 5%
- Max plan iterations: 3 (not exercised — harvest-only)
- Max impl iterations: 2 (not exercised — harvest-only)

## Register 3: Stopping Criteria

- All Phase 0 + Phase 1 + Phase 1.5 work complete
- Phase 1.5 result presented to user via CHECKPOINT
- `--harvest-only` honored: no Phase 4 / Phase 4.1 / Phase 4.5 / file creation
- Updated `dev/wkmigrate-issue-map.json` with W-1..W-6 last_tested fields
- Session ledger written to `dev/autodev-sessions/LMV-AUTODEV-2026-04-08.md`

---

## Selected Meta-KPIs

### L-Series Baseline (lmv hygiene, wkmigrate-agnostic)

| ID    | Meta-KPI                                | Target | Current               | Status   |
|-------|-----------------------------------------|--------|-----------------------|----------|
| LR-1  | Unit test pass rate (fast tier)         | 100%   | **CANNOT RUN** (L-F8) | BLOCKED  |
| LR-2  | Regression count (fast tier)            | 0      | CANNOT RUN            | BLOCKED  |
| LR-3  | Unit test pass rate (full tier)         | 100%   | not attempted         | --       |
| LR-4  | Ruff compliance                         | 0 err  | **26 errors** (L-F10) | FAIL     |
| LR-5  | Black compliance                        | 0 diff | **NOT INSTALLED** (L-F9) | BLOCKED |
| LR-6  | mypy (informational)                    | no new | not run               | --       |
| LA-1  | Adapter boundary invariant              | 1 file | **1 file**            | **PASS** |
| LA-2  | Contract frozen                         | 100%   | not verified (no mutations) | --       |
| LA-3  | Graceful degradation preserved          | clean  | not measured          | --       |
| LA-4  | Hot-swap endpoint healthy               | 200 OK | backend not running   | --       |
| LA-5  | `evaluate_full` survives missing judge  | passes | not run               | --       |
| LT-1  | Test count delta                        | ≥ 0    | CANNOT RUN            | --       |
| LT-2  | Golden-set integrity                    | 100%   | **PASS** (200 expressions, 6 categories present) | **PASS** |
| LT-3  | Regression pipelines pass               | exit 0 | not run               | --       |

### X-Series (wkmigrate@alpha_1@969e74d, expression golden-set corpus)

| ID    | Meta-KPI                                              | Target  | Current   | Caveat |
|-------|-------------------------------------------------------|---------|-----------|--------|
| X-1   | mean expression_coverage on `expressions.json` (200 pairs, wrapped SetVariable, FLAT input) | ≥0.80   | **1.000** | corpus too thin (L-F4, L-F5); X-1 silently 1.0 when total==0 (L-F2) |
| X-2 (proxy) | byte-equivalence to expected_python on the 200 pairs | ≥0.75   | **1.000** | corpus is wkmigrate-circular (L-F3) |
| X-6.string    | per-category byte-match | ≥0.70 | **34/34** (1.000) | |
| X-6.math      | per-category byte-match | ≥0.70 | **34/34** (1.000) | |
| X-6.datetime  | per-category byte-match | ≥0.70 | **33/33** (1.000) | depends on PR 27-2 datetime helpers |
| X-6.logical   | per-category byte-match | ≥0.70 | **33/33** (1.000) | |
| X-6.collection | per-category byte-match | ≥0.70 | **33/33** (1.000) | |
| X-6.nested    | per-category byte-match | ≥0.70 | **33/33** (1.000) | |
| X-3   | % unsupported attributable to a tracked finding | ≥0.90 | **n/a** | 0 unsupported entries total |
| X-4   | findings filed this session (counter) | ≥1 | **0** | `--harvest-only` mode |
| X-5   | regressions caught after apply (counter) | n/a | n/a | hot-swap not used |
| X-6   | per-category mean expression_coverage | all ≥0.70 | all 1.000 | corpus uniform / circular |
| X-7   | time-to-detection after apply | ≤120s | n/a | hot-swap not used |
| X-8   | synthetic generator weak-spot hit rate | ≥0.60 | not measured | |
| X-9   | findings closed by upstream merge | n/a | n/a | no upstream PRs filed yet |

---

## Findings Harvested (Phase 1.5)

### Cluster harvest result (against `dev/wkmigrate-issue-map.json` v2)

| Signature | Hits on alpha_1 | Verdict |
|-----------|-----------------|---------|
| W-1 `unsupported_function:concat`         | **0** | **FIXED in alpha_1@969e74d** (verified: 34/34 string-category resolved + byte-match) |
| W-2 `pipeline_param_in_non_notebook`      | 0 | **NOT TESTED** — corpus has no `@pipeline().parameters.X` references; needs adversarial fixtures |
| W-3 `param_math_no_coercion`              | 0 | **NOT TESTED** — math literals resolve fully; type-coercion path on parameter refs unexercised |
| W-4 `activity_output_chain_unresolved`    | 0 | **NOT TESTED** — corpus has no multi-activity chains and never wraps in Lookup |
| W-5 `pipeline_adapter_recursion`          | 0 | **NOT TESTED** — corpus has no Execute Pipeline / recursive structure |
| W-6 `unstructured_warning_message`        | 0 | **NOT TESTED** — corpus produced 0 not_translatable warnings of any kind, so no payloads to tag |

### Multi-branch journey table (PR-review evidence for ghanse upstream review)

Each row: switch wkmigrate to `<ref>`, fresh-process measurement against the 200-pair golden set wrapped as SetVariable activities.

```
branch                             sha         resolved  unsupp  empty  err   X-1     X-2-byte
                                                                              ────────────────
pr/27-0-expression-docs            e6b5c25     0         0       0      0     0.000   0.000
pr/27-1-expression-parser          be9e3a5     167       0       0      0     1.000*  0.835
pr/27-2-datetime-emission          7b0bcd5     200       0       0      0     1.000   1.000
pr/27-3-translator-adoption        3d8c541     200       0       0      0     1.000   1.000
pr/27-4-integration-tests          4313f21     200       0       0      0     1.000   1.000
alpha (= phases 1-5 merged)        7ae9575     200       0       0      0     1.000   1.000
alpha_1 (= alpha + lint + dev docs) 969e74d    200       0       0      0     1.000   1.000
```

`* X-1=1.000 on pr/27-1 is misleading — 33 datetime expressions silently produce` `resolved=0/unsupp=0` `which compute_expression_coverage maps to 1.0 by default. See L-F2.`

#### Per-category byte-match progression

```
branch                            string  math   datetime  logical  collection  nested
pr/27-0-expression-docs            0/34    0/34   0/33      0/33     0/33        0/33
pr/27-1-expression-parser         34/34   34/34   0/33     33/33    33/33       33/33
pr/27-2-datetime-emission         34/34   34/34  33/33     33/33    33/33       33/33
pr/27-3-translator-adoption       34/34   34/34  33/33     33/33    33/33       33/33
pr/27-4-integration-tests         34/34   34/34  33/33     33/33    33/33       33/33
alpha                             34/34   34/34  33/33     33/33    33/33       33/33
alpha_1                           34/34   34/34  33/33     33/33    33/33       33/33
```

#### Interpretation (the message ghanse should see in PR bodies)

| PR | Cumulative byte-match | Δ vs prior | What it actually delivers |
|----|-----------------------|------------|---------------------------|
| **PR 27-0** | 0.000 | — | Architecture doc — establishes vocabulary. No measurable expression coverage on `main` baseline. |
| **PR 27-1** | **0.835** | **+0.835** | Parser + emitter + 47-Python-fn registry. Resolves 5 of 6 categories outright (string, math, logical, collection, nested = 167/200). Datetime is gated on the runtime helpers in PR 27-2. |
| **PR 27-2** | **1.000** | **+0.165** | Datetime helpers + Spark SQL emitter + EmissionConfig. Closes the last 33-expression datetime category → full coverage on this corpus. **Validates the bundling decision in `dev/pr-strategy-issue-27.md`**. |
| **PR 27-3** | 1.000 | 0.000 | No measurable delta on the SetVariable-wrapped corpus. Translator adoption affects Notebook/Web/ForEach/IfCondition wrappers — needs an activity-context sweep to surface its real contribution. |
| **PR 27-4** | 1.000 | 0.000 | Tests only. No behavior delta as expected. |
| **alpha → alpha_1** | 1.000 | 0.000 | Lint cleanup + emission_config threading + dev docs. No expression-coverage delta — alpha already has the resolution work merged in. |

#### Raw measurement artifacts (under `/tmp/`)

- `/tmp/lmv_branch_measure.py` — fresh-process measurement script
- `/tmp/sweep_alpha.json`, `/tmp/sweep_alpha_1.json`
- `/tmp/sweep_pr_27-0-expression-docs.json` ... `/tmp/sweep_pr_27-4-integration-tests.json`
- `/tmp/lmv_journey_table.json` — aggregated journey table
- `/tmp/lmv_x1_baseline.json`, `/tmp/lmv_x1_alpha1_real.json`, `/tmp/lmv_expressions_alpha1.json`, `/tmp/lmv_x2_alpha1_syntactic.json` — earlier baseline runs

---

## Findings Filed (lmv issues)

**None.** `--harvest-only` mode — no `gh issue create` invocations this session.

The W-series catalog has been updated in `dev/wkmigrate-issue-map.json` (v1 → v2) with `last_tested` provenance and `status: fixed | not_tested_on_corpus` markers. W-1 is now marked `lmv_issue: "fixed-in:alpha_1@969e74d"`.

---

## L-Series Findings (NEW — surfaced incidentally during baseline)

These are the *real* fish from this session. The W-series had nothing to file because alpha_1 fully clears the corpus. The actual findings are all on the lmv side and they explain why X-series measurements were giving misleading results.

| ID | Severity | Finding | Where to fix |
|----|----------|---------|--------------|
| **L-F1** | 🔴 P0 | **Schema drift between lmv golden set and wkmigrate `translate_pipeline()`.** wkmigrate alpha_1's `translate_pipeline()` accepts the FLATTENED ADF shape `{name, activities, parameters}` but **silently produces `tasks: []` with zero warnings** when given the WRAPPED Azure-native shape `{name, properties: {activities, parameters}}`. lmv's `golden_sets/pipelines.json` uses the wrapped shape. Result: every X-series KPI was silently wrong before the workaround. | `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py` should unwrap `properties` before calling, OR file a wkmigrate finding asking `translate_pipeline` to either auto-unwrap or warn |
| **L-F2** | 🟠 P1 | **`compute_expression_coverage` returns `1.0` by default when `total == 0`** (`dimensions/expression_coverage.py:14-15`). This masks the silent-empty-IR case from L-F1 by reporting perfect coverage instead of `None` / a sentinel. Distinguishes "no expressions in source" from "evaluator could not measure". | `src/lakeflow_migration_validator/dimensions/expression_coverage.py:14-15` — return a 3-tuple `(score, details, was_measurable)` or use `None` for unmeasured |
| **L-F3** | 🟠 P1 | **`golden_sets/expressions.json` is wkmigrate-circular.** All 200 `expected_python` strings byte-match alpha_1's emitter output exactly, suggesting the corpus was generated by running this same emitter. Means X-2 measurements against this corpus only catch *regressions*, never bugs in the emitter's notion of correctness. | Source `expected_python` from an independent oracle: human-written, ADF→Python reference docs, or parallel-test execution comparison |
| **L-F4** | 🟡 P2 | **`golden_sets/pipelines.json` is uniform medium difficulty.** All 60 pipelines are `difficulty=medium`, all use 3-4 trivial expressions (`@concat('hello', 'world')`, `@equals(1,1)`, `@item()`). Cannot stratify X-6 by category from this corpus, cannot stress W-2..W-5. | Regenerate `pipelines.json` with `lmv synthetic --difficulty simple|medium|complex --target nested_expressions|math_on_params|...`, balancing across the 5 weak-spot stress areas |
| **L-F5** | 🟡 P2 | **The 200-pair corpus only wraps each expression in a SetVariable activity.** Never exercises Lookup, Copy, Web, ForEach, IfCondition wrappers where alpha_1 has lower or zero translator adoption (per `dev/pr-strategy-issue-27.md`'s deferred work to wkmigrate #28). | Add `lmv batch-expressions --activity-context lookup|copy|web|foreach|ifcondition` (extends L-8 in lmv-autodev's L-series backlog) — for each expression, wrap in each context and re-measure |
| **L-F6** | 🟠 P1 | **lmv venv has a stale namespace-package install of wkmigrate** at `/private/var/folders/.../T/lmv_wkmigrate_cache/MiguelPeralvo__wkmigrate/src/wkmigrate`. Cache directory has the subpackages but is missing `__init__.py` / `__about__.py`, so it registers as a namespace package and produces zero `iter_modules` results. The hot-swap endpoint hadn't been called this session, leaving the venv in a half-built state. Workaround: prepend `PYTHONPATH=/Users/miguel/Code/wkmigrate/src` to use the local checkout. | The hot-swap apply path should ensure `__init__.py` is copied / written when caching, OR the venv install should be a real `pip install -e` not a namespace stub |
| **L-F7** | 🟡 P2 | **Stale `wkmigrate-wip` path config.** Every `poetry run python` invocation prints `Path /Users/miguel/Code/wkmigrate-wip for wkmigrate does not exist`. Some lmv startup code (likely `apps/lmv/backend/main.py:100-102` per the architecture explore) hardcodes a `wkmigrate-wip` discovery path that was never created on this machine. Cosmetic but pollutes logs. | Make the discovery path optional and silent when missing |
| **L-F8** | 🟠 P1 | **`make test` (LR-1) is broken.** The Makefile invokes bare `python` (`PYTHONPATH=src python -m pytest ...`) and the user's environment has `python3` but no `python`. Blocks LR-1 / LR-2 / LR-3 entirely. | `Makefile` — change `python` to `poetry run python` or `python3` |
| **L-F9** | 🟡 P2 | **`black` is not installed in the lmv poetry env.** `poetry run black --check` fails with `Command not found: black`. LR-5 cannot be measured at all. | `poetry add --group dev black` OR remove LR-5 from the meta-KPI catalog |
| **L-F10** | 🟠 P1 | **`ruff check` reports 26 errors** in lmv codebase (mostly unused imports under `tests/unit/validation/`). Soft-gate LR-4 fail. 16 are auto-fixable. | `poetry run ruff check --fix src tests` then triage the remaining 10 |
| **L-F11** | 🟡 P2 | **No LLM judge available locally.** `_JUDGE_PROVIDER` is None because `DATABRICKS_HOST` isn't set in this shell, so true X-2 (semantic equivalence) cannot be computed in this session. Worked around with a syntactic byte-match proxy, but that proxy is itself contaminated by L-F3 (circular corpus). | Either run with `DATABRICKS_HOST` / `DATABRICKS_TOKEN` set, OR implement L-F11-mitigation: an offline judge using ast-equivalence + symbolic execution as a stronger-than-byte-match proxy |
| **L-F12** | 🟡 P2 | **wkmigrate's pre-#27 wkmigrate (= main / pr/27-0) silently maps `SetVariable` activities to `DatabricksNotebookActivity` placeholders.** The IR has 1 task but it's the wrong type (`DatabricksNotebookActivity` instead of `SetVariableActivity`), and the lmv adapter's `variable_name`/`variable_value` extraction finds nothing. Produces a third class of false-zero distinct from L-F1 (schema drift) and L-F2 (defensive 1.0). | `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py` should detect placeholder activities and emit them as `not_translatable` entries with a clear marker, instead of producing an empty `resolved_expressions` |

### G-series candidates (wkmigrate-side, NOT filed this session)

Per the doc-only constraint (your decision in the design session), these stay queued until both (a) the lmv-side corpus is rebuilt to actually probe them and (b) they appear in a real harvest under a real `wkmigrate_version_under_test`:

| ID | Title | Mapped upstream |
|----|-------|----------------|
| G-1 | wkmigrate `translate_pipeline()` should warn on unrecognized top-level shape (instead of silently producing empty IR for the wrapped Azure-native form) | follow-up to ghanse/wkmigrate#27 / new wkmigrate issue |
| G-2 | Lookup/Copy translator adoption (deferred per `dev/pr-strategy-issue-27.md` to "proposed issue #28") | future ghanse/wkmigrate#28 |
| G-3 | Repsol-driven function registry gap (~34-40 missing functions deferred per `dev/pr-strategy-issue-27.md` to "proposed issue #29") | future ghanse/wkmigrate#29 |

---

## Handoff Log

**Empty.** `--harvest-only` mode skips Phase 4. No `/wkmigrate-autodev` sessions suggested this run.

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
| 0. Input normalization + baseline | **DONE** | wkmigrate ref pinned to alpha_1@969e74d. lmv backend not running → bypassed via local PYTHONPATH. L-series baseline blocked by L-F8/L-F9; LA-1 PASS; X-1/X-6/X-2 measured via direct adapter calls after schema-flatten workaround for L-F1. |
| 1. Research + meta-KPI proposal | **DONE** | L-series + X-series presented at CHECKPOINT. User validated and chose multi-branch sweep. |
| 1.5. Finding harvest + local issue filing | **DONE (harvest only, no filing)** | 0 W-series cluster hits across all 7 branches. 12 L-series findings surfaced incidentally. Multi-branch journey table built. |
| 2. Plan validation | SKIPPED | `--harvest-only` |
| 3. Documentation | **DONE** | This ledger + `dev/wkmigrate-issue-map.json` v1→v2 update. No commit (per project convention: only commit when explicitly asked). |
| 4. Handoff to /wkmigrate-autodev | SKIPPED | `--harvest-only` |
| 4.1. lmv-side implementation loop | SKIPPED | `--harvest-only` |
| 4.5. Post-handoff re-validation | SKIPPED | `--harvest-only` |
| 5. Session summary + convergence | **DONE** | This document |

---

## Self-Evaluation

| Dimension | Score | Notes |
|-----------|-------|-------|
| Input Handling | 5 | Auto-detected URL, parsed `--wkmigrate-branch`, `--harvest-only`, `--autonomy semi-auto` flags |
| Meta-KPI Relevance | 4 | L-series + X-series presented; L-F11 (no judge) prevented true X-2 measurement |
| Finding Harvest Quality | 5 | Cluster signature run produced 0 W-hits cleanly; 12 L-side findings surfaced via corpus probing |
| Plan Quality | n/a | --harvest-only, no plan |
| Phase Completeness | 5 | All phases that apply to --harvest-only mode complete |
| Ratchet Enforcement | n/a | --harvest-only, no L-side code changes to ratchet against |
| Cross-Repo Discipline | 5 | wkmigrate working tree restored to alpha_1; no unintended state left behind |
| Git Discipline | 4 | Map updated, ledger written; not committed (project convention) |
| Checkpoint Compliance | 5 | Phase 1 CHECKPOINT honored; --harvest-only stop honored |
| Convergence Report | 5 | Journey table + L-F1..L-F12 inventory + W-series last_tested update + next-actions |
| **Total** | **42 / 50** | well above 35/50 target |

---

## Next Actions (recommended)

The picture from this session is sharp. Recommended sequence in priority order:

1. **Fix L-F8 + L-F9 + L-F10** (1 PR, lmv-side, ~30 min). Unblocks `make test`, `black --check`, and `ruff check --fix` so the **L-series ratchet can actually run** in a future session. Without these, every future `/lmv-autodev` invocation will start with three blocked hard-gate measurements.

2. **Fix L-F1 + L-F2 + L-F12** (1 PR, lmv-side, ~1 hour). The schema-unwrap in `wkmigrate_adapter.py`, the `compute_expression_coverage` "unmeasurable" return path, and the placeholder-activity detection. After this, X-series measurements will be honest by default (no PYTHONPATH workaround needed; no false 1.0; no false 0.0 on placeholder activities).

3. **Address L-F4 + L-F5** by building a **stratified, activity-context-diversified corpus** (1 PR, lmv-side, ~2 hours). Either regenerate `golden_sets/pipelines.json` with synthetic generator presets covering all 5 weak-spot stress areas at multiple difficulties, OR add `lmv batch-expressions --activity-context lookup|copy|web|foreach|ifcondition` so each existing pair is exercised in each wrapper context. This is the **prerequisite for actually testing W-2..W-5**.

4. **Address L-F3** by sourcing an independent oracle for `expected_python` (research task, no PR yet). Could be: (a) human-written by you/Lorenzo for a small adversarial seed, (b) imported from an existing ADF→Python migration reference doc, (c) generated by parallel-test execution where lmv runs both ADF and the converted Databricks notebook against the same input data and compares outputs.

5. **Re-run `/lmv-autodev https://github.com/ghanse/wkmigrate/issues/27 --wkmigrate-branch alpha_1`** (no `--harvest-only` this time, semi-auto). With (1)–(3) in place, the harvest should now produce real not_translatable clusters that map to G-1 / G-2 / G-3 candidates, and Phase 1.5 will draft real lmv issues for review.

6. **Use the journey table from this session** in upstream PR bodies. When you open the 5-PR sequence on `ghanse/wkmigrate`, paste the per-category byte-match progression block (section "Per-category byte-match progression" above) into each PR body. It is exactly the KPI delta evidence `dev/meta-kpis/issue-27-expression-meta-kpis.md` PR-2e mandates. Give credit: "Validated by Lakeflow Migration Validator session LMV-AUTODEV-2026-04-08."

To resume this session (e.g., after wkmigrate moves to a new ref):
```
/lmv-autodev --resume dev/autodev-sessions/LMV-AUTODEV-2026-04-08.md
```
The Status field is `DONE`, so resume will start a new Phase 0 against the new wkmigrate ref rather than jumping to Phase 4.5. Treat this ledger as the baseline historical record.
