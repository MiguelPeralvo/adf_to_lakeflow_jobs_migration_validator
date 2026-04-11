# wkmigrate Fix Spec: W-17 (firstRow flattening) + W-18 (type coercion) + W-19 (variables taskKey)

> Self-contained specification for /wkmigrate-autodev. Semantic equivalence evaluation of 200 adversarial expressions (via LLM judge at 97.75% baseline agreement) reveals 3 root causes accounting for 73/200 low-scoring pairs (score < 0.7). These are correctness bugs — the expressions *resolve* but produce *wrong Python code*.

## Evidence

200 adversarial expressions resolved through wkmigrate (pr/27-4-integration-tests @ ad749f9) in set_variable context, then scored by calibrated LLM judge (databricks-claude-sonnet-4-6).

| Metric | Value |
|--------|-------|
| Overall mean semantic score | 0.735 |
| Expressions scored < 0.7 | 73/200 (36.5%) |
| datetime category | 0.970 (excellent) |
| math category | 0.830 (good) |
| string category | 0.445 (poor — dominated by W-17) |
| collection category | 0.652 (weak — dominated by W-17) |
| logical category | 0.710 (borderline — dominated by W-18) |

Full results: `golden_sets/semantic_eval_results.json` in the lmv repo.

---

## W-17: `firstRow` Flattening in Activity Output References

### What it is

ADF `@activity('Lookup').output.firstRow.config_value` accesses `output → firstRow → config_value` — a 3-level property chain. wkmigrate emits:

```python
# WRONG — missing firstRow level:
json.loads(dbutils.jobs.taskValues.get(taskKey='Lookup', key='result'))['config_value']

# CORRECT:
json.loads(dbutils.jobs.taskValues.get(taskKey='Lookup', key='result'))['firstRow']['config_value']
```

The `firstRow` property is ADF's way of accessing the first row of a Lookup activity's result set. Dropping it means the emitted code accesses the wrong level of the JSON structure.

### Impact

This is the **highest-impact bug** — it affects every expression that references `activity('X').output.firstRow.Y`. In the adversarial set, this pattern appears in:
- All `string` category expressions using activity refs (drives the 0.445 mean)
- Many `nested` and `collection` expressions with activity refs
- ~17 of the top 20 lowest-scoring expressions

### Where to fix

**File:** `src/wkmigrate/parsers/expression_emitter.py` (or wherever `PropertyAccess` nodes for `activity().output.firstRow.X` are emitted)

The expression emitter currently handles the property chain `activity('Lookup').output.firstRow.config_value` by:
1. Recognizing `activity('Lookup')` → `dbutils.jobs.taskValues.get(taskKey='Lookup', key='result')`
2. Recognizing `.output` → wrapping in `json.loads(...)`
3. Recognizing `.firstRow.config_value` → **flattening to `['config_value']`**

Step 3 should emit `['firstRow']['config_value']` instead. The `firstRow` is NOT a semantic no-op in ADF — it's a real property access that must be preserved.

**Fix pattern:**
```python
# In the PropertyAccess emitter, when handling activity().output chain:
# After .output, the remaining chain is [firstRow, config_value]
# Currently: emits ['config_value'] (drops firstRow)
# Should: emits ['firstRow']['config_value'] (preserves full chain)
```

### Test Cases

```python
def test_activity_output_firstrow_preserved():
    """@activity('Lookup').output.firstRow.config_value should preserve firstRow."""
    expr = "@activity('Lookup').output.firstRow.config_value"
    result = get_literal_or_expression({"type": "Expression", "value": expr}, context)
    assert "['firstRow']" in result.code or "firstRow" in result.code

def test_activity_output_firstrow_nested():
    """@activity('Lookup').output.firstRow.nested.deep should preserve all levels."""
    expr = "@activity('Lookup').output.firstRow.nested.deep"
    result = get_literal_or_expression({"type": "Expression", "value": expr}, context)
    # Should have ['firstRow']['nested']['deep'], not just ['deep']

def test_activity_output_without_firstrow():
    """@activity('Lookup').output.count (no firstRow) should work unchanged."""
    expr = "@activity('Lookup').output.count"
    result = get_literal_or_expression({"type": "Expression", "value": expr}, context)
    # Should have ['count'], NOT ['firstRow']['count']
```

---

## W-18: Missing Type Coercion in Comparison Functions

### What it is

ADF comparison functions (`greater`, `less`, `greaterOrEquals`, `lessOrEquals`) implicitly coerce their arguments to numbers when comparing. wkmigrate emits the comparison without coercion:

```python
# ADF: @greater(pipeline().parameters.threshold, 50)
# WRONG — string > int = TypeError in Python 3:
(dbutils.widgets.get('threshold') > 50)

# CORRECT:
(int(dbutils.widgets.get('threshold')) > 50)
```

`dbutils.widgets.get()` always returns a string. ADF's `greater()` function coerces both sides to the same type (number if either side is numeric). The emitted Python must do the same.

### Impact

Affects all `logical` category expressions that use `greater/less/greaterOrEquals/lessOrEquals` with pipeline parameters and numeric literals. This drives the `logical` category down to 0.710 mean score.

### Where to fix

