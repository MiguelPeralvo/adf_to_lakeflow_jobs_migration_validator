---
finding_id: W-32
kind: bug
severity: P1
area: expressions
session: LMV-AUTODEV-2026-04-17-crp11-harvest
wkmigrate_version_under_test: MiguelPeralvo/wkmigrate@pr/27-4-integration-tests@e21c1e3
status: draft
upstream_issues:
  - ghanse/wkmigrate#27
---

# W-32 — `@variables(...)` producer inside multi-activity ForEach: best-effort task key fails at runtime

## Problem

Step-3 audit (wkmigrate `6e0a3f5`, authored as part of CRP-11) documented a known limitation: when a `SetVariable` producer lives inside a multi-activity `ForEach` body and its consumer (an `IfCondition` referencing `@variables('X')`) sits at the outer scope, wkmigrate emits a **best-effort task key** that does not exist at Databricks runtime.

```
ForEach
  └── SetVariable X, ...          # producer (nested)
IfCondition @variables('X') == Y  # consumer (outer, reads via taskValues.get)
```

Current emission (`src/wkmigrate/parsers/expression_emitter.py:135`):

```python
task_key = f"set_variable_{variable_name}"   # best-effort fallback
dbutils.jobs.taskValues.get(taskKey='set_variable_X', key='X')
```

This fails at runtime for two reasons:

1. No Databricks task is keyed `set_variable_X` — the name is a wkmigrate convention, not reality. The inner SetVariable lives in a `RunJob` child, which sanitizes its own task key and does not expose `set_variable_X` to the outer job.
2. Even if the key were renamed to match, ADF `taskValues` do not cross `RunJob` boundaries. The inner RunJob has its own task-values scope.

## Evidence

- `src/wkmigrate/parsers/expression_emitter.py:129-146` emits a `NotTranslatableWarning` (CRP-11 Step 3) when this path fires. The warning surfaces in the lmv adapter's `not_translatable` collection.
- Design doc: `/Users/miguel.peralvo/Code/wkmigrate/dev/step-3-variables-fanin.md` (§ Case B — "Wrong at runtime, known limitation").
- Lock-in test: `tests/integration/test_if_condition_wrapper.py::test_wrapper_resolves_variables_to_upstream_setvariable_task_keys` expects the best-effort fallback, documenting the limitation.

## Lakeflow Migration Validator evidence (this session)

- 195/208 compound IfCondition predicates in `if_condition` context go through CRP-11 wrappers.
- `variables()` in a compound predicate is the dominant real-world pattern in CRP0001 — Lorenzo's master analysis doc categorised 11/62 PARTIAL cases as `variables-fan-in` cases.
- With the best-effort fallback, these 11 cases will silently return `None` from `taskValues.get(...)` at runtime and the `bool(predicate)` evaluation will take the False branch regardless of the ADF semantics.

## Suggested wkmigrate fix (proper fan-in design)

Per the Step-3 design doc:

1. Inner `SetVariable` continues to emit `dbutils.jobs.taskValues.set(key='X', value=…)` inside the RunJob.
2. Add a **fan-in notebook task** between the RunJob and the outer IfCondition wrapper. The fan-in reads `RunJob.output.task_values['X']` and re-publishes it under the outer job's `taskValues`.
3. The outer wrapper notebook then reads the re-published value via `dbutils.jobs.taskValues.get(taskKey='<fan-in-task>', key='X')`.

Open semantic question (must clarify with Repsol/Lorenzo): when `SetVariable` runs inside a `ForEach`, every iteration overwrites. ADF's published semantic is "last iteration wins"; confirm that is the intended aggregation (vs. `all(values)` for short-circuit-style continue flags used in CRP0001).

## Test plan

- Add `tests/integration/test_variables_fanin.py` (new): multi-activity ForEach body with a SetVariable, outer IfCondition reading the variable. Expect the wrapper to read via the fan-in task key, not `set_variable_X`.
- Add a minimal `test_for_each_fanin_preparer.py` verifying the fan-in notebook artifact is emitted.
- Re-run `lmv sweep-activity-contexts` — expect the 11 CRP0001 `variables()` consumers to produce real `taskValues.get()` lookups pointing at the fan-in task.

## Labels

`wkmigrate-feedback`, `filed-by:lmv-autodev`, `area:expressions`, `kind:bug`, `severity:P1`, `source:crp11-harvest`, `crp:crp-11-step-3`
