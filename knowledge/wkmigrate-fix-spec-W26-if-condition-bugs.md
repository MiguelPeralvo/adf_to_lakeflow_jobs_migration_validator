# wkmigrate Fix Spec: W-26 — IfCondition Comparison Emission Bugs

> Self-contained specification for /wkmigrate-autodev. Three real bugs surfaced by the improved LLM judge (v3 calibration) in the if_condition context. These are the only remaining wkmigrate translation bugs — all other low scores were judge calibration issues.

## Evidence

200 expressions evaluated via `lmv semantic-eval --context if_condition` against `pr/27-4-integration-tests@b8c9be2`. The v3 judge (with activity output, variables, and div calibration) correctly identifies 3 real bugs:

| Bug | What it emits | What it should emit | Pairs affected |
|-----|--------------|---------------------|----------------|
| W-26a | `NOT_EQUAL` | `!=` | @not(equals(...)) expressions |
| W-26b | `prod` (bare) | `'prod'` (quoted) | Comparison with string literals |
| W-26c | No coercion | `int()`/`float()` wrap | @greaterOrEquals, @lessOrEquals |

## W-26a: `@not(equals(...))` emits `NOT_EQUAL` pseudo-code

### What it is

When `@not(equals(pipeline().parameters.env, 'prod'))` is the IfCondition predicate, wkmigrate emits `NOT_EQUAL` as a literal string instead of the Python `!=` operator.

### Fix

**File:** `src/wkmigrate/parsers/expression_emitter.py` or `if_condition_activity_translator.py`

The `@not(equals(a, b))` pattern should emit `(a != b)` in the Python code, not `(a NOT_EQUAL b)`.

### Test

```python
def test_not_equals_emits_python_operator():
    resolved = resolve_if_condition("@not(equals(pipeline().parameters.env, 'prod'))")
    assert "NOT_EQUAL" not in resolved
    assert "!=" in resolved
```

---

## W-26b: String literal comparisons emit unquoted identifiers

### What it is

When comparing against string literals, the emitted Python has bare identifiers instead of quoted strings:
- Emits: `(dbutils.widgets.get('status') == complete)` 
- Should: `(dbutils.widgets.get('status') == 'complete')`

This causes `NameError` at runtime.

### Fix

**File:** `src/wkmigrate/parsers/expression_emitter.py`

String literal arguments in comparison functions must be emitted with quotes in the Python output.

### Test

```python
def test_string_literal_quoted_in_comparison():
    resolved = resolve_if_condition("@equals(pipeline().parameters.status, 'complete')")
    assert "'complete'" in resolved  # quoted
    assert " complete)" not in resolved  # not bare
```

---

## W-26c: `@greaterOrEquals`/`@lessOrEquals` missing numeric coercion

### What it is

W-24 added coercion for `@greater`/`@less` but missed `@greaterOrEquals` and `@lessOrEquals`. These emit comparisons without `int()`/`float()` wrapping, which fails because `dbutils.widgets.get()` returns strings.

- Emits: `(dbutils.widgets.get('score') >= 85.5)`
- Should: `(float(dbutils.widgets.get('score')) >= 85.5)`

### Fix

**File:** `src/wkmigrate/parsers/expression_functions.py`

Ensure `greaterOrEquals` and `lessOrEquals` use the same `_emit_numeric_binary_operator` path as `greater` and `less`.

### Test

```python
def test_greater_or_equals_coerces():
    resolved = resolve_if_condition("@greaterOrEquals(pipeline().parameters.score, 85.5)")
    assert "float(" in resolved or "int(" in resolved
```

---

## Execution Order

1. **W-26b (string quoting) FIRST** — most impactful, causes NameError at runtime
2. **W-26a (NOT_EQUAL → !=) SECOND** — pseudo-code in output
3. **W-26c (coercion) THIRD** — extends W-24 pattern to remaining comparison functions

## Branch

```bash
git checkout pr/27-4-integration-tests  # current tip: b8c9be2
```

Push to MiguelPeralvo/wkmigrate only. NEVER open a PR to ghanse/wkmigrate.

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| W26a-1 | `@not(equals(...))` emits `!=` not `NOT_EQUAL` | test passes |
| W26b-1 | String literals are quoted in comparisons | test passes |
| W26c-1 | `@greaterOrEquals` coerces to numeric | test passes |
| OVERALL | if_condition X-2 score | > 0.85 (up from 0.769) |

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
  --limit 26
# Target: overall > 0.85
```
