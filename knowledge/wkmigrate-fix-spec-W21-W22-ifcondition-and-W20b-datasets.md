# wkmigrate Fix Spec: W-21/W-22 (IfCondition EQUAL_TO leak) + W-20b (missing datasets crash)

> Self-contained specification for /wkmigrate-autodev. Two independent bugs, both discovered by the lmv autonomous ratchet run on 2026-04-12.

---

## W-21 + W-22: IfCondition Semantic Failure (X-2 = 0.157)

### Evidence

200 adversarial expressions evaluated via `lmv semantic-eval --context if_condition` against `pr/27-4-integration-tests@21c6d06`:

| Metric | Value |
|--------|-------|
| Context | if_condition |
| Overall X-2 score | **0.157** (vs 0.808 on set_variable) |
| Pairs evaluated | 190 |
| Pairs below 0.7 | **190/190 (100%)** |
| Pairs with `EQUAL_TO` in python_code | **20/20 sampled (100%)** |

Full results: `golden_sets/semantic_eval_by_context/if_condition.json`

### What's happening

The IfCondition translator decomposes the predicate expression into `(op, left, right)` on the IR's `IfConditionActivity`. The lmv L-F17 walker then synthesizes `python_code = f"({left} {op} {right})"`. Two bugs compound:

**W-21: Non-boolean expressions get wrapped in a truthy check**

When a non-boolean expression (e.g., `@concat(...)`, `@formatDateTime(...)`) is used as an IfCondition predicate, wkmigrate wraps it as `(expression EQUAL_TO True)` — treating it as a truthy check. This produces:

```python
# ADF: @concat(formatDateTime(utcNow(),'yyyy-MM-dd'), '/', pipeline().parameters.env)
# wkmigrate emits:
(str(_wkmigrate_format_datetime(...)) + str('/') + str(dbutils.widgets.get('env')) EQUAL_TO True)
```

This is invalid Python syntax AND semantically wrong: the ADF expression produces a string, not a boolean.

**W-22: IR uses enum names instead of Python operators**

Even for genuine boolean predicates like `@equals(a, b)`, the IR stores `op="EQUAL_TO"` instead of `op="=="`. The L-F17 walker passes the enum through verbatim:

```python
# ADF: @equals(pipeline().parameters.env, 'prod')
# wkmigrate emits:
(dbutils.widgets.get('env') EQUAL_TO 'prod')
# Should be:
(dbutils.widgets.get('env') == 'prod')
```

### Where to fix

**W-21 — IfCondition non-boolean wrap** 

**File:** `src/wkmigrate/translators/activity_translators/if_condition_activity_translator.py`

The translator should NOT wrap non-boolean expressions in `EQUAL_TO True`. Instead:
- If the expression is already a comparison (`@equals`, `@greater`, `@less`, `@and`, `@or`, `@not`), decompose into `(op, left, right)` normally.
- If the expression is NOT a comparison (e.g., `@concat`, `@formatDateTime`), emit it as `bool(expression)` for a truthy check, not `expression EQUAL_TO True`.
- Better yet: route the full expression through `get_literal_or_expression(ExpressionContext.IF_CONDITION)` and let the emitter handle it — the emitter already knows how to produce valid Python for any expression.

**W-22 — Op enum → Python operator mapping**

**File:** `src/wkmigrate/translators/activity_translators/if_condition_activity_translator.py` (or wherever `IfConditionActivity.op` is set)

Add a mapping from IR enum names to Python operators:

```python
_OP_MAP = {
    "EQUAL_TO": "==",
    "NOT_EQUAL_TO": "!=",
    "GREATER_THAN": ">",
    "GREATER_THAN_OR_EQUAL": ">=",
    "LESS_THAN": "<",
    "LESS_THAN_OR_EQUAL": "<=",
}

# When constructing IfConditionActivity:
python_op = _OP_MAP.get(adf_op, "==")  # fallback to == for unknown
```

OR: fix at the emitter level — `expression_emitter.py` should map `EQUAL_TO` → `==` when emitting comparison expressions.

### Test cases

```python
def test_if_condition_equals_uses_python_operator():
    """@equals(a, b) in IfCondition should emit (a == b), not (a EQUAL_TO b)."""
    pipeline = wrap_in_if_condition("@equals(pipeline().parameters.env, 'prod')",
                                    referenced_params=[{"name": "env", "type": "String"}])
    snap = adf_to_snapshot(pipeline)
    for pair in snap.resolved_expressions:
        assert "EQUAL_TO" not in pair.python_code
        assert "==" in pair.python_code

def test_if_condition_non_boolean_no_truthy_wrap():
    """Non-boolean expression in IfCondition should NOT get EQUAL_TO True appended."""
    pipeline = wrap_in_if_condition("@concat('a', 'b')")
    snap = adf_to_snapshot(pipeline)
    for pair in snap.resolved_expressions:
        assert "EQUAL_TO" not in pair.python_code
        assert "True" not in pair.python_code or "bool(" in pair.python_code

def test_if_condition_greater_uses_gt_operator():
    """@greater(a, 50) in IfCondition should emit (a > 50)."""
    pipeline = wrap_in_if_condition("@greater(pipeline().parameters.threshold, 50)",
                                    referenced_params=[{"name": "threshold", "type": "Int"}])
    snap = adf_to_snapshot(pipeline)
    for pair in snap.resolved_expressions:
        assert ">" in pair.python_code
        assert "GREATER" not in pair.python_code
```

---

## W-20b: Missing Datasets Crash in Preparer (68/175 pipelines)

### Evidence

175 LLM-generated pipelines batch-evaluated against `pr/27-4-integration-tests@21c6d06`:

