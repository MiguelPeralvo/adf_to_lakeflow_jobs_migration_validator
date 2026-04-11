# wkmigrate Fix Spec: W-12 (Copy query path) + W-13 (IfCondition compound predicates)

> Self-contained specification for /wkmigrate-autodev. Activity context sweep on pr/27-4+fixes shows copy_query at 0% and if_condition at 6.5%. These are the two remaining expression resolution gaps blocking lmv from reaching >80% overall.

## Current State (pr/27-4-integration-tests + W-9/W-10/W-11 fixes)

Activity context sweep on 200 golden expressions × 7 contexts:

| Context | Resolution Rate | Status |
|---------|----------------|--------|
| set_variable | 200/200 (100%) | Fixed (pr/27-1) |
| notebook_base_param | 200/200 (100%) | Fixed (pr/27-1) |
| lookup_query | 200/200 (100%) | Fixed (pr/27-3) |
| web_body | 200/200 (100%) | Fixed (pr/27-3) |
| **if_condition** | **13/200 (6.5%)** | **W-13: only simple binary comparisons work** |
| **for_each** | 0/200 (0%) | Corpus mismatch (scalars, not arrays) — not a bug |
| **copy_query** | **0/200 (0%)** | **W-12: structural rejection before expression resolution** |

Fixing W-12 + W-13 would raise overall from **58.1%** to potentially **>85%** (4 contexts at 100% + 2 more near 100%).

---

## W-12: Copy Source Query Expression Never Reached (0%)

### Summary

When lmv wraps an expression as `Copy.source.sql_reader_query`, wkmigrate's `translate_copy_activity` rejects the activity at structural validation (missing `input_dataset_definitions` / `output_dataset_definitions`) before ever examining the expression. The W-9 fix (adding `sql_reader_query` to `_parse_sql_format_options`) and the W-11 fix (graceful degradation) are both unreachable because the rejection happens earlier in the chain.

### Root Cause

**File:** `src/wkmigrate/translators/activity_translators/copy_activity_translator.py`

```python
def translate_copy_activity(activity: dict, base_kwargs: dict) -> CopyActivity | UnsupportedValue:
    source_dataset = get_data_source_definition(get_value_or_unsupported(activity, "input_dataset_definitions"))
    if isinstance(source_dataset, UnsupportedValue):
        return UnsupportedValue(...)  # <-- REJECTS HERE, lines 39-41
    
    sink_dataset = get_data_source_definition(get_value_or_unsupported(activity, "output_dataset_definitions"))
    if isinstance(sink_dataset, UnsupportedValue):
        return UnsupportedValue(...)  # <-- OR HERE, lines 43-45
    
    source_properties = get_data_source_properties(get_value_or_unsupported(activity, "source"))
    # ... _parse_sql_format_options is called here, but we never get this far
```

The `input_dataset_definitions` and `output_dataset_definitions` are complex structures that come from resolving ADF dataset references against the factory's dataset definitions. Many real-world pipelines have these as inline references (`datasetReference: {referenceName: "...", type: "DatasetReference"}`) rather than expanded definitions.

When calling through lmv's `wrap_in_copy_query`, the activity has `source` and `sink` blocks but NO `input_dataset_definitions` or `output_dataset_definitions`.

### The Fix

The Copy translator should handle the case where dataset definitions are absent but source/sink blocks are present. The `source.sql_reader_query` expression is fully self-contained — it doesn't need dataset definitions to resolve.

**Option A (recommended): Extract source query BEFORE dataset validation:**

