# W-28: taskValues Numeric Coercion + Null-Safe String Ops

## Context

After W-23 through W-27, the X-2 semantic eval scores 0.946 on 197 expressions.
4 expressions still score below 0.70. Root cause analysis:

| Score | Expression Pattern | Root Cause | Fix Location |
|-------|-------------------|------------|--------------|
| 0.30 | `@replace(path, '\\', '/')` | **Judge error** — ADF has NO backslash escaping, `\\` = two literal backslashes. wkmigrate is correct. | Judge calibration rule #11 |
| 0.50 | `@last(split(replace(path, '\\', '/'), '/'))` | Same judge error as above | Judge calibration rule #11 |
| 0.45 | `@coalesce(trim(activity().output...), ...)` | `str(None).strip()` → `'None'` breaks coalesce null-fallthrough | expression_functions.py |
| 0.65 | `@equals(mod(add(param, variables('x')), 2), 0)` | `taskValues.get()` not coerced in numeric context | expression_functions.py |

## Fix 1: Extend numeric coercion to taskValues.get() references

**File:** `src/wkmigrate/parsers/expression_functions.py`

**Current (line 106-111):**
```python
_PIPELINE_PARAMETER_EXPRESSION_PREFIX = "dbutils.widgets.get("

def _coerce_numeric_operand(arg: str) -> str:
    if arg.startswith(_PIPELINE_PARAMETER_EXPRESSION_PREFIX):
        return f"(lambda __wkm_p: ...)(str({arg}))"
    return arg
```

**Fix:** Also coerce `dbutils.jobs.taskValues.get(` references:
```python
_TASKVALUES_EXPRESSION_PREFIX = "dbutils.jobs.taskValues.get("

def _coerce_numeric_operand(arg: str) -> str:
    if arg.startswith(_PIPELINE_PARAMETER_EXPRESSION_PREFIX) or arg.startswith(_TASKVALUES_EXPRESSION_PREFIX):
        return f"(lambda __wkm_p: ...)(str({arg}))"
    return arg
```

**Affected functions:** All that use `_emit_numeric_binary_operator` — add, sub, mul, mod, greater, less, greaterOrEquals, lessOrEquals — plus `_emit_div`.

## Fix 2: Null-safe unary string operations

**File:** `src/wkmigrate/parsers/expression_functions.py`

**Current (line 52-58):**
```python
def _emit_unary_string_call(name: str, method: str) -> FunctionEmitter:
    def _emit(args: list[str]) -> str | UnsupportedValue:
        if error := _require_arity(name, args, 1, 1):
            return error
        return f"str({args[0]}).{method}()"
    return _emit
```

**Problem:** `str(None).strip()` → `'None'` (string), not `None`. ADF: `trim(null)` → `null`.

**Fix:** Guard against None:
```python
def _emit_unary_string_call(name: str, method: str) -> FunctionEmitter:
    def _emit(args: list[str]) -> str | UnsupportedValue:
        if error := _require_arity(name, args, 1, 1):
            return error
        arg = args[0]
        return f"(None if ({arg}) is None else str({arg}).{method}())"
    return _emit
```

**Scope:** Affects `trim`, `toLower`, `toUpper` (all registered via `_emit_unary_string_call`).

**Note:** `_emit_concat` does NOT need this fix — ADF `concat(null, 'x')` coerces null to empty string, which `str(None)` approximates (though `str(None)` = `'None'` not `''`). This is a separate, lower-priority issue.

## Fix 3: Judge calibration rule #11 (ADF backslash literals)

**File (lmv):** `src/lakeflow_migration_validator/dimensions/semantic_equivalence.py` and
`src/lakeflow_migration_validator/optimization/judge_optimizer.py`

**New rule:**
```
11. ADF string literal escaping — ADF expression strings use ONLY doubled single-quote
    ('') for escaping. Backslashes are NOT escape characters. So '\\' in ADF is TWO
    literal backslash characters, and the Python repr '\\\\' (which also represents
    two backslashes at runtime) is CORRECT. Do NOT penalize backslash count mismatches
    between ADF source notation and Python repr notation.
```

## Files to Modify

### wkmigrate
- `src/wkmigrate/parsers/expression_functions.py` — Fix 1 + Fix 2
- `tests/unit/test_expression_emitter.py` — new tests for both fixes

### lmv (judge calibration)
- `src/lakeflow_migration_validator/dimensions/semantic_equivalence.py` — add rule #11
- `src/lakeflow_migration_validator/optimization/judge_optimizer.py` — add rule #11

## Acceptance Criteria

- `@add(variables('x'), 1)` emits coerced code (not bare `taskValues.get() + 1`)
- `@trim(null_expr)` inside `coalesce()` preserves None (not `'None'` string)
- All existing tests pass (`make test`)
- `make fmt` clean
- Re-run X-2 semantic eval: mean > 0.96, 0 pairs below 0.50

## Workflow Notes

- **Base branch:** `feature/27-W27-datetime-utility-functions` (current HEAD of wkmigrate work)
- **PR target:** `alpha_1`
