# wkmigrate Fix Spec: W-20 — Robustness Gaps Discovered by LLM-Generated Pipelines

> Self-contained specification for /wkmigrate-autodev. LLM-generated synthetic pipelines (175 via `lmv synthetic --mode llm` across 7 presets) crash wkmigrate at a 39% rate (68/175). Three root causes dominate.

## Evidence

175 LLM-generated pipelines (7 presets × 25 each) evaluated via `lmv batch` against `pr/27-4-integration-tests@3aaa16e`:

| Metric | Value |
|--------|-------|
| Evaluated successfully | 107/175 (61%) |
| Crashed | 68/175 (39%) |
| Mean CCS (of successful) | 88.6 |
| Below 70 threshold | 10 |

Full results: `golden_sets/batch_results_175_pipelines.json` in the lmv repo.

---

## W-20a: `_parse_policy` crashes on Expression-typed `retry` and non-numeric `timeout`

### What it is

`activity_translator.py:421` calls `int(retry_value)` directly. When `retry` is:
- An ADF Expression dict `{"type": "Expression", "value": "@pipeline().parameters.retry_count"}` → `int(dict)` → **TypeError**
- A raw expression string `"@pipeline().parameters.retry_count"` → `int(string)` → **ValueError**

Similarly, `activity_translator.py:416` calls `parse_timeout_string(timeout_value)` which expects a string like `"0.00:30:00"`. When `timeout` is an integer `30` → `_TIMEOUT_PATTERN.match(30)` → **TypeError**.

### Impact

39% of LLM-generated pipelines (68/175) crashed on this path. In real-world ADF pipelines, `policy.retry` as an Expression reference is a **valid ADF pattern** — it lets pipelines parameterize their retry count.

### Where to fix

**File:** `src/wkmigrate/translators/activity_translators/activity_translator.py`

**`_parse_policy` function (~line 410-430):**

```python
# Current (fragile):
parsed_policy["max_retries"] = int(retry_value)

# Fix:
if isinstance(retry_value, (int, float)):
    parsed_policy["max_retries"] = int(retry_value)
elif isinstance(retry_value, str) and retry_value.strip().lstrip('-').isdigit():
    parsed_policy["max_retries"] = int(retry_value)
elif isinstance(retry_value, dict) and retry_value.get("type") == "Expression":
    # Expression-typed retry — resolve via get_literal_or_expression or default
    parsed_policy["max_retries"] = 3  # safe default; log warning
else:
    parsed_policy["max_retries"] = 3  # safe default
```

Same pattern for `timeout`:
```python
# Current (fragile):
parsed_policy["timeout_seconds"] = parse_timeout_string(timeout_value)

# Fix:
if isinstance(timeout_value, (int, float)):
    parsed_policy["timeout_seconds"] = int(timeout_value)
elif isinstance(timeout_value, str):
    parsed_policy["timeout_seconds"] = parse_timeout_string(timeout_value)
else:
    parsed_policy["timeout_seconds"] = 300  # 5 min default
```

And `retry_interval_in_seconds`:
```python
# Same pattern — guard against non-numeric values
```

### Test cases

```python
def test_parse_policy_expression_typed_retry():
    policy = {"retry": {"type": "Expression", "value": "@pipeline().parameters.retryCount"}}
    result = _parse_policy(policy)
    assert result["max_retries"] == 3  # safe default, no crash

def test_parse_policy_string_expression_retry():
    policy = {"retry": "@pipeline().parameters.retryCount"}
    result = _parse_policy(policy)
    assert result["max_retries"] == 3  # safe default, no crash

def test_parse_policy_integer_timeout():
    policy = {"timeout": 30}
    result = _parse_policy(policy)
    assert result["timeout_seconds"] == 30

def test_parse_policy_expression_timeout():
    policy = {"timeout": {"type": "Expression", "value": "@pipeline().parameters.timeout"}}
    result = _parse_policy(policy)
    assert result["timeout_seconds"] == 300  # safe default
```

---

## W-20b: Copy/Lookup translators crash on missing `dataset_definitions`

### What it is

`copy_activity_translator.py` and `lookup_activity_translator.py` call `get_data_source_definition(get_value_or_unsupported(activity, "input_dataset_definitions"))` which raises `ValueError("Dataset definition or properties missing")` when the key is absent or the value is not a list.

LLM-generated Copy activities sometimes omit `input_dataset_definitions` / `output_dataset_definitions` entirely (the LLM generates the Copy with `source` and `sink` type properties but no linked dataset definitions).

### Impact

Every Copy/Lookup activity without properly structured dataset definitions crashes the entire pipeline translation.

### Where to fix

**File:** `src/wkmigrate/translators/activity_translators/copy_activity_translator.py` (~line 39-45)
**File:** `src/wkmigrate/translators/activity_translators/lookup_activity_translator.py` (same pattern)

The fix is to return `UnsupportedValue` (the existing error convention) instead of raising `ValueError`:

```python
# Current (raises):
source_dataset = get_data_source_definition(get_value_or_unsupported(activity, "input_dataset_definitions"))
if isinstance(source_dataset, UnsupportedValue):
    return UnsupportedValue(value=activity, message=f"Could not translate copy activity. {source_dataset.message}")

# Fix: ensure get_data_source_definition handles None/missing gracefully
# OR catch ValueError and convert to UnsupportedValue
```

