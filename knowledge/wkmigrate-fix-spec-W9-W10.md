# wkmigrate Fix Spec: W-9 and W-10

> Self-contained specification for /wkmigrate-autodev. Contains everything needed to understand, locate, fix, and verify these two bugs without external context.

## Background: What is wkmigrate?

wkmigrate (`ghanse/wkmigrate`, fork at `MiguelPeralvo/wkmigrate`) is a Python library that converts Azure Data Factory (ADF) pipeline JSON into Databricks Lakeflow Jobs notebooks. It has:

- **Parsers** (`src/wkmigrate/parsers/`): Parse ADF JSON → typed IR (frozen dataclasses)
- **Translators** (`src/wkmigrate/translators/activity_translators/`): Convert IR → Python notebook code
- **Expression system** (`parsers/expression_parsers.py`): Parse ADF expressions like `@concat(...)` → Python code

The critical shared utility is:
```python
from wkmigrate.parsers.expression_parsers import get_literal_or_expression
```
This function takes a raw value (string, dict with `{"type": "Expression", "value": "@..."}`, or literal), parses it, and returns a `ResolvedExpression` with the translated Python code. Activities that DON'T call this function lose expression data silently.

## What is lmv?

lmv (Lakeflow Migration Validator) is a **separate project** that tests wkmigrate by:
1. Generating synthetic ADF pipelines (via LLM or templates)
2. Running them through wkmigrate
3. Scoring the output on multiple dimensions (activity_coverage, expression_coverage, etc.)
4. Clustering failures by signature and filing them as findings

lmv discovered W-9 and W-10 through its adversarial testing loop (40 pipelines, 100% failure rate, 2026-04-11).

---

## W-9: Copy Activity `sql_reader_query` Silently Dropped

### Summary
When a Copy activity has a SQL query in `source.sql_reader_query` (especially one containing an ADF expression), wkmigrate's translation silently drops it. The query never appears in the generated notebook.

### Root Cause

The translation path is:
```
copy_activity_translator.translate_copy_activity()
  → utils.get_data_source_properties(source_dict)
    → dataset_parsers.parse_format_options(source_dict)
      → _parse_sql_format_options(source_dict, sql_type)
```

**File:** `src/wkmigrate/parsers/dataset_parsers.py`, function `_parse_sql_format_options` (line ~484):

```python
def _parse_sql_format_options(dataset: dict, dataset_type: str) -> dict | UnsupportedValue:
    format_settings = dataset.get("format_settings", {})
    return {
        "type": dataset_type,
        "query_isolation_level": _parse_query_isolation_level(format_settings.get("query_isolation_level")),
        "query_timeout_seconds": _parse_query_timeout_seconds(format_settings.get("query_timeout_seconds")),
        "numPartitions": format_settings.get("numPartitions"),
        "batchsize": format_settings.get("batchsize"),
        "sessionInitStatement": format_settings.get("sessionInitStatement"),
        "mode": _parse_sql_write_behavior(format_settings.get("mode")),
    }
```

**The bug:** The returned dict has a fixed key list. `sql_reader_query` is NOT in it. In ADF, the SQL query lives at `source.sql_reader_query` (top-level of the source dict, NOT inside `format_settings`). This function only looks at `format_settings` sub-keys.

### How ADF Structures Copy Source

In a real ADF pipeline JSON, a Copy activity with a SQL source looks like:
```json
{
  "name": "CopyData",
  "type": "Copy",
  "typeProperties": {
    "source": {
      "type": "AzureSqlSource",
      "sql_reader_query": {
        "type": "Expression",
        "value": "@concat('SELECT * FROM ', pipeline().parameters.table_name, ' WHERE date >= ''', formatDateTime(utcNow(), 'yyyy-MM-dd'), '''')"
      },
      "queryTimeout": "02:00:00",
      "partitionOption": "None"
    },
    "sink": { ... }
  }
}
```

The `sql_reader_query` is at the SAME level as `type`, not inside any `format_settings`.

### The Fix

**Option A (minimal):** In `_parse_sql_format_options`, add `sql_reader_query` to the returned dict by reading it from the top-level `dataset` dict:

```python
def _parse_sql_format_options(dataset: dict, dataset_type: str) -> dict | UnsupportedValue:
    format_settings = dataset.get("format_settings", {})
    return {
        "type": dataset_type,
        "sql_reader_query": dataset.get("sql_reader_query"),  # <-- ADD THIS
        "query_isolation_level": _parse_query_isolation_level(format_settings.get("query_isolation_level")),
        ...
    }
```

**Option B (full expression support, preferred):** Add expression resolution for `sql_reader_query` using `get_literal_or_expression`. This requires threading `TranslationContext` and `EmissionConfig` through the call chain (similar to how the Lookup translator does it at `lookup_activity_translator.py:132-145`):

```python
# In copy_activity_translator.py, BEFORE calling get_data_source_properties:
raw_query = source_dict.get("sql_reader_query")
if raw_query is not None:
    resolved_query = get_literal_or_expression(
        raw_query,
        context,
        ExpressionContext.COPY_QUERY,  # new context enum value
        emission_config=emission_config,
    )
    # Store resolved_query in the CopyActivity IR
```

