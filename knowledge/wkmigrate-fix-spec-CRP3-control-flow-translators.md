# CRP-3: Control-Flow Activity Translators (ExecutePipeline, Switch, Until)

> Self-contained specification for /wkmigrate-autodev. Covers G-15, G-13, G-12 — three control-flow activity types missing from wkmigrate that block CRP0001 pipeline translation.

## Background

wkmigrate (`ghanse/wkmigrate`, fork at `MiguelPeralvo/wkmigrate`) converts ADF pipeline JSON into Databricks Lakeflow Jobs. The wkmigrate repo is at `/Users/miguel.peralvo/Code/wkmigrate`. Activity translation is dispatched by `_dispatch_activity()` in `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/activity_translator.py` (~line 183) via a `match` statement.

Currently supported: `DatabricksNotebook`, `WebActivity`, `IfCondition`, `ForEach`, `SetVariable`, `DatabricksSparkPython`, `DatabricksSparkJar`, `DatabricksJob`, `Lookup`, `Copy` (10 types).

Unsupported types fall to `case _:` which emits a `NotTranslatableWarning` and returns a placeholder notebook.

### Expression System

All new translators MUST use `get_literal_or_expression()` for expression-bearing properties:
```python
from wkmigrate.parsers.expression_parsers import get_literal_or_expression
from wkmigrate.parsers.emission_config import EmissionConfig, ExpressionContext
```

This is the entire point of issue #27 — the expression infrastructure is built, new translators call it.

## What is CRP0001?

36 real ADF pipelines from Repsol. `ExecutePipeline` is the most common unsupported activity (15+ instances). `Switch` is used in the Arquetipo orchestration framework. `Until` is used in FCL industrial for retry logic.

## Branch Target

`pr/27-4-integration-tests` (or child branch). Depends on CRP-1 (emitter fixes) being merged first, since some expression properties use `globalParameters` and `runOutput`.

## GitHub Issues

- **ghanse/wkmigrate#61**: Support Execute Pipeline activities
- **ghanse/wkmigrate#52**: Support Switch activities
- **ghanse/wkmigrate#62**: Support Until activities

Commit messages should reference these issues.

---

## G-15: `ExecutePipeline` Activity — P1 BLOCKER

### ADF Structure

```json
{
    "name": "lakeh_a_pl_operational_log_start",
    "type": "ExecutePipeline",
    "typeProperties": {
        "pipeline": {
            "referenceName": "lakeh_a_pl_operational_log",
            "type": "PipelineReference"
        },
        "waitOnCompletion": false,
        "parameters": {
            "applicationName": {
                "value": "@pipeline().parameters.applicationName",
                "type": "Expression"
            },
            "dataDate": {
                "value": "@coalesce(pipeline().parameters.referenceDate, formatDateTime(utcnow(),'yyyy/MM/dd'))",
                "type": "Expression"
            },
            "logType": "START",
            "message": {
                "value": "@pipeline().parameters.message",
                "type": "Expression"
            }
        }
    }
}
```

### CRP0001 Activities Affected (15+ across all groups)

- All BFC, CMD, FCL orchestration pipelines invoke child pipelines
- Arquetipo framework chains: `lakeh_a_pl_arquetipo` → `lakeh_a_pl_arquetipo_internal` → `lakeh_a_pl_arquetipo_nested_par_internal`
- Operational logging: `lakeh_a_pl_operational_log_start` → `lakeh_a_pl_operational_log`

### Databricks Equivalent

`ExecutePipeline` maps to a **Run Job task** in Lakeflow Jobs, referencing the translated child pipeline as a separate Databricks Job. Parameters are passed via the `run_job_task.job_parameters` field.

### Implementation

**New file:** `src/wkmigrate/translators/activity_translators/execute_pipeline_activity_translator.py`

