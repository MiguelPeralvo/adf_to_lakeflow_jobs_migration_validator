# wkmigrate Fix Spec: Full Activity Coverage + Issue #73

> Self-contained specification for /wkmigrate-autodev. After issue #27 expression handling is complete (100% on 5 contexts, 95% on if_condition), the next gap is activity type coverage. wkmigrate currently supports 10 activity types; 14 more are requested in open issues.

## Current State

### Supported Activity Types (10)

| ADF Type | Translator | Issue |
|----------|-----------|-------|
| DatabricksNotebook | `notebook_activity_translator.py` | — |
| WebActivity | `web_activity_translator.py` | #4 (closed) |
| IfCondition | `if_condition_activity_translator.py` | — |
| ForEach | `for_each_activity_translator.py` | — |
| SetVariable | `set_variable_activity_translator.py` | #17 (closed) |
| DatabricksSparkPython | `spark_python_activity_translator.py` | — |
| DatabricksSparkJar | `spark_jar_activity_translator.py` | — |
| DatabricksJob | `databricks_job_activity_translator.py` | #5 (closed) |
| Lookup | `lookup_activity_translator.py` | #2 (closed) |
| Copy | `copy_activity_translator.py` | #1 (closed) |

### Missing Activity Types (14 open issues)

| Priority | ADF Type | Issue | Complexity | Databricks Equivalent |
|----------|----------|-------|-----------|----------------------|
| **HIGH** | ExecutePipeline | #61 | Medium | Run Job task (nested job) |
| **HIGH** | Switch | #52 | Medium | Multiple If-Else condition_tasks |
| **HIGH** | Until | #62 | Medium | While-loop in notebook or retry policy |
| **HIGH** | Filter | #65 | Low | Python list comprehension in notebook |
| **MEDIUM** | AppendVariable | #64 | Low | `variable.append(value)` in notebook |
| **MEDIUM** | Wait | #63 | Low | `time.sleep(seconds)` in notebook |
| **MEDIUM** | GetMetadata | #66 | Medium | dbutils.fs.ls / spark.read metadata |
| **MEDIUM** | StoredProcedure | #3 | Medium | spark.sql("EXEC ...") in notebook |
| **MEDIUM** | Delete | #70 | Low | dbutils.fs.rm in notebook |
| **LOW** | Validation | #67 | Low | dbutils.fs.ls + assert in notebook |
| **LOW** | Webhook | #68 | Medium | requests.post in notebook (like WebActivity) |
| **LOW** | SynapseNotebook | #69 | Low | Same as DatabricksNotebook (different runtime) |
| **LOW** | SparkActivities | #51 | Low | Already have SparkPython/SparkJar |
| **LOW** | Copy from SFTP | #57 | Medium | Spark read with SFTP connector |

### Issue #73: Bare parameter in IfCondition

**Problem:** `@pipeline().parameters.enable` (no operator) → UnsupportedValue.
**ADF semantics:** Truthy check (non-empty, non-null, non-false → true branch).
**Fix:** In `_parse_condition_expression`, when the parsed AST is a `PropertyAccess` (not a `FunctionCall`), emit `NOT_EQUAL` with the resolved parameter as left and empty string as right:

```python
# When expression is @pipeline().parameters.X (bare parameter, no function):
if isinstance(parsed, PropertyAccess):
    resolved = emit(parsed, context)
    if not isinstance(resolved, UnsupportedValue):
        return {"op": "NOT_EQUAL", "left": resolved, "right": ""}
```

This maps to Databricks' condition_task: `NOT_EQUAL` with right `""` = true when param is non-empty.

---

## Implementation Plan

### Phase 1: Quick wins (LOW complexity, HIGH frequency)

These are trivial notebook-based translations — one function each:

#### AppendVariable (#64)
```python
# ADF: AppendVariable activity appends to a pipeline variable array
# Databricks: variable.append(value) in a notebook cell
def translate_append_variable_activity(activity, base_kwargs, context=None, emission_config=None):
    variable_name = activity.get("variable_name")
    value = get_literal_or_expression(activity.get("value"), context, emission_config=emission_config)
    # Emit: variables['name'].append(resolved_value)
```

#### Wait (#63)
```python
# ADF: Wait activity pauses for N seconds
# Databricks: time.sleep(seconds) in notebook
def translate_wait_activity(activity, base_kwargs, context=None, emission_config=None):
    wait_time = activity.get("wait_time_in_seconds")
    # Can be literal or expression: get_literal_or_expression
    # Emit: import time; time.sleep(resolved_seconds)
```

#### Filter (#65)
```python
# ADF: Filter activity filters an array by condition
# Databricks: [item for item in array if condition(item)] in notebook
def translate_filter_activity(activity, base_kwargs, context=None, emission_config=None):
    items = get_literal_or_expression(activity.get("items"), context, ...)
    condition = get_literal_or_expression(activity.get("condition"), context, ...)
    # Emit: filtered = [item for item in items if condition]
```

