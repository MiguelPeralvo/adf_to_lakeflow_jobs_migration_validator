# ADF Expression Syntax and Semantics

> Last updated: 2026-04-11

## Expression Grammar

ADF expressions use `@` prefix for top-level invocations and parenthesised function calls:

```
expression   ::= '@' function_call
               | '@' property_access
function_call ::= name '(' args ')'
args          ::= expression (',' expression)*
property_access ::= object '.' property ('.' property)*
object        ::= 'pipeline()' | 'activity(' string ')' | 'variables(' string ')'
                | 'dataset()' | 'linkedService()'
```

## Type System

| ADF Type | Runtime Representation | Coercion Rules |
|----------|----------------------|----------------|
| String | UTF-16 string | Auto-coerced by `concat()`, `replace()`, etc. |
| Int | 64-bit signed integer | String to int via `int()`, float truncation via `int()` |
| Float | 64-bit double | String to float via `float()` |
| Bool | `true`/`false` literals | Truthy: non-zero, non-empty. `bool()` explicit. |
| Array | JSON array | Created via `createArray()`, `split()` |
| Object | JSON object | Created via `json()`, accessed via `.property` |
| Null | `null` literal | Propagates through most functions (except `coalesce`) |

## Critical Semantics

### 1. Auto-coercion in string functions
`concat(1, 'a')` is VALID in ADF — it auto-coerces `1` to `"1"`. Python translation MUST include `str()` wrapping:
```python
# Correct
str(1) + str('a')
# Wrong — TypeError at runtime
1 + 'a'
```

### 2. Parameter references always return strings
`pipeline().parameters.X` always returns a string from `dbutils.widgets.get('X')`. Math operations MUST coerce:
```python
# ADF: @add(pipeline().parameters.count, 1)
# Correct
(int(dbutils.widgets.get('count')) + 1)
# Wrong — concatenation, not addition
(dbutils.widgets.get('count') + 1)
```

### 3. Division semantics
ADF `div(a, b)` performs integer division (floor). Python `/` is float division:
```python
# ADF: @div(9, 2) = 4
# Correct
int(9 / 2)  # or 9 // 2
# Wrong
9 / 2  # = 4.5
```

### 4. Null propagation
Most ADF functions return null if ANY argument is null (except `coalesce`, `if`, `equals`):
```python
# ADF: @concat(null, 'x') = null
# This is different from Python str(None) + 'x' = 'Nonex'
```

### 5. Activity output access patterns
```
@activity('LookupStep').output.firstRow.columnName
@activity('ForEachStep').output.count
@activity('WebActivity').output.statusCode
```
These resolve at runtime to the previous activity's output. In Databricks, they map to task values or shared state.

## Expression Categories (for golden sets)

| Category | Example | Key Challenge |
|----------|---------|---------------|
| string | `@concat('a', toUpper('b'))` | Auto-coercion, multi-arg |
| math | `@add(mul(param, 2), 1)` | Type coercion from widget strings |
| datetime | `@formatDateTime(utcNow(), 'yyyy-MM-dd')` | Format token mapping |
| logical | `@and(greater(x, 0), not(equals(y, null)))` | Short-circuit semantics |
| collection | `@createArray(1, 2, 3)` | Array construction, `first()`/`last()` |
| nested | `@if(equals(mod(length(x),2),0),'even','odd')` | Deep nesting, evaluation order |
| parameter | `@pipeline().parameters.env` | Widget coercion, type safety |

## Functions Reference (Top 30 by frequency in production pipelines)

| ADF Function | Python Equivalent | Notes |
|-------------|-------------------|-------|
| `concat(a, b, ...)` | `str(a) + str(b) + ...` | Variadic, auto-coerces |
| `replace(s, old, new)` | `str(s).replace(old, new)` | |
| `toUpper(s)` | `str(s).upper()` | |
| `toLower(s)` | `str(s).lower()` | |
| `trim(s)` | `str(s).strip()` | |
| `substring(s, start, len)` | `str(s)[start:start+len]` | 0-indexed |
| `indexOf(s, sub)` | `str(s).find(sub)` | Returns -1 if not found |
| `add(a, b)` | `(a + b)` | Integer arithmetic |
| `sub(a, b)` | `(a - b)` | |
| `mul(a, b)` | `(a * b)` | |
| `div(a, b)` | `int(a / b)` | Integer division! |
| `mod(a, b)` | `(a % b)` | |
| `equals(a, b)` | `(a == b)` | |
| `greater(a, b)` | `(a > b)` | |
| `less(a, b)` | `(a < b)` | |
| `and(a, b)` | `(a and b)` | |
| `or(a, b)` | `(a or b)` | |
| `not(a)` | `(not a)` | |
| `if(cond, t, f)` | `(t if cond else f)` | |
| `coalesce(a, b, ...)` | `next(v for v in [a,b,...] if v is not None)` | |
| `createArray(...)` | `[...]` | |
| `length(x)` | `len(x)` | Works on strings and arrays |
| `first(arr)` | `arr[0]` | |
| `last(arr)` | `arr[-1]` | |
| `split(s, delim)` | `str(s).split(delim)` | |
| `join(arr, delim)` | `delim.join(arr)` | |
| `formatDateTime(dt, fmt)` | `_wkmigrate_format_datetime(dt, fmt)` | Custom helper |
| `utcNow()` | `_wkmigrate_utc_now()` | Custom helper |
| `pipeline().parameters.X` | `dbutils.widgets.get('X')` | Always string! |
| `int(s)` | `int(s)` | |
| `float(s)` | `float(s)` | |
| `string(x)` | `str(x)` | |
| `bool(x)` | `bool(x)` | |
