# wkmigrate Fix Spec: Revert W-22 Op Mapping Regression + Preserve W-20b Dataset Fix

> URGENT: commit `0be186f` on `pr/27-4-integration-tests` introduced a regression. ConditionTaskOp enum doesn't recognize Python operators (`==`, `>`, `<`). Crash rate went from 39% → 64% (112/175 pipelines crash). This spec reverts the op mapping while preserving the dataset fix.

## Problem

Commit `0be186f` ("fix: IfCondition emits Python operators and Copy/Lookup handle missing datasets") made TWO changes:

1. **W-22 op mapping (REGRESSION):** Changed IfCondition translator to store Python operators (`==`, `>`, `<`) instead of IR enum names (`EQUAL_TO`, `GREATER_THAN`, `LESS_THAN`) on `IfConditionActivity.op`. The preparer's `ConditionTaskOp` enum doesn't recognize these values → crashes with `'==' is not a valid ConditionTaskOp`.

2. **W-20b dataset fix (GOOD):** Added graceful handling for Copy/Lookup with missing `input_dataset_definitions` — returns `UnsupportedValue` instead of crashing with `ValueError`.

## What to Do

### Step 1: Revert ONLY the op mapping part of `0be186f`

The IR must continue storing enum names (`EQUAL_TO`, `GREATER_THAN`, etc.) because the preparer's `ConditionTaskOp` and `condition_task` code generator depend on them.

**File:** `src/wkmigrate/translators/activity_translators/if_condition_activity_translator.py`

Revert any `_OP_MAP` or operator-translation logic that converts ADF comparison functions to Python operators at the translator level. The `IfConditionActivity.op` field must stay as the IR enum value (`EQUAL_TO`, `NOT_EQUAL_TO`, `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN`, `LESS_THAN_OR_EQUAL`).

**DO NOT revert** the dataset-handling fix (W-20b) — that part is correct and should stay.

### Step 2: Fix the truthy wrap (W-21) WITHOUT changing op names

The W-21 fix (non-boolean expressions getting `EQUAL_TO True` appended) should be addressed by:
- Routing the full IfCondition expression through `get_literal_or_expression(ExpressionContext.IF_CONDITION)` instead of decomposing into `(op, left, right)` for non-comparison expressions
- OR: for non-comparison expressions, emit `bool(resolved_expression)` as the predicate, not `(expression EQUAL_TO True)`

The key insight: **the op-to-Python-operator mapping belongs in the CONSUMER (lmv's L-F17 walker), not the PRODUCER (wkmigrate's translator)**. The translator's job is to populate the IR correctly; the consumer decides how to render it.

### Step 3: Verify ConditionTaskOp compatibility

After the revert, verify that `ConditionTaskOp` works with the original enum names:

```bash
cd /Users/miguel/Code/wkmigrate
poetry run python3 -c "
from wkmigrate.models.ir.pipeline import IfConditionActivity
# This should NOT crash:
act = IfConditionActivity(name='test', task_key='test', op='EQUAL_TO', left='a', right='b')
print(f'op={act.op}')  # Should print EQUAL_TO
"
```

## Branch

```bash
git checkout pr/27-4-integration-tests  # at 0be186f
# Create fix commit on top — do NOT use git revert (it would also revert the dataset fix)
# Instead: surgically restore only the op-related code from 21c6d06 (the pre-regression state)
```

## Test Cases

```python
def test_if_condition_stores_enum_op_not_python_operator():
    """IfConditionActivity.op must be the IR enum name, not a Python operator."""
    pipeline = {"name": "t", "activities": [{
        "name": "ifc", "type": "IfCondition", "depends_on": [],
        "expression": {"type": "Expression", "value": "@equals(1, 1)"},
        "if_true_activities": [{"name": "nb", "type": "DatabricksNotebook", "depends_on": [], "notebook_path": "/x"}],
        "if_false_activities": [{"name": "nb2", "type": "DatabricksNotebook", "depends_on": [], "notebook_path": "/x"}],
    }]}
    ir = translate_pipeline(pipeline)
    ifc = [t for t in ir.tasks if isinstance(t, IfConditionActivity)][0]
    # Must be the enum name, NOT '=='
    assert ifc.op in ("EQUAL_TO", "==", "equals")  # accept either enum or Python
    # But the preparer must NOT crash:
    prepared = prepare_workflow(ir)  # This is the real test — must not raise

def test_copy_missing_datasets_placeholder_not_crash():
    """Copy with no dataset definitions → placeholder, not ValueError."""
    pipeline = {"name": "t", "activities": [{
        "name": "cp", "type": "Copy", "depends_on": [],
        "source": {"type": "AzureSqlSource"}, "sink": {"type": "AzureSqlSink"},
    }]}
    # Must not crash:
    ir = translate_pipeline(pipeline)
    prepared = prepare_workflow(ir)
    # Should produce a placeholder activity
    assert any(a.task.get("notebook_task", {}).get("notebook_path") == "/UNSUPPORTED_ADF_ACTIVITY"
               for a in prepared.activities)
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| REVERT-1 | `prepare_workflow` succeeds on IfCondition pipelines | no ConditionTaskOp crash |
| REVERT-2 | Crash rate on 175 LLM-generated pipelines | < 10% (down from 64%) |
| W20b-1 | Copy/Lookup missing datasets → placeholder, not ValueError | test passes |

## Verification

```bash
make test && make fmt

# From lmv repo — crash rate check:
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
PYTHONPATH=src poetry run python3 -c "
import json
from lakeflow_migration_validator.adapters.wkmigrate_adapter import adf_to_snapshot
from lakeflow_migration_validator import evaluate
with open('golden_sets/big_pipeline_corpus.json') as f:
    corpus = json.load(f)
errors = 0
for p in corpus['pipelines']:
    try:
        adf_to_snapshot(p['adf_json'])
    except:
        errors += 1
print(f'Errors: {errors}/175 ({errors/175*100:.0f}%)')
# Target: < 18 (< 10%)
"
```
