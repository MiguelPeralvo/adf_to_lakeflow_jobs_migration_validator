# CRP-8: DateTime Runtime Fixes (W-25 + W-27)

> Self-contained specification for /wkmigrate-autodev. Covers 2 runtime bugs in `datetime_helpers.py` discovered in the V4 deep validation. Together they affect 24 expressions across 7+ CRP0001 pipelines.

## Background

After V3 achieved 100% expression translation success (2,792/2,792), the V4 deep validation tested **semantic correctness** by executing generated Python expressions with mock values. Result: **99.5%** corrected success rate (2,778/2,792). Of the 14 real failures, **10 are W-25** (Windows timezone mapping) and **4 are W-27** (formatDateTime on string input). Both bugs are in `runtime/datetime_helpers.py`.

## What is CRP0001?

36 real ADF pipelines from Repsol covering BFC (batch forecasting), CMD (command execution), FCL (industrial forecasting), Arquetipo (orchestration framework), and operational logging groups. Repsol is located in Spain and uses `Romance Standard Time` (Windows timezone name for CET/CEST) in their ADF expressions.

## Branch Target

`pr/27-4-integration-tests` (or child branch). Depends on CRP-1 through CRP-6 already landed.

---

## W-25: Windows Timezone Mapping Gap -- P0

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/runtime/datetime_helpers.py`, lines 132-148.

The `convert_time_zone()` function passes timezone names directly to `ZoneInfo()`:

```python
def convert_time_zone(dt: datetime, source_tz: str, target_tz: str) -> datetime:
    """Convert a datetime between named time zones."""
    try:
        source_zone = ZoneInfo(source_tz)      # <-- no Windows→IANA mapping
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid source timezone '{source_tz}'") from exc
    try:
        target_zone = ZoneInfo(target_tz)      # <-- no Windows→IANA mapping
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid target timezone '{target_tz}'") from exc
```

The **docstring** (lines 36-38) explicitly claims Windows timezone support:
> "The helpers accept both Windows timezone IDs ('Pacific Standard Time') and IANA names ('America/Los_Angeles'). Windows IDs are translated to IANA via an internal mapping."

But **no mapping exists**. The docstring is aspirational; the implementation never delivered.

### CRP0001 Expressions Blocked (7 pipelines, 20 expressions)

**Hardcoded `Romance Standard Time`** (3 pipelines, 12 expressions):
- `crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal.json`
- `crp0001_c_pl_prc_anl_bfcdt_all_parallel_ppal_AMR.json`
- `crp0001_c_pl_prc_anl_cmd_all_paral_ppal.json`

**Pattern:**
```
@convertFromUtc(utcnow(),'Romance Standard Time','dd/MM/yyyy HH:mm')
@convertFromUtc(utcnow(),'Romance Standard Time','HH:mm')
```

**Hardcoded `Eastern Standard Time`** (synthetic corpus, 8 expressions).

**Parameterized timezone** (4 pipelines) — will also fail if parameter value is a Windows name:
```
@convertFromUtc(utcnow(), pipeline().parameters.target_timezone, ...)
@convertFromUtc(utcnow(), pipeline().parameters.timezone, 'yyyy-MM-dd HH:mm:ss')
```

### Generated Python That Fails

```python
_wkmigrate_format_datetime(
    _wkmigrate_convert_time_zone(_wkmigrate_utc_now(), 'UTC', 'Romance Standard Time'),
    'dd/MM/yyyy HH:mm'
)
```
Raises: `ValueError: Invalid target timezone 'Romance Standard Time'`

### Databricks Equivalent

IANA timezone `Europe/Madrid` is the correct mapping for `Romance Standard Time`. Python's `zoneinfo.ZoneInfo("Europe/Madrid")` handles CET/CEST transitions correctly.

### Implementation

Add a `_WINDOWS_TO_IANA` mapping dict and use it as a lookup before passing to `ZoneInfo`:

```python
# Place after the _ADF_TO_STRFTIME list (around line 64)