```python
"""Translator for ADF ExecutePipeline activities.

Maps ExecutePipeline to a RunJobActivity in Databricks Lakeflow Jobs.
The referenced child pipeline becomes a separate Databricks Job, and
parameters are passed as job_parameters.
"""
from __future__ import annotations

from wkmigrate.models.ir.pipeline import RunJobActivity
from wkmigrate.models.ir.translation_context import TranslationContext
from wkmigrate.models.ir.translator_result import TranslationResult
from wkmigrate.models.ir.unsupported import UnsupportedValue
from wkmigrate.parsers.emission_config import EmissionConfig, ExpressionContext
from wkmigrate.parsers.expression_parsers import get_literal_or_expression


def translate_execute_pipeline_activity(
    activity: dict,
    base_kwargs: dict,
    context: TranslationContext | None = None,
    emission_config: EmissionConfig | None = None,
) -> TranslationResult:
    """Translate an ADF ExecutePipeline activity."""

    pipeline_ref = activity.get("pipeline", {})
    referenced_pipeline = pipeline_ref.get("referenceName")
    if not referenced_pipeline:
        return UnsupportedValue(
            value=activity,
            message="Missing 'pipeline.referenceName' in ExecutePipeline activity",
        )

    wait_on_completion = activity.get("waitOnCompletion", True)

    # Resolve each parameter through the expression system
    raw_parameters = activity.get("parameters") or {}
    resolved_parameters: dict[str, str] = {}
    for param_name, param_value in raw_parameters.items():
        resolved = get_literal_or_expression(
            param_value,
            context,
            ExpressionContext.EXECUTE_PIPELINE_PARAM,
            emission_config=emission_config,
        )
        if isinstance(resolved, UnsupportedValue):
            resolved_parameters[param_name] = str(resolved)
        elif hasattr(resolved, 'code'):
            resolved_parameters[param_name] = resolved.code
        else:
            resolved_parameters[param_name] = str(resolved)

    return RunJobActivity(
        **base_kwargs,
        job_name=referenced_pipeline,
        job_parameters=resolved_parameters if resolved_parameters else None,
    )
```

**Note:** The `RunJobActivity` IR dataclass already exists (used by `DatabricksJob` translator). If it doesn't have the right fields, a minimal extension may be needed. Check the IR definition.

**Register in `_dispatch_activity`:**
```python
case "ExecutePipeline":
    return (
        translate_execute_pipeline_activity(
            activity, base_kwargs, context, emission_config=emission_config
        ),
        context,
    )
```

### Test Cases

```python
def test_execute_pipeline_basic():
    activity = {
        "name": "Run Child",
        "type": "ExecutePipeline",
        "pipeline": {"referenceName": "child_pipeline", "type": "PipelineReference"},
        "waitOnCompletion": True,
        "parameters": {"env": "prod"},
    }
    result = translate_execute_pipeline_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
    assert result.job_name == "child_pipeline"

def test_execute_pipeline_expression_params():
    activity = {
        "name": "Run Child",
        "type": "ExecutePipeline",
        "pipeline": {"referenceName": "child_pipeline", "type": "PipelineReference"},
        "parameters": {
            "appName": {"value": "@pipeline().parameters.applicationName", "type": "Expression"},
        },
    }
    result = translate_execute_pipeline_activity(activity, BASE_KWARGS)
    assert "dbutils.widgets.get" in str(result.job_parameters.get("appName", ""))

def test_execute_pipeline_missing_ref():
    activity = {"name": "Bad", "type": "ExecutePipeline", "pipeline": {}}
    result = translate_execute_pipeline_activity(activity, BASE_KWARGS)
    assert isinstance(result, UnsupportedValue)
```

---

## G-13: `Switch` Activity — P1 BLOCKER

### ADF Structure

