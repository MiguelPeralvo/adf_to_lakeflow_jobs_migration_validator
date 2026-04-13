# CRP-1: Expression Emitter + Function Registry Gaps

> Self-contained specification for /wkmigrate-autodev. Covers 9 gaps (G-2 through G-10) in the expression emitter and function registry that block CRP0001 pipeline translation.

## Background: What is wkmigrate?

wkmigrate (`ghanse/wkmigrate`, fork at `MiguelPeralvo/wkmigrate`) is a Python library that converts Azure Data Factory (ADF) pipeline JSON into Databricks Lakeflow Jobs. Its expression system:

- **Tokenizer** (`parsers/expression_tokenizer.py`): ADF expression string → token list
- **Parser** (`parsers/expression_parser.py`): token list → typed AST
- **Emitter** (`parsers/expression_emitter.py`): AST → Python code string
- **Function registry** (`parsers/expression_functions.py`): maps ADF function names → Python emitter functions

The critical shared utility is `get_literal_or_expression()` which all activity translators call to resolve expression-typed properties.

## What is CRP0001?

CRP0001 is a real-world set of 36 ADF pipeline JSON files from Repsol (energy company). These pipelines use complex expressions across BFC (batch forecasting), CMD (command execution), FCL (industrial forecasting), Arquetipo (orchestration framework), and operational logging groups.

## Branch Target

All changes target `pr/27-4-integration-tests` (or a child branch). This branch has the complete expression system already in place.

---

## G-2: `pipeline().globalParameters.X` — P0 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, method `_emit_pipeline_property_access` (lines ~205-230)

Current code handles two cases:
1. `len(properties) == 1` → lookup in `_PIPELINE_VARS` (only `Pipeline`, `RunId`, `TriggerTime`, `GroupId`)
2. `properties[0] == "parameters" and len(properties) == 2` → `dbutils.widgets.get(properties[1])`

When `properties[0] == "globalParameters"`, neither case matches. Falls to:
```python
return UnsupportedValue(
    value=".".join(properties),
    message=f"Unsupported pipeline property access '@pipeline().{'.'.join(properties)}'",
)
```

### CRP0001 Expressions Blocked (ALL 36 pipelines)

- `pipeline().globalParameters.env_variable` — library JAR paths in every pipeline
- `pipeline().globalParameters.libFileName` — library JAR paths
- `pipeline().globalParameters.deequLibFileName` — library JAR paths
- `pipeline().globalParameters.clusterVersion` — linked service params
- `pipeline().globalParameters.DatabricksUCUrl` — WebActivity URLs
- `pipeline().globalParameters.GroupLogs` — WebActivity body interpolation via `@{pipeline().globalParameters.GroupLogs}`

### Fix

Add a third case in `_emit_pipeline_property_access`:

```python
def _emit_pipeline_property_access(self, root: FunctionCall, properties: list[str]) -> str | UnsupportedValue:
    # ... existing args check ...

    if len(properties) == 1:
        property_name = properties[0]
        if property_name in _PIPELINE_VARS:
            return _PIPELINE_VARS[property_name]
        return UnsupportedValue(...)

    if properties[0] == "parameters" and len(properties) == 2:
        return f"dbutils.widgets.get({properties[1]!r})"

    # NEW: globalParameters → spark.conf or dbutils.widgets.get
    if properties[0] == "globalParameters" and len(properties) == 2:
        return f"spark.conf.get({('pipeline.globalParam.' + properties[1])!r}, '')"

    return UnsupportedValue(...)
```

**Design choice:** Global parameters don't have a direct Databricks equivalent. `spark.conf.get()` is the most flexible option — users can set them via job parameters, init scripts, or cluster config. The `pipeline.globalParam.` prefix provides a namespace to avoid collisions.

### Test Cases

```python
def test_global_parameters_emit():
    ast = parse_expression("@pipeline().globalParameters.env_variable")
    result = emit(ast)
    assert result == "spark.conf.get('pipeline.globalParam.env_variable', '')"

def test_global_parameters_in_concat():
    ast = parse_expression("@concat('/Volumes/', pipeline().globalParameters.env_variable, '/libs/')")
    result = emit(ast)
    assert "spark.conf.get('pipeline.globalParam.env_variable', '')" in result

def test_global_parameters_string_interpolation():
    ast = parse_expression("@{pipeline().globalParameters.GroupLogs}")
    result = emit(ast)
    assert "spark.conf.get('pipeline.globalParam.GroupLogs', '')" in result
```

---

## G-3: `activity().output.runOutput` — P0 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, line 30

```python
_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES: set[str] = {"firstRow", "value"}
```

`runOutput` is the return value from `DatabricksNotebook` activities (via `dbutils.notebook.exit()`). It is NOT in the supported set.

### CRP0001 Expressions Blocked (8 BFC/CMD/FCL pipelines)

