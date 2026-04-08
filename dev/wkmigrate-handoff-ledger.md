# wkmigrate Handoff Ledger — `/lmv-autodev` → `/wkmigrate-autodev`

> **Purpose.** Single source of truth for every wkmigrate finding produced by `/lmv-autodev`. Anyone running `/wkmigrate-autodev` can paste a row's command verbatim and start fixing the upstream issue without re-deriving the context.
>
> **Authoritative metadata** lives in [`dev/wkmigrate-issue-map.json`](wkmigrate-issue-map.json) — the JSON is what the matchers consume, this Markdown is what humans (and `/wkmigrate-autodev`) read. Keep them in sync.
>
> **Last updated:** 2026-04-08 (session `LMV-AUTODEV-2026-04-08-session2`)
> **wkmigrate ref under test:** `MiguelPeralvo/wkmigrate@alpha_1@969e74d`
> **Filing repo for lmv issues:** `MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator`
> **Upstream repo (informational only — never auto-filed):** `ghanse/wkmigrate`

---

## How to use this ledger

1. **Pick a row** from the *Active findings* table.
2. **Copy its `/wkmigrate-autodev` command** verbatim into a new Claude session.
3. The skill will fetch the upstream issue, harvest its scope, and run the standard ratchet loop.
4. **When the upstream PR merges**, come back to this ledger and:
   - Update the row's *State* column (`open` → `awaiting-revalidation`).
   - Resume the originating lmv session (`/lmv-autodev --resume <ledger>`) to drive Phase 4.5 re-validation against the new wkmigrate ref.
5. **If re-validation passes**, mark the row `fixed-in:<ref>` (mirror the field in `wkmigrate-issue-map.json` → `failure_signatures[].lmv_issue`) and move it to *Resolved findings*.

**Hard rule:** never edit `ghanse/wkmigrate` issues directly from `/lmv-autodev`. The handoff is always a *suggested* `/wkmigrate-autodev` command — the human runs it in a separate session.

---

## At-a-glance status table

| ID | Title (short) | Severity | Match target | lmv issue | Upstream | State |
|----|---------------|----------|--------------|-----------|----------|-------|
| **W-1** | `@concat(...)` Python emitter | — | `not_translatable.message` | n/a (fixed before filing) | ghanse/wkmigrate#27 | **fixed-in:`alpha_1@969e74d`** |
| **W-2** | `@pipeline().parameters.X` in non-notebook activities | enhancement | `not_translatable.message` | not yet filed | ghanse/wkmigrate#27, #55 | **not_tested_on_corpus** |
| **W-3** | Type coercion for `@add/@mul/...` on parameters | bug | `not_translatable.message` | not yet filed | ghanse/wkmigrate#27 | **not_tested_on_corpus** |
| **W-4** | `@activity('Lookup').output.firstRow.X` chaining | enhancement | `not_translatable.message` | not yet filed | ghanse/wkmigrate#27 (deferred to proposed #28) | **not_tested_on_corpus** |
| **W-5** | PipelineAdapter cycle detection | bug | `not_translatable.message` | not yet filed | ghanse/wkmigrate#71 | **not_tested_on_corpus** |
| **W-6** | Structured `failure_mode` tags on warnings | enhancement (meta) | n/a | not yet filed | ghanse/wkmigrate#27 | **not_tested_on_corpus** |
| **W-7** | **Lookup HARD CRASH** on Expression-typed `sql_reader_query` | **P0** bug | `exception` | [`#22`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/22) | ghanse/wkmigrate#27 (deferred Lookup adoption → proposed #28) | **OPEN — awaiting upstream fix** |
| **W-8** | Copy translator silent placeholder on Expression `sql_reader_query` | P1 bug | `not_translatable.message` (`(type: Copy)`) | [`#23`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/23) | ghanse/wkmigrate#27 (deferred Copy adoption → proposed #28) | **OPEN — awaiting upstream fix** |
| **W-10** | ForEach translator silent placeholder on `items` | P1 bug | `not_translatable.message` (`(type: ForEach)`) | [`#24`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/24) | ghanse/wkmigrate#27 | **OPEN — awaiting upstream fix** |

**Counts:**
- Active findings: 9 (W-1..W-8 + W-10 — there is no W-9 in the catalog yet)
- Filed lmv issues: 3 (`#22`, `#23`, `#24`)
- Fixed (with re-validation evidence): 1 (W-1)
- Awaiting upstream fix: 3 (W-7, W-8, W-10)
- Discovered but not yet exercised against wkmigrate: 5 (W-2..W-6)

