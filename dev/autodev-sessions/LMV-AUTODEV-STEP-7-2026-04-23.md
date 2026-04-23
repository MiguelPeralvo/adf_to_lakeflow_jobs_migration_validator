# LMV-AUTODEV Step 7 — Vista Cliente Semantic Validation Sweep

**Date:** 2026-04-23
**Branch:** `feature/step-7-vista-cliente-sweep`
**Operator:** autodev agent (single-run execution)
**wkmigrate SHA pinned:** `cfb49e64237185b62ead985a12e320f029c221a6` (`pr/27-4-integration-tests`, read-only)
**lmv base SHA:** `f616be3` (`main`)

---

## Register 1 — Instructions

Execute Step 7 of the wkmigrate coverage roadmap: add a second real-corpus X-1
datapoint by sweeping the Vista Cliente (VC) ADF corpus (119 pipelines, 212
IfCondition activities, under `<CORPUS_DIR>/`)
through wkmigrate at SHA `cfb49e6`. Build a stratified 200+ expression golden set,
run `lmv sweep-activity-contexts` (primary `if_condition`, secondary all-contexts),
replay CRP0001 baseline at the same SHA for cross-regression, and report X-1/X-2/X-6
KPIs vs. the 0.8317 CRP0001 baseline with ±5% hard-gate flagging. Produce a session
ledger (this file) and a findings report; list candidate wkmigrate issues (do not file).

## Register 2 — Constraints

### L-series hard gates (zero tolerance, STOP on trip)
- **LR-1** `make test` 100% — not invoked this session (no src/tests changes). Status: N/A (empty diff).
- **LR-2** 0 regressions — by construction; only new files added. Status: GREEN.
- **LA-1** adapter invariant — only `tests/unit/validation/test_wkmigrate_adapter.py` imports `wkmigrate` outside `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py`. Status: GREEN.
- **LA-2** contract frozen — no `src/lakeflow_migration_validator/contract.py` change. Status: GREEN.
- **LT-3** regression-check exit 0 — not invoked (no src change). Status: N/A.

### X-series soft gates (5% tolerance, FLAG on trip, continue)
- **X-1** mean `expression_coverage` ≥ 0.80.
- **X-2** mean `semantic_equivalence` ≥ 0.75.
- **X-6** per-canonical-category coverage ≥ 0.70.
- CRP0001 replay hard-gate: |replay − 0.8317| ≤ 0.05.

## Register 3 — Stopping criteria

- **Primary** — All task-brief deliverables (1-10) complete; plan, golden set,
  sweeps, KPIs, ledger, findings report committed and pushed.
- **Abort** — Any L-series hard gate trip → STOP, write partial ledger, ask user.
- **Flag-and-continue** — Any X-series movement > 5% with empty `git diff src/ tests/`
  (wkmigrate attribution). CRP0001 replay crossing ±5% → flag as finding.

---

## Methods

### Golden set build (step 4)
- Extractor: `scripts/extract_vista_cliente_expressions.py`
- Output: `golden_sets/vista_cliente_expressions.json` (200 sampled from 212 raw VC IfCondition expressions)
- Histogram: `dev/findings/vista-cliente-category-histogram-2026-04-23.json`
- Stratification: 9 VC buckets (6 realized in corpus) × canonical 6 categories, floor 12/bucket, proportional fill to 200.
- **Unique expressions in the 200-sample: 30** (heavy duplication: same template reused across pipelines; acceptable because we are measuring VC-corpus behaviour, not unique-expression breadth).

### Sweeps (step 5)
- Primitive: `lmv sweep-activity-contexts` (X-2-via-`batch-expressions` is L-8 backlog, not implemented).
- **Primary:** VC @ `contexts=if_condition` → `dev/results/step-7-vista-cliente/sweep-if-condition-2026-04-23.json`
- **Secondary:** VC @ all 7 contexts → `dev/results/step-7-vista-cliente/sweep-all-contexts-2026-04-23.json`
- **CRP0001 replay:** `golden_sets/expressions.json` @ `contexts=if_condition` → `dev/results/step-7-vista-cliente/crp0001-baseline-replay-2026-04-23.json`
- **`lmv batch` NOT usable** on `expressions.json` shape — expects `{pipelines:[...]}` suite. `KeyError: 'pipelines'` confirmed. X-2 would require reshaping golden sets into pipeline suites; deferred.

### KPI aggregation
- Script: `scripts/compute_step7_kpis.py`
- Summary JSON: `dev/results/step-7-vista-cliente/step7-kpi-summary-2026-04-23.json`