- `activity('Control ejecucion').output.runOutput` — BFC control condition
- `activity('ExisteDatoDelDia').output.runOutput` — CMD second execution check
- `activity('cmd_copy').output.runOutput` — CMD formulas condition
- `activity('cmd_notebook_BW1').output.runOutput` — CMD copy baseParams (x9 instances)
- `activity('Fec_cerrado').output.runOutput` — BFC mail VC condition
- `activity('Busqueda fechaCierre').output.runOutPut` — BFC email body (note: case variation)
- `activity('formulas').output.runOutput` — BFC copiado tablon

### Fix

Add `"runOutput"` to the set:

```python
_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES: set[str] = {"firstRow", "value", "runOutput"}
```

The emitter already generates `dbutils.jobs.taskValues.get(taskKey=X, key='result')['runOutput']` for property chains — adding the string to the set is sufficient.

### Test Cases

```python
def test_activity_run_output():
    ast = parse_expression("@activity('Control ejecucion').output.runOutput")
    result = emit(ast)
    assert result == "dbutils.jobs.taskValues.get(taskKey='Control ejecucion', key='result')['runOutput']"

def test_activity_run_output_in_equals():
    ast = parse_expression("@equals(activity('ExisteDatoDelDia').output.runOutput, 1)")
    result = emit(ast)
    assert "taskValues.get" in result
    assert "['runOutput']" in result
```

---

## G-4: `activity().output.pipelineReturnValue.X` — P0 BLOCKER

### Root Cause

Same as G-3 — `pipelineReturnValue` is not in `_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES`.

`pipelineReturnValue` is how ADF `ExecutePipeline` activities return values from child pipelines.

### CRP0001 Expressions Blocked (4 pipelines)

- `activity('datatsources').output.pipelineReturnValue.str_array`
- `activity('lakeh_a_pl_arquetipo_nested_par_internal').output.pipelineReturnValue.result`
- `activity('internal switch').output.pipelineReturnValue.result`

### Fix

Add `"pipelineReturnValue"` to the set:

```python
_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES: set[str] = {"firstRow", "value", "runOutput", "pipelineReturnValue"}
```

This produces `dbutils.jobs.taskValues.get(taskKey='datatsources', key='result')['pipelineReturnValue']['str_array']` — correct for Lakeflow Jobs where child job return values are stored as task values.

### Test Cases

```python
def test_pipeline_return_value():
    ast = parse_expression("@activity('datatsources').output.pipelineReturnValue.str_array")
    result = emit(ast)
    assert "taskValues.get" in result
    assert "['pipelineReturnValue']" in result
    assert "['str_array']" in result
```

---

## G-5: `activity().error.X` — P1 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, method `_emit_activity_property_access` (line ~255)

```python
if len(properties) < 2 or properties[0] != "output":
    return UnsupportedValue(
        value=".".join(properties),
        message="Unsupported activity reference; expected @activity('X').output.<type>",
    )
```

When properties is `['error', 'message']`, `properties[0]` is `"error"` (not `"output"`), so it rejects immediately.

### CRP0001 Expressions Blocked (3 arquetipo pipelines)

- `activity('internal switch').error.message` — arquetipo error handling
- `activity('internal switch').error.errorCode` — arquetipo error handling
- `activity('lakeh_a_pl_arquetipo_nested_par_internal').error.message`
- `activity('lakeh_a_pl_arquetipo_nested_par_internal').error.errorCode`

### Fix

Add a branch for `properties[0] == "error"` before the existing `output` check:

```python
def _emit_activity_property_access(self, root, properties, index_segments):
    if len(root.args) != 1 or not isinstance(root.args[0], StringLiteral):
        return UnsupportedValue(...)

    task_key = root.args[0].value

    # NEW: Handle error property access
    if len(properties) >= 1 and properties[0] == "error":
        error_property = properties[1] if len(properties) >= 2 else "message"
        return f"dbutils.jobs.taskValues.get(taskKey={task_key!r}, key='error').get({error_property!r}, '')"

    if len(properties) < 2 or properties[0] != "output":
        return UnsupportedValue(...)
    # ... rest unchanged ...
```

**Design note:** In Lakeflow Jobs, failed tasks don't directly expose `.error` properties via `taskValues`. The pragmatic translation assumes the error is stored as a task value by a wrapper pattern. This is a best-effort mapping.

### Test Cases

```python
def test_activity_error_message():
    ast = parse_expression("@activity('internal switch').error.message")
    result = emit(ast)
    assert "taskValues.get" in result
    assert "'error'" in result

def test_activity_error_code():
    ast = parse_expression("@activity('internal switch').error.errorCode")
    result = emit(ast)
    assert "'errorCode'" in result
```

---

## G-6: `activity().output` Without Sub-property — P1 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, line ~255