```python
def translate_copy_activity(activity, base_kwargs, context=None, emission_config=None):
    # NEW: Extract sql_reader_query early, before dataset validation
    source_block = activity.get("source", {})
    raw_query = source_block.get("sql_reader_query")
    resolved_query = None
    if raw_query is not None and context is not None:
        resolved_query = get_literal_or_expression(
            raw_query, context, ExpressionContext.COPY_QUERY, emission_config=emission_config
        )
    
    # Existing dataset validation
    source_dataset = get_data_source_definition(get_value_or_unsupported(activity, "input_dataset_definitions"))
    sink_dataset = get_data_source_definition(get_value_or_unsupported(activity, "output_dataset_definitions"))
    
    if isinstance(source_dataset, UnsupportedValue) or isinstance(sink_dataset, UnsupportedValue):
        # NEW: If we have a resolved query, produce a partial CopyActivity
        # instead of a full UnsupportedValue
        if resolved_query is not None and not isinstance(resolved_query, UnsupportedValue):
            warnings.warn(
                NotTranslatableWarning(
                    f"Copy activity '{base_kwargs.get('name')}': dataset definitions missing, "
                    f"but source query preserved as resolved expression"
                )
            )
            return CopyActivity(
                **base_kwargs,
                source_dataset=Dataset(name="unknown", type="sql", ...),  # minimal placeholder dataset
                sink_dataset=Dataset(name="unknown", type="unknown", ...),
                source_properties={"type": source_block.get("type", "unknown"), "sql_reader_query": resolved_query},
                sink_properties={},
                column_mapping=[],
            )
        return merge_unsupported_values([source_dataset, sink_dataset, ...])
```

**Option B (simpler but less complete): Add `context` and `emission_config` parameters and thread them through:**

Currently `translate_copy_activity(activity, base_kwargs)` doesn't receive `context` or `emission_config`. Add them:

```python
def translate_copy_activity(
    activity: dict,
    base_kwargs: dict,
    context: TranslationContext | None = None,
    emission_config: EmissionConfig | None = None,
) -> CopyActivity | UnsupportedValue:
```

Then update the caller in `activity_translator.py` to pass them. This is the same pattern that `translate_for_each_activity`, `translate_if_condition_activity`, and `translate_lookup_activity` already use.

### Required Changes

1. **`copy_activity_translator.py`**: Add `context` and `emission_config` params, extract query early
2. **`activity_translator.py`**: Pass `context` and `emission_config` to `translate_copy_activity`
3. **`emission_config.py`**: Add `ExpressionContext.COPY_QUERY` if not already present
4. **`tests/unit/test_activity_translators.py`**: Add test for Copy with query but no dataset defs

### Verification

```bash
make test  # all existing pass
# From lmv repo:
lmv sweep-activity-contexts --golden-set golden_sets/expressions.json --contexts copy_query
# copy_query resolved rate should jump from 0% to >90%
```

---

## W-13: IfCondition Only Handles Simple Binary Comparisons (6.5%)

### Summary

The IfCondition translator only supports 6 top-level comparison patterns: `@equals`, `@greater`, `@greaterOrEquals`, `@less`, `@lessOrEquals`, and `@not(equals(...))`. Any compound predicate (`@and(...)`, `@or(...)`) or non-comparison expression (`@concat(...)`, `@add(...)`) returns `UnsupportedValue`.

### Root Cause

**File:** `src/wkmigrate/translators/activity_translators/if_condition_activity_translator.py`

The `_parse_condition_expression` function (line 173) only handles:

```python
_CONDITION_FUNCTION_TO_OP: dict[str, str] = {
    "equals": "EQUAL_TO",
    "greater": "GREATER_THAN",
    "greaterorequals": "GREATER_THAN_OR_EQUAL",
    "less": "LESS_THAN",
    "lessorequals": "LESS_THAN_OR_EQUAL",
}
```

Plus `@not(equals(x, y))` → `NOT_EQUAL`.

**What fails (187/200 expressions):**
- `@and(equals(1,1), greater(3,2))` — `and` not in the map, returns UnsupportedValue
- `@or(less(1,0), equals('x','x'))` — `or` not in the map
- `@concat('hello','world')` — not a comparison at all
- `@add(1, 2)` — not a comparison
- `@if(equals(mod(5,2),1),'odd','even')` — `if` not in the map

**What passes (13/200):** Simple comparisons with literal operands: `@equals(1,1)`, `@greater(3,2)`, `@less(2,3)`, `@not(false)` when structured as `@not(equals(...))`, etc.

### The Fix

The fundamental issue is that Databricks' `condition_task` API requires binary comparisons (`op`, `left`, `right`). Compound conditions like `@and(...)` don't map to a single `condition_task`. Two approaches:

**Option A (recommended): Decompose compound conditions into nested condition_tasks:**

```python
# @and(equals(x, y), greater(a, b)) →
# condition_task_1: op=EQUAL_TO, left=x, right=y
#   → if true: condition_task_2: op=GREATER_THAN, left=a, right=b
#       → if true: run child activities

# @or(equals(x, y), greater(a, b)) →
# condition_task_1: op=EQUAL_TO, left=x, right=y
#   → if true: run child activities
#   → if false: condition_task_2: op=GREATER_THAN, left=a, right=b
#       → if true: run child activities
```