**File:** `src/wkmigrate/parsers/expression_emitter.py` (or wherever comparison function calls are emitted)

When emitting `greater(left, right)`, `less(left, right)`, etc.:
- If one operand is a numeric literal and the other is a parameter reference or expression, wrap the non-numeric side in `int()` or `float()`
- This matches ADF's implicit type coercion semantics

**Fix pattern:**
```python
# In the comparison function emitter:
def _emit_comparison(op, left, right, ctx):
    left_code = _emit(left, ctx)
    right_code = _emit(right, ctx)
    
    # If one side is a numeric literal and the other is a string source,
    # wrap the string source in int() for type safety
    if _is_numeric_literal(right) and _is_string_source(left):
        left_code = f"int({left_code})"
    elif _is_numeric_literal(left) and _is_string_source(right):
        right_code = f"int({right_code})"
    
    return f"({left_code} {op} {right_code})"
```

A simpler approach: ADF's `greater/less` always do numeric comparison, so always wrap both sides in a numeric coercion when emitting these functions:
```python
# Simpler: greater(a, b) → (int(a) > int(b)) always
# This is safe because ADF's greater() is defined as numeric comparison
```

### Test Cases

```python
def test_greater_with_param_and_literal():
    """@greater(pipeline().parameters.threshold, 50) should coerce param to int."""
    expr = "@greater(pipeline().parameters.threshold, 50)"
    result = get_literal_or_expression({"type": "Expression", "value": expr}, context)
    # Result should contain int() wrapping around the widgets.get call
    assert "int(dbutils.widgets.get('threshold'))" in result.code or "int(" in result.code

def test_less_with_param_and_literal():
    """@less(pipeline().parameters.retries, 5) should coerce param to int."""
    expr = "@less(pipeline().parameters.retries, 5)"
    result = get_literal_or_expression({"type": "Expression", "value": expr}, context)
    assert "int(" in result.code

def test_greater_with_two_params():
    """@greater(pipeline().parameters.a, pipeline().parameters.b) — both strings, should coerce both."""
    expr = "@greater(pipeline().parameters.a, pipeline().parameters.b)"
    result = get_literal_or_expression({"type": "Expression", "value": expr}, context)
    # Both sides should have int() wrapping
```

---

## W-19: `variables()` Task Value Naming Convention

### What it is

ADF `@variables('myVar')` reads a pipeline variable. wkmigrate emits:

```python
# Current emission:
dbutils.jobs.taskValues.get(taskKey='set_variable_myVar', key='myVar')
```

The taskKey `'set_variable_myVar'` is an invented naming convention that assumes:
1. A prior SetVariable activity exists with that exact name
2. The variable was stored using `dbutils.jobs.taskValues.set(key='myVar', value=...)`

This is fragile and may not match the actual pipeline structure. The LLM judge flags it because the naming convention is not derivable from the ADF expression alone.

### Impact

Lower impact than W-17 and W-18 — affects expressions that use `variables()` which are less common than activity refs or parameter comparisons. This is more of a convention concern than a correctness bug.

### Recommendation

This is a **design decision** rather than a clear bug. Two options:

**Option A (simple):** Keep the current convention but document it clearly. Add a comment in the emitted code explaining the taskKey naming convention. The judge would still flag it, but the convention is at least intentional.

**Option B (robust):** Emit a helper function call instead:
```python
# Instead of:
dbutils.jobs.taskValues.get(taskKey='set_variable_myVar', key='myVar')

# Emit:
_get_pipeline_variable('myVar')

# Where _get_pipeline_variable is a runtime helper that searches for the variable
# across all SetVariable task results
```

**Recommended: Option A for now.** The naming convention works when the SetVariable translator uses the same convention. Focus on W-17 and W-18 first.

---

## Execution Order

1. **W-17 (firstRow flattening) FIRST** — highest impact, clearest fix, affects the most expressions
2. **W-18 (type coercion) SECOND** — clear correctness bug, straightforward fix in comparison emitters
3. **W-19 (variables taskKey) DEFER** — design decision, lower impact, works with current SetVariable translator

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests  # current tip: ad749f9
git checkout -b pr/27-8-semantic-correctness
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3..4 | Lint compliance | 0 |
| W17-1 | `activity('X').output.firstRow.Y` preserves firstRow in emitted code | test passes |
| W17-2 | `activity('X').output.Y` (no firstRow) still works | test passes |
| W18-1 | `greater(param, 50)` emits with int() coercion | test passes |
| W18-2 | `less(param, literal)` emits with int() coercion | test passes |
| W18-3 | `greater(param_a, param_b)` (both params) coerces both | test passes |
| OVERALL | lmv semantic-eval mean score on set_variable context | > 0.80 (up from 0.735) |

## Verification

```bash
make test
# From lmv repo:
source .env && export DATABRICKS_HOST DATABRICKS_TOKEN
lmv semantic-eval --golden-set golden_sets/expression_loop_post_w16.json --context set_variable --model databricks-claude-sonnet-4-6 --limit 50
# string category should jump from 0.445 to > 0.70
# logical category should jump from 0.710 to > 0.85
# overall should jump from 0.735 to > 0.80
```
