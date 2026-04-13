# CRP-9: Dependency Parser Fix (W-26)

> Self-contained specification for /wkmigrate-autodev. Fixes a P1 bug in the activity dependency parser that blocks notebook preparation for 15/36 CRP0001 pipelines (41.7%).

## Background

The V4 deep validation ran end-to-end notebook generation on all 36 CRP0001 pipelines. While `translate_pipeline()` succeeds for all 36, `prepare_workflow()` crashes on 15 pipelines with `AttributeError: 'UnsupportedValue' object has no attribute 'task_key'`. Root cause: the dependency parser incorrectly rejects valid `Succeeded` dependency conditions for activities inside IfCondition branches.

## What is CRP0001?

36 real ADF pipelines from Repsol. The affected pipelines include BFC processing (`crp0001_c_pl_prc_edw_bfcdt_process_data`), analytics (`crp0001_c_pl_prc_anl_persist_global`), and operational logging (`lakeh_a_pl_operational_log`). All use IfCondition activities with multiple child activities that depend on each other via standard `Succeeded` conditions.

## Branch Target

`pr/27-4-integration-tests` (or child branch). Depends on CRP-1 through CRP-6 already landed.

---

## W-26: `is_conditional_task` Flag Propagation Bug -- P1

### Root Cause

**Two files, two sub-bugs:**

#### Sub-bug A: Incorrect flag propagation in IfCondition translator

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/if_condition_activity_translator.py`, lines 162-168.

```python
def _translate_child_activities(child_activities, parent_task_name, parent_task_outcome, context):
    activity_translator = import_module(...)
    visit_activity = activity_translator.visit_activity
    parent_dependency = {"activity": parent_task_name, "outcome": parent_task_outcome}

    translated = []
    for activity in child_activities:
        _activity = activity.copy()
        _activity["depends_on"] = [*(activity.get("depends_on") or []), parent_dependency]
        result, context = visit_activity(_activity, True, context)   # <-- True for ALL deps
    ...
```

The `True` passed to `visit_activity()` (the `is_conditional_task` parameter) propagates to `_get_base_properties()` and then to `_parse_dependencies()`, causing **ALL** dependencies of the child activity to be parsed with conditional rules -- including the original sibling dependencies that use `Succeeded`.

#### Sub-bug B: `_parse_dependency()` logic

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/activity_translator.py`, lines 534-544.

```python
def _parse_dependency(dependency, is_conditional_task=False):
    conditions = dependency.get("dependency_conditions", [])
    if len(conditions) > 1:
        return UnsupportedValue(...)

    if is_conditional_task:
        supported_conditions = ["TRUE", "FALSE"]         # <-- only TRUE/FALSE
        outcome = dependency.get("outcome")
    else:
        supported_conditions = ["SUCCEEDED"]
        outcome = None

    if any(condition.upper() not in supported_conditions for condition in conditions):
        return UnsupportedValue(...)                     # <-- rejects "Succeeded"
```

When `is_conditional_task=True`, the function only allows `TRUE` and `FALSE` conditions. But the **injected parent dependency** (line 162) has an `outcome` field and no `dependency_conditions` -- it's the **original sibling dependencies** (from the ADF JSON) that have `dependency_conditions: ["Succeeded"]`. These are rejected because the function treats ALL dependencies the same when `is_conditional_task=True`.

#### Sub-bug C: Preparer crash on UnsupportedValue

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/preparers/utils.py`, lines 57-68.

```python
def get_base_task(activity):
    depends_on = None
    if activity.depends_on:
        depends_on = [
            parse_mapping({
                "task_key": dep.task_key,     # <-- crashes here
                "outcome": dep.outcome,
            })
            for dep in activity.depends_on     # dep is UnsupportedValue, not Dependency
        ]