```python
if len(properties) < 2 or properties[0] != "output":
```

When the expression is `activity('X').output` (properties = `['output']`, length 1), the `len(properties) < 2` check fails. This pattern is used in `contains(activity('X').output, 'runError')` to check if the output dict contains a key.

### CRP0001 Expressions Blocked (2 CMD pipelines)

- `contains(activity('cmd_notebook_BW1').output, 'runError')` — CMD copy baseParams (x9 instances)

### Fix

Handle the bare output case before the `< 2` check:

```python
task_key = root.args[0].value

# NEW: Handle bare .output (no sub-property)
if len(properties) == 1 and properties[0] == "output":
    return f"dbutils.jobs.taskValues.get(taskKey={task_key!r}, key='result')"

# NEW: Handle .error (G-5)
if len(properties) >= 1 and properties[0] == "error":
    # ...

if len(properties) < 2 or properties[0] != "output":
    return UnsupportedValue(...)
```

### Test Cases

```python
def test_activity_output_bare():
    ast = parse_expression("@activity('cmd_notebook_BW1').output")
    result = emit(ast)
    assert result == "dbutils.jobs.taskValues.get(taskKey='cmd_notebook_BW1', key='result')"

def test_contains_activity_output():
    ast = parse_expression("@contains(activity('cmd_notebook_BW1').output, 'runError')")
    result = emit(ast)
    assert "'runError' in str(dbutils.jobs.taskValues.get(" in result
```

---

## G-7: `pipeline().DataFactory` System Variable — P1 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, lines 24-28

```python
_PIPELINE_VARS: dict[str, str] = {
    "Pipeline": "spark.conf.get('spark.databricks.job.parentName', '')",
    "RunId": "dbutils.jobs.getContext().tags().get('runId', '')",
    "TriggerTime": "dbutils.jobs.getContext().tags().get('startTime', '')",
    "GroupId": "dbutils.jobs.getContext().tags().get('multitaskParentRunId', '')",
}
```

`DataFactory` (the ADF factory name) is not present. It's used to distinguish environments.

### CRP0001 Expression Blocked (1 BFC pipeline)

- `equals(pipeline().DataFactory, 'datahub01pdfcrp0001')` — BFC "If Send Mail VC" condition

### Fix

Add to `_PIPELINE_VARS`:

```python
_PIPELINE_VARS: dict[str, str] = {
    "Pipeline": "spark.conf.get('spark.databricks.job.parentName', '')",
    "RunId": "dbutils.jobs.getContext().tags().get('runId', '')",
    "TriggerTime": "dbutils.jobs.getContext().tags().get('startTime', '')",
    "GroupId": "dbutils.jobs.getContext().tags().get('multitaskParentRunId', '')",
    "DataFactory": "spark.conf.get('pipeline.globalParam.DataFactory', '')",
}
```

**Design note:** `DataFactory` is a deployment artifact (factory name), not a runtime value. In Databricks, the equivalent could be the workspace name (`spark.conf.get('spark.databricks.workspaceUrl', '')`), but using `spark.conf` with a configurable key gives users control over the mapping.

### Test Case

```python
def test_pipeline_data_factory():
    ast = parse_expression("@pipeline().DataFactory")
    result = emit(ast)
    assert result == "spark.conf.get('pipeline.globalParam.DataFactory', '')"
```

---

## G-8: `pipeline().TriggeredByPipelineRunId` — P2

### Root Cause

Same as G-7 — not in `_PIPELINE_VARS`.

### CRP0001 Expression Blocked (1 operational log pipeline)

- Variable default value in `lakeh_a_pl_operational_log_start.json` (uid construction):
  `concat('lakeh#$', pipeline().parameters.applicationName, '$', pipeline().parameters.pipelineName, '#', utcnow('yyyy/MM/dd'), '#', pipeline().TriggeredByPipelineRunId)`

### Fix

Add to `_PIPELINE_VARS`:

```python
"TriggeredByPipelineRunId": "dbutils.jobs.getContext().tags().get('multitaskParentRunId', '')",
```

This maps to the same value as `GroupId` — in Lakeflow Jobs, the parent run ID is available via `multitaskParentRunId`.

### Test Case

```python
def test_pipeline_triggered_by_run_id():
    ast = parse_expression("@pipeline().TriggeredByPipelineRunId")
    result = emit(ast)
    assert "multitaskParentRunId" in result
```

---

## G-9: `convertFromUtc` Function Not Registered — P0 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_functions.py`, `FUNCTION_REGISTRY` (lines ~270-310)

The registry contains `"converttimezone"` (mapped to `_emit_convert_time_zone` requiring exactly 3 args) but does NOT contain `"convertfromutc"`. Grep confirms zero matches.

ADF semantics:
- `convertFromUtc(timestamp, targetTimezone, format?)` — converts from UTC to target timezone, optionally formats
- `convertTimeZone(timestamp, sourceTimezone, targetTimezone, format?)` — converts between arbitrary timezones