| Metric | Value |
|--------|-------|
| Total pipelines | 175 |
| Crashed | 68 (39%) |
| Error message | `ValueError: Dataset definition or properties missing` |
| All 68 from same root cause | Yes |

The W-20 fix commit (`21c6d06`) addressed W-20a (policy.retry) and W-20c (typeProperties normalization) but incorrectly claimed W-20b was "already handled". It is NOT handled — the error persists.

### What's happening

LLM-generated Copy/Lookup activities sometimes omit `input_dataset_definitions` / `output_dataset_definitions`. The translator creates `CopyActivity(source_dataset=None, ...)` or `LookupActivity(source_dataset=None, ...)`. Then the preparer calls `merge_dataset_definition(None, ...)` which raises `ValueError`.

**Call chain:**
```
prepare_copy_activity(activity)
  → merge_dataset_definition(activity.source_dataset, activity.source_properties)
    → ValueError("Dataset definition or properties missing")  # when source_dataset is None
```

### Where to fix

**Option A (translator level — preferred):** Validate datasets before constructing the Activity:

**File:** `src/wkmigrate/translators/activity_translators/copy_activity_translator.py` (~line 39)

```python
# Current:
source_dataset = get_data_source_definition(get_value_or_unsupported(activity, "input_dataset_definitions"))

# Fix: if input_dataset_definitions is missing entirely, return UnsupportedValue
# (the existing get_value_or_unsupported should handle this, but verify it does)
```

The issue might be that `get_value_or_unsupported` returns the activity dict itself when the key is missing (not UnsupportedValue). Check and fix.

**Option B (preparer level — defensive):** Catch the ValueError in the preparer and emit a placeholder:

**File:** `src/wkmigrate/preparers/copy_activity_preparer.py`

```python
def prepare_copy_activity(activity):
    try:
        source_definition = merge_dataset_definition(activity.source_dataset, activity.source_properties)
    except (ValueError, TypeError):
        # Missing dataset — emit placeholder notebook with warning
        return _placeholder_copy_notebook(activity)
```

**Recommended: Option A** — fail early at the translator, not late at the preparer. This produces a proper UnsupportedValue that flows through `normalize_translated_result` → placeholder activity, which is the wkmigrate convention.

### Test cases

```python
def test_copy_missing_input_datasets_returns_unsupported():
    """Copy activity with no input_dataset_definitions → UnsupportedValue, not crash."""
    activity = {"source": {"type": "AzureSqlSource"}, "sink": {"type": "AzureSqlSink"},
                "translator": {"type": "TabularTranslator", "mappings": []}}
    result = translate_copy_activity(activity, {"name": "test", "task_key": "test"})
    assert isinstance(result, UnsupportedValue)

def test_lookup_missing_datasets_returns_unsupported():
    """Lookup activity with no input_dataset_definitions → UnsupportedValue, not crash."""
    activity = {"source": {"type": "AzureSqlSource"}, "first_row_only": True}
    result = translate_lookup_activity(activity, {"name": "test", "task_key": "test"})
    assert isinstance(result, UnsupportedValue)

def test_pipeline_with_missing_dataset_copy_produces_placeholder():
    """End-to-end: pipeline with Copy missing datasets → placeholder activity, not crash."""
    pipeline = {"name": "test", "activities": [
        {"name": "bad_copy", "type": "Copy", "depends_on": [],
         "source": {"type": "AzureSqlSource"}, "sink": {"type": "AzureSqlSink"}}
    ]}
    snap = adf_to_snapshot(pipeline)  # must not crash
    assert any(t.is_placeholder for t in snap.tasks)
```

---

## Execution Order

1. **W-22 (op enum mapping) FIRST** — smallest, most surgical fix (add _OP_MAP dict + 1 line change)
2. **W-21 (non-boolean truthy wrap) SECOND** — requires understanding how IfCondition decomposes predicates; may need to change how non-comparison expressions are handled
3. **W-20b (missing datasets) THIRD** — validate at translator level that datasets exist before creating Activity

## Branch Strategy

```bash
cd /Users/miguel/Code/wkmigrate
git checkout pr/27-4-integration-tests  # current tip: 21c6d06
git checkout -b pr/27-10-ifcondition-and-dataset-robustness
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3..4 | Lint compliance | 0 |
| W21-1 | `EQUAL_TO` never appears in resolved python_code for IfCondition | grep confirms 0 |
| W22-1 | if_condition context X-2 score | > 0.60 (up from 0.157) |
| W20b-1 | Crash rate on 175 LLM-generated pipelines | < 5% (down from 39%) |
| W20b-2 | Copy/Lookup with missing datasets → UnsupportedValue (not ValueError) | test passes |

## Verification

```bash
# wkmigrate tests
cd /Users/miguel/Code/wkmigrate
make test && make fmt

# lmv verification (run from lmv repo)
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude

# 1. IfCondition X-2 improvement
source .env && export DATABRICKS_HOST DATABRICKS_TOKEN
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context if_condition \
  --model databricks-claude-sonnet-4-6 \
  --limit 20
# Target: overall > 0.60 (from 0.157); no "EQUAL_TO" in python_code

# 2. Crash rate reduction  
PYTHONPATH=src poetry run python3 -c "
import json
from lakeflow_migration_validator.adapters.wkmigrate_adapter import adf_to_snapshot
from lakeflow_migration_validator import evaluate
with open('golden_sets/big_pipeline_corpus.json') as f:
    corpus = json.load(f)
errors = sum(1 for p in corpus['pipelines']
             if not (lambda: [adf_to_snapshot(p['adf_json']), True][-1])()  # hack
             )
# Proper: iterate and count exceptions
"
# Target: < 9 errors (< 5%)
```