```

When `_parse_dependency()` returns `UnsupportedValue` objects in the `depends_on` list, `get_base_task()` tries to access `.task_key` on them, which doesn't exist. This crashes with `AttributeError: 'UnsupportedValue' object has no attribute 'task_key'`.

### CRP0001 Pipelines Blocked (15 pipelines, 56 unsupported dependencies)

| Pipeline | Unsupported Dependencies |
|----------|------------------------:|
| `crp0001_c_pl_prc_edw_bfcdt_process_data` | 8 |
| `crp0001_c_pl_prc_edw_bfcdt_process_data_AMR` | 8 |
| `crp0001_c_pl_prc_anl_persist_global` | 6 |
| `crp0001_c_pl_prc_anl_persist_global_AMR` | 6 |
| `lakeh_a_pl_operational_log` | 4 |
| `lakeh_a_pl_operational_log_aria` | 4 |
| + 9 more pipelines | ~20 |

**Example ADF structure that triggers the bug:**

```json
{
  "name": "Pipeline",
  "activities": [
    {
      "name": "Check_Status",
      "type": "IfCondition",
      "expression": { "value": "@equals(1, 1)" },
      "ifTrueActivities": [
        {
          "name": "Step1_Notebook",
          "type": "DatabricksNotebook",
          "dependsOn": []
        },
        {
          "name": "Step2_Notebook",
          "type": "DatabricksNotebook",
          "dependsOn": [
            {
              "activity": "Step1_Notebook",
              "dependencyConditions": ["Succeeded"]
            }
          ]
        }
      ]
    }
  ]
}
```

After `_translate_child_activities()` processes `Step2_Notebook`:
- Its `depends_on` becomes: `[{"activity": "Step1_Notebook", "dependencyConditions": ["Succeeded"]}, {"activity": "Check_Status", "outcome": "true"}]`
- `visit_activity(step2, True, context)` is called
- `_parse_dependencies([...], is_conditional_task=True)` is called
- The **Step1_Notebook sibling dep** has `dependency_conditions: ["Succeeded"]` → REJECTED (only TRUE/FALSE allowed)
- The **Check_Status parent dep** has `outcome: "true"`, no `dependency_conditions` → ACCEPTED

### Fix

**The core insight:** `is_conditional_task` should only affect dependencies that have an `outcome` field (i.e., the injected parent dependency). Sibling dependencies with `dependency_conditions` should always use the standard `SUCCEEDED` logic.

#### Fix A: Update `_parse_dependency()` (preferred)

**File:** `activity_translator.py`, lines 530-550.

Replace the current logic with per-dependency type detection:

```python
def _parse_dependency(dependency: dict, is_conditional_task: bool = False) -> Dependency | UnsupportedValue:
    """
    Parses an individual dependency from a dictionary.

    When ``is_conditional_task`` is True, dependencies fall into two categories:
    1. **Parent dependencies** — have an ``outcome`` field (injected by IfCondition
       translator). These use TRUE/FALSE as valid conditions.
    2. **Sibling dependencies** — have ``dependency_conditions`` (from ADF JSON).
       These use the standard SUCCEEDED condition regardless of the parent flag.
    """
    conditions = dependency.get("dependency_conditions", [])
    outcome = dependency.get("outcome")

    if len(conditions) > 1:
        # Future: map ["Succeeded", "Failed"] → ALL_DONE
        return UnsupportedValue(
            value=dependency,
            message="Dependencies with multiple conditions are not supported.",
        )

    if outcome is not None:
        # Parent dependency injected by IfCondition/ForEach translator
        # outcome is "true"/"false" — no dependency_conditions to check
        task_key = dependency.get("activity")
        if not task_key:
            return UnsupportedValue(
                value=dependency,
                message="Missing value 'activity' for task dependency",
            )
        return Dependency(task_key=task_key, outcome=outcome)

    # Sibling dependency — standard ADF dependency with conditions
    supported_conditions = ["SUCCEEDED"]
    if any(condition.upper() not in supported_conditions for condition in conditions):
        return UnsupportedValue(
            value=dependency,
            message="Dependencies with conditions other than 'Succeeded' are not supported.",
        )

    task_key = dependency.get("activity")
    if not task_key:
        return UnsupportedValue(
            value=dependency,
            message="Missing value 'activity' for task dependency",
        )
    return Dependency(task_key=task_key, outcome=None)
```

**Key change:** Instead of branching on `is_conditional_task`, branch on whether the dependency has an `outcome` field. This naturally separates parent deps (injected with `outcome`) from sibling deps (from ADF JSON with `dependency_conditions`).

#### Fix B: Defensive handling in `get_base_task()` (safety net)

**File:** `preparers/utils.py`, lines 57-68.

Even with Fix A, add a safety net that skips `UnsupportedValue` objects:

```python
def get_base_task(activity: Activity) -> dict[str, Any]:
    depends_on = None
    if activity.depends_on:
        depends_on = [
            parse_mapping(
                {
                    "task_key": dep.task_key,
                    "outcome": dep.outcome,
                }
            )
            for dep in activity.depends_on
            if not isinstance(dep, UnsupportedValue)   # <-- skip unsupported
        ]
        if not depends_on:
            depends_on = None
    # ... rest unchanged
```

Add the import at the top of `utils.py`:
```python
from wkmigrate.models.ir.unsupported import UnsupportedValue
```

---

## Bonus: Support ADF `Completed` and `Failed` Dependency Conditions (P2)

### Root Cause

ADF supports 4 dependency conditions: `Succeeded`, `Failed`, `Completed` (run regardless), `Skipped`. Currently only `Succeeded` is supported. CRP0001 uses `Completed` (12 occurrences) and `Failed` (4 occurrences) in operational logging pipelines.

### Databricks Mapping

| ADF Condition | Meaning | Databricks Equivalent |
|---------------|---------|----------------------|
| `Succeeded` | Run if upstream succeeded | `SUCCEEDED` (default) |
| `Failed` | Run if upstream failed | `ALL_FAILED` |
| `Completed` | Run regardless of outcome | `ALL_DONE` |
| `Skipped` | Run if upstream was skipped | No direct equivalent |

### Implementation (Optional Enhancement)

Extend the supported conditions in the sibling-dependency branch of `_parse_dependency()`:

```python
_ADF_TO_DATABRICKS_CONDITION: dict[str, str | None] = {
    "SUCCEEDED": None,  # Default — no outcome needed
    "FAILED": "FAILED",
    "COMPLETED": "ALL_DONE",
}