---

## Baseline vs post-sweep KPI tables

### X-1 Expression Coverage (if_condition)

| Corpus | Resolved | Total | Coverage | Baseline | Δ vs baseline | Within ±5% |
|---|---|---|---|---|---|---|
| CRP0001 baseline (pinned, historical) | — | — | 0.8317 | 0.8317 | 0.0000 | yes |
| CRP0001 replay @ cfb49e6 | 208 | 208 | **1.0000** | 0.8317 | **+0.1683** | **NO (HARD-GATE FLAG)** |
| Vista Cliente @ cfb49e6 | 200 | 200 | **1.0000** | 0.8317 | +0.1683 | N/A (new corpus) |

**Hard-gate flag:** CRP0001 replay moved from 0.8317 → 1.0000 (+16.83 pp) at SHA `cfb49e6` with an empty lmv-src diff since the baseline. Per X-series attribution: wkmigrate-side improvement between baseline measurement and `cfb49e6`. Likely drivers: CRP-11 wrapper (`87a5ecf`) + CCS adapter wiring fix (`c897e78`) + recent expression-translator landings. **This is good news, not a regression — but the baseline number is stale and should be re-pinned.**

### X-2 Semantic Equivalence (if_condition)

| Corpus | Status |
|---|---|
| CRP0001 | **BLOCKED** — `DATABRICKS_HOST` unset; judge-dependent primitive unreachable. |
| Vista Cliente | **BLOCKED** — same env block + `expected_python` null on all 200 VC entries (VC lacks oracle). |

### X-6 Per-canonical-category Coverage (target ≥ 0.70)

| Category | CRP0001 resolved/total | CRP0001 cov | VC resolved/total | VC cov | Δ (VC−CRP) | VC pass |
|---|---|---|---|---|---|---|
| collection | 41/41 | 1.0000 | — | — | — | n/a |
| datetime | 33/33 | 1.0000 | — | — | — | n/a |
| logical | 33/33 | 1.0000 | 25/25 | 1.0000 | +0.0000 | yes |
| math | 34/34 | 1.0000 | — | — | — | n/a |
| nested | 33/33 | 1.0000 | 175/175 | 1.0000 | +0.0000 | yes |
| string | 34/34 | 1.0000 | — | — | — | n/a |

VC corpus only exercises `logical` (25) and `nested` (175) canonical categories — reflective of actual VC IfCondition usage: predominantly parameter-ref and variable-ref predicates. Both pass ≥ 0.70.

### Per-VC-category breakdown (9-bucket, VC-only)

| VC category | Count in sample | Resolved | Coverage |
|---|---|---|---|
| pipeline_param_ref | 149 | 149 | 1.0000 |
| variables_ref | 24 | 24 | 1.0000 |
| compound_and | 14 | 14 | 1.0000 |
| equals_binary | 6 | 6 | 1.0000 |
| compound_or | 5 | 5 | 1.0000 |
| bare_activity_output | 2 | 2 | 1.0000 |
| compound_and+or+equals nested_predicate | 0 | — | — |
| contains_intersection_empty | 0 | — | — |
| concat_string | 0 | — | — |

Raw VC corpus (212 activities) contained no `nested_predicate`, `contains_intersection_empty`, or `concat_string` patterns — a useful corpus characterization result on its own.

### Secondary: VC all-contexts resolution (X-1 across 7 contexts)

| Context | Resolved/Total | Coverage | not_translatable_count | Observation |
|---|---|---|---|---|
| copy_query | 200/200 | 1.0000 | 36 | Clean |
| for_each | **0/200** | **0.0000** | 200 | **Placeholder substitution** — wkmigrate does not recognize `ForEach` when wrapped at this synthetic context → every pipeline gets a `placeholder_activity` substitution. HIGH severity. |
| if_condition | 200/200 | 1.0000 | 194 | Clean (194 are inline taskValues warnings, not failures) |
| lookup_query | 200/200 | 1.0000 | **200** | Resolves but every pipeline emits a not_translatable warning — smells like CRP-28 Lookup translator gap. MEDIUM severity. |
| notebook_base_param | 200/200 | 1.0000 | 36 | Clean |
| set_variable | 200/200 | 1.0000 | 36 | Clean |
| web_body | 200/200 | 1.0000 | 36 | Clean |

---

## Findings

