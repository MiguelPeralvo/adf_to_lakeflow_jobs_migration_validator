# wkmigrate Architecture

> Last updated: 2026-04-11

## Overview

wkmigrate is a Python library that converts Azure Data Factory (ADF) pipeline JSON into Databricks Lakeflow Jobs notebooks. It lives at `ghanse/wkmigrate` (upstream) and `MiguelPeralvo/wkmigrate` (fork).

## Core Design: Immutable IR

```
ADF JSON → [Parsers] → IR (frozen dataclasses) → [Translators] → Notebooks (Python code strings)
```

Every intermediate type is `@dataclass(frozen=True, slots=True)`. No mutation anywhere.

## Key Components

### 1. Parsers (`src/wkmigrate/parsers/`)

Parse raw ADF JSON into typed IR objects:
- `pipeline_parser.py` — top-level pipeline structure
- `activity_parsers.py` — per-activity-type parsing (Notebook, Copy, Lookup, ForEach, IfCondition, etc.)
- `dataset_parsers.py` — dataset/linked service references
- `expression_parsers.py` — ADF expression string → AST nodes (the #27 target)

### 2. Translators (`src/wkmigrate/translators/`)

Convert IR into Python notebook code:
- `notebook_translator.py` — main entry point
- `activity_translators/` — per-type translation (one module per activity type)
- `expression_emitter.py` — AST → Python code string (the #27 output)
- `parameter_translator.py` — pipeline parameters → `dbutils.widgets.get()` calls

### 3. Expression Pipeline (Issue #27)

```
ADF expression string
  → ExpressionParser.parse() → ExpressionAST (tree of nodes)
  → PythonEmitter.emit() → Python code string
```

Key types in the expression AST:
- `FunctionCall(name, args)` — e.g., `concat`, `add`, `toUpper`
- `PropertyAccess(object, path)` — e.g., `pipeline().parameters.X`
- `Literal(value, type)` — strings, ints, bools, null
- `ActivityOutput(activity_name, path)` — `activity('X').output.Y`

### 4. The `get_literal_or_expression()` Pattern

This is the critical pattern for #27 adoption. Before #27:
```python
# Old pattern — loses expression info
value = source.get("someProperty", "")
```

After #27:
```python
# New pattern — preserves and translates expressions
from wkmigrate.parsers.expression_parsers import get_literal_or_expression
value = get_literal_or_expression(source, "someProperty", context)
# Returns: literal string if no expression, or translated Python if expression
```

Adoption status (as of alpha_1):
- SetVariable: ADOPTED (pr/27-1)
- DatabricksNotebook base params: ADOPTED
- Lookup source.query: PARTIALLY (pr/27-3 target)
- Copy source.sql_reader_query: NOT ADOPTED (W-9)
- ForEach items: NOT ADOPTED (W-10)
- IfCondition predicate: ADOPTED
- WebActivity body: NOT ADOPTED

### 5. Config Threading

`TranslationContext` is a frozen dataclass threaded through all translation functions:
```python
@dataclass(frozen=True, slots=True)
class TranslationContext:
    pipeline_name: str
    parameters: dict[str, dict]
    variables: dict[str, dict]
    # ... more fields
```

PR review pattern: if a new config field is needed, it MUST be added to `TranslationContext` and threaded through ALL layers. Half-threaded config is a P1 review finding.

### 6. Warning Infrastructure

When translation is impossible, wkmigrate emits:
```python
import warnings
warnings.warn(
    NotTranslatableWarning("Could not translate expression: ..."),
    stacklevel=2,
)
# Returns UnsupportedValue sentinel — not an exception
return UnsupportedValue(reason="...", original_value="...")
```

lmv captures these via `pytest.warns` in tests and via the adapter's `all_not_translatable` tuple.

## Branch Map (as of 2026-04-11)

| Branch | Purpose | Status |
|--------|---------|--------|
| `main` | ghanse's stable trunk | Upstream |
| `alpha` | MiguelPeralvo's integration branch | Active |
| `alpha_1` | Extended development (needs rebuild on pr/27-4) | Stale — DO NOT BASE NEW WORK HERE |
| `pr/27-0..4` | Canonical #27 implementation chain | CANONICAL |
| `feature/27-phase*` | Abandoned parallel implementation | ABANDONED (tagged) |

## How lmv Interfaces with wkmigrate

lmv's ONLY touchpoint is `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py`:
```python
from wkmigrate.models.pipeline import PreparedWorkflow
from wkmigrate.translate import translate_pipeline

def adf_to_snapshot(adf_json: dict) -> ConversionSnapshot:
    """The one function that bridges wkmigrate → lmv contract."""
    ...
```

This is the LA-1 invariant. No other file in lmv imports wkmigrate.
