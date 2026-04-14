# Failure Mode Catalog

> Last updated: 2026-04-13 (V3 re-validation after CRP-6 -- all 24 gaps closed)

## Active Failure Signatures

These are tracked in `dev/wkmigrate-issue-map.json` and matched by the adversarial loop's `_classify_failure()`.

### W-2: Bare parameter reference not resolved
- **Regex:** `(?i)param(eter)?.*not.*resolv|pipeline\(\)\.parameters.*unsupported`
- **Root cause:** wkmigrate's expression parser doesn't handle bare `@pipeline().parameters.X` outside of a function call
- **Impact:** expression_coverage drops, parameter_completeness may also drop
- **Upstream:** ghanse/wkmigrate#27
- **Adversarial trigger:** `@pipeline().parameters.name` as a standalone SetVariable value

### W-3: Math on parameters without type coercion
- **Regex:** `(?i)type.*coercion|param.*math|arithmetic.*string`
- **Root cause:** `dbutils.widgets.get()` returns strings; wkmigrate emits `(param + 1)` which is string concatenation
- **Impact:** Runtime errors or wrong results in generated notebooks
- **Upstream:** ghanse/wkmigrate#27, #55
- **Adversarial trigger:** `@add(pipeline().parameters.count, 1)`

### W-9: Copy sql_reader_query dropped in format options
- **Regex:** `(?i)sql_reader_query.*drop|format_options.*miss|copy.*source.*query`
- **Signature key:** `copy_sql_reader_query_silent_placeholder`
- **Root cause:** `_parse_sql_format_options()` in `parsers/dataset_parsers.py` builds from fixed key list that excludes `sql_reader_query`
- **Impact:** SQL queries silently vanish from Copy activities
- **Upstream:** ghanse/wkmigrate#27 (related to #28 translator adoption)
- **lmv issue:** #29
- **Adversarial hits (2026-04-11):** 3 in first loop run

### W-10: ForEach items expression becomes silent placeholder
- **Regex:** `(?i)\(type:\s*ForEach\)|forEach.*placeholder|createArray.*placeholder`
- **Signature key:** `for_each_items_silent_placeholder`
- **Root cause:** ForEach translator doesn't call `get_literal_or_expression()` on the items property
- **Impact:** Entire ForEach body becomes a placeholder notebook
- **Upstream:** ghanse/wkmigrate#27
- **lmv issue:** #30
- **Adversarial hits (2026-04-11):** 2 in first loop run

### W-7: SetVariable expression not resolved (pre-pr/27-1)
- **Regex:** `(?i)setVariable.*not.*translat|set_variable.*placeholder`
- **Root cause:** SetVariable translator didn't use `get_literal_or_expression()`
- **Impact:** SetVariable activities become placeholders
- **Upstream:** ghanse/wkmigrate#27 (fixed in pr/27-1)
- **Status:** FIXED on pr/27-1+

### W-8: Lookup source query expression not resolved
- **Regex:** `(?i)lookup.*query.*not.*resolv|lookup.*source.*placeholder`
- **Root cause:** Lookup translator not adopted to `get_literal_or_expression()`
- **Upstream:** ghanse/wkmigrate#28
- **Status:** Partially fixed