# Mapping of common Windows timezone IDs to IANA timezone names.
# ADF uses Windows timezone names (e.g., "Romance Standard Time") because
# Azure is built on .NET, which uses the Windows timezone database.
# Python's zoneinfo only supports IANA names, so we translate here.
# Source: https://learn.microsoft.com/en-us/windows-hardware/manufacture/desktop/default-time-zones
_WINDOWS_TO_IANA: dict[str, str] = {
    "Romance Standard Time": "Europe/Madrid",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central European Standard Time": "Europe/Warsaw",
    "Central Europe Standard Time": "Europe/Budapest",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Eastern Standard Time": "America/New_York",
    "Pacific Standard Time": "America/Los_Angeles",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Atlantic Standard Time": "America/Halifax",
    "US Mountain Standard Time": "America/Phoenix",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Alaskan Standard Time": "America/Anchorage",
    "China Standard Time": "Asia/Shanghai",
    "Tokyo Standard Time": "Asia/Tokyo",
    "India Standard Time": "Asia/Kolkata",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "New Zealand Standard Time": "Pacific/Auckland",
    "SA Pacific Standard Time": "America/Bogota",
    "Arabian Standard Time": "Asia/Dubai",
    "Russian Standard Time": "Europe/Moscow",
    "UTC": "UTC",
}


def _resolve_timezone(tz_name: str) -> str:
    """Resolve a timezone name to an IANA name, translating Windows IDs if needed."""
    return _WINDOWS_TO_IANA.get(tz_name, tz_name)
```

Then update `convert_time_zone()`:

```python
def convert_time_zone(dt: datetime, source_tz: str, target_tz: str) -> datetime:
    """Convert a datetime between named time zones."""
    try:
        source_zone = ZoneInfo(_resolve_timezone(source_tz))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid source timezone '{source_tz}'") from exc
    try:
        target_zone = ZoneInfo(_resolve_timezone(target_tz))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid target timezone '{target_tz}'") from exc

    if dt.tzinfo is None:
        localized = dt.replace(tzinfo=source_zone)
    else:
        localized = dt.astimezone(source_zone)

    return localized.astimezone(target_zone)
```

**Important:** The `_WINDOWS_TO_IANA` dict and `_resolve_timezone()` function must ALSO be included in the **inlined helpers** that get injected into generated notebooks (via `code_generator.py`'s `_INLINE_DATETIME_HELPERS`). Otherwise the fix only works when `wkmigrate` is installed, not at notebook runtime.

### Inline Helper Update

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/code_generator.py`

Find where `_INLINE_DATETIME_HELPERS` is defined and ensure the inlined source includes:
1. The `_WINDOWS_TO_IANA` dict
2. The `_resolve_timezone()` helper
3. Updated `convert_time_zone()` using `_resolve_timezone()`

---

## W-27: `formatDateTime` on String Input -- P1

### Root Cause

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/runtime/datetime_helpers.py`, lines 73-111.

`format_datetime()` calls `dt.strftime()` directly on its first argument:

```python
def format_datetime(dt: datetime, adf_format: str) -> str:
    """Format datetime using ADF/.NET style format tokens."""
    working_format = adf_format
    # ... token translation ...
    formatted = dt.strftime(working_format)    # <-- assumes dt is datetime, fails on str
```

ADF's `formatDateTime()` accepts both datetime objects AND ISO 8601 date strings. When wkmigrate translates `@formatDateTime(pipeline().parameters.dataDate, 'yyyy/MM/dd')`, the Python output is:

```python
_wkmigrate_format_datetime(dbutils.widgets.get('dataDate'), 'yyyy/MM/dd')
```

`dbutils.widgets.get()` returns a **string** (e.g., `"2026-04-13T00:00:00"`), not a datetime. The `.strftime()` call raises `AttributeError: 'str' object has no attribute 'strftime'`.

### CRP0001 Expressions Blocked (4 expressions)

Pattern:
```
@if(empty(pipeline().parameters.dataDate), '', formatDateTime(pipeline().parameters.dataDate, 'yyyy/MM/dd'))
```

Pipelines: `crp0001_c_pl_prc_anl_persist_global.json` and variants.

### Databricks Equivalent

ADF `formatDateTime` auto-parses ISO 8601 strings. The Python equivalent should do:
```python
from datetime import datetime
dt = datetime.fromisoformat(input_value) if isinstance(input_value, str) else input_value
```

### Implementation

Add string auto-parsing to `format_datetime()`:

```python
def format_datetime(dt: datetime | str, adf_format: str) -> str:
    """Format datetime using ADF/.NET style format tokens.

    Accepts both datetime objects and ISO 8601 date strings (ADF behavior).
    """
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)

    working_format = adf_format
    # ... rest unchanged ...