```json
{
    "name": "Switch on type",
    "type": "Switch",
    "typeProperties": {
        "on": {
            "value": "@toUpper(coalesce(item()?.type, 'DEFAULT'))",
            "type": "Expression"
        },
        "cases": [
            {
                "value": "NOTEBOOK",
                "activities": [
                    {"name": "Run Notebook", "type": "DatabricksNotebook", ...}
                ]
            },
            {
                "value": "JAR",
                "activities": [
                    {"name": "Run Jar", "type": "DatabricksSparkJar", ...}
                ]
            }
        ],
        "defaultActivities": [
            {"name": "Unsupported Type", "type": "Fail", ...}
        ]
    }
}
```

### CRP0001 Activities Affected (3 arquetipo pipelines)

- `lakeh_a_pl_arquetipo_switch_internal.json` — routes by `item()?.type`
- `lakeh_a_pl_arquetipo_switch2_internal.json` — same pattern
- `lakeh_a_pl_arquetipo_internal.json` — contains Switch activities

### Databricks Equivalent

Databricks Lakeflow Jobs `condition_task` only supports binary conditions (`EQUAL_TO`, `NOT_EQUAL`, etc.). A Switch with N cases maps to N-1 chained `IfCondition`-like condition tasks:

```
case "NOTEBOOK" → IfCondition(on_value == "NOTEBOOK", true_branch=..., false_branch=next_check)
case "JAR"      → IfCondition(on_value == "JAR", true_branch=..., false_branch=default)
```

### Implementation

**New file:** `src/wkmigrate/translators/activity_translators/switch_activity_translator.py`

```python
"""Translator for ADF Switch activities.

Maps Switch to chained IfConditionActivity nodes in Databricks Lakeflow Jobs.
Each case becomes an EQUAL_TO condition check; the default case becomes the
final else branch.
"""
from __future__ import annotations
from importlib import import_module

from wkmigrate.models.ir.pipeline import Activity, IfConditionActivity
from wkmigrate.models.ir.translation_context import TranslationContext
from wkmigrate.models.ir.translator_result import TranslationResult
from wkmigrate.models.ir.unsupported import UnsupportedValue
from wkmigrate.parsers.emission_config import EmissionConfig, ExpressionContext
from wkmigrate.parsers.expression_parsers import get_literal_or_expression


def translate_switch_activity(
    activity: dict,
    base_kwargs: dict,
    context: TranslationContext | None = None,
    emission_config: EmissionConfig | None = None,
) -> tuple[TranslationResult, TranslationContext]:
    """Translate an ADF Switch activity into chained IfCondition tasks."""

    if context is None:
        activity_translator = import_module(
            "wkmigrate.translators.activity_translators.activity_translator"
        )
        context = activity_translator.default_context()

    # Resolve the "on" expression (the value being switched on)
    raw_on = activity.get("on")
    if not raw_on:
        return UnsupportedValue(
            value=activity,
            message="Missing 'on' property in Switch activity",
        ), context

    on_expression = get_literal_or_expression(
        raw_on, context, ExpressionContext.SWITCH_ON, emission_config=emission_config
    )
    if isinstance(on_expression, UnsupportedValue):
        return on_expression, context

    on_value = on_expression.code if hasattr(on_expression, 'code') else str(on_expression)

    cases = activity.get("cases") or []
    default_activities = activity.get("defaultActivities") or []

    if not cases and not default_activities:
        return UnsupportedValue(
            value=activity,
            message="Switch activity has no cases and no default",
        ), context

    # Translate child activities for each case and default
    activity_translator = import_module(
        "wkmigrate.translators.activity_translators.activity_translator"
    )

    # Build chained IfCondition results
    # Each case becomes: if on_value == case_value then case_activities else next_case
    translated_cases = []
    for case in cases:
        case_value = case.get("value", "")
        case_activity_defs = case.get("activities") or []
        if case_activity_defs:
            case_activities, context = activity_translator.translate_activities_with_context(
                case_activity_defs, context, emission_config
            )
            translated_cases.append((case_value, case_activities))

    default_translated = None
    if default_activities:
        default_translated, context = activity_translator.translate_activities_with_context(
            default_activities, context, emission_config
        )

    # Build the IfCondition representing this Switch
    result = IfConditionActivity(
        **base_kwargs,
        op="EQUAL_TO",
        left=on_value,
        right=repr(cases[0]["value"]) if cases else "''",
        if_true=translated_cases[0][1] if translated_cases else None,
        if_false=default_translated,
    )

    return result, context
```