### G-19: uriComponent / uriComponentToString not registered -- FIXED
- **Regex:** `(?i)unsupported function.*uriComponent`
- **Root cause:** `uriComponent` and `uriComponentToString` not in `FUNCTION_REGISTRY`
- **Impact:** 8 expressions in 2 operational logging pipelines
- **Upstream:** ghanse/wkmigrate#27
- **Fix:** Registered with `urllib.parse.quote(safe='')` / `urllib.parse.unquote()`
- **Discovered:** 2026-04-13 (V2 sweep)
- **Fixed:** 2026-04-13 (PR #14, commit `124fc38`)

### G-21: runOutPut case sensitivity (capital P) -- FIXED
- **Regex:** `(?i)unsupported activity output.*runOutPut`
- **Root cause:** `_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES` whitelist used exact match
- **Impact:** 4 expressions + also blocked G-22 (14 exprs) and G-23 (4 exprs)
- **Fix:** Removed output type whitelist entirely; any `activity().output.X` now resolves as dict accessor
- **Discovered:** 2026-04-13 (V2 sweep)
- **Fixed:** 2026-04-13 (PR #14, commit `124fc38`)

### G-22: runPageUrl output type not supported
- **Regex:** `(?i)unsupported activity output.*runPageUrl`
- **Root cause:** `runPageUrl` not in `_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES`
- **Impact:** 14 expressions in 3 Arquetipo pipelines
- **Upstream:** ghanse/wkmigrate#27
- **Fix:** Add `"runPageUrl"` to the set
- **Discovered:** 2026-04-13 (V2 sweep)

### G-23: Deep output chain (output.tasks[N].prop)
- **Regex:** `(?i)unsupported activity output.*\.tasks`
- **Root cause:** Property chain after `output.` only supports known types, not arbitrary chains
- **Impact:** 4 expressions (cluster ID extraction via `output.tasks[0].cluster_instance.cluster_id`)
- **Upstream:** ghanse/wkmigrate#27
- **Fix:** Support arbitrary property/index chains after `output.`
- **Discovered:** 2026-04-13 (V2 sweep)

### G-24: substring 2-arg form
- **Regex:** `(?i)substring.*expects at least 3.*got 2`
- **Root cause:** `_require_arity("substring", args, 3, 3)` rejects 2-arg form
- **Impact:** 1 expression in Arquetipo
- **Fix:** Change arity to `(2, 3)`; 2-arg form means "from start to end"
- **Discovered:** 2026-04-13 (V2 sweep)

## Failure Mode Taxonomy (for judge output)

Used by `dspy_judge.py` `FAILURE_MODES`:

| Mode | Meaning | Common Trigger |
|------|---------|----------------|
| `type_coercion_missing` | Math/comparison on string params without `int()`/`float()` | W-3 |
| `function_mapping_wrong` | ADF function maps to wrong Python function | Rare |
| `nesting_order_broken` | Evaluation order differs from ADF semantics | Deep nesting (4+ levels) |
| `parameter_reference_broken` | `pipeline().parameters.X` not mapped to `dbutils.widgets.get` | W-2 |
| `null_handling_missing` | Null propagation not implemented | `coalesce()` edge cases |
| `edge_case_unhandled` | Works for common cases, fails on edge cases | Empty string, div by zero |
| `semantically_correct` | Translation is correct | Expected for score >= 0.95 |

### W-25: Windows timezone mapping gap in datetime helpers
- **Regex:** `(?i)invalid.*timezone.*Standard Time|ZoneInfoNotFoundError.*Standard Time`
- **Signature key:** `windows_timezone_mapping_missing`
- **Root cause:** `convert_time_zone()` in `runtime/datetime_helpers.py` passes timezone names directly to `ZoneInfo()` with no Windows-to-IANA mapping, despite docstring claiming support
- **Impact:** Any ADF pipeline using Windows TZ names (e.g., `Romance Standard Time`, `Eastern Standard Time`) fails at runtime
- **Upstream:** ghanse/wkmigrate#27
- **Discovered:** 2026-04-13 (V4 deep validation)
- **Fix:** Added `_WINDOWS_TO_IANA` mapping dict + `_resolve_timezone()` helper (PR #15, commit `5ee2e1c`)
- **Status:** FIXED

### W-26: `is_conditional_task` dependency parser bug -- FIXED
- **Regex:** `(?i)UnsupportedValue.*task_key|is_conditional_task.*Succeeded`
- **Signature key:** `conditional_task_dependency_parser_bug`
- **Root cause:** `_parse_dependency()` in `activity_translator.py` uses `is_conditional_task=True` for all inner activities of IfCondition branches, rejecting valid `Succeeded` dependency conditions as unsupported
- **Impact:** 15/36 CRP0001 pipelines cannot complete notebook preparation (41.7%)
- **Upstream:** ghanse/wkmigrate#27
- **Discovered:** 2026-04-13 (V4 deep validation)
- **Fix:** Rewrote `_parse_dependency()` to branch on `outcome` field presence instead of `is_conditional_task` flag; added `UnsupportedValue` guard in `get_base_task()` (PR #16, commit `6f498bd`)
- **Status:** FIXED

### W-27: `formatDateTime` on string input
- **Regex:** `(?i)strftime.*str.*has no attribute|format_datetime.*string`
- **Signature key:** `format_datetime_string_input`
- **Root cause:** `_wkmigrate_format_datetime()` calls `.strftime()` directly on input; fails when input is a date string from `dbutils.widgets.get()` rather than a datetime object
- **Impact:** 4 CRP0001 expressions using `formatDateTime(pipeline().parameters.dataDate, ...)`
- **Upstream:** ghanse/wkmigrate#27
- **Discovered:** 2026-04-13 (V4 deep validation)
- **Fix:** Added `datetime.fromisoformat()` fallback when input is a string (PR #15, commit `5ee2e1c`)
- **Status:** FIXED

## Discovery Log

| Date | Session | New Signatures | Adversarial Hits |
|------|---------|---------------|-----------------|
| 2026-04-11 | adversarial-loop-run-1 | W-9 (3), W-10 (2) | 10/10 pipelines failed |
| 2026-04-13 | CRP0001 V2 re-validation | G-19 (8), G-20 (2), G-21 (4), G-22 (14), G-23 (4), G-24 (1) | 33/2842 real failures (98.8% adjusted success) |
| 2026-04-13 | CRP0001 V3 re-validation | All G-19..G-24 FIXED | **0/2792 real failures (100% adjusted success)** |
| 2026-04-13 | CRP0001 V4 deep validation | W-25 (20 exprs), W-26 (15 pipelines), W-27 (4 exprs) | 99.5% semantic correctness, 87.1% notebook prep |
| 2026-04-14 | CRP0001 V5 re-validation | All W-25..W-27 FIXED (CRP-8 PR#15 + CRP-9 PR#16) | **100% semantic, 100% notebook prep (36/36), 152 notebooks** |
