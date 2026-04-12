# W-27: Missing DateTime & Utility Functions

## Context

After W-23 through W-26 fixes, the current wkmigrate correctly handles:
- Activity output property chains (`['firstRow']['col']`) — no `json.loads` wrapping
- Numeric coercion for pipeline parameter comparisons
- IfCondition string quoting and `not(equals(...))` fallback

Only 2 out of 200 expression corpus entries hit genuinely unsupported functions.
The X-2 semantic eval results are stale (pre-W-23) and need re-running.

## Unsupported Functions to Add

### Tier 1: DateTime functions (high value — used in real pipelines)

| ADF Function | Python Equivalent | Notes |
|---|---|---|
| `@dayOfWeek(dt)` | `_wkmigrate_day_of_week(dt)` | Returns 1-7 (Sun-Sat) per ADF convention |
| `@dayOfMonth(dt)` | `_wkmigrate_day_of_month(dt)` | Returns 1-31 |
| `@dayOfYear(dt)` | `_wkmigrate_day_of_year(dt)` | Returns 1-366 |
| `@addMinutes(dt, n)` | `_wkmigrate_add_minutes(dt, n)` | Follows addDays/addHours pattern |
| `@addSeconds(dt, n)` | `_wkmigrate_add_seconds(dt, n)` | Follows addDays/addHours pattern |
| `@ticks(dt)` | `_wkmigrate_ticks(dt)` | .NET ticks: 100-ns intervals since 0001-01-01 |

### Tier 2: Utility functions (lower priority — rare in pipelines)

| ADF Function | Python Equivalent | Notes |
|---|---|---|
| `@guid()` | `str(uuid.uuid4())` | Random UUID |
| `@rand(min, max)` | `random.randint(min, max)` | Random integer |
| `@base64(s)` | `base64.b64encode(s.encode()).decode()` | Base64 encode |
| `@base64ToString(s)` | `base64.b64decode(s).decode()` | Base64 decode |
| `@nthIndexOf(s, search, n)` | Custom helper | nth occurrence |

## Implementation Pattern

Follow existing helpers pattern (`_wkmigrate_format_datetime`, `_wkmigrate_utc_now`, `_wkmigrate_add_days`, `_wkmigrate_add_hours`, `_wkmigrate_start_of_day`, `_wkmigrate_convert_time_zone`):

1. Add emitter functions in `expression_functions.py`
2. Register in `FUNCTION_REGISTRY` (lowercase keys)
3. Add unit tests in `tests/unit/test_expression_parsers.py`
4. Runtime helpers go in the generated notebook preamble

## Files to Modify

- `src/wkmigrate/parsers/expression_functions.py` — add emitters + registry entries
- `tests/unit/test_expression_parsers.py` — new test cases
- `tests/resources/expressions/` — any new fixture data

## Acceptance Criteria

- All Tier 1 functions emit valid Python (not `UnsupportedValue`)
- Existing tests pass (`make test`)
- `make fmt` clean
