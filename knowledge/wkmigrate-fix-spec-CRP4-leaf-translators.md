# CRP-4: Leaf Activity Translators + Behavior Fixes

> Self-contained specification for /wkmigrate-autodev. Covers G-11, G-14, G-16, G-17, G-18 — two new leaf translators and three behavior fixes to existing translators.

## Background

wkmigrate (`ghanse/wkmigrate`, fork at `MiguelPeralvo/wkmigrate`) converts ADF pipeline JSON into Databricks Lakeflow Jobs. The wkmigrate repo is at `/Users/miguel.peralvo/Code/wkmigrate`. Activity dispatch lives in `_dispatch_activity()` in `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/activity_translator.py`.

All new translators use `get_literal_or_expression()` for expression-bearing properties.

## What is CRP0001?

36 real ADF pipelines from Repsol. The BFC (batch forecasting) group uses `AppendVariable` for array building and `setSystemVariable` for pipeline return values. The Arquetipo group uses `isSequential` ForEach loops. Fail activities appear in error handling paths.

## Branch Target

`pr/27-4-integration-tests` (or child branch). Depends on CRP-1 and CRP-3 landing first.

---

## G-11: `AppendVariable` Activity — P1 BLOCKER

### ADF Structure

```json
{
    "name": "Append to array_copy",
    "type": "AppendVariable",
    "typeProperties": {
        "variableName": "array_copy",
        "value": {
            "value": "@item()",
            "type": "Expression"
        }
    }
}
```

### CRP0001 Activities Affected (4 BFC pipelines)

- 8+ `AppendVariable` activities in `crp0001_c_pl_prc_edw_bfcdt_process_data_AMR.json` and `crp0001_c_pl_prc_edw_bfcdt_process_data.json`, appending to `array_copy` variable

### Databricks Equivalent

AppendVariable is semantically `variable.append(value)`. In Lakeflow Jobs, variables are stored as task values. The translation:

```python
# Read current array
current = dbutils.jobs.taskValues.get(taskKey='set_variable_array_copy', key='array_copy')
# Append
current.append(resolved_value)
# Write back
dbutils.jobs.taskValues.set(key='array_copy', value=current)
```

### Implementation

**New file:** `src/wkmigrate/translators/activity_translators/append_variable_activity_translator.py`

```python
"""Translator for ADF AppendVariable activities.

Maps AppendVariable to a SetVariableActivity-like notebook that appends
to a list stored as a task value.
"""
from __future__ import annotations
from importlib import import_module

from wkmigrate.models.ir.pipeline import SetVariableActivity
from wkmigrate.models.ir.translation_context import TranslationContext
from wkmigrate.models.ir.unsupported import UnsupportedValue
from wkmigrate.parsers.emission_config import EmissionConfig
from wkmigrate.parsers.expression_parsers import parse_variable_value


def translate_append_variable_activity(
    activity: dict,
    base_kwargs: dict,
    context: TranslationContext | None = None,
    emission_config: EmissionConfig | None = None,
) -> tuple[SetVariableActivity | UnsupportedValue, TranslationContext]:
    """Translate an ADF AppendVariable activity."""

    if context is None:
        activity_translator = import_module(
            "wkmigrate.translators.activity_translators.activity_translator"
        )
        context = activity_translator.default_context()

    variable_name = activity.get("variable_name")
    if not variable_name:
        return UnsupportedValue(
            value=activity,
            message="Missing 'variable_name' in AppendVariable activity",
        ), context

    raw_value = activity.get("value")
    if raw_value is None:
        return UnsupportedValue(
            value=activity,
            message="Missing 'value' in AppendVariable activity",
        ), context

    parsed_value = parse_variable_value(raw_value, context, emission_config=emission_config)
    if isinstance(parsed_value, UnsupportedValue):
        return UnsupportedValue(
            value=activity,
            message=f"Unsupported value in AppendVariable: {parsed_value.message}",
        ), context

    # Look up existing variable task key
    task_key = context.get_variable_task_key(variable_name) if context else None
    if task_key is None:
        task_key = f"set_variable_{variable_name}"

    # Generate append code: read current → append → write back
    append_code = (
        f"_current = dbutils.jobs.taskValues.get(taskKey={task_key!r}, key={variable_name!r})\n"
        f"_current.append({parsed_value})\n"
        f"dbutils.jobs.taskValues.set(key={variable_name!r}, value=_current)"
    )

    result = SetVariableActivity(
        **base_kwargs,
        variable_name=variable_name,
        variable_value=append_code,
    )
    context = context.with_variable(variable_name, base_kwargs["task_key"])
    return result, context
```

