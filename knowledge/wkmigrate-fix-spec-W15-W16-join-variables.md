# wkmigrate Fix Spec: W-15 (@join) + W-16 (variables())

> Self-contained specification for /wkmigrate-autodev. Expression loop analysis of 39 failing adversarial expressions reveals two unsupported ADF functions causing all failures in the set_variable/notebook/lookup/web/copy contexts.

## Evidence

200 adversarial expressions × 7 contexts. 5 non-for_each contexts resolve at 80.5% (161/200). The 39 failing expressions break down to exactly 2 root causes:

| Root Cause | Failures | % of Gap |
|-----------|----------|----------|
| `@join()` function not supported | 20/39 | 51% |
| `variables('name')` not resolved | 21/39 | 54% |
| (overlap: both) | ~12 | — |

Fixing both would push per-context resolution from **80.5% to ~100%** on adversarial expressions.

### Proof (isolated tests in set_variable context)

```
@join(createArray('a', 'b', 'c'), ',')          → PLACEHOLDER (join not supported)
@variables('myVar')                               → PLACEHOLDER (variables not resolved)
@coalesce(pipeline().parameters.x, 'default')     → RESOLVED ✓
@div(sub(mul(int(param.a), int(param.b)), 1), 2)  → RESOLVED ✓ (deep math, no variables)
@div(sub(mul(int(param.a), int(variables('m'))), 1), 2) → PLACEHOLDER (variables)
```

---

## W-15: @join() Function Not Supported

### What it is

ADF `@join(array, delimiter)` concatenates array elements with a delimiter:
```
@join(createArray('a', 'b', 'c'), ',')  →  "a,b,c"
@join(createArray(param.env, param.region), '/')  →  "dev/us-east-1"
```

Python equivalent: `delimiter.join(array)` or `','.join(['a', 'b', 'c'])`.

### Where to fix

**File:** `src/wkmigrate/parsers/expression_emitter.py` (or `expression_functions.py`)

The expression emitter has a registry of supported ADF functions. `join` is missing. The fix is to add it:

```python
# In the function registry:
"join": lambda args, ctx: f"{_emit(args[1], ctx)}.join({_emit(args[0], ctx)})"
# Or more robustly:
# "join": _emit_join  # with proper handling of the args
```

The `join` function takes 2 arguments:
- `args[0]`: the array (e.g., `createArray(...)` or a variable)
- `args[1]`: the delimiter string

Python emission: `str(delimiter).join(array_expression)`

### Failing Expressions (20 examples)

```
@join(createArray(pipeline().parameters.region, pipeline().parameters.env, formatDateTime(utcNow(), 'yyyyMMdd')), '/')
@join(createArray(pipeline().parameters.env, toLower(activity('Lookup').output.firstRow.code)), '-')
@join(createArray(pipeline().parameters.sourceSystem, pipeline().parameters.entity, formatDateTime(utcNow(), 'yyyyMMdd_HHmmss')), '/')
@join(createArray(toUpper(pipeline().parameters.env), substring(formatDateTime(utcNow(), 'yyyy-MM-dd'), 0, 7), string(add(pipeline().parameters.batch, 1))), '_')
```

### Test Cases

```python
def test_join_simple_array():
    """@join(createArray('a','b','c'), ',') → ','.join(['a','b','c'])"""
    # Should resolve, not placeholder

def test_join_with_expressions():
    """@join(createArray(param.env, param.region), '/') → '/'.join([widgets.get('env'), widgets.get('region')])"""
    # Should resolve with parameter coercion

def test_join_single_element():
    """@join(createArray('only'), ',') → ','.join(['only'])"""
    # Edge case: single-element array
```

---

## W-16: variables('name') Not Resolved in Expression Context

### What it is

ADF `@variables('name')` reads a pipeline variable. In the expression context of `get_literal_or_expression`, wkmigrate needs to emit code that reads the variable at runtime.

```
@variables('myVar')  →  variables['myVar']   (wkmigrate convention for variable access)
@add(int(variables('counter')), 1)  →  (int(variables['counter']) + 1)
```

### Where to fix

**File:** `src/wkmigrate/parsers/expression_emitter.py` (or the expression resolver)

The expression parser likely recognizes `variables('name')` as a `PropertyAccess` or `FunctionCall` AST node, but the emitter doesn't know how to emit code for it. It needs a handler similar to `pipeline().parameters.X` → `dbutils.widgets.get('X')`.

For `variables('name')`:
```python
# In the emitter:
if isinstance(node, FunctionCall) and node.name == "variables":
    var_name = node.args[0]  # StringLiteral
    return f"variables['{var_name.value}']"
```

Or if wkmigrate uses a different convention for variables:
```python
return f"spark.conf.get('pipeline.variables.{var_name.value}')"
```

Check how the SetVariable translator currently handles variables — it writes to `variable_name` / `variable_value` in the IR, but reading them back in expressions is the gap.

### Failing Expressions (21 examples)

```
@variables('myVar')
@add(int(variables('counter')), 1)
@coalesce(activity('Lookup').output.firstRow.optional_value, variables('defaultValue'), pipeline().parameters.fallback)
@if(and(greater(int(pipeline().parameters.max_retries), int(variables('retryCount'))), not(equals(coalesce(...)))))
@mod(add(mul(int(pipeline().parameters.count), int(variables('multiplier'))), int(pipeline().parameters.offset)), 100)
@div(sub(mul(int(pipeline().parameters.batch_size), int(pipeline().parameters.parallelism)), int(variables('overhead'))), 4)
```

### Test Cases

```python
def test_variables_simple():
    """@variables('myVar') → variables['myVar']"""
    # Should resolve, not placeholder

def test_variables_in_math():
    """@add(int(variables('counter')), 1) → (int(variables['counter']) + 1)"""
    # Should resolve with coercion

def test_variables_in_coalesce():
    """@coalesce(param.x, variables('default')) → coalesce with variable fallback"""
    # Should resolve both branches
```

---

## Execution Order

1. **W-15 (@join) first** — simpler (add one function to the registry), 20 direct fixes
2. **W-16 (variables) second** — may require changes to the expression resolver, 21 direct fixes

Both together fix all 39 failing expressions → per-context rate goes from 80.5% to ~100%.

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests  # or wherever W-14 landed
git checkout -b pr/27-7-join-variables-support
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3..4 | Lint compliance | 0 |
| W15-1 | @join(createArray('a','b','c'), ',') resolves | test passes |
| W15-2 | @join with expression args resolves | test passes |
| W16-1 | @variables('myVar') resolves | test passes |
| W16-2 | @variables in math context resolves | test passes |
| W16-3 | @variables in coalesce resolves | test passes |
| OVERALL | expression_loop per-context rate ≥ 95% (up from 80.5%) | measured |

## Verification

```bash
make test
# From lmv repo:
lmv expression-loop --rounds 5 --expressions 20 --model databricks-gpt-5-4
# per-context rates should jump from 80.5% to >95%
```