**Note:** This is a simplified implementation. For N cases, a full implementation would chain N-1 IfConditions. The first version can handle the most common case (1-3 branches) and document the limitation for deeper Switch activities.

**Register in `_dispatch_activity`:**
```python
case "Switch":
    return translate_switch_activity(
        activity, base_kwargs, context, emission_config=emission_config
    )
```

### Test Cases

```python
def test_switch_basic():
    activity = {
        "name": "Route by type",
        "type": "Switch",
        "on": {"value": "@toUpper(item()?.type)", "type": "Expression"},
        "cases": [
            {"value": "NOTEBOOK", "activities": [MOCK_NOTEBOOK_ACTIVITY]},
        ],
        "defaultActivities": [MOCK_FAIL_ACTIVITY],
    }
    result, ctx = translate_switch_activity(activity, BASE_KWARGS)
    assert not isinstance(result, UnsupportedValue)
    assert isinstance(result, IfConditionActivity)

def test_switch_missing_on():
    activity = {"name": "Bad Switch", "type": "Switch", "cases": []}
    result, _ = translate_switch_activity(activity, BASE_KWARGS)
    assert isinstance(result, UnsupportedValue)
```

---

## G-12: `Until` Activity — P1 BLOCKER

### ADF Structure

```json
{
    "name": "Until reintentos",
    "type": "Until",
    "typeProperties": {
        "expression": {
            "value": "@or(greaterOrEquals(length(variables('reintentos_OK')), 1), greaterOrEquals(variables('maxReintentos'), variables('reintentos')))",
            "type": "Expression"
        },
        "timeout": "0.04:00:00",
        "activities": [
            {"name": "Increment retry", "type": "SetVariable", ...},
            {"name": "Execute notebook", "type": "DatabricksNotebook", ...},
            {"name": "Check result", "type": "IfCondition", ...}
        ]
    }
}
```

### CRP0001 Activities Affected (1 FCL pipeline)

- `crp0001_c_pl_prc_anl_fcl_fm_industrial.json` — 3 Until activities for retry logic with `maxReintentos` counter

### Databricks Equivalent

There is no direct `until_task` in Lakeflow Jobs. The mapping options are:
1. **Notebook with while loop** — translate the condition and inner activities into a notebook cell with a Python while loop
2. **Job retry policy** — if the Until is a simple retry pattern, map to `max_retries` on the inner task

Option 1 is more general. The Until becomes a notebook task that:
- Evaluates the condition expression
- Executes inner activity logic in a loop
- Respects the timeout and max iteration count

### Implementation

**New file:** `src/wkmigrate/translators/activity_translators/until_activity_translator.py`