---

## Active findings — handoff blocks

Each block below is a self-contained briefing for `/wkmigrate-autodev`. The "Handoff command" is what to paste into a new Claude session.

---

### W-7 — Lookup translator HARD CRASH (P0)

- **Filed as:** [`MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#22`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/22)
- **Upstream parent:** ghanse/wkmigrate#27 (deferred Lookup adoption — see proposed wkmigrate#28)
- **Discovered via:** `lmv sweep-activity-contexts` (PR #19)
- **Match target:** `exception` — `(?i)AttributeError.*'dict'.*has no attribute 'replace'`
- **Sweep evidence:** **200 / 200 hard crashes** across all 6 categories on `golden_sets/expressions.json` × `lookup_query` context.
- **Blast radius:** every Expression-typed `Lookup.source.sql_reader_query` in any pipeline.
- **Suggested fix sketch:** route the source query through the same `get_literal_or_expression()` shared utility that `pr/27-1-expression-parser` introduced for `SetVariable`. Today the translator does `query.replace(...)` directly on the source dict; the fix is to resolve the expression first, then fall back to `NotTranslatableWarning + UnsupportedValue` if resolution fails.
- **Weak spots tagged:** `activity_output_chaining`

**Handoff command:**

```text
/wkmigrate-autodev https://github.com/ghanse/wkmigrate/issues/27 --autonomy semi-auto

Scope this run to W-7 only (lmv issue
MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#22). The repro and full
context are in dev/wkmigrate-handoff-ledger.md (W-7 block) in the lmv repo.

Acceptance criterion: rerun `lmv sweep-activity-contexts --activity lookup_query`
on the new wkmigrate ref and observe 0 / 200 AttributeError crashes
(any non-zero count is a regression).
```

---

### W-8 — Copy translator silent placeholder (P1)

- **Filed as:** [`MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#23`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/23)
- **Upstream parent:** ghanse/wkmigrate#27 (deferred Copy adoption — see proposed wkmigrate#28)
- **Discovered via:** `lmv sweep-activity-contexts` (PR #19)
- **Match target:** `not_translatable.message` — `(?i)\(type:\s*Copy\)` (works because of the L-F18 placeholder enrichment in PR #21)
- **Sweep evidence:** **200 / 200 placeholder warnings** across all 6 categories on `golden_sets/expressions.json` × `copy_query` context. Every Expression-typed `source.sql_reader_query` is silently dropped into a `/UNSUPPORTED_ADF_ACTIVITY` notebook.
- **Blast radius:** every Expression-typed `Copy.source.sql_reader_query` in any pipeline that already provides a `column_mapping`.
- **Suggested fix sketch:** identical pattern to W-7 — route `source.sql_reader_query` through `get_literal_or_expression()`. The Copy translator already accepts a `column_mapping` (TabularTranslator), so the regression is purely the source query field.
- **Weak spots tagged:** `activity_output_chaining`

**Handoff command:**

```text
/wkmigrate-autodev https://github.com/ghanse/wkmigrate/issues/27 --autonomy semi-auto

Scope this run to W-8 only (lmv issue
MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#23). Repro is in
dev/wkmigrate-handoff-ledger.md (W-8 block) in the lmv repo. Same root cause
as W-7 but for Copy.source.sql_reader_query — the fix in `get_literal_or_expression`
should slot in symmetrically.

Acceptance criterion: rerun `lmv sweep-activity-contexts --activity copy_query`
on the new wkmigrate ref and observe 0 / 200 placeholder warnings whose message
contains `(type: Copy)`.
```

---

### W-10 — ForEach translator silent placeholder (P1)

- **Filed as:** [`MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#24`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/24)
- **Upstream parent:** ghanse/wkmigrate#27 (`pr/27-3-translator-adoption` documented coverage on the IR side, but the preparer never picked it up)
- **Discovered via:** `lmv sweep-activity-contexts` (PR #19)
- **Match target:** `not_translatable.message` — `(?i)\(type:\s*ForEach\)` (L-F18-enriched message format)
- **Sweep evidence:** **200 / 200 placeholder warnings**, INCLUDING the 33 `collection`-category entries like `@createArray('a', 'b')` that are valid array sources.
- **Blast radius:** every ForEach activity whose `items` field is an Expression — even when the expression evaluates statically to a literal array.
- **Suggested fix sketch:** wire the preparer in `wkmigrate/preparers/for_each_activity_preparer.py` (start there) to call `get_literal_or_expression()` on `items`. Emit a literal Python list when statically resolvable; otherwise emit a runtime expression that produces an array.
- **Weak spots tagged:** `nested_expressions`

**Handoff command:**

```text
/wkmigrate-autodev https://github.com/ghanse/wkmigrate/issues/27 --autonomy semi-auto

Scope this run to W-10 only (lmv issue
MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#24). Repro is in
dev/wkmigrate-handoff-ledger.md (W-10 block) in the lmv repo. The IR side is
already in pr/27-3 — the missing piece is the preparer integration.

Acceptance criterion: rerun `lmv sweep-activity-contexts --activity for_each`
on the new wkmigrate ref and observe 0 / 200 placeholder warnings whose message
contains `(type: ForEach)`. The 33 collection-category entries should resolve
to literal Python lists.
```

---

### W-2 — `@pipeline().parameters.X` in non-notebook activities (not yet filed)

- **lmv issue:** *not yet filed* — needs an adversarial corpus run first
- **Upstream parents:** ghanse/wkmigrate#27, ghanse/wkmigrate#55
- **Match target:** `not_translatable.message` — `(?i)pipeline\(\)\.parameters.*(?:setvariable|ifcondition|copy|filter)|param.*not.*resolved`
- **Why not filed yet:** the existing 200-pair `golden_sets/expressions.json` corpus uses literal expressions only (no `@pipeline().parameters.X` references). The L-F4 stratified rebuild (PR #25) adds parameterised pipelines; the adversarial corpus L-F3 (PR #26) adds independence — but neither yet exercises this signature against the activities listed. **Next step:** extend the L-F3 corpus or `lmv sweep-activity-contexts` with parameter-injected fixtures, then run Phase 1.5 wet mode.
- **Suggested fix sketch:** generalise the wkmigrate#55 fix beyond notebook activities — `SetVariable`, `IfCondition` predicates, and `Copy` source paths all need `pipeline().parameters.X → {{job.parameters.X}}` substitution.
- **Weak spots tagged:** `math_on_params`, `complex_conditions`

**Handoff command (after the lmv issue exists):**

```text
/wkmigrate-autodev https://github.com/ghanse/wkmigrate/issues/55 --autonomy semi-auto

Scope: W-2. Generalise the issue-#55 notebook fix to SetVariable, IfCondition,
and Copy. Cross-reference: lmv issue MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#<TBD>
(file via /lmv-autodev Phase 1.5 once the corpus extension lands).
```

---

### W-3 — Type coercion for math on parameters (not yet filed)

- **lmv issue:** *not yet filed*
- **Upstream parent:** ghanse/wkmigrate#27
- **Match target:** `not_translatable.message` — `(?i)(@add|@mul|@sub|@div|@mod).*pipeline\(\)\.parameters|type.*coercion.*missing`
- **Why not filed yet:** same gap as W-2 — corpus has 34 / 34 math-category byte matches because all operands are literals. The path that triggers the bug (`@add(pipeline().parameters.x, 1)` where `x` arrives as a string from `dbutils.widgets.get`) is not yet exercised.
- **Suggested fix sketch:** track each parameter's declared type from the pipeline spec; when emitting a `pipeline().parameters.X` reference inside a math context, wrap with `int(...)` or `float(...)` per the declared type.
- **Weak spots tagged:** `math_on_params`

**Handoff command (after the lmv issue exists):** scope to ghanse/wkmigrate#27 with cross-reference to the future lmv issue. Same template as W-2.

---

### W-4 — `@activity('Lookup').output.firstRow.X` chaining (not yet filed)

- **lmv issue:** *not yet filed*
- **Upstream parent:** ghanse/wkmigrate#27 (Lookup adoption deferred to proposed wkmigrate#28)
- **Match target:** `not_translatable.message` — `(?i)@activity\(.*\)\.output|activity.*output.*chain`
- **Why not filed yet:** the corpus is single-activity SetVariable wrappers; multi-activity chains never occur. Once W-7 (Lookup hard crash) is fixed upstream, this becomes the natural follow-on test — a Lookup feeding a downstream SetVariable that consumes its `firstRow`.
- **Suggested fix sketch:** translate `Lookup` activities into a notebook cell that assigns its result to a task value; downstream references resolve via `dbutils.jobs.taskValues.get(taskKey='Lookup', key='firstRow')`.
- **Weak spots tagged:** `activity_output_chaining`

**Handoff command:** filed only after W-7 fix lands AND the L-F3 corpus grows multi-activity chains.

---

### W-5 — PipelineAdapter cycle detection (not yet filed)

- **lmv issue:** *not yet filed*
- **Upstream parent:** ghanse/wkmigrate#71
- **Match target:** `not_translatable.message` — `(?i)recursionerror|maximum recursion depth|cycle.*pipeline.*adapter`
- **Why not filed yet:** corpus has no `Execute Pipeline` activities. Need a fixture with self-referencing or circular pipelines to trigger the recursion path.
- **Suggested fix sketch:** thread a `visited: set[str]` through `PipelineAdapter` recursive calls; raise `NotTranslatableWarning + UnsupportedValue` on revisit.
- **Weak spots tagged:** `deep_nesting`

**Handoff command:** scope to ghanse/wkmigrate#71 once the corpus exercises Execute Pipeline.

---

### W-6 — Structured `failure_mode` tags on `NotTranslatableWarning` (meta enhancement)

- **lmv issue:** *not yet filed*
- **Upstream parent:** ghanse/wkmigrate#27
- **Match target:** n/a (this is a meta improvement, not a failure signature)
- **Why filed-as-pending:** the fix would extend `NotTranslatableWarning` with a `failure_mode` field whose values are one of `function_not_mapped`, `type_coercion_missing`, `nesting_depth_exceeded`, `parameter_reference_dropped`, `activity_output_chain_unresolved`, `unsupported_activity_type`. Would let `/lmv-autodev` Phase 1.5 cluster much more reliably (the current regex matchers are brittle).
- **Suggested handoff:** bundle into the next general wkmigrate observability sweep — not P0/P1, but high leverage for the feedback loop itself. Track in this ledger so it doesn't get forgotten.

---

## Resolved findings

### W-1 — `@concat(...)` Python emitter (fixed)

- **Status:** `fixed-in:alpha_1@969e74d`
- **Verified via journey:** First lands in `pr/27-1-expression-parser@be9e3a5` — wkmigrate's 47-fn Python registry now includes `concat` as Tier-1.
- **Re-validation evidence:** `golden_sets/expressions.json` (34 string-category expressions) → 34 / 34 resolved, 34 / 34 byte-match `expected_python`, 0 `not_translatable`, 0 W-1 cluster hits in the 2026-04-08 sweep.
- **Cross-reference:** `dev/wkmigrate-issue-map.json` → `failure_signatures[].id == "W-1"`

---

## Generic `/wkmigrate-autodev` handoff template

If you discover a *new* finding mid-session and want to draft a handoff before adding it to the ledger:

```text
/wkmigrate-autodev <upstream URL> --autonomy semi-auto

Scope this run to <signature ID>. Filed locally as
MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#<N>.

Failure signature: <regex>
Match target: <not_translatable.message | exception>
Sweep evidence: <count> / <total> hits on <corpus> × <activity context>
Suggested fix sketch: <one-liner>

Acceptance criterion: rerun `lmv sweep-activity-contexts --activity <ctx>`
on the new wkmigrate ref and observe 0 / <total> matches for the signature
above. (Any non-zero count is a regression — file a new finding.)

Provenance for context: dev/wkmigrate-handoff-ledger.md +
dev/wkmigrate-issue-map.json in the lmv repo.
```

---

## Maintenance rules

1. **One row per signature.** If you add a new `failure_signatures[]` entry to `wkmigrate-issue-map.json`, add a matching row + handoff block here in the same commit.
2. **Never delete a row.** If a finding is fixed, move it to *Resolved findings* and keep its history. The journey is the point.
3. **Keep the wkmigrate ref pointer fresh.** When `/lmv-autodev` runs Phase 0 baseline against a new ref, update the header at the top of this file in the same commit that updates the session ledger.
4. **Cross-link both directions.** Each lmv issue body references this ledger; each row here links the lmv issue. If one is missing, fix it.
5. **Track the *not yet filed* tail.** W-2..W-6 are not bugs in waiting — they're known wkmigrate gaps that the current corpus does not yet exercise. The corpus growth that lights them up is itself part of the lmv ratchet.