#### Delete (#70)
```python
# ADF: Delete activity removes files/folders
# Databricks: dbutils.fs.rm(path, recurse=True)
def translate_delete_activity(activity, base_kwargs, context=None, emission_config=None):
    # Extract dataset path (may be expression)
    # Emit: dbutils.fs.rm(resolved_path, recurse=True)
```

### Phase 2: Control flow (MEDIUM complexity)

#### ExecutePipeline (#61)
```python
# ADF: Calls another pipeline with parameters
# Databricks: dbutils.notebook.run() or Run Job task
def translate_execute_pipeline_activity(activity, base_kwargs, context=None, emission_config=None):
    pipeline_ref = activity.get("pipeline", {}).get("referenceName")
    parameters = activity.get("parameters", {})
    # Each parameter value may be an expression: get_literal_or_expression for each
    # Emit: RunJobActivity pointing to the referenced pipeline's translated job
```

#### Switch (#52)
```python
# ADF: Switch on an expression value, multiple case branches
# Databricks: Multiple nested condition_tasks (if-elif-else chain)
def translate_switch_activity(activity, base_kwargs, context=None, emission_config=None):
    on_expression = get_literal_or_expression(activity.get("on"), context, ...)
    cases = activity.get("cases", [])
    default = activity.get("default_activities", [])
    # Emit: chain of IfConditionActivity with EQUAL_TO checks for each case value
```

#### Until (#62)
```python
# ADF: Loop until condition is true (max iterations, timeout)
# Databricks: while loop in notebook with retry count
def translate_until_activity(activity, base_kwargs, context=None, emission_config=None):
    expression = get_literal_or_expression(activity.get("expression"), context, ...)
    timeout = activity.get("timeout")
    activities = activity.get("activities", [])
    # Emit: notebook with while loop, condition check, max iterations guard
```

### Phase 3: Issue #73 fix (standalone)

In `if_condition_activity_translator.py`:

```python
def _parse_condition_expression(condition, context):
    ...
    parsed = parse_expression(condition_value)
    if isinstance(parsed, UnsupportedValue):
        return UnsupportedValue(...)

    # NEW: Handle bare property access (e.g., @pipeline().parameters.enable)
    if not isinstance(parsed, FunctionCall):
        # Bare expression — treat as truthy check: NOT_EQUAL to ""
        emitted = emit(parsed, context)
        if isinstance(emitted, UnsupportedValue):
            return UnsupportedValue(...)
        return {"op": "NOT_EQUAL", "left": emitted, "right": ""}

    # Existing function call handling...
    lowered_name = parsed.name.lower()
    ...
```

---

## Priority Order for /wkmigrate-autodev

1. **#73** (bare params in IfCondition) — trivial fix, directly requested by ghanse, closes an issue
2. **#64** (AppendVariable) — trivial, good first issue label
3. **#63** (Wait) — trivial, good first issue label
4. **#65** (Filter) — low complexity, good first issue label
5. **#61** (ExecutePipeline) — medium, high value (common in real pipelines)
6. **#52** (Switch) — medium, enables complex conditional logic
7. **#62** (Until) — medium, enables retry/polling patterns

## Expression Integration

ALL new activity translators should use `get_literal_or_expression()` for their expression-bearing properties from day 1. This is the entire point of #27 — the infrastructure is built, new translators just need to call it.

Pattern for every new translator:
```python
from wkmigrate.parsers.expression_parsers import get_literal_or_expression
from wkmigrate.parsers.emission_config import EmissionConfig, ExpressionContext

def translate_X_activity(activity, base_kwargs, context=None, emission_config=None):
    # Every property that can be an expression:
    value = get_literal_or_expression(
        activity.get("property_name"),
        context,
        ExpressionContext.GENERIC,  # or a specific context if needed
        emission_config=emission_config,
    )
```

## Test Strategy

For each new translator:
1. Test with literal values (backward compat)
2. Test with Expression-typed values (expressions resolve)
3. Test with missing required fields (UnsupportedValue, not crash)
4. Run `make fmt` + `make test`

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests
git checkout -b feature/activity-coverage-phase1
# Do #73 + #64 + #63 + #65 in one PR (all trivial)
# Then feature/activity-coverage-phase2 for #61 + #52 + #62
```

## Meta-KPIs

| ID | Target |
|----|--------|
| GR-1 | 100% test pass rate |
| GR-2 | 0 regressions |
| NEW-1 | 4 new activity types translate (AppendVariable, Wait, Filter, Delete) |
| NEW-2 | #73 bare param IfCondition resolves |
| NEW-3 | All new translators use get_literal_or_expression |
| NEW-4 | lmv adversarial loop discovers new expression patterns in new activity contexts |
