# CRP-10: Support ADF Completed/Failed Dependency Conditions

> Self-contained specification for /wkmigrate-autodev. Adds support for ADF `Completed` and `Failed` dependency conditions, resolving 25 dropped dependencies across 12 CRP0001 pipelines.

## Background

V5 re-validation achieved 100% notebook preparation for all 36 CRP0001 pipelines. However, 25 dependency conditions across 12 pipelines are gracefully dropped as `UnsupportedValue` because `_parse_dependency()` only supports `Succeeded`. The dropped deps don't crash (CRP-9's `get_base_task()` safety net filters them), but the dependency DAG is incomplete.

## What is CRP0001?

36 real ADF pipelines from Repsol. The affected pipelines include operational logging (`lakeh_a_pl_operational_log`), analytics persistence (`crp0001_c_pl_prc_anl_persist_global`), and BFC processing pipelines. These use `Completed` conditions for error-handling activities that must run regardless of upstream success/failure, and `Failed` conditions for failure notification activities.

## Branch Target

`pr/27-4-integration-tests` (or child branch). Depends on CRP-9 (PR #16) already landed at `6f498bd`.

---

## ADF Dependency Condition Semantics

| ADF Condition | Meaning | When Activity Runs |
|---------------|---------|-------------------|
| `Succeeded` | Upstream completed successfully | Only on success (default) |
| `Failed` | Upstream completed with failure | Only on failure |
| `Completed` | Upstream completed (any outcome) | Always after upstream finishes |
| `Skipped` | Upstream was skipped | Only when skipped (not supported) |

## Databricks Lakeflow Jobs Mapping

| ADF Condition | Databricks `outcome` Value | Notes |
|---------------|---------------------------|-------|
| `Succeeded` | `None` (omitted, default) | Standard dependency |
| `Completed` | `"ALL_DONE"` | Run regardless of outcome |
| `Failed` | `"ALL_FAILED"` | Run only on failure |
| `Skipped` | N/A | No direct equivalent (P3, not implemented) |

## Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/translators/activity_translators/activity_translator.py`, lines 550-555.

```python
# Sibling dependency from ADF JSON (dependency_conditions)
supported_conditions = ["SUCCEEDED"]
if any(condition.upper() not in supported_conditions for condition in conditions):
    return UnsupportedValue(
        value=dependency, message="Dependencies with conditions other than 'Succeeded' are not supported."
    )
```

The `supported_conditions` list only contains `"SUCCEEDED"`. Any other condition (including valid `Completed` and `Failed`) is rejected.

## CRP0001 Impact (25 dependencies in 12 pipelines)

| Pipeline | Completed | Failed | Total Dropped |
|----------|-----------|--------|--------------|
| `crp0001_c_pl_prc_anl_cmd_all_paral_ppal` | 9 | 0 | 9 |
| `crp0001_c_pl_prc_anl_persist_global` | 3 | 1 | 4 |
| `crp0001_c_pl_prc_anl_persist_global_AMR` | 3 | 1 | 4 |
| `lakeh_a_pl_operational_log` | 1 | 1 | 2 |
| `lakeh_a_pl_operational_log_aria` | 1 | 1 | 2 |
| + 7 more pipelines | ~0 | ~4 | ~4 |
| **Total** | **~16** | **~9** | **~25** |

## Fix

### Add condition-to-outcome mapping

Replace the hardcoded `supported_conditions` list with a mapping dict:

```python
_CONDITION_TO_OUTCOME: dict[str, str | None] = {
    "SUCCEEDED": None,       # Default — no outcome filter
    "COMPLETED": "ALL_DONE", # Run regardless of upstream outcome
    "FAILED": "ALL_FAILED",  # Run only if upstream failed
}
```

Then update the sibling dependency branch of `_parse_dependency()`:

```python
condition_key = conditions[0].upper() if conditions else "SUCCEEDED"
if condition_key not in _CONDITION_TO_OUTCOME:
    return UnsupportedValue(
        value=dependency,
        message=f"Dependency condition '{conditions[0]}' is not supported.",
    )

task_key = dependency.get("activity")
if not task_key:
    return UnsupportedValue(value=dependency, message="Missing value 'activity' for task dependency")

return Dependency(task_key=task_key, outcome=_CONDITION_TO_OUTCOME[condition_key])
```

### No changes needed elsewhere

- `preparers/utils.py` — `get_base_task()` already serializes `dep.outcome` via `parse_mapping()`, which strips `None` values naturally. `Succeeded` produces `{"task_key": "X"}`, `Completed` produces `{"task_key": "X", "outcome": "ALL_DONE"}`.
- `models/ir/pipeline.py` — `Dependency.outcome` is already `str | None`, flexible enough.
- Multi-condition case (`len(conditions) > 1`) stays rejected (P3).

## Files to Modify

| # | File | Action | Fix |
|---|------|--------|-----|
| 1 | `src/wkmigrate/translators/activity_translators/activity_translator.py` | **MODIFY** | Add `_CONDITION_TO_OUTCOME` mapping, update sibling dependency branch |

## Test Strategy

Add to `TestParseDependency` in `tests/unit/test_activity_translator.py`:

1. `test_completed_condition_maps_to_all_done` — `Completed` → `Dependency(outcome="ALL_DONE")`
2. `test_failed_condition_maps_to_all_failed` — `Failed` → `Dependency(outcome="ALL_FAILED")`
3. `test_completed_case_insensitive` — `completed` (lowercase) → same result
4. `test_succeeded_outcome_still_none` — regression check
5. `test_skipped_still_rejected` — `Skipped` → `UnsupportedValue`

## Expected Impact

| Metric | Before | After CRP-10 |
|--------|--------|-------------|
| Unsupported dependency warnings | ~25 | **~0** (only multi-condition and Skipped remain) |
| Dependency preservation score | ~85% | **~98%+** |
| CRP0001 notebook preparation | 36/36 (100%) | 36/36 (100%, unchanged) |

## Workflow Notes

- **Base branch:** `pr/27-4-integration-tests` at `6f498bd`
- **Feature branch:** `feature/crp10-dependency-conditions`
- **PR target:** `pr/27-4-integration-tests` at `MiguelPeralvo/wkmigrate`
- **Build system:** `uv` via Makefile — `make test` (unit), `make fmt` (lint)
- **Risk:** Very low. Strictly additive — only new conditions are accepted that were previously rejected. Existing `Succeeded` behavior unchanged. `Skipped` still rejected.