The Lookup translator at `lookup_activity_translator.py:132-145` is the exact reference implementation for this pattern.

### Where Context/EmissionConfig Are Available

Currently `translate_copy_activity(activity, base_kwargs)` does NOT receive `context` or `emission_config`. You'll need to:
1. Add `context: TranslationContext | None = None` and `emission_config: EmissionConfig | None = None` parameters
2. Update the caller in `activity_translator.py` to pass them through
3. Add `ExpressionContext.COPY_QUERY` to the `ExpressionContext` enum in `parsers/emission_config.py`

### Verification

After the fix:
```bash
# Run existing tests
make test

# Run the lmv adversarial golden set (the 40 pipelines that triggered W-9)
# From the lmv repo:
lmv batch --golden-set golden_sets/overnight_adversarial.json --threshold 50
# expression_coverage should improve from ~0.0 to > 0.5 for Copy pipelines
```

### Evidence from lmv adversarial loop

- **16 out of 40** adversarial pipelines triggered W-9
- All 16 had Copy activities with `sql_reader_query` containing expressions like:
  - `@concat('SELECT * FROM dbo.', pipeline().parameters.table, ' WHERE ...')`
  - `@if(equals(pipeline().parameters.is_full_load, true), 'full_extract', 'incremental_load')`
- After wkmigrate translation, the `source_properties` dict had NO `sql_reader_query` key
- The generated notebook therefore has no SQL query — a critical data loss

---

## W-10: ForEach `items` Expression Returns UnsupportedValue for Complex Cases

### Summary
When a ForEach activity has an `items` expression containing nested function calls (e.g., `@createArray(concat('prefix_', param), concat('other_', param))`), `_parse_for_each_items` returns `UnsupportedValue`, causing the entire ForEach body to become a placeholder notebook.

### Root Cause

**File:** `src/wkmigrate/translators/activity_translators/for_each_activity_translator.py`, function `_parse_for_each_items` (line ~233) and `_evaluate_for_each_item` (line ~312).

The function DOES call `get_literal_or_expression()` (line 258), and it DOES handle `createArray`/`array` function calls (line 270). However, `_evaluate_for_each_item` at line 312 has a limited set of supported node types:

```python
def _evaluate_for_each_item(item: AstNode, context: TranslationContext) -> str | UnsupportedValue:
    if isinstance(item, StringLiteral): return item.value
    if isinstance(item, NumberLiteral): return str(item.value)
    if isinstance(item, BoolLiteral): return str(item.value).lower()
    if isinstance(item, FunctionCall) and item.name.lower() == "concat":
        # handles concat recursively
        ...
    # For everything else:
    emitted = emit(item, context)
    if isinstance(emitted, UnsupportedValue): return emitted
    try:
        literal = ast.literal_eval(emitted)  # <-- FAILS for complex expressions
    except (SyntaxError, ValueError):
        return UnsupportedValue(...)  # <-- THIS IS THE BUG
```

**The bug:** When a `createArray` item is a complex expression that can't be `ast.literal_eval()`'d (e.g., `concat('prefix_', pipeline().parameters.env)` which emits to `str('prefix_') + str(dbutils.widgets.get('env'))`), the `ast.literal_eval()` call raises `ValueError`, and the function returns `UnsupportedValue`. This propagates up and the entire ForEach becomes unsupported.

The fundamental issue: `_evaluate_for_each_item` tries to reduce expressions to STATIC strings. But expressions containing `pipeline().parameters.X` are DYNAMIC — they can't be known at translation time. The function should emit them as runtime Python code, not try to evaluate them to literals.

### The Fix

**Option A (minimal):** When `ast.literal_eval` fails, return the emitted code AS-IS instead of UnsupportedValue. The ForEach items will be a Python expression evaluated at runtime:

```python
def _evaluate_for_each_item(item: AstNode, context: TranslationContext) -> str | UnsupportedValue:
    if isinstance(item, StringLiteral): return item.value
    if isinstance(item, NumberLiteral): return str(item.value)
    if isinstance(item, BoolLiteral): return str(item.value).lower()
    if isinstance(item, FunctionCall) and item.name.lower() == "concat":
        ...
    
    emitted = emit(item, context)
    if isinstance(emitted, UnsupportedValue): return emitted
    try:
        literal = ast.literal_eval(emitted)
        return str(literal)
    except (SyntaxError, ValueError):
        # Dynamic expression — can't reduce to static, but IS valid Python
        return emitted  # <-- RETURN THE CODE, don't fail
```

**Option B (preferred):** Restructure `_parse_for_each_items` to handle dynamic items as a Python list expression:

```python
# When items contain dynamic expressions, emit as:
# [str('prefix_') + str(dbutils.widgets.get('env')), str('other_') + str(dbutils.widgets.get('env'))]
# instead of trying to produce a static JSON array '["prefix_prod","other_prod"]'
```

This requires changing the return type semantics — currently `_parse_for_each_items` returns a JSON-formatted string `'["a","b","c"]'`, but for dynamic items it should return a Python expression that evaluates to a list at runtime.