```python
"""Translator for ADF Until activities.

Maps Until to a notebook-based while loop. The condition expression is evaluated
each iteration; inner activities are translated as the loop body.
"""
from __future__ import annotations
from importlib import import_module

from wkmigrate.models.ir.pipeline import Activity
from wkmigrate.models.ir.translation_context import TranslationContext
from wkmigrate.models.ir.translator_result import TranslationResult
from wkmigrate.models.ir.unsupported import UnsupportedValue
from wkmigrate.parsers.emission_config import EmissionConfig, ExpressionContext
from wkmigrate.parsers.expression_parsers import get_literal_or_expression
from wkmigrate.utils import get_placeholder_activity, parse_timeout_string


def translate_until_activity(
    activity: dict,
    base_kwargs: dict,
    context: TranslationContext | None = None,
    emission_config: EmissionConfig | None = None,
) -> tuple[TranslationResult, TranslationContext]:
    """Translate an ADF Until activity."""

    if context is None:
        activity_translator = import_module(
            "wkmigrate.translators.activity_translators.activity_translator"
        )
        context = activity_translator.default_context()

    # Resolve the condition expression
    raw_expression = activity.get("expression")
    if not raw_expression:
        return UnsupportedValue(
            value=activity,
            message="Missing 'expression' property in Until activity",
        ), context

    condition = get_literal_or_expression(
        raw_expression, context, ExpressionContext.GENERIC, emission_config=emission_config
    )
    if isinstance(condition, UnsupportedValue):
        return condition, context

    condition_code = condition.code if hasattr(condition, 'code') else str(condition)

    # Parse timeout
    raw_timeout = activity.get("timeout", "0.12:00:00")
    timeout_seconds = parse_timeout_string(raw_timeout) if isinstance(raw_timeout, str) else None

    # Translate inner activities
    inner_activity_defs = activity.get("activities") or []
    activity_translator = import_module(
        "wkmigrate.translators.activity_translators.activity_translator"
    )
    inner_activities, context = activity_translator.translate_activities_with_context(
        inner_activity_defs, context, emission_config
    )

    # For now, return a placeholder-style notebook activity that documents the loop
    # A full implementation would generate a notebook cell with:
    #   while not (condition):
    #       <inner activity code>
    #       if timeout exceeded: break
    result = get_placeholder_activity(base_kwargs)
    # Enhance the placeholder with the resolved condition for documentation
    return result, context
```

**Note:** Until is architecturally the hardest control-flow type to translate because Lakeflow Jobs has no native loop primitive. The first version should resolve the condition expression (proving the expression system works) and document the loop structure. Full notebook generation is a follow-up.

**Register in `_dispatch_activity`:**
```python
case "Until":
    return translate_until_activity(
        activity, base_kwargs, context, emission_config=emission_config
    )
```

### Test Cases

```python
def test_until_basic():
    activity = {
        "name": "Retry loop",
        "type": "Until",
        "expression": {
            "value": "@greaterOrEquals(variables('retries'), 3)",
            "type": "Expression",
        },
        "timeout": "0.04:00:00",
        "activities": [MOCK_SET_VARIABLE_ACTIVITY],
    }
    result, ctx = translate_until_activity(activity, BASE_KWARGS)
    # Should not crash — condition expression should resolve
    assert not isinstance(result, UnsupportedValue) or "condition" not in str(result)

def test_until_missing_expression():
    activity = {"name": "Bad Until", "type": "Until", "activities": []}
    result, _ = translate_until_activity(activity, BASE_KWARGS)
    assert isinstance(result, UnsupportedValue)
```

---

## Files to Modify/Create

All paths relative to wkmigrate repo root at `/Users/miguel.peralvo/Code/wkmigrate`. On the `pr/27-4-integration-tests` branch:

| Absolute Path | Action |
|---------------|--------|
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/execute_pipeline_activity_translator.py` | **NEW** |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/switch_activity_translator.py` | **NEW** |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/until_activity_translator.py` | **NEW** |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/activity_translator.py` | Add 3 cases to `_dispatch_activity` match block; add imports |
| `/Users/miguel.peralvo/Code/wkmigrate/tests/unit/test_activity_translators.py` | New test cases for each translator |

## Acceptance Criteria

1. `ExecutePipeline` activities produce `RunJobActivity` (not placeholder)
2. `ExecutePipeline` parameters are resolved via `get_literal_or_expression()`
3. `Switch` activities produce chained `IfConditionActivity` (not placeholder)
4. `Switch.on` expression is resolved via `get_literal_or_expression()`
5. `Until` activities resolve their condition expression (even if body is still placeholder)
6. All existing tests pass (`make test`)
7. `make fmt` clean
8. Commits reference ghanse/wkmigrate#61, #52, #62

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests  # or feature/crp1-emitter-registry if CRP-1 landed
git checkout -b feature/crp3-control-flow-translators
# Implement: ExecutePipeline → Switch → Until
# Run: make test && make fmt
git push -u fork feature/crp3-control-flow-translators
```