**Register in `_dispatch_activity`:**
```python
case "AppendVariable":
    return translate_append_variable_activity(
        activity, base_kwargs, context, emission_config=emission_config
    )
```

**GitHub issue:** ghanse/wkmigrate#64

### Test Cases

```python
def test_append_variable_basic():
    activity = {
        "name": "Append item",
        "type": "AppendVariable",
        "variable_name": "array_copy",
        "value": "test_value",
    }
    result, ctx = translate_append_variable_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
    assert result.variable_name == "array_copy"

def test_append_variable_expression():
    activity = {
        "name": "Append item",
        "type": "AppendVariable",
        "variable_name": "array_copy",
        "value": {"value": "@item()", "type": "Expression"},
    }
    result, ctx = translate_append_variable_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
```

---

## G-14: `Fail` Activity — P2

### ADF Structure

```json
{
    "name": "Error - No se reconoce tipo",
    "type": "Fail",
    "typeProperties": {
        "message": {
            "value": "@concat('Unsupported activity type: ', item()?.type)",
            "type": "Expression"
        },
        "errorCode": "UNSUPPORTED_TYPE"
    }
}
```

### CRP0001 Activities Affected (2 pipelines)

- BFC control check failure
- Arquetipo error propagation (`lakeh_a_pl_arquetipo_switch_internal.json`)

### Databricks Equivalent

A Fail activity maps to a notebook that raises an exception:
```python
raise Exception(f"ADF Fail: {error_code} - {message}")
```

Or more precisely, `dbutils.notebook.exit()` with a failure indicator.

### Implementation

**New file:** `src/wkmigrate/translators/activity_translators/fail_activity_translator.py`

```python
"""Translator for ADF Fail activities.

Maps Fail to a notebook task that raises an exception with the specified
message and error code.
"""
from __future__ import annotations

from wkmigrate.models.ir.pipeline import Activity
from wkmigrate.models.ir.translation_context import TranslationContext
from wkmigrate.models.ir.translator_result import TranslationResult
from wkmigrate.models.ir.unsupported import UnsupportedValue
from wkmigrate.parsers.emission_config import EmissionConfig, ExpressionContext
from wkmigrate.parsers.expression_parsers import get_literal_or_expression
from wkmigrate.utils import get_placeholder_activity


def translate_fail_activity(
    activity: dict,
    base_kwargs: dict,
    context: TranslationContext | None = None,
    emission_config: EmissionConfig | None = None,
) -> TranslationResult:
    """Translate an ADF Fail activity."""

    raw_message = activity.get("message", "Pipeline failed")
    message = get_literal_or_expression(
        raw_message, context, ExpressionContext.FAIL_MESSAGE, emission_config=emission_config
    )
    message_str = message.code if hasattr(message, 'code') else str(message)

    raw_error_code = activity.get("errorCode", "FAIL")
    error_code = get_literal_or_expression(
        raw_error_code, context, ExpressionContext.GENERIC, emission_config=emission_config
    )
    error_code_str = error_code.code if hasattr(error_code, 'code') else str(error_code)

    # Return a placeholder that documents the fail behavior
    # The preparer can generate: raise Exception(f"ADF Fail [{error_code}]: {message}")
    result = get_placeholder_activity(base_kwargs)
    return result
```

**Register in `_dispatch_activity`:**
```python
case "Fail":
    return (
        translate_fail_activity(activity, base_kwargs, context, emission_config=emission_config),
        context,
    )
```

### Test Case

