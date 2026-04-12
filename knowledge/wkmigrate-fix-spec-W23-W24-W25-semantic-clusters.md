# wkmigrate Fix Spec: W-23/W-24/W-25 — Top Semantic Clusters from 7-Context Eval

> Self-contained specification for /wkmigrate-autodev. After W-17/W-18/W-20/W-21 fixes, 127 low-scoring expression pairs remain. The top actionable clusters (excluding stale pre-fix data) are: json_parse_assumption (49), type_coercion residual (19), and division_semantics (12). These 3 clusters account for ~80 fixable pairs.

## Evidence

Full cluster analysis: `knowledge/wkmigrate-fix-spec-W23-auto.md` (auto-generated from `scripts/cluster_low_scoring.py`). 9 clusters total; top 2 (activity_output_structure=75, firstRow_flattening=57) are stale pre-fix data that will disappear on re-eval. The 3 actionable clusters below are confirmed present on the CURRENT wkmigrate tip (`pr/27-4-integration-tests@2c86a1b`).

---

## W-23: `json.loads()` assumption on activity output (49 pairs)

### What it is

When resolving `@activity('Lookup').output.firstRow.X`, wkmigrate emits:

```python
json.loads(dbutils.jobs.taskValues.get(taskKey='Lookup', key='result'))['firstRow']['X']
```

The `json.loads()` wrapper assumes the task value was stored as a JSON string. But `dbutils.jobs.taskValues.set()` can store raw Python objects (dicts, lists, strings) — they don't need JSON serialization. The LLM judge flags this as semantically fragile because:
1. If the upstream task stores a dict directly, `json.loads(dict)` crashes with TypeError
2. If it stores a string that's NOT JSON, `json.loads("hello")` crashes with JSONDecodeError
3. The correct pattern is conditional: `json.loads(v) if isinstance(v, str) else v`

### Impact

Every expression referencing `activity('X').output` gets the fragile `json.loads()` wrapper. Affects all activity-chaining expressions across all contexts.

### Fix

**File:** `src/wkmigrate/parsers/expression_emitter.py` (wherever activity output references are emitted)

Replace:
```python
f"json.loads(dbutils.jobs.taskValues.get(taskKey='{name}', key='result'))"
```

With a safer pattern:
```python
# Option A: Remove json.loads entirely (taskValues stores Python objects natively)
f"dbutils.jobs.taskValues.get(taskKey='{name}', key='result')"

# Option B: Conditional parse (safest for mixed environments)
f"(lambda __v: json.loads(__v) if isinstance(__v, str) else __v)(dbutils.jobs.taskValues.get(taskKey='{name}', key='result'))"
```

**Recommended: Option A** — `dbutils.jobs.taskValues.get()` returns the object as-stored. The Lookup preparer already stores the result as a Python dict via `dbutils.jobs.taskValues.set(key='result', value=rows)`. No JSON round-trip needed.

### Test

```python
def test_activity_output_no_json_loads():
    """activity('X').output should NOT wrap in json.loads — taskValues stores objects natively."""
    resolved = get_literal_or_expression("@activity('Lookup').output.firstRow.col")
    assert "json.loads" not in resolved.code
    assert "taskValues.get" in resolved.code
```

---

## W-24: Residual type coercion gaps (19 pairs)

### What it is

W-18 fixed `greater/less` to wrap in `int()`. But 19 expressions still fail because:
1. `@greaterOrEquals` and `@lessOrEquals` were not covered by the W-18 fix
2. Nested math inside comparisons (e.g., `@greater(add(pipeline().parameters.a, 1), 10)`) coerces the inner `add()` result but not the outer comparison operands
3. `@equals` with a numeric literal on one side and a parameter on the other doesn't coerce

### Fix

**File:** `src/wkmigrate/parsers/expression_functions.py`

Ensure ALL comparison functions (`equals`, `not_equals`, `greater`, `greater_or_equals`, `less`, `less_or_equals`) apply the `_emit_numeric_binary_operator` path when either operand is numeric or a known-numeric expression.

### Test

```python
def test_greater_or_equals_coerces_parameter():
    resolved = get_literal_or_expression("@greaterOrEquals(pipeline().parameters.count, 10)")
    assert "int(" in resolved.code or "float(" in resolved.code
```

---

## W-25: Integer division (`div()` → `/` instead of `//`) (12 pairs)

### What it is

ADF `@div(a, b)` performs **integer division** (truncates toward zero). wkmigrate emits `(a / b)` which is **float division** in Python 3. The outer `int()` wrap from W-18 partially compensates but:
1. For very large numbers, float precision loss produces wrong results
2. The semantic intent is lost — `//` is the clear Python idiom for integer division

### Fix

**File:** `src/wkmigrate/parsers/expression_functions.py`

Change the `div` function emitter from `/` to `//`:

```python
# Current:
"div": lambda args: f"({args[0]} / {args[1]})" if len(args) == 2 else UnsupportedValue(...)

# Fix:
"div": lambda args: f"({args[0]} // {args[1]})" if len(args) == 2 else UnsupportedValue(...)
```

### Test

```python
def test_div_emits_integer_division():
    resolved = get_literal_or_expression("@div(10, 3)")
    assert "//" in resolved.code
    assert resolved.code.count("/") >= 2  # // has two slashes
```

---

## Execution Order

1. **W-25 (div → //) FIRST** — 1-line change, highest confidence, immediately verifiable
2. **W-23 (json.loads removal) SECOND** — small change but affects all activity-output expressions; need to verify Lookup preparer compatibility
3. **W-24 (coercion residuals) THIRD** — extend the W-18 fix to greaterOrEquals/lessOrEquals/equals

## Branch

```bash
git checkout pr/27-4-integration-tests  # current tip: 2c86a1b
```

Push to MiguelPeralvo/wkmigrate only. NEVER open a PR to ghanse/wkmigrate.

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| W25-1 | `@div(10, 3)` emits `//` not `/` | test passes |
| W23-1 | `@activity('X').output` does NOT emit `json.loads` | test passes |
| W24-1 | `@greaterOrEquals(param, 10)` coerces to numeric | test passes |
| OVERALL | set_variable X-2 score | > 0.85 (up from 0.812) |

## Verification

```bash
make test && make fmt

# From lmv repo:
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
source .env && export DATABRICKS_HOST DATABRICKS_TOKEN
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context set_variable \
  --model databricks-claude-sonnet-4-6 \
  --limit 30
# Target: overall > 0.85
```