### The Existing Lookup Pattern (reference implementation)

The Lookup translator at `lookup_activity_translator.py:132-145` shows how to handle this correctly:
```python
raw_query = source.get("sql_reader_query") or source.get("query")
if raw_query is None:
    return None
resolved = get_literal_or_expression(raw_query, context, ExpressionContext.LOOKUP_QUERY, emission_config=emission_config)
if isinstance(resolved, UnsupportedValue):
    return resolved
if resolved.is_dynamic:
    return resolved  # <-- PRESERVE DYNAMIC EXPRESSIONS, don't try to evaluate them
return _unwrap_static_string(resolved.code, fallback=str(raw_query))
```

The key insight: **dynamic expressions should be preserved as `ResolvedExpression` objects**, not forced through `ast.literal_eval()`.

### Verification

After the fix:
```bash
make test

# Test with a ForEach pipeline that uses createArray with expressions:
# golden_sets/expressions_adversarial.json has 3 W-10 entries
# From lmv repo:
lmv sweep-activity-contexts --golden-set golden_sets/expressions_adversarial.json --contexts for_each
# for_each context should show resolved=N (currently 0) instead of all placeholder
```

### Evidence from lmv adversarial loop

- **5 out of 40** adversarial pipelines triggered W-10
- All had ForEach activities with items like:
  - `@createArray(concat('batch_', pipeline().parameters.batch_id), concat('chunk_', pipeline().parameters.chunk_id))`
  - `@createArray(string(add(mul(pipeline().parameters.chunk_size, 2), div(pipeline().parameters.total, 4))))`
- After translation, these ForEach activities returned `UnsupportedValue` → placeholder notebooks
- The child activities inside the ForEach (often DatabricksNotebook or Copy) were lost entirely

---

## Execution Order

1. **Fix W-9 first** — it's simpler (just add a key to a dict + thread context) and has higher impact (16 hits vs 5)
2. **Fix W-10 second** — requires changing the semantics of `_parse_for_each_items` to handle dynamic values

## Branch Strategy

Both fixes should target `pr/27-3` or create a new `pr/27-5` branch (the canonical pr/27-N line):
```bash
git checkout pr/27-4  # or the latest in the pr/27-N chain
git checkout -b pr/27-5-copy-foreach-expression-adoption
```

## Test Strategy

For each fix, follow TDD:
1. Write a failing test that exercises the bug
2. Implement the fix
3. Verify the test passes
4. Run `make test` + `make fmt` (hard gates)

### W-9 Test Case

```python
def test_copy_activity_preserves_sql_reader_query_expression():
    """Copy with Expression sql_reader_query should preserve it in source_properties."""
    activity = {
        "type": "Copy",
        "typeProperties": {
            "source": {
                "type": "AzureSqlSource",
                "sql_reader_query": {
                    "type": "Expression",
                    "value": "@concat('SELECT * FROM ', pipeline().parameters.table)"
                }
            },
            "sink": { "type": "ParquetSink" }
        }
    }
    result = translate_copy_activity(activity, base_kwargs, context=context)
    assert not isinstance(result, UnsupportedValue)
    assert "sql_reader_query" in result.source_properties
    # The value should be resolved Python code, not the raw ADF expression
```

### W-10 Test Case

```python
def test_for_each_items_with_dynamic_concat_expression():
    """ForEach with createArray(concat(...param...)) should NOT return UnsupportedValue."""
    items = {
        "type": "Expression",
        "value": "@createArray(concat('prefix_', pipeline().parameters.env))"
    }
    activity = {"items": items, "activities": [{"name": "inner", "type": "DatabricksNotebook", ...}]}
    result, _ = translate_for_each_activity(activity, base_kwargs, context=context)
    assert not isinstance(result, UnsupportedValue)
    assert isinstance(result, ForEachActivity)
    # items_string should contain the dynamic expression, not fail
```

## Meta-KPIs for /wkmigrate-autodev

When running `/wkmigrate-autodev` for this spec, use these from `dev/meta-kpis/general-meta-kpis.md`:

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3 | Black compliance | 0 diffs |
| GR-4 | Ruff compliance | 0 errors |
| EA-3 | Backward compatibility | existing tests still pass |

Plus issue-specific:
| ID | Gate | Target |
|----|------|--------|
| W9-1 | Copy with Expression sql_reader_query preserves it | test passes |
| W9-2 | Copy with literal sql_reader_query preserves it | test passes |
| W9-3 | Copy without sql_reader_query still works (no regression) | test passes |
| W10-1 | ForEach with createArray(concat(...param...)) resolves | test passes |
| W10-2 | ForEach with createArray(literal, literal) still works | test passes |
| W10-3 | ForEach with simple @array([...]) still works | test passes |

## Invocation

```
/wkmigrate-autodev "Fix W-9 (Copy sql_reader_query dropped in _parse_sql_format_options) and W-10 (ForEach items UnsupportedValue for dynamic expressions). See knowledge/wkmigrate-fix-spec-W9-W10.md for full context, root cause analysis, fix patterns, and test cases." --autonomy semi-auto
```