**Option B (simpler): Emit compound conditions as Python code in a notebook:**

When the condition is compound, instead of a `condition_task`, emit a regular DatabricksNotebook task that evaluates the Python expression and conditionally runs children:

```python
# @and(equals(x, y), greater(a, b)) →
# Notebook cell:
#   result = (x == y) and (a > b)
#   if result:
#       dbutils.notebook.run("true_branch", ...)
```

This is the approach for non-comparison expressions too — `@concat(...)` as an IfCondition predicate means "if the result is truthy" in ADF.

**Option C (minimal): Add `and`/`or` to the handler:**

```python
def _parse_condition_expression(condition, context):
    ...
    lowered_name = parsed.name.lower()
    
    # NEW: handle @and/@or by decomposing into the first comparison
    if lowered_name in ("and", "or"):
        if len(parsed.args) >= 2 and all(isinstance(a, FunctionCall) for a in parsed.args):
            # Try to parse the first argument as the primary condition
            # Emit the full compound expression as a warning
            first_condition = _parse_single_condition(parsed.args[0], context)
            if not isinstance(first_condition, UnsupportedValue):
                warnings.warn(
                    NotTranslatableWarning(
                        f"IfCondition: compound '{lowered_name}' simplified to first operand. "
                        f"Full predicate: {condition.get('value')}"
                    )
                )
                return first_condition
    ...
```

Option C is the minimum that would raise the resolution rate significantly (every `@and(equals(...), greater(...))` would at least partially translate).

### What each option yields

| Option | Expected if_condition rate | Complexity |
|--------|--------------------------|------------|
| Current | 6.5% (13/200) | — |
| C (simplify @and/@or) | ~30% (add logical category) | Low |
| B (notebook fallback) | ~80%+ (all parseable expressions) | Medium |
| A (nested condition_tasks) | ~30% for compound, rest via B | High |

**Recommendation:** Option B as the primary path (covers ALL expression types), with Option A as a follow-up for clean `and`/`or` decomposition.

### Required Changes

1. **`if_condition_activity_translator.py`**: Add `_try_notebook_fallback()` for expressions that don't fit `condition_task`
2. **`_parse_condition_expression`**: When the top-level function is not in `_CONDITION_FUNCTION_TO_OP`, fall through to notebook emission instead of returning UnsupportedValue
3. **`activity_translator.py`**: No changes needed (already passes context and emission_config)
4. **`tests/unit/test_activity_translators.py`**: Add tests for `@and(...)`, `@or(...)`, and non-comparison predicates

### Verification

```bash
make test
# From lmv repo:
lmv sweep-activity-contexts --golden-set golden_sets/expressions.json --contexts if_condition
# if_condition resolved rate should jump from 6.5% to >60%
```

---

## Execution Order

1. **W-12 first** — simpler fix (add params + extract query early), bigger impact (200 expressions from 0% to ~100%)
2. **W-13 second** — more complex (compound condition decomposition or notebook fallback), but also 200 expressions from 6.5% to >60%

## Branch Strategy

Base on `pr/27-4-integration-tests` (includes all prior work):
```bash
git checkout pr/27-4-integration-tests
git checkout -b pr/27-5-copy-query-ifcondition
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3..4 | Lint compliance | 0 |
| W12-1 | Copy with sql_reader_query but no dataset defs → NOT placeholder | test |
| W12-2 | Copy without sql_reader_query still works | test |
| W12-3 | copy_query sweep rate ≥ 80% (up from 0%) | measured |
| W13-1 | IfCondition with @and(equals, greater) → NOT UnsupportedValue | test |
| W13-2 | IfCondition with @or(...) → NOT UnsupportedValue | test |
| W13-3 | IfCondition with simple @equals still works (no regression) | test |
| W13-4 | if_condition sweep rate ≥ 50% (up from 6.5%) | measured |

## Related Specs

- `knowledge/wkmigrate-fix-spec-W9-W10.md` — predecessor (W-9/W-10 now fixed)
- `knowledge/wkmigrate-fix-spec-W11-structural.md` — predecessor (W-11 partially fixed)
