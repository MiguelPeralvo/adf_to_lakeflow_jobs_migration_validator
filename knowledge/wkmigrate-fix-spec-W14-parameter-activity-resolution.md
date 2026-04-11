# wkmigrate Fix Spec: W-14 — Parameter and Activity Output Resolution Gaps

> Self-contained specification for /wkmigrate-autodev. Expression loop run 1 (200 adversarial expressions × 7 activity contexts) shows 81% resolution in 5 contexts (down from 100% on simple expressions). The 19% gap comes from expressions referencing `pipeline().parameters.X` and `activity('Name').output.firstRow.Y` that wkmigrate can't resolve without proper pipeline context.

## Evidence from Expression Loop

**Run:** 200 LLM-generated expressions, 10 rounds, GPT 5.4, $0.30 total

| Context | Rate on Golden Set | Rate on Adversarial | Gap |
|---------|-------------------|--------------------|----|
| set_variable | 100% | 81% | 19% |
| notebook_base_param | 100% | 81% | 19% |
| lookup_query | 100% | 81% | 19% |
| web_body | 100% | 81% | 19% |
| copy_query | 100% | 81% | 19% |
| if_condition | 98% | 76% | 22% |

The golden set uses simple literal expressions (`@concat('hello', 'world')`). The adversarial expressions use `pipeline().parameters.X` and `activity('Lookup').output.firstRow.Y` — these require runtime context that the test wrappers provide (parameter definitions in the pipeline) but wkmigrate may not fully thread through.

## Failing Expression Patterns (from 71 discovered patterns)

### Pattern 1: Parameter references in math context (most common, 30+ hits)
```
@add(int(pipeline().parameters.count), 1)                    — depth 3
@add(mul(int(pipeline().parameters.count), 2), 1)            — depth 4
@div(sub(mul(int(pipeline().parameters.maxRecords), 10), ...) — depth 11
@mod(add(int(pipeline().parameters.batchId), ...)             — depth 7
```
These fail when wkmigrate's expression parser doesn't have the parameter definition in `TranslationContext.parameters`. The lmv wrappers inject `referenced_params` into the pipeline's `parameters` block, but the adversarial generator doesn't include `referenced_params` in the expression dicts — so the wrappers don't inject them.

**Root cause (lmv-side):** The expression loop generates expressions with `pipeline().parameters.X` but doesn't include `referenced_params` metadata, so `_normalise_referenced_params` returns `{}` and the wrapper pipeline has no `parameters` block.

**Root cause (wkmigrate-side):** When `TranslationContext.parameters` is empty and an expression references `pipeline().parameters.X`, `get_literal_or_expression` may return `UnsupportedValue` instead of emitting `dbutils.widgets.get('X')` as a best-effort fallback.

### Pattern 2: Activity output references (10+ hits)
```
@activity('Lookup').output.firstRow.config_value              — depth 1
@substring(activity('Lookup').output.firstRow.config_value, ...) — depth 5
@length(split(activity('Lookup').output.firstRow.csv_list, ...)) — depth 3
```
These reference upstream activities that don't exist in the single-activity test wrappers.

**Root cause (lmv-side):** The wrappers create single-activity pipelines. There's no upstream Lookup activity to reference.

**Root cause (wkmigrate-side):** When an expression references `activity('X')` but activity 'X' doesn't exist in the pipeline, wkmigrate should emit a `NotTranslatableWarning` + best-effort code (e.g., `dbutils.jobs.taskValues.get(taskKey='X', key='config_value')`) rather than failing silently.

### Pattern 3: Deep nesting (depth 10+, 15+ hits)
```
@concat(substring(toUpper(trim(pipeline().parameters.region)), 0, 2), ...) — depth 11
@or(and(greater(int(pipeline().parameters.threshold), 10), ...) — depth 15
@if(and(greater(int(pipeline().parameters.retryCount), 3), ...) — depth 19
```
Extreme nesting (10-19 levels deep). These may hit parser stack limits or cause `ast.literal_eval` failures on the resolved code.

## Fixes (Two-Pronged)

### Prong 1: wkmigrate — Best-effort resolution for undefined parameters and activities

**File:** `src/wkmigrate/parsers/expression_parsers.py` (or `expression_emitter.py`)

