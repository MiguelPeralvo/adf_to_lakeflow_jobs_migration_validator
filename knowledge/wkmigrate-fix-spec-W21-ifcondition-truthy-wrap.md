# wkmigrate Fix Spec: W-21 — IfCondition Truthy Wrap

> Self-contained specification for /wkmigrate-autodev. The IfCondition translator wraps ALL non-comparison expressions in `(expression EQUAL_TO True)`, producing semantically wrong Python. if_condition context X-2 = 0.157 (190/190 below 0.7). This is the single biggest remaining semantic quality blocker.

## Evidence

200 adversarial expressions evaluated via `lmv semantic-eval --context if_condition` against `pr/27-4-integration-tests@10653f5`:

| Metric | Value |
|--------|-------|
| Context | if_condition |
| X-2 score | **0.157** (vs 0.808 on set_variable — same expressions) |
| Pairs evaluated | 190 |
| Pairs below 0.7 | **190/190 (100%)** |
| Root cause | `right="True"` on every IfConditionActivity |

Comparison with other contexts (same 200 expressions):
- set_variable: 0.808, lookup_query: 0.812, copy_query: 0.808, notebook_base_param: 0.810
- **if_condition is 5x worse** than every other context on the same expressions

## What's happening

When a non-comparison expression (e.g., `@concat(...)`, `@formatDateTime(...)`, `@if(...)`) is used as an IfCondition predicate, the translator decomposes it as:

```
IfConditionActivity(
    op="EQUAL_TO",
    left="<resolved full expression>",
    right="True"
)
```

The lmv walker then renders this as: `(bool(<resolved expression>) == True)`

Examples from the eval:

```python
# ADF: @if(equals(mod(int(pipeline().parameters.partitionId), 2), 0), 
#          concat('even/', ...), concat('odd/', ...))
# Wkmigrate IR: op=EQUAL_TO, left=<full ternary>, right=True
# Rendered: (bool(str('even/') + ... if ((int(...) % 2) == 0) else str('odd/') + ...) == True)
# WRONG: returns True/False instead of the string value

# ADF: @concat(formatDateTime(utcNow(),'yyyy-MM-dd'), '/', pipeline().parameters.env)
# Wkmigrate IR: op=EQUAL_TO, left=<concat result>, right=True
# Rendered: (bool(str(...) + str('/') + str(dbutils.widgets.get('env'))) == True)
# WRONG: returns True instead of the concatenated string
```

The `== True` is always wrong for non-boolean expressions. Even for boolean expressions it's redundant (`x == True` is just `x` in Python).

## Root Cause

The IfCondition translator forces EVERY expression into the `(op, left, right)` decomposition. When the expression isn't a direct comparison (equals, greater, less, etc.), it falls back to:
- `op = "EQUAL_TO"`
- `left = <the resolved expression>`
- `right = "True"`

This transforms a string/number/array expression into a boolean comparison, fundamentally changing its semantics.

## Fix

**File:** `src/wkmigrate/translators/activity_translators/if_condition_activity_translator.py`

The fix depends on what the IfCondition's `expression` field actually IS:

### Case 1: Expression is a comparison (`@equals`, `@greater`, `@less`, etc.)
Keep the current decomposition: `op=EQUAL_TO, left=a, right=b` → wkmigrate correctly extracts the comparison.

### Case 2: Expression is NOT a comparison (everything else)
**Do not decompose.** Instead:
- Route the expression through `get_literal_or_expression(ExpressionContext.IF_CONDITION)` to get the resolved Python code
- Store the result as: `op="BOOL", left=<resolved expression>, right=""` (or use a separate field)
- OR: store the full resolved expression as a single value without decomposing

The simplest fix that preserves backward compat with `ConditionTaskOp`:

```python
def _translate_if_condition_expression(expression_value, context, emission_config):
    """Resolve the IfCondition predicate expression."""
    resolved = get_literal_or_expression(expression_value, context, 
                                          emission_config=emission_config,
                                          expression_context=ExpressionContext.IF_CONDITION)
    if isinstance(resolved, UnsupportedValue):
        return resolved
    
    # If the resolved expression is already a comparison (contains ==, >, <, etc.),
    # decompose it for ConditionTask. Otherwise, use it as a truthy predicate
    # WITHOUT wrapping in "== True".
    code = resolved.code if hasattr(resolved, 'code') else str(resolved)
    
    # Check if the expression resolves to a comparison
    # (This is a heuristic — better to check at the AST level)
    if _is_comparison_expression(expression_value):
        # Decompose into op/left/right for ConditionTask
        return _decompose_comparison(expression_value, context, emission_config)
    else:
        # Non-comparison: store as a truthy check WITHOUT == True
        # The ConditionTask should evaluate bool(expression), not expression == True
        return IfConditionActivity(
            ...,
            op="BOOL",  # or some sentinel that means "truthy check"
            left=code,
            right="",
        )
```

**Alternative simpler fix** if `ConditionTaskOp` can't be changed: keep `op="EQUAL_TO"` but set `right=""` (empty) for non-comparisons. The lmv walker already skips pairs where `right` is empty (line 376: `isinstance(right, str) and right`). This means non-comparison IfCondition expressions would NOT produce an ExpressionPair — which is better than producing a wrong one.

**Recommended: the "right="" sentinel" approach.** It's a 1-line change in the IfCondition translator (set `right=""` instead of `right="True"` for non-comparisons) and it immediately stops the wrong pairs from polluting X-2.

## Test Cases

```python
def test_if_condition_non_comparison_no_truthy_wrap():
    """Non-comparison IfCondition predicate should NOT get == True."""
    pipeline = {"name": "t", "activities": [{
        "name": "ifc", "type": "IfCondition", "depends_on": [],
        "expression": {"type": "Expression", "value": "@concat('a', 'b')"},
        "if_true_activities": [{"name": "nb", "type": "DatabricksNotebook", 
                                "depends_on": [], "notebook_path": "/x"}],
        "if_false_activities": [],
    }]}
    ir = translate_pipeline(pipeline)
    ifc = [t for t in ir.tasks if isinstance(t, IfConditionActivity)][0]
    # right should be empty for non-comparison, NOT "True"
    assert ifc.right != "True"

def test_if_condition_equals_still_decomposes():
    """@equals(a, b) should still decompose into op/left/right."""
    pipeline = {"name": "t", "activities": [{
        "name": "ifc", "type": "IfCondition", "depends_on": [],
        "expression": {"type": "Expression", "value": "@equals(1, 2)"},
        "if_true_activities": [{"name": "nb", "type": "DatabricksNotebook",
                                "depends_on": [], "notebook_path": "/x"}],
        "if_false_activities": [],
    }]}
    ir = translate_pipeline(pipeline)
    ifc = [t for t in ir.tasks if isinstance(t, IfConditionActivity)][0]
    assert ifc.op == "EQUAL_TO"
    assert ifc.right != "True"  # right should be "2", not "True"
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| W21-1 | No IfConditionActivity has `right="True"` for non-comparison expressions | test passes |
| W21-2 | if_condition X-2 score (lmv semantic-eval) | > 0.50 (up from 0.157) |
| W21-3 | `prepare_workflow` still succeeds on all IfCondition pipelines | no ConditionTaskOp crash |

## Verification

```bash
make test && make fmt

# From lmv repo:
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
source .env && export DATABRICKS_HOST DATABRICKS_TOKEN
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context if_condition \
  --model databricks-claude-sonnet-4-6 \
  --limit 20
# Target: overall > 0.50, no "== True" in python_code for non-comparison expressions
```

## Branch

```bash
git checkout pr/27-4-integration-tests  # current tip: 10653f5
```

Push to MiguelPeralvo/wkmigrate only. NEVER open a PR to ghanse/wkmigrate.