# In the sibling branch:
if conditions:
    condition = conditions[0].upper()
    databricks_outcome = _ADF_TO_DATABRICKS_CONDITION.get(condition)
    if databricks_outcome is None and condition != "SUCCEEDED":
        return UnsupportedValue(
            value=dependency,
            message=f"Dependency condition '{conditions[0]}' is not supported.",
        )
    outcome = databricks_outcome  # None for Succeeded, "FAILED" or "ALL_DONE" otherwise
```

**This is optional/P2** — only needed if Repsol's operational logging pipelines need the `Completed`/`Failed` patterns working. The primary fix (W-26) handles the `Succeeded` case which blocks 15 pipelines.

---

## Files to Modify

| # | File | Action | Fix |
|---|------|--------|-----|
| 1 | `src/wkmigrate/translators/activity_translators/activity_translator.py` | **MODIFY** | W-26A: Rewrite `_parse_dependency()` to branch on `outcome` presence instead of `is_conditional_task` |
| 2 | `src/wkmigrate/preparers/utils.py` | **MODIFY** | W-26B: Add `UnsupportedValue` guard in `get_base_task()` |

**No new files needed.**

## Test Strategy

### Unit Tests

**W-26A — Sibling deps inside IfCondition:**
```python
from wkmigrate.translators.activity_translators.activity_translator import _parse_dependency
from wkmigrate.models.ir.pipeline import Dependency
from wkmigrate.models.ir.unsupported import UnsupportedValue

# Sibling dependency with Succeeded should work even when is_conditional_task=True
result = _parse_dependency(
    {"activity": "Step1", "dependency_conditions": ["Succeeded"]},
    is_conditional_task=True,
)
assert isinstance(result, Dependency)
assert result.task_key == "Step1"
assert result.outcome is None

# Parent dependency with outcome should work
result = _parse_dependency(
    {"activity": "IfCheck", "outcome": "true"},
    is_conditional_task=True,
)
assert isinstance(result, Dependency)
assert result.task_key == "IfCheck"
assert result.outcome == "true"

# Non-conditional task with Succeeded should still work (regression)
result = _parse_dependency(
    {"activity": "Upstream", "dependency_conditions": ["Succeeded"]},
    is_conditional_task=False,
)
assert isinstance(result, Dependency)
assert result.task_key == "Upstream"
```

**W-26B — Preparer safety net:**
```python
from wkmigrate.preparers.utils import get_base_task
from wkmigrate.models.ir.pipeline import Activity, Dependency
from wkmigrate.models.ir.unsupported import UnsupportedValue

# Activity with mixed Dependency + UnsupportedValue deps should not crash
activity = Activity(
    name="test",
    task_key="test",
    depends_on=[
        Dependency(task_key="good_dep", outcome=None),
        UnsupportedValue(value={}, message="bad dep"),
    ],
)
result = get_base_task(activity)
# Should succeed with only the good dependency
assert len(result["depends_on"]) == 1
assert result["depends_on"][0]["task_key"] == "good_dep"
```

### Integration Tests

Run notebook generation on the 15 previously-blocked CRP0001 pipelines:
```python
import json
from wkmigrate.translators.pipeline_translators.pipeline_translator import translate_pipeline
from wkmigrate.preparers import prepare_workflow

# These 15 pipelines should now prepare successfully
for pipeline_file in BLOCKED_PIPELINES:
    with open(pipeline_file) as f:
        adf_json = json.load(f)
    pipeline_ir = translate_pipeline(adf_json)
    workflow = prepare_workflow(pipeline_ir)  # Should not crash
    assert workflow is not None
```

## Implementation Order

1. **W-26A** (P1) — Rewrite `_parse_dependency()`. This is the core fix.
2. **W-26B** (P1) — Add `UnsupportedValue` guard in `get_base_task()`. Safety net.
3. **Bonus** (P2) — Optional: Support `Completed`/`Failed` conditions.

## Expected Impact

| Metric | Current (V4) | After CRP-9 |
|--------|-------------|-------------|
| CRP0001 notebook preparation | 21/36 (58.3%) | **36/36 (100%)** |
| Blocked pipelines | 15 | **0** |
| Unsupported dependency warnings | 56 | **~4** (only multi-condition deps remain) |
| Notebook syntax validity | 100% | 100% (regression check) |

## Workflow Notes

- **Base branch:** `pr/27-4-integration-tests`
- **Feature branch:** `feature/crp9-dependency-parser-fix`
- **PR target:** `pr/27-4-integration-tests` at `MiguelPeralvo/wkmigrate`
- **Build system:** `uv` via Makefile -- `make test` (unit), `make fmt` (lint)
- **Risk:** Low. The fix narrows the scope of `is_conditional_task` rather than expanding it. Existing tests for non-conditional dependencies should continue to pass.
- **Critical regression check:** After the fix, re-run the V4 notebook validator on all 116 pipelines (36 real + 80 synthetic) to confirm:
  1. All 36 CRP0001 pipelines prepare successfully
  2. All 80 synthetic pipelines still prepare successfully
  3. No new `UnsupportedValue` objects in dependency lists