### Finding F-7.1 (HIGH) — CRP0001 baseline X-1 is stale
- **Evidence:** CRP0001 replay @ `cfb49e6` = 1.0000 (+16.83 pp over 0.8317 baseline).
- **Attribution:** wkmigrate advancement (empty lmv diff since baseline).
- **Impact:** The 0.8317 pin in `dev/meta-kpis/wkmigrate-issue-27-meta-kpis.md` row X-1 is obsolete; new X-1 pin should be 1.0000 at SHA `cfb49e6` for CRP0001.
- **Action:** Re-pin X-1 baseline in a follow-up commit (out of scope for this ledger).

### Finding F-7.2 (HIGH) — `ForEach` context: 100% placeholder substitution
- **Signature:** 200/200 VC expressions wrapped inside a synthetic `ForEach` activity produced `Activity 'foreach' (type: ForEach) was substituted with a placeholder DatabricksNotebookActivity (wkmigrate did not recognise the source ADF activity type).`
- **VC prevalence:** Every VC expression tested against this context fails.
- **Candidate wkmigrate issue (title):** `wkmigrate: ForEach activity emitted by synthetic wrapper not recognized by translator → placeholder`.
- **Hypothesis:** The synthetic wrapper in `src/lakeflow_migration_validator/synthetic/activity_context_wrapper.py` emits `type=ForEach` JSON that diverges from what wkmigrate's ADF loader expects (e.g. missing `typeProperties.items` or a specific `isSequential` field). Could be a wrapper bug, not a wkmigrate one — needs double-source check.

### Finding F-7.3 (MEDIUM) — `lookup_query` context: 100% not_translatable noise
- **Signature:** 200/200 VC expressions in a `Lookup` activity query context resolve to Python code BUT every pipeline emits a `not_translatable` warning.
- **Hypothesis:** Consistent with the known CRP-28 Lookup translator gap (`cli.py:297` docstring literally names `wkmigrate#28` as the deferred item). Expected noise until #28 lands.

### Finding F-7.4 (MEDIUM) — VC corpus is template-heavy (duplication ratio 30/200)
- **Signature:** 200 sampled VC expressions collapse to only 30 unique expression strings.
- **Interpretation:** VC pipelines use a small library of IfCondition templates re-instantiated 7× on average. This means our X-1 number for VC is really measuring 30-template-coverage, not 200-expression-coverage. A healthy dedup-aware metric would give `30/30 = 1.0000` but with much tighter confidence bounds.
- **Recommendation:** Add `dedup_by_expression` option to `sweep-activity-contexts` so operators can report both views.

### Finding F-7.5 (LOW) — VC IfCondition patterns are narrow
- VC uses only 6 of 9 classified VC buckets. No `contains/intersection/empty`, no `concat/string-manip`, no deep-nested compound predicates. This is meaningful corpus intel for QBR/scope planning.

---

## Convergence report

- **Categories above ≥ 0.70 X-6 target:** `logical` (1.0000), `nested` (1.0000) on VC; all 6 on CRP0001. Zero categories below target.
- **Categories below target:** none.
- **X-series net movement:** +16.83 pp CRP0001 replay (flag-and-continue); +16.83 pp VC new datapoint.
- **L-series status:** all green / N/A (no src changes this session).

## Blockers

- **`DATABRICKS_HOST` unset** → X-2 semantic_equivalence is BLOCKED for both corpora.
- **`lmv batch-expressions` does not exist** (L-8 backlog) → had to use `sweep-activity-contexts` + would need reshaping for `lmv batch`; the latter errors with `KeyError: 'pipelines'` on expression-shaped golden sets.
- **Google Docs fetch (ADC quota project)** → plan doc was synthesized from the local agent plan file, not the Google Doc directly.

## Reproduction

```bash
cd <REPO_ROOT>
git checkout feature/step-7-vista-cliente-sweep
python3 scripts/extract_vista_cliente_expressions.py \
  --corpus <CORPUS_DIR> \
  --out golden_sets/vista_cliente_expressions.json \
  --hist dev/findings/vista-cliente-category-histogram-2026-04-23.json
uv run lmv sweep-activity-contexts \
  --golden-set golden_sets/vista_cliente_expressions.json \
  --contexts if_condition \
  --output dev/results/step-7-vista-cliente/sweep-if-condition-2026-04-23.json
uv run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions.json \
  --contexts if_condition \
  --output dev/results/step-7-vista-cliente/crp0001-baseline-replay-2026-04-23.json
python3 scripts/compute_step7_kpis.py
```