```python
def test_fail_activity():
    activity = {
        "name": "Error",
        "type": "Fail",
        "message": {"value": "@concat('Error: ', item()?.type)", "type": "Expression"},
        "errorCode": "BAD_TYPE",
    }
    result = translate_fail_activity(activity, BASE_KWARGS)
    assert result is not None  # Should not crash
```

---

## G-16: `SetVariable` Ignores `setSystemVariable: true` — P1 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/set_variable_activity_translator.py`

The translator reads `variable_name` and `value` but does NOT check `setSystemVariable`. When this flag is `true`, the activity sets a `pipelineReturnValue` (pipeline output), not a regular variable. The value is a key-value array:

```json
{
    "name": "mkstring",
    "type": "SetVariable",
    "typeProperties": {
        "variableName": "pipelineReturnValue",
        "value": [
            {"key": "str_array", "value": {"type": "Expression", "content": "@join(variables('array_copy'),',')"}}
        ],
        "setSystemVariable": true
    }
}
```

### CRP0001 Activities Affected (3 BFC pipelines)

- `mkstring` in `crp0001_c_pl_prc_edw_bfcdt_process_data_AMR.json`
- Similar patterns in other BFC process data pipelines

### Fix

In `translate_set_variable_activity`, check `setSystemVariable` before the standard variable path:

```python
def translate_set_variable_activity(activity, base_kwargs, context=None, emission_config=None):
    # ... existing context init ...

    # NEW: Handle setSystemVariable (pipeline return values)
    if activity.get("setSystemVariable", False) or activity.get("set_system_variable", False):
        raw_value = activity.get("value")
        if isinstance(raw_value, list):
            # Key-value array → emit dbutils.jobs.taskValues.set() for each key
            for entry in raw_value:
                key = entry.get("key", "result")
                entry_value = entry.get("value")
                parsed = parse_variable_value(entry_value, context, emission_config=emission_config)
                # Emit: dbutils.jobs.taskValues.set(key=key, value=parsed)
            # Return a SetVariableActivity that captures all return values
            return SetVariableActivity(
                **base_kwargs,
                variable_name="pipelineReturnValue",
                variable_value=str(raw_value),  # Store the resolved values
            ), context

    # ... existing standard variable handling ...
```

**Note:** The exact handling depends on how `_normalize_activity` transforms the raw ADF JSON. Check if `setSystemVariable` is preserved or lowercased to `set_system_variable`.

### Test Cases

```python
def test_set_system_variable():
    activity = {
        "name": "mkstring",
        "type": "SetVariable",
        "variable_name": "pipelineReturnValue",
        "value": [{"key": "str_array", "value": "@join(variables('array_copy'),',')"}],
        "set_system_variable": True,
    }
    result, ctx = translate_set_variable_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
    assert result.variable_name == "pipelineReturnValue"

def test_regular_set_variable_unchanged():
    """Ensure regular SetVariable still works."""
    activity = {
        "name": "Set var",
        "type": "SetVariable",
        "variable_name": "myVar",
        "value": "hello",
    }
    result, ctx = translate_set_variable_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
    assert result.variable_name == "myVar"
```

---

## G-17: `ForEach` Ignores `isSequential: true` — P1

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/for_each_activity_translator.py`

The translator resolves `batch_count` (concurrency) via `_resolve_batch_count()` (~line 104) but does NOT read `isSequential`. When `isSequential: true`, the ForEach must execute items one at a time (concurrency=1).

### CRP0001 Activities Affected (2 arquetipo pipelines)

- `ForEach1` in `lakeh_a_pl_arquetipo_internal.json` (`"isSequential": true`)
- `ForEach1` in `lakeh_a_pl_arquetipo_nested_internal.json` (`"isSequential": true`)

### Fix

In `translate_for_each_activity`, after resolving `batch_count`, check `is_sequential`:

```python
concurrency = _resolve_batch_count(activity.get("batch_count"), context, emission_config)

# NEW: isSequential overrides batch_count
is_sequential = activity.get("is_sequential", False)
if is_sequential:
    concurrency = 1