```

**Note:** `datetime.fromisoformat()` is available in Python 3.7+ and handles most ISO 8601 formats including `2026-04-13`, `2026-04-13T14:30:00`, and `2026-04-13T14:30:00Z` (Python 3.11+). For broader compatibility, strip trailing `Z` before parsing:

```python
if isinstance(dt, str):
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    dt = datetime.fromisoformat(dt)
```

---

## Files to Modify

| # | File | Action | Findings |
|---|------|--------|----------|
| 1 | `src/wkmigrate/runtime/datetime_helpers.py` | **MODIFY** | W-25 (add `_WINDOWS_TO_IANA` + `_resolve_timezone()`, update `convert_time_zone()`), W-27 (add string parsing to `format_datetime()`) |
| 2 | `src/wkmigrate/code_generator.py` | **MODIFY** | W-25 (update inlined helpers to include `_WINDOWS_TO_IANA` + `_resolve_timezone()`) |

**No new files needed.**

## Test Strategy

### Unit Tests (datetime-level)

**W-25:**
```python
from wkmigrate.runtime.datetime_helpers import convert_time_zone
from datetime import datetime, timezone

dt = datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc)

# Windows timezone names should now work
result = convert_time_zone(dt, "UTC", "Romance Standard Time")
assert result.hour == 16  # CEST = UTC+2 in April

result = convert_time_zone(dt, "UTC", "Eastern Standard Time")
assert result.hour == 10  # EDT = UTC-4 in April

result = convert_time_zone(dt, "UTC", "Pacific Standard Time")
assert result.hour == 7  # PDT = UTC-7 in April

# IANA names should still work (regression check)
result = convert_time_zone(dt, "UTC", "Europe/Madrid")
assert result.hour == 16

# Unknown timezone should still raise ValueError
try:
    convert_time_zone(dt, "UTC", "Nonexistent Time")
    assert False, "Should have raised ValueError"
except ValueError:
    pass
```

**W-27:**
```python
from wkmigrate.runtime.datetime_helpers import format_datetime

# String input (ISO 8601)
result = format_datetime("2026-04-13T14:30:00", "yyyy/MM/dd")
assert result == "2026/04/13"

# String with Z suffix
result = format_datetime("2026-04-13T14:30:00Z", "yyyy-MM-dd HH:mm:ss")
assert result == "2026-04-13 14:30:00"

# Date-only string
result = format_datetime("2026-04-13", "yyyy/MM/dd")
assert result == "2026/04/13"

# datetime object should still work (regression check)
from datetime import datetime, timezone
dt = datetime(2026, 4, 13, 14, 30, 0, tzinfo=timezone.utc)
result = format_datetime(dt, "yyyy-MM-dd")
assert result == "2026-04-13"
```

### Integration Tests

Update CRP0001 integration tests with:
- `@convertFromUtc(utcnow(), 'Romance Standard Time', 'dd/MM/yyyy HH:mm')` — should now produce valid Python
- `@formatDateTime(pipeline().parameters.dataDate, 'yyyy/MM/dd')` — should handle string input

## Implementation Order

1. **W-25** (P0) — Windows timezone mapping. Higher severity, more expressions affected.
2. **W-27** (P1) — String parsing in formatDateTime. Quick fix, fewer expressions.

## Expected Impact

| Metric | Current (V4) | After CRP-8 |
|--------|-------------|-------------|
| Semantic correctness | 99.5% (14 real bugs) | **100%** (0 real bugs in datetime) |
| Runtime failures on CRP0001 notebooks | 24 expressions | **0** |
| Windows TZ support | 0/5 names | **23/23 common names** |
| formatDateTime on string | fails | **works** |

## Workflow Notes

- **Base branch:** `pr/27-4-integration-tests`
- **Feature branch:** `feature/crp8-datetime-runtime-fixes`
- **PR target:** `pr/27-4-integration-tests` at `MiguelPeralvo/wkmigrate`
- **Build system:** `uv` via Makefile -- `make test` (unit), `make fmt` (lint)
- **Critical:** The inlined helpers in `code_generator.py` MUST be updated alongside `datetime_helpers.py`. Generated notebooks use the inlined version, not the installed package.
