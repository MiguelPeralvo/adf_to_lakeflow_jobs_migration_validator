# Failure Mode Catalog

> Last updated: 2026-04-11 (auto-updated by adversarial loop)

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

## Discovery Log

| Date | Session | New Signatures | Adversarial Hits |
|------|---------|---------------|-----------------|
| 2026-04-11 | adversarial-loop-run-1 | W-9 (3), W-10 (2) | 10/10 pipelines failed |
