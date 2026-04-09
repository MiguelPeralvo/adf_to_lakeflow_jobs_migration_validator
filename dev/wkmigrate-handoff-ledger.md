# wkmigrate Handoff Ledger — `/lmv-autodev` → `/wkmigrate-autodev`

> **Purpose.** Single source of truth for every wkmigrate finding produced by `/lmv-autodev`. Anyone running `/wkmigrate-autodev` can paste a row's command verbatim and start fixing the upstream issue without re-deriving the context.
>
> **Authoritative metadata** lives in [`dev/wkmigrate-issue-map.json`](wkmigrate-issue-map.json) — the JSON is what the matchers consume, this Markdown is what humans (and `/wkmigrate-autodev`) read. Keep them in sync.
>
> **Last updated:** 2026-04-09 (session `LMV-AUTODEV-2026-04-09` — adds **W-9** discovered via L-F19 detector, filed as lmv #29)
> **wkmigrate ref under test:** `MiguelPeralvo/wkmigrate@alpha_1` ↔ `MiguelPeralvo/wkmigrate@pr/27-3-translator-adoption@3d8c541` (the fixes live on the PR series; alpha_1 still pending integration)
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
| **W-7** | **Lookup HARD CRASH** on Expression-typed `sql_reader_query` | **P0** bug | `exception` | [`#22`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/22) | ghanse/wkmigrate#27 (deferred Lookup adoption → proposed #28) | **fixed-in:`pr/27-3-translator-adoption@3d8c541`** (verified 200/200 resolved on the PR branch; awaits alpha_1 integration) |
| **W-8** | Copy translator placeholder fallback on Expression `sql_reader_query` | P1 → **MIS-DIAGNOSED** | `not_translatable.message` (`(type: Copy)`) | [`#23`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/23) | ghanse/wkmigrate#27 | **lmv-fixture-bug, fixed in lmv** (missing `sink.type`; see *Resolved findings*) |
| **W-9** | Copy translator drops `source.sql_reader_query` in `_parse_sql_format_options` | **P1** bug | `not_translatable.message` (`dropped_expression_field` from L-F19) | [`#29`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/29) | ghanse/wkmigrate#27 (deferred Copy adoption → proposed #28) | **open** — filed 2026-04-09 via Phase 1.5; affects both alpha_1 and pr/27-3 |
| **W-10** | ForEach translator placeholder fallback on `items` | P1 → **MIS-DIAGNOSED** | `not_translatable.message` (`(type: ForEach)`) | [`#24`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/24) | ghanse/wkmigrate#27 | **fixed-in:`pr/27-3-translator-adoption@3d8c541`** for valid array inputs; corpus contains zero ForEach-compatible expressions so the 0/200 acceptance was unreachable. See *Resolved findings*. |

**Counts:**
- Active findings: 10 (W-1..W-10)
- Filed lmv issues: 4 (`#22`, `#23`, `#24`, `#29`)
- Fixed (with re-validation evidence): 4 (W-1 already fixed; W-7 fixed on pr/27-3; W-8 was an lmv fixture bug, fixed in lmv; W-10 fixed on pr/27-3 for valid arrays)
- Awaiting alpha_1 integration: 2 (W-7, W-10 — the fixes live on `pr/27-3-translator-adoption` and need a normal merge cycle to land in `alpha_1`)
- Open and awaiting upstream fix: 1 (W-9 — `_parse_sql_format_options` drop, filed as lmv #29)
- Discovered but not yet exercised against wkmigrate: 5 (W-2..W-6)

---

## Active findings — handoff blocks

Each block below is a self-contained briefing for `/wkmigrate-autodev`. The "Handoff command" is what to paste into a new Claude session.

---

### W-7 — Lookup translator HARD CRASH (P0) — fixed on pr/27-3, awaits alpha_1 integration

- **Filed as:** [`MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#22`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/22)
- **Upstream parent:** ghanse/wkmigrate#27 (deferred Lookup adoption — see proposed wkmigrate#28)
- **Discovered via:** `lmv sweep-activity-contexts` (PR #19)
- **Match target:** `exception` — `(?i)AttributeError.*'dict'.*has no attribute 'replace'`
- **Sweep evidence (alpha_1):** 200 / 200 hard crashes across all 6 categories.
- **Sweep evidence (`pr/27-3-translator-adoption@3d8c541`, verified 2026-04-08 by `/wkmigrate-autodev`):** **200 / 200 resolved**, 0 placeholders, 0 errors. The fix exists on the PR series via `_resolve_source_query`, which routes the raw query through `get_literal_or_expression()` with `ExpressionContext.LOOKUP_QUERY` and stores the emitted Python-code string on `LookupActivity.source_query`. The lookup notebook embeds it verbatim in `.option("query", ...)`.
- **Blast radius:** every Expression-typed `Lookup.source.sql_reader_query` in any pipeline.
- **Why it isn't already on alpha_1:** the full pr/27-3 translator-adoption work (lookup + copy + for_each + if_condition + 5 other translators + emission_config threading + IR widening + AD-series adoption) is bundled into a single PR. A surgical port of just the W-7 piece into alpha_1 was attempted in this `/wkmigrate-autodev` run but reverted (intentional — alpha_1 should pick up the fix via the normal pr/27-3 → alpha_1 review cycle, not via piecemeal patches).
- **Weak spots tagged:** `activity_output_chaining`

**Handoff command (unchanged — still valid for ghanse/wkmigrate#27):**

```text
/wkmigrate-autodev https://github.com/ghanse/wkmigrate/issues/27 --autonomy semi-auto

W-7 is already fixed on MiguelPeralvo/wkmigrate@pr/27-3-translator-adoption@3d8c541
(verified by lmv sweep-activity-contexts: 200/200 resolved on lookup_query). The
lmv issue MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#22 stays open
until pr/27-3 lands on alpha_1 OR upstream ghanse/wkmigrate#27 merges the same
shared-utility approach.

Acceptance criterion: rerun `lmv sweep-activity-contexts --contexts lookup_query`
against the new ref and observe 0 / 200 AttributeError crashes AND >= 200 / 200
resolved expressions on the lookup_query context.
```

---

### W-8 — Copy translator placeholder fallback (mis-diagnosed → lmv-fixture bug, fixed in lmv)

- **Filed as:** [`MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#23`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/23)
- **Original diagnosis:** "wkmigrate Copy translator silently falls to placeholder for Expression-typed source.sql_reader_query"
- **Corrected diagnosis (`/wkmigrate-autodev` run, 2026-04-08):** the placeholder fallback was caused by an **lmv test-fixture bug**, not by anything wkmigrate does with the source query expression. The `wrap_in_copy_query` helper in `src/lakeflow_migration_validator/synthetic/activity_context_wrapper.py` was emitting a column mapping with `sink: {name: "tgt_col"}` and **no `type` field**. wkmigrate's `_parse_dataset_mapping` requires `sink.type` (it raises `UnsupportedValue("Missing value for key 'type' in sink dataset")`), and the resulting `UnsupportedValue` propagates up to `normalize_translated_result` which converts it to a `/UNSUPPORTED_ADF_ACTIVITY` placeholder. The `(type: Copy)` regex match wasn't catching a wkmigrate failure — it was catching an lmv malformed-fixture failure.
- **Trace:**
  1. lmv emits `wrap_in_copy_query` → `translator.mappings[0].sink = {name: "tgt_col"}`
  2. wkmigrate `copy_activity_translator._parse_dataset_mapping` calls `get_value_or_unsupported(sink, "type", ...)` → returns `UnsupportedValue("Missing value for key 'type' in sink dataset")`
  3. wkmigrate aggregates it into the activity-level `UnsupportedValue("Could not parse property 'translator' of dataset...")`
  4. `normalize_translated_result` converts the `UnsupportedValue` into the `/UNSUPPORTED_ADF_ACTIVITY` placeholder DatabricksNotebookActivity
  5. lmv adapter sees `notebook_path == "/UNSUPPORTED_ADF_ACTIVITY"` and emits the placeholder warning with `original_activity_type: "Copy"`
  6. The W-8 regex `(?i)\(type:\s*Copy\)` matches — but the underlying cause is the missing `sink.type`, NOT the source query expression.
- **lmv fix (this run):** the `wrap_in_copy_query` fixture now emits `sink: {name: "tgt_col", "type": "string"}`. After the fix, an lmv sweep against the same `alpha_1@969e74d` ref returns **200 / 200 with 0 placeholders, 0 errors** on the `copy_query` context (verified 2026-04-08).
- **Why `resolved_expressions` is still 0 on copy_query:** the lmv L-F17 walker that extracts `ExpressionPair` entries from non-SetVariable activities doesn't yet walk `Copy.source.sql_reader_query`. That's a known lmv-side enhancement (not blocked on wkmigrate), tracked in `dev/wkmigrate-issue-map.json` as a future L-series item.
- **Implication for upstream wkmigrate:** there is no W-8 work for `/wkmigrate-autodev` to do. wkmigrate's Copy translator behavior is correct given the malformed input — the sink.type validation is intentional and well-tested.

**Handoff command:** no longer needed. `MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#23` will be updated with the corrected diagnosis and closed (or relabeled) by the same `/wkmigrate-autodev` session.

---

### W-9 — Copy translator silently drops `source.sql_reader_query` (P1, filed 2026-04-09)

- **Filed as:** [`MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#29`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/29) (filed via `/lmv-autodev` Phase 1.5 on 2026-04-09; finding markdown at `dev/findings/W-9.md`)
- **Upstream parent:** ghanse/wkmigrate#27 (deferred Copy adoption — proposed wkmigrate#28)
- **Discovered via:** **L-F19 dropped-expression-field detector** in `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py::_detect_dropped_expression_fields` (this session). The detector emits a synthetic `not_translatable` warning of kind `dropped_expression_field` whenever the source ADF dict has `Copy.source.sql_reader_query` as an Expression (or a literal) but the IR-side `CopyActivity.source_properties` is missing the `sql_reader_query` key.
- **Match target:** `not_translatable.message` — `(?i)dropped_expression_field.*Copy.*sql_reader_query|_parse_sql_format_options dropped`
- **Root cause:** wkmigrate's `parsers/dataset_parsers.py::_parse_sql_format_options` builds `CopyActivity.source_properties` from a fixed key list — `type`, `query_isolation_level`, `query_timeout_seconds`, `numPartitions`, `batchsize`, `sessionInitStatement`, `mode`. **It does not include `sql_reader_query`.** The query (literal OR Expression) is silently lost the moment `translate_copy_activity` runs. The Copy preparer then generates a JDBC read with no query, which would either pull the entire table or omit the `WHERE` clause depending on downstream code.
- **Distinction from W-7:** W-7 is the Lookup translator hard-crashing on Expression `sql_reader_query` (`'dict' object has no attribute 'replace'`). W-9 is the Copy translator silently *dropping* the query (literal or Expression) without crashing or warning. **Different code paths, different fixes.**
- **Distinction from W-8:** W-8 was an lmv fixture bug (missing `sink.type`) that produced a misleading placeholder. W-9 is the real wkmigrate gap that the W-8 fixture fix unblocked us to see.
- **Sweep evidence:** verified end-to-end via `wrap_in_copy_query` → `adf_to_snapshot` → `expression_coverage` drops to **0.0 (measurable=True)** with **1 dropped_expression_field warning** per Copy activity. Pinned by `tests/unit/validation/test_wkmigrate_adapter_lf17.py::test_adapter_emits_dropped_field_warning_for_copy_with_expression_sql_reader_query`. The same drop exists on `pr/27-3-translator-adoption` — the W-9 gap is independent of the W-7 fix.
- **Blast radius:** every Copy activity with a `source.sql_reader_query` (literal or Expression) in any pipeline. ADF Copy activities with `AzureSqlSource` / `AzurePostgreSqlSource` / `AzureMySqlSource` / `OracleSource` that use a custom query (not just a table reference) all hit this gap.
- **Suggested fix sketch:** extend `_parse_sql_format_options` in `wkmigrate/parsers/dataset_parsers.py` to extract `sql_reader_query` from the source definition. For literal strings, store directly. For `{type: Expression, value: ...}` dicts, route through `get_literal_or_expression()` with an appropriate `ExpressionContext` (analogous to `ExpressionContext.LOOKUP_QUERY` introduced in pr/27-1). Then have the Copy preparer / code generator embed the resolved query in the JDBC read expression's `WHERE` clause.
- **Acceptance criterion (post-fix):** rerun `lmv sweep-activity-contexts --contexts copy_query` against the new wkmigrate ref and observe **0 / 200 dropped_expression_field warnings** AND **>= 200 / 200 resolved expressions** on the `copy_query` cell. Lmv-side, the L-F17 walker should also be extended to extract the new `CopyActivity.source_properties["sql_reader_query"]` field as a regular `ExpressionPair` once wkmigrate exposes it (test `test_adapter_skips_dropped_field_warning_for_copy_when_ir_already_has_sql_reader_query` already pins the contract for that future state).
- **Weak spots tagged:** `activity_output_chaining`

**Handoff command (lmv issue filed as #29 — ready to invoke `/wkmigrate-autodev`):**

```text
/wkmigrate-autodev https://github.com/ghanse/wkmigrate/issues/27 --autonomy semi-auto

Scope this run to W-9 — Copy.source.sql_reader_query is silently dropped by
_parse_sql_format_options in wkmigrate/parsers/dataset_parsers.py. Both literal
strings and Expression dicts are lost; the resulting CopyActivity has no
sql_reader_query in source_properties and the generated JDBC read has no
WHERE clause.

Failure signature (lmv L-F19 detector):
  (?i)dropped_expression_field.*Copy.*sql_reader_query|_parse_sql_format_options dropped

Match target: not_translatable.message (synthesised by lmv adapter, NOT a
wkmigrate-emitted warning — wkmigrate currently emits NOTHING for this case,
which is the entire problem).

Sweep evidence: 200 / 200 dropped on the copy_query context (both alpha_1 and
pr/27-3-translator-adoption). End-to-end verification pinned by
tests/unit/validation/test_wkmigrate_adapter_lf17.py::test_adapter_emits_dropped_field_warning_for_copy_with_expression_sql_reader_query
in the lmv repo.

Suggested fix sketch: extend _parse_sql_format_options to extract sql_reader_query
(literal → store directly; Expression dict → route through get_literal_or_expression
with an ExpressionContext analogous to LOOKUP_QUERY from pr/27-1). Update the Copy
preparer / code_generator.py to embed the resolved query in the JDBC read.

Distinction from W-7 (Lookup): W-7 hard-crashes the preparer; W-9 silently
drops the query at translate time and never reaches the preparer with the
query in hand. The fix is in dataset_parsers.py + preparer wiring, not in
copy_activity_translator.py.

Acceptance criterion: rerun `lmv sweep-activity-contexts --contexts copy_query`
on the new ref and observe 0 / 200 dropped_expression_field warnings AND
>= 200 / 200 resolved expressions on the copy_query cell.

Provenance: dev/wkmigrate-handoff-ledger.md (W-9 handoff block) +
dev/wkmigrate-issue-map.json (W-9 failure_signature entry) in the lmv repo.
```

---

### W-10 — ForEach translator placeholder fallback (mis-diagnosed → corpus mismatch + fix lives on pr/27-3)

- **Filed as:** [`MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#24`](https://github.com/MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator/issues/24)
- **Original diagnosis:** "wkmigrate ForEach translator silently falls to placeholder for arbitrary items expressions, INCLUDING the 33 collection-category entries"
- **Corrected diagnosis (`/wkmigrate-autodev` run, 2026-04-08):**
  - **The "arbitrary items expressions → placeholder" fall-through is correct behavior**, not a bug. ADF `ForEach.items` must evaluate to an array. Expressions like `@toUpper('abc')`, `@add(1, 2)`, `@equals(1, 1)` evaluate to scalars and cannot drive a ForEach loop, so wkmigrate correctly produces a placeholder rather than emitting nonsense.
  - **The 33 collection-category entries are mostly transformations OF arrays, not bare arrays.** Examples: `@length(createArray(1, 2, 3))` → returns int (count), `@first(createArray('a', 'b'))` → returns element, `@last(...)` → returns element, `@empty(createArray())` → returns bool. These are correct test fixtures for the `length`/`first`/`last`/`empty` *functions*, but they are NOT valid ForEach items.
  - **Bare `@createArray(...)` expressions ARE handled correctly on `pr/27-3-translator-adoption`** (and even on alpha_1's existing for_each translator at lines 207-218). Verified directly: `wrap_in_for_each("@createArray('a', 'b', 'c')")` returns `ForEachActivity(items_string='["a","b","c"]')` with 1 resolved expression and `is_placeholder=False`.
  - **The 0 / 200 acceptance criterion in the original ledger was unreachable** because the corpus contains zero bare `@createArray(...)` expressions — every collection-category entry wraps `createArray` inside another scalar-returning function.
- **What IS a real (small) wkmigrate UX issue:** when ForEach receives a non-array expression, the resulting placeholder warning carries the generic message `(type: ForEach) was substituted with a placeholder DatabricksNotebookActivity (wkmigrate did not recognise the source ADF activity type)`. That message is misleading: the type WAS recognised, the items WAS evaluated, the items just didn't return an array. A more specific `NotTranslatableWarning` with `failure_mode = "items_expression_not_array"` would be more useful — but that's a P3 messaging improvement folded into W-6 (structured failure_mode tags), not a P1 functional bug.
- **lmv-side follow-up:** the L-F3 adversarial corpus should grow at least one bare `@createArray(...)` expression so the W-10 fix has a positive test that lights up. Filed as a corpus growth task, not a wkmigrate issue.

**Handoff command:** no longer needed. `MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator#24` will be updated with the corrected diagnosis and closed (or relabeled) by the same `/wkmigrate-autodev` session.

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
