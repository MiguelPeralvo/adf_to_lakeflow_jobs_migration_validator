# CRP-6: Remaining Expression Gaps (G-19 through G-24)

> Self-contained specification for /wkmigrate-autodev. Covers 6 expression-level gaps discovered in the V2 post-fix re-validation report. Closes the last 33 real failures across the CRP0001 corpus.

## Background

After CRP-1 through CRP-5 resolved the original 18 gaps (G-1 through G-18), the V2 re-validation report tested 2,842 expressions across 36 real CRP0001 pipelines + 80 synthetic pipelines. Result: **97.1% success** (2,759/2,842). Of the 83 failures, 50 are false positives (bare identifiers, dataset names). The remaining **33 are real gaps** across 6 new categories (G-19 through G-24).

## What is CRP0001?

36 real ADF pipelines from Repsol covering BFC (batch forecasting), CMD (command execution), FCL (industrial forecasting), Arquetipo (orchestration framework), and operational logging groups.

## Branch Target

`pr/27-4-integration-tests` (or child branch). Depends on CRP-1 through CRP-5 already landed.

---

## G-19: `uriComponent()` / `uriComponentToString()` — P1

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_functions.py`

Neither `uriComponent` nor `uriComponentToString` are registered in `FUNCTION_REGISTRY` (lines 332-393).

### CRP0001 Expressions Blocked (2 pipelines, 8 expressions)

- `lakeh_a_pl_operational_log.json` — URL-encodes `pipeline().parameters.message` for operational logging payloads
- `lakeh_a_pl_operational_log_aria.json` — same pattern for ARIA telemetry

**Example:**
```
@if(empty(pipeline().parameters.message), '',
  string(replace(replace(replace(uriComponentToString(
    replace(replace(replace(uriComponent(pipeline().parameters.message), '%0D', '%20'), '%0A', '%20'), '%0D%0A', '%20')
  ), '%20', ' '), ...)))
```

### Databricks Equivalent

ADF `uriComponent(s)` = Python `urllib.parse.quote(s, safe='')` (percent-encodes everything).
ADF `uriComponentToString(s)` = Python `urllib.parse.unquote(s)` (decodes percent-encoded).

### Implementation

Add two emitter functions + register them:

```python
def _emit_uri_component(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("uriComponent", args, 1, 1):
        return error
    return f"urllib.parse.quote(str({args[0]}), safe='')"


def _emit_uri_component_to_string(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("uriComponentToString", args, 1, 1):
        return error
    return f"urllib.parse.unquote(str({args[0]}))"
```

Register in `FUNCTION_REGISTRY`:
```python
"uricomponent": _emit_uri_component,
"uricomponenttostring": _emit_uri_component_to_string,
```

**Note:** `urllib.parse` is a stdlib module. The generated notebook may need `import urllib.parse` in the preamble. Check if the preamble generator already includes it, or whether a `_wkmigrate_` helper wrapper is preferred for consistency.

---

## G-20: `char(N)` Function — P2

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_functions.py`

`char` is not registered in `FUNCTION_REGISTRY`.

### CRP0001 Expressions Blocked (synthetic only, 2 expressions)

No real CRP0001 pipelines use `char()`. Found in 1 synthetic pipeline only.

### Databricks Equivalent

ADF `char(N)` = Python `chr(N)` (converts integer → character).

### Implementation

```python
def _emit_char(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("char", args, 1, 1):
        return error
    return f"chr(int({args[0]}))"
```

Register: `"char": _emit_char,`

---

## G-21: `runOutPut` Case Sensitivity — P0 BLOCKER

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, line 32 and 286.

```python
_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES: set[str] = {"firstRow", "value", "runOutput", "pipelineReturnValue"}
```

At line 286:
```python
output_type = properties[1]
if output_type not in _SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES:  # CASE-SENSITIVE
```

CRP0001 BFC pipelines use `runOutPut` (capital P) in the JSON. The case-sensitive check rejects it.

### CRP0001 Expressions Blocked (2 pipelines, 4 expressions)

- `crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal.json`
- `crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal_AMR.json`

### Fix

Case-normalize the lookup at line 286:

```python
output_type = properties[1]
output_type_lower = output_type.lower()
supported_lower = {t.lower() for t in _SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES}
if output_type_lower not in supported_lower:
    return UnsupportedValue(...)
```

**Alternative (simpler):** Add a lower-cased lookup set:

```python
_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES_LOWER: set[str] = {t.lower() for t in _SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES}
```

And change line 286 to:
```python
if output_type.lower() not in _SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES_LOWER:
```

Keep the original set for generating correct Python output (use `output_type.lower()` to find the canonical casing, or just use `output_type` as-is since it becomes a dict key accessor).

---

## G-22: `activity().output.runPageUrl` — P1

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, line 32.

`runPageUrl` is not in `_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES`. When encountered, line 286 returns `UnsupportedValue`.

### CRP0001 Expressions Blocked (3 pipelines, 14 expressions)

- `lakeh_a_pl_arquetipo_sendmail_internal.json` — 2 instances
- `lakeh_a_pl_arquetipo_switch_internal.json` — 12 instances
- Used in send-mail activities to embed notebook run URLs

**Example:**
```
@activity('lakeh_custom_notebook').output.runPageUrl
```

### Databricks Equivalent

`runPageUrl` is the URL of the Databricks notebook run. In Lakeflow Jobs:
```python
dbutils.jobs.taskValues.get(taskKey='lakeh_custom_notebook', key='result')['runPageUrl']
```

The notebook can set this via `dbutils.notebook.getContext().tags().get('browserHostName', '')` + run ID construction. But at the translation level, it's just another output property.

### Fix

Add `"runPageUrl"` to `_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES`:

```python
_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES: set[str] = {
    "firstRow", "value", "runOutput", "pipelineReturnValue", "runPageUrl"
}
```

---

## G-23: Deep Property Chains After `activity().output` — P2

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, lines 285-290.

The validation at line 286 checks `properties[1]` against `_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES` before allowing any further property traversal. Expressions like `activity('X').output.tasks[0].cluster_instance.cluster_id` fail because `"tasks"` is not in the supported set.

Once an output type IS supported, deep chains work fine (lines 293-307 handle arbitrary depth). The issue is the whitelist gate at `properties[1]`.

### CRP0001 Expressions Blocked (2 pipelines, 4 expressions)

- `lakeh_a_pl_arquetipo_grant_permission.json` — deep chain on task output
- 2 synthetic pipelines

**Example:**
```
@activity('X').output.tasks[0].cluster_instance.cluster_id
```

### Fix Options

**Option A (conservative):** Add known patterns to the supported set:
```python
_SUPPORTED_ACTIVITY_OUTPUT_REFERENCE_TYPES: set[str] = {
    "firstRow", "value", "runOutput", "pipelineReturnValue", "runPageUrl", "tasks"
}
```

**Option B (open-ended):** Remove the whitelist gate entirely and let any `output.X` through:
```python
# Replace lines 285-290 with:
output_type = properties[1]
# All output types are valid — just accessor chains on task result
base = f"dbutils.jobs.taskValues.get(taskKey={task_key!r}, key='result')"
```

**Recommendation:** Option B. The whitelist was a safety measure when only a few output types were known. Now that we've validated against 36 real pipelines, any unknown output type should still translate to a dict accessor on the task result. Worst case: a runtime KeyError, which is more useful than a translation-time rejection.

However, if the whitelist serves as documentation of supported patterns (and ghanse prefers explicit support), Option A is safer for review.

---

## G-24: `substring(s, start)` 2-Argument Form — P2

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_functions.py`, lines 41-44.

```python
def _emit_substring(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("substring", args, 3, 3):
        return error
    return f"str({args[0]})[{args[1]}:{args[1]} + {args[2]}]"
```

Arity is `(3, 3)` — requires exactly 3 arguments. ADF allows 2-argument form `substring(s, start)` meaning "from start to end of string."

### CRP0001 Expressions Blocked (1 pipeline, 1 expression)

- `lakeh_a_pl_arquetipo.json`

### Fix

Change arity to `(2, 3)` and handle 2-arg case:

```python
def _emit_substring(args: list[str]) -> str | UnsupportedValue:
    if error := _require_arity("substring", args, 2, 3):
        return error
    if len(args) == 2:
        return f"str({args[0]})[{args[1]}:]"
    return f"str({args[0]})[{args[1]}:{args[1]} + {args[2]}]"
```

---

## Files to Modify

| # | File | Action | Gaps |
|---|------|--------|------|
| 1 | `src/wkmigrate/parsers/expression_functions.py` | **MODIFY** | G-19 (uriComponent), G-20 (char), G-24 (substring arity) |
| 2 | `src/wkmigrate/parsers/expression_emitter.py` | **MODIFY** | G-21 (case-insensitive), G-22 (runPageUrl), G-23 (open-ended chains) |

**No new files needed.** All changes are additions to existing registries and minor logic adjustments.

## Test Strategy

### Unit Tests (expression-level)

Add fixtures to existing test JSON files or create new test cases in the expression test suite:

**G-19:** `uriComponent('hello world')` → `urllib.parse.quote(str('hello world'), safe='')`, `uriComponentToString('%20')` → `urllib.parse.unquote(str('%20'))`

**G-20:** `char(65)` → `chr(int(65))`

**G-21:** `activity('X').output.runOutPut` (capital P) → should resolve same as `runOutput`

**G-22:** `activity('X').output.runPageUrl` → `dbutils.jobs.taskValues.get(taskKey='X', key='result')['runPageUrl']`

**G-23:** `activity('X').output.tasks[0].prop` → `dbutils.jobs.taskValues.get(taskKey='X', key='result')['tasks'][0]['prop']`

**G-24:** `substring('hello', 2)` → `str('hello')[2:]`

### Integration Tests

Update `tests/integration/test_crp0001_integration.py` with additional expressions exercising G-19 through G-24 (if fixture pipelines contain these patterns).

## Implementation Order

1. **G-21** (P0) — case-insensitive output type lookup. Highest severity.
2. **G-22** (P1) — add `runPageUrl` to supported types. Quick one-liner.
3. **G-19** (P1) — register `uriComponent` / `uriComponentToString`. 2 new emitters.
4. **G-23** (P2) — open up output type whitelist. Architecture decision (Option A vs B).
5. **G-24** (P2) — substring 2-arg. Arity change + branch.
6. **G-20** (P2) — char function. Simple one-liner.

## Expected Impact

| Metric | Current (V2) | After CRP-6 |
|--------|-------------|-------------|
| Real gap failures | 33 | **0** |
| Expression success rate | 97.1% | **~98.8%** (adjusted for false positives: **100%**) |
| Remaining failures | 83 | ~50 (all false positives) |

## Workflow Notes

- **Base branch:** `pr/27-4-integration-tests`
- **Feature branch:** `feature/crp6-remaining-gaps` (or split per severity if ghanse prefers)
- **PR target:** `pr/27-4-integration-tests` at `MiguelPeralvo/wkmigrate`
- **Build system:** `uv` via Makefile — `make test` (unit), `make fmt` (lint)