When resolving `pipeline().parameters.X` and `X` is NOT in `TranslationContext.parameters`:

**Current behavior:** Returns `UnsupportedValue` or silently drops the reference.

**Desired behavior:** Emit `dbutils.widgets.get('X')` with a `NotTranslatableWarning`:
```python
# When parameter X is not defined in the pipeline:
warnings.warn(
    NotTranslatableWarning(
        f"Parameter '{param_name}' referenced but not defined in pipeline parameters. "
        f"Emitting best-effort dbutils.widgets.get('{param_name}')."
    )
)
return ResolvedExpression(code=f"dbutils.widgets.get('{param_name}')", is_dynamic=True)
```

Similarly for `activity('X').output.Y` when activity 'X' doesn't exist:
```python
warnings.warn(
    NotTranslatableWarning(
        f"Activity '{activity_name}' referenced but not found in pipeline. "
        f"Emitting best-effort task value lookup."
    )
)
return ResolvedExpression(
    code=f"dbutils.jobs.taskValues.get(taskKey='{activity_name}', key='{field_name}')",
    is_dynamic=True,
)
```

**Why best-effort, not failure:** In real migrations, parameters and activities DO exist at runtime. The translation-time absence is a limitation of the test harness, not of the real pipeline. Emitting best-effort code produces a functional notebook that works at runtime when the parameter/activity exists.

### Prong 2: lmv — Improve expression loop to provide referenced_params

**File:** `src/lakeflow_migration_validator/optimization/adversarial_expression_loop.py`

After LLM generates expressions, post-process them to extract parameter references and add `referenced_params`:

```python
def _enrich_with_referenced_params(expressions: list[dict]) -> list[dict]:
    """Extract pipeline().parameters.X references and add referenced_params."""
    import re
    param_pattern = re.compile(r"pipeline\(\)\.parameters\.(\w+)")
    for expr in expressions:
        adf = expr.get("adf_expression", "")
        params = param_pattern.findall(adf)
        if params:
            expr["referenced_params"] = [
                {"name": p, "type": "String"} for p in set(params)
            ]
    return expressions
```

This ensures the wrappers inject proper `parameters` blocks into the test pipelines, so wkmigrate's `TranslationContext` has the parameter definitions.

## Test Cases

### wkmigrate tests

```python
def test_undefined_parameter_emits_best_effort():
    """Expression referencing undefined parameter should emit dbutils.widgets.get, not fail."""
    # Pipeline with NO parameters defined
    pipeline = {"name": "test", "activities": [...], "parameters": {}}
    # Expression references pipeline().parameters.env
    # Should resolve to dbutils.widgets.get('env') with a warning
    
def test_undefined_activity_reference_emits_best_effort():
    """Expression referencing non-existent activity should emit task value get, not fail."""
    # Pipeline with only 1 activity, expression references activity('Lookup')
    # Should resolve to dbutils.jobs.taskValues.get(...) with a warning

def test_deep_nesting_depth_15():
    """Expression with 15 levels of nesting should still resolve."""
    expr = "@concat(toUpper(trim(substring(replace(toLower(pipeline().parameters.x), 'a', 'b'), 0, 5))), '_suffix')"
    # Should not hit stack limits
```

### lmv tests

```python
def test_enrich_with_referenced_params():
    """Expressions with pipeline().parameters.X get referenced_params added."""
    expressions = [{"adf_expression": "@add(int(pipeline().parameters.count), 1)"}]
    enriched = _enrich_with_referenced_params(expressions)
    assert enriched[0]["referenced_params"] == [{"name": "count", "type": "String"}]
```

## Verification

```bash
# wkmigrate
make test

# lmv — re-run expression loop after both fixes
lmv expression-loop --rounds 5 --expressions 20 --model databricks-gpt-5-4
# per-context rates should jump from 81% to >90% for the 5 non-for_each contexts
```

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests
git checkout -b pr/27-6-best-effort-resolution
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3..4 | Lint compliance | 0 |
| W14-1 | Undefined parameter → best-effort dbutils.widgets.get + warning | test passes |
| W14-2 | Undefined activity ref → best-effort taskValues.get + warning | test passes |
| W14-3 | Depth-15 nested expression resolves without error | test passes |
| W14-4 | expression_loop per-context rate ≥ 90% (up from 81%) | measured |