```

**Note:** Check how `_normalize_activity` transforms the raw ADF JSON. The raw key is `isSequential` (camelCase); after normalization it may be `is_sequential` (snake_case).

### Test Cases

```python
def test_for_each_is_sequential():
    activity = {
        "name": "ForEach1",
        "type": "ForEach",
        "items": {"value": "@createArray('a','b')", "type": "Expression"},
        "is_sequential": True,
        "activities": [MOCK_NOTEBOOK_ACTIVITY],
    }
    result, ctx = translate_for_each_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
    assert result.concurrency == 1

def test_for_each_not_sequential():
    activity = {
        "name": "ForEach1",
        "type": "ForEach",
        "items": {"value": "@createArray('a','b')", "type": "Expression"},
        "batch_count": 20,
        "activities": [MOCK_NOTEBOOK_ACTIVITY],
    }
    result, ctx = translate_for_each_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
    assert result.concurrency == 20
```

---

## G-18: Inactive Activities (`state: "Inactive"`) Ignored — P2

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/activity_translator.py`, `_get_base_properties()` (~line 374)

The base property extraction reads `name`, `type`, `depends_on`, `timeout`, etc. but does NOT read `state`. Activities with `"state": "Inactive"` and `"onInactiveMarkAs": "Succeeded"` should be skipped or marked as always-succeed.

### CRP0001 Activities Affected (1 BFC pipeline)

- `fcfm_real_VC historic_custom` in `crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal_AMR.json`

### Fix

In `visit_activity()`, check the activity state before dispatching:

```python
def visit_activity(activity, is_conditional_task, context, emission_config=None):
    # ... existing cache check ...
    activity = _normalize_activity(activity)

    # NEW: Skip inactive activities
    state = activity.get("state", "Active")
    if state == "Inactive":
        on_inactive = activity.get("on_inactive_mark_as", "Succeeded")
        if on_inactive == "Succeeded":
            # Return a no-op activity that always succeeds
            base_properties = _get_base_properties(activity, is_conditional_task)
            result = get_placeholder_activity(base_properties)
            # Mark as inactive in the result for documentation
            if name:
                context = context.with_activity(name, result)
            return result, context

    # ... existing dispatch logic ...
```

**Note:** Check the normalization — raw ADF uses `"state": "Inactive"` and `"onInactiveMarkAs": "Succeeded"`. After `_normalize_activity`, these may be snake_cased.

### Test Case

```python
def test_inactive_activity_skipped():
    activity = {
        "name": "Inactive Task",
        "type": "DatabricksNotebook",
        "state": "Inactive",
        "on_inactive_mark_as": "Succeeded",
    }
    result, ctx = visit_activity(activity, False, default_context())
    # Should not crash; should produce a valid (possibly placeholder) result
    assert result is not None
```

---

## Files to Modify/Create

All paths relative to wkmigrate repo root at `/Users/miguel.peralvo/Code/wkmigrate`. On the `pr/27-4-integration-tests` branch:

| Absolute Path | Action |
|---------------|--------|
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/append_variable_activity_translator.py` | **NEW** (G-11) |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/fail_activity_translator.py` | **NEW** (G-14) |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/activity_translator.py` | Add 2 cases to `_dispatch_activity`; add G-18 state check in `visit_activity` |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/set_variable_activity_translator.py` | G-16: handle `setSystemVariable` |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/for_each_activity_translator.py` | G-17: read `isSequential` |
| `/Users/miguel.peralvo/Code/wkmigrate/tests/unit/test_activity_translators.py` | New test cases |

## Acceptance Criteria

1. `AppendVariable` produces `SetVariableActivity` (not placeholder)
2. `Fail` does not crash; resolves message expression
3. `SetVariable` with `setSystemVariable: true` handles key-value array
4. `ForEach` with `isSequential: true` sets `concurrency=1`
5. Inactive activities are handled gracefully (not crash)
6. All existing tests pass (`make test`)
7. `make fmt` clean
8. Commit references ghanse/wkmigrate#64

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests  # or after CRP-3 lands
git checkout -b feature/crp4-leaf-translators
# Implement: AppendVariable → Fail → setSystemVariable → isSequential → inactive state
# Run: make test && make fmt
git push -u fork feature/crp4-leaf-translators
```