Actually, the real fix is in `utils.py:get_data_source_definition` — it should return `UnsupportedValue` when the input is None/missing, not raise.

### Test cases

```python
def test_copy_activity_missing_datasets_returns_unsupported():
    activity = {"source": {"type": "AzureSqlSource"}, "sink": {"type": "AzureSqlSink"}}
    result = translate_copy_activity(activity, base_kwargs)
    assert isinstance(result, UnsupportedValue)
    # NOT a ValueError/crash

def test_lookup_activity_missing_datasets_returns_unsupported():
    activity = {"source": {"type": "AzureSqlSource"}}
    result = translate_lookup_activity(activity, base_kwargs)
    assert isinstance(result, UnsupportedValue)
```

---

## W-20c: Pipeline format normalization gap — `typeProperties` not unwrapped

### What it is

LLM-generated pipelines use the Azure REST API format where activity properties are nested inside `typeProperties`:
```json
{"name": "SetVar", "type": "SetVariable", "typeProperties": {"variable_name": "result", "value": "..."}}
```

But wkmigrate's translators expect the flattened SDK format:
```json
{"name": "SetVar", "type": "SetVariable", "variable_name": "result", "value": "..."}
```

The pipeline-level `properties` envelope is handled by `unwrap_adf_pipeline()`, but **activity-level `typeProperties` is NOT unwrapped** anywhere in the translation chain.

### Impact

Any ADF pipeline in the Azure REST API format (which is what `az datafactory pipeline show` returns) will have 0% activity_coverage because all activity properties are invisible inside `typeProperties`.

### Where to fix

**File:** `src/wkmigrate/translators/activity_translators/activity_translator.py`

Add a normalization step in `_dispatch_activity` or `translate_activities`:

```python
def _normalize_activity(activity: dict) -> dict:
    """Flatten typeProperties into the activity root, matching SDK format."""
    if "typeProperties" not in activity:
        return activity
    normalized = {k: v for k, v in activity.items() if k != "typeProperties"}
    normalized.update(activity["typeProperties"])
    return normalized
```

Call it before dispatching each activity.

### Test cases

```python
def test_normalize_activity_flattens_type_properties():
    act = {"name": "SetVar", "type": "SetVariable", 
           "typeProperties": {"variable_name": "x", "value": "hello"}}
    result = _normalize_activity(act)
    assert result["variable_name"] == "x"
    assert result["value"] == "hello"
    assert "typeProperties" not in result

def test_normalize_activity_preserves_flat_format():
    act = {"name": "SetVar", "type": "SetVariable", "variable_name": "x"}
    result = _normalize_activity(act)
    assert result == act  # unchanged
```

---

## Execution Order

1. **W-20a (_parse_policy robustness) FIRST** — highest impact (39% crash rate), simplest fix (type guards + defaults)
2. **W-20c (typeProperties normalization) SECOND** — unlocks all LLM-generated and Azure API-format pipelines for evaluation
3. **W-20b (missing datasets → UnsupportedValue) THIRD** — correctness fix, converts crashes to graceful degradation

## Branch Strategy

```bash
cd /Users/miguel/Code/wkmigrate
git checkout pr/27-4-integration-tests
git checkout -b pr/27-9-robustness-fixes
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3..4 | Lint compliance | 0 |
| W20-1 | `_parse_policy` handles Expression dict retry without crash | test passes |
| W20-2 | `_parse_policy` handles string expression retry without crash | test passes |
| W20-3 | `_parse_policy` handles integer timeout without crash | test passes |
| W20-4 | Copy with missing datasets returns UnsupportedValue, not crash | test passes |
| W20-5 | typeProperties-wrapped activities are normalized before dispatch | test passes |
| OVERALL | lmv batch mean CCS on 175 LLM-generated pipelines | > 85.0 (up from 88.6 on 107 evaluated; but 175/175 should evaluate) |
| CRASH-RATE | Crash rate on 175 pipelines | < 5% (down from 39%) |

## Verification

```bash
cd /Users/miguel/Code/wkmigrate
make test   # GR-1, GR-2
make fmt    # GR-3, GR-4

# From lmv repo:
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
PYTHONPATH=src poetry run python3 -c "
import json, sys
from lakeflow_migration_validator.adapters.wkmigrate_adapter import adf_to_snapshot
from lakeflow_migration_validator import evaluate

with open('golden_sets/big_pipeline_corpus.json') as f:
    corpus = json.load(f)
errors = 0
scores = []
for p in corpus['pipelines']:
    try:
        snap = adf_to_snapshot(p['adf_json'])
        sc = evaluate(snap)
        scores.append(sc.score)
    except:
        errors += 1
print(f'Evaluated: {len(scores)}/{len(corpus[\"pipelines\"])}')
print(f'Errors: {errors} ({errors/len(corpus[\"pipelines\"])*100:.0f}%)')
print(f'Mean CCS: {sum(scores)/len(scores):.1f}' if scores else 'N/A')
"
# Target: errors < 9 (< 5%), mean CCS > 85
```