These are different functions with different arities.

### CRP0001 Expressions Blocked (3 BFC/CMD pipelines)

- `convertFromUtc(utcnow(), 'Romance Standard Time', 'dd/MM/yyyy HH:mm')` — BFC Fecha Inicio
- `convertFromUtc(utcnow(), 'Romance Standard Time', 'HH:mm')` — CMD HoraInicio
- `convertFromUtc(utcnow(), 'Romance Standard Time', 'dd/MM/yyyy')` — BFC FechaInicio

### Fix

Add emitter function and register it:

```python
def _emit_convert_from_utc(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("convertFromUtc", args, 2, 3):
        return error
    if len(args) == 2:
        return f"_wkmigrate_convert_time_zone({args[0]}, 'UTC', {args[1]})"
    return f"_wkmigrate_format_datetime(_wkmigrate_convert_time_zone({args[0]}, 'UTC', {args[1]}), {args[2]})"
```

Register in `FUNCTION_REGISTRY`:
```python
"convertfromutc": _emit_convert_from_utc,
```

Also add to `_DATETIME_HELPER_FUNCTIONS` in `expression_emitter.py`:
```python
_DATETIME_HELPER_FUNCTIONS: set[str] = {
    "utcnow", "formatdatetime", "adddays", "addhours",
    "startofday", "converttimezone", "convertfromutc",  # NEW
}
```

### Test Cases

```python
def test_convert_from_utc_2_args():
    ast = parse_expression("@convertFromUtc(utcnow(), 'Romance Standard Time')")
    result = emit(ast)
    assert "_wkmigrate_convert_time_zone(" in result
    assert "'UTC'" in result
    assert "'Romance Standard Time'" in result

def test_convert_from_utc_3_args():
    ast = parse_expression("@convertFromUtc(utcnow(), 'Romance Standard Time', 'dd/MM/yyyy HH:mm')")
    result = emit(ast)
    assert "_wkmigrate_format_datetime(" in result
    assert "_wkmigrate_convert_time_zone(" in result
```

---

## G-10: `convertTimeZone` Lacks 4th Arg (Format) — P2

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_functions.py`, line ~233

```python
def _emit_convert_time_zone(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("convertTimeZone", args, 3, 3):
        return error
    return f"_wkmigrate_convert_time_zone({args[0]}, {args[1]}, {args[2]})"
```

The arity is enforced as exactly 3. The 4-arg form `convertTimeZone(timestamp, srcTz, dstTz, format)` is rejected.

### CRP0001 Impact

None directly — CRP0001 uses `convertFromUtc` (G-9), not the 4-arg `convertTimeZone`. But worth fixing for completeness since the implementation pattern mirrors G-9.

### Fix

```python
def _emit_convert_time_zone(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("convertTimeZone", args, 3, 4):
        return error
    if len(args) == 3:
        return f"_wkmigrate_convert_time_zone({args[0]}, {args[1]}, {args[2]})"
    return f"_wkmigrate_format_datetime(_wkmigrate_convert_time_zone({args[0]}, {args[1]}, {args[2]}), {args[3]})"
```

### Test Case

```python
def test_convert_time_zone_4_args():
    ast = parse_expression("@convertTimeZone(utcnow(), 'UTC', 'Romance Standard Time', 'dd/MM/yyyy')")
    result = emit(ast)
    assert "_wkmigrate_format_datetime(" in result
```

---

## Files to Modify

All paths are relative to the wkmigrate repo root at `/Users/miguel.peralvo/Code/wkmigrate`. On the `pr/27-4-integration-tests` branch:

| Absolute Path | Changes |
|---------------|---------|
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py` | G-2: add `globalParameters` case in `_emit_pipeline_property_access`; G-3/G-4: add to `_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES`; G-5: add `error` branch in `_emit_activity_property_access`; G-6: handle bare `.output`; G-7/G-8: add to `_PIPELINE_VARS`; G-9: add `convertfromutc` to `_DATETIME_HELPER_FUNCTIONS` |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_functions.py` | G-9: add `_emit_convert_from_utc` + register; G-10: fix `_emit_convert_time_zone` arity |
| `/Users/miguel.peralvo/Code/wkmigrate/tests/unit/test_expression_parsers.py` | New test cases for each gap |

## Acceptance Criteria

1. All G-2 through G-10 expressions emit valid Python (not `UnsupportedValue`)
2. Existing tests pass (`make test`)
3. `make fmt` clean
4. Each gap has at least one unit test using a CRP0001 expression

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests
git checkout -b feature/crp1-emitter-registry
# Implement all 9 gaps
# Run: make test && make fmt
git push -u fork feature/crp1-emitter-registry
# Open PR against pr/27-4-integration-tests
```
