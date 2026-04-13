# CRP-2: Optional Chaining (`?.`) Tokenizer + Parser + Emitter

> Self-contained specification for /wkmigrate-autodev. Covers G-1 — the `?.` optional chaining operator that blocks 5 arquetipo pipelines.

## Background: What is wkmigrate?

wkmigrate (`ghanse/wkmigrate`, fork at `MiguelPeralvo/wkmigrate`) converts ADF pipeline JSON into Databricks Lakeflow Jobs. The expression system pipeline is:

1. **Tokenizer** (`parsers/expression_tokenizer.py`): source string → `list[Token]` (12 token types)
2. **Parser** (`parsers/expression_parser.py`): tokens → typed AST (8 node types)
3. **AST** (`parsers/expression_ast.py`): `PropertyAccess(target, property_name)` etc.
4. **Emitter** (`parsers/expression_emitter.py`): AST → Python code string

## What is CRP0001?

CRP0001 is 36 real ADF pipeline files from Repsol. The Arquetipo group (orchestration framework) uses `item()?.property` extensively — a JavaScript-like optional chaining syntax that ADF supports natively.

## Branch Target

`pr/27-4-integration-tests` (or child branch).

---

## G-1: `?.` Optional Chaining — P0 BLOCKER

### Problem

The tokenizer has 12 token types. The `?` character is not in `_SINGLE_CHAR_TOKENS` and is not alphanumeric, so when encountered:

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_tokenizer.py`, end of main while loop (~line 108):
```python
return UnsupportedValue(
    value=expression,
    message=f"Unsupported token '{char}' at position {idx}",
)
```

The entire expression fails to tokenize.

### CRP0001 Expressions Blocked (5 arquetipo pipelines)

These appear in `lakeh_a_pl_arquetipo_internal.json`, `lakeh_a_pl_arquetipo_nested_internal.json`, `lakeh_a_pl_arquetipo_nested_par_internal.json`, `lakeh_a_pl_arquetipo_switch_internal.json`, `lakeh_a_pl_arquetipo_switch2_internal.json`:

1. `@if(equals(string(coalesce(item()?.condition, 'notFound')), 'notFound'), 'true', string(item()?.condition))`
2. `@string(union(json(if(startswith(string(coalesce(item()?.condition, 'notFound')), 'notFound'), '[]', string(item()?.condition))), json(string(variables('outputs')))))`
3. `@coalesce(item()?.condition?.name, 'name_notFound')`
4. `@coalesce(item()?.type, 'default')` — Switch routing
5. `@coalesce(item()?.aux_params, '{}')` — nested pipeline params
6. `@coalesce(item()?.name, 'no_name')` — Trace Condition
7. `@toUpper(coalesce(item()?.type, 'DEFAULT'))` — Switch activity on expression

### ADF Semantics of `?.`

In ADF expressions, `x?.prop` means:
- If `x` is `null` or does not have property `prop`, return `null`
- Otherwise, return `x.prop`

This is semantically equivalent to JavaScript's `?.` operator. It is commonly used with `item()` in ForEach loops where each item may be a dict with optional keys.

### Fix: 4 Files Changed

#### Step 1: Tokenizer — Add `OPTIONAL_DOT` token

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_tokenizer.py`

Add to `TokenType` enum:
```python
class TokenType(StrEnum):
    STRING = "STRING"
    NUMBER = "NUMBER"
    BOOL = "BOOL"
    NULL = "NULL"
    IDENT = "IDENT"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    LBRACKET = "LBRACKET"
    RBRACKET = "RBRACKET"
    COMMA = "COMMA"
    DOT = "DOT"
    OPTIONAL_DOT = "OPTIONAL_DOT"  # NEW: ?.
    EOF = "EOF"
```

In the `tokenize()` main while loop, before the final `return UnsupportedValue(...)`, add:
```python
# Handle ?. (optional chaining)
if char == "?" and idx + 1 < length and expression[idx + 1] == ".":
    tokens.append(Token(token_type=TokenType.OPTIONAL_DOT, value="?.", position=idx))
    idx += 2
    continue
```

This must be placed BEFORE the fallback error at the end of the loop. The peek-ahead ensures that a lone `?` still returns `UnsupportedValue`.

#### Step 2: AST — No new node needed

Reuse `PropertyAccess` but add an `optional: bool` field:

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_ast.py`

```python
@dataclass(frozen=True, slots=True)
class PropertyAccess:
    """Property access expression (``target.property`` or ``target?.property``)."""

    target: "AstNode"
    property_name: str
    optional: bool = False
```

The default `False` preserves backward compatibility — all existing `PropertyAccess(target=x, property_name=y)` constructions continue to work.

Update the `AstNode` type alias — no change needed since `PropertyAccess` is already in the union.

#### Step 3: Parser — Handle `OPTIONAL_DOT` in postfix loop

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_parser.py`, method `_parse_expression` (~line 235)

Current code:
```python
while True:
    token = self._current()
    if token.token_type == TokenType.DOT:
        self._advance()
        identifier = self._consume(TokenType.IDENT, "Expected property name after '.'")
        if isinstance(identifier, UnsupportedValue):
            return identifier
        primary = PropertyAccess(target=primary, property_name=str(identifier.value))
        continue
    # ... LBRACKET handling ...
    break
```

Add an `OPTIONAL_DOT` case immediately after the `DOT` case:
```python
while True:
    token = self._current()
    if token.token_type == TokenType.DOT:
        self._advance()
        identifier = self._consume(TokenType.IDENT, "Expected property name after '.'")
        if isinstance(identifier, UnsupportedValue):
            return identifier
        primary = PropertyAccess(target=primary, property_name=str(identifier.value))
        continue

    # NEW: Optional chaining (?.)
    if token.token_type == TokenType.OPTIONAL_DOT:
        self._advance()
        identifier = self._consume(TokenType.IDENT, "Expected property name after '?.'")
        if isinstance(identifier, UnsupportedValue):
            return identifier
        primary = PropertyAccess(target=primary, property_name=str(identifier.value), optional=True)
        continue

    if token.token_type == TokenType.LBRACKET:
        # ... unchanged ...
```

Also add the import:
```python
from wkmigrate.parsers.expression_tokenizer import Token, TokenType, tokenize
```
(Already imports `TokenType`, just needs `OPTIONAL_DOT` to be defined there.)

#### Step 4: Emitter — Null-safe property access for optional nodes

**File:** `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py`, method `_emit_property_access` (~line 148)

Current code processes `PropertyAccess` nodes by flattening the chain and checking if the root is `pipeline()` or `activity()`. For optional access, the emitter needs a null-safe pattern.

Modify `_emit_property_access` to check the `optional` flag:

```python
def _emit_property_access(self, node: PropertyAccess) -> str | UnsupportedValue:
    """Emit property access chain."""

    root, properties = _flatten_property_chain(node)

    if isinstance(root, FunctionCall):
        lowered = root.name.lower()
        if lowered == "pipeline":
            return self._emit_pipeline_property_access(root, properties)
        if lowered == "activity":
            return self._emit_activity_property_access(root, properties, index_segments=[])

    root_result = self.emit_node(root)
    if isinstance(root_result, UnsupportedValue):
        return root_result

    code = root_result.code
    for property_name in properties:
        code = f"({code})[{property_name!r}]"
    return code
```

The issue is that `_flatten_property_chain` loses the `optional` flag. We need to update it to preserve optionality, or handle optional access in the chain builder.

**Recommended approach:** Modify `_flatten_property_chain` to return optionality info:

```python
def _flatten_property_chain(node: PropertyAccess) -> tuple[AstNode, list[tuple[str, bool]]]:
    """Flatten nested property-access AST to ``(root, [(prop1, optional1), ...])``."""

    properties: list[tuple[str, bool]] = []
    current: AstNode = node

    while isinstance(current, PropertyAccess):
        properties.append((current.property_name, current.optional))
        current = current.target

    properties.reverse()
    return current, properties
```

Then update `_emit_property_access` to use null-safe access for optional properties:

```python
def _emit_property_access(self, node: PropertyAccess) -> str | UnsupportedValue:
    root, properties = _flatten_property_chain(node)

    # Extract just names for pipeline/activity dispatch (they don't use ?.)
    prop_names = [name for name, _ in properties]

    if isinstance(root, FunctionCall):
        lowered = root.name.lower()
        if lowered == "pipeline":
            return self._emit_pipeline_property_access(root, prop_names)
        if lowered == "activity":
            return self._emit_activity_property_access(root, prop_names, index_segments=[])

    root_result = self.emit_node(root)
    if isinstance(root_result, UnsupportedValue):
        return root_result

    code = root_result.code
    for property_name, is_optional in properties:
        if is_optional:
            code = f"({code} or {{}}).get({property_name!r})"
        else:
            code = f"({code})[{property_name!r}]"
    return code
```

The `(x or {}).get('prop')` pattern is the null-safe access:
- If `x` is `None` or falsy, `(x or {})` gives `{}`, then `.get('prop')` returns `None`
- If `x` is a dict, `.get('prop')` returns the value or `None`

**Important:** Update all callers of `_flatten_property_chain`:
- `_emit_property_access` — updated above
- `_emit_index_access` — needs the same update to extract just names for the `activity()` dispatch

### Test Cases

```python
def test_optional_chaining_tokenize():
    from wkmigrate.parsers.expression_tokenizer import tokenize, TokenType
    tokens = tokenize("item()?.condition")
    types = [t.token_type for t in tokens]
    assert TokenType.OPTIONAL_DOT in types

def test_optional_chaining_parse():
    from wkmigrate.parsers.expression_parser import parse_expression
    from wkmigrate.parsers.expression_ast import PropertyAccess
    ast = parse_expression("@item()?.condition")
    assert isinstance(ast, PropertyAccess)
    assert ast.optional is True
    assert ast.property_name == "condition"

def test_optional_chaining_emit():
    from wkmigrate.parsers.expression_parser import parse_expression
    from wkmigrate.parsers.expression_emitter import emit
    result = emit(parse_expression("@item()?.condition"))
    assert result == "(item or {}).get('condition')"

def test_optional_chaining_in_coalesce():
    result = emit(parse_expression("@coalesce(item()?.condition, 'notFound')"))
    assert "(item or {}).get('condition')" in result
    assert "'notFound'" in result

def test_optional_chaining_nested():
    result = emit(parse_expression("@coalesce(item()?.condition?.name, 'name_notFound')"))
    assert ".get('condition')" in result
    assert ".get('name')" in result

def test_optional_chaining_in_toupper():
    result = emit(parse_expression("@toUpper(coalesce(item()?.type, 'DEFAULT'))"))
    assert "(item or {}).get('type')" in result
    assert ".upper()" in result

def test_regular_dot_unchanged():
    """Ensure regular dot access still works."""
    result = emit(parse_expression("@pipeline().parameters.env"))
    assert result == "dbutils.widgets.get('env')"

def test_lone_question_mark_still_errors():
    """Ensure ? without . still returns UnsupportedValue."""
    from wkmigrate.parsers.expression_tokenizer import tokenize
    from wkmigrate.models.ir.unsupported import UnsupportedValue
    result = tokenize("item()? condition")
    assert isinstance(result, UnsupportedValue)
```

---

## Files to Modify

All paths relative to wkmigrate repo root at `/Users/miguel.peralvo/Code/wkmigrate`. On the `pr/27-4-integration-tests` branch:

| Absolute Path | Changes |
|---------------|---------|
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_tokenizer.py` | Add `OPTIONAL_DOT` to `TokenType`; add `?.` peek-ahead in `tokenize()` |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_ast.py` | Add `optional: bool = False` to `PropertyAccess` |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_parser.py` | Handle `OPTIONAL_DOT` token in `_parse_expression` postfix loop |
| `/Users/miguel.peralvo/Code/wkmigrate/src/wkmigrate/parsers/expression_emitter.py` | Update `_flatten_property_chain` to preserve optionality; update `_emit_property_access` to emit `(x or {}).get('prop')` for optional access; update `_emit_index_access` to pass prop names correctly |
| `/Users/miguel.peralvo/Code/wkmigrate/tests/unit/test_expression_parsers.py` | New test cases for tokenization, parsing, and emission of `?.` |

## Acceptance Criteria

1. `@item()?.condition` tokenizes successfully (no `UnsupportedValue`)
2. `@item()?.condition` parses to `PropertyAccess` with `optional=True`
3. `@item()?.condition` emits `(item or {}).get('condition')`
4. Nested optional chaining works: `@item()?.condition?.name`
5. Regular `.` access is unchanged
6. Lone `?` (without `.`) still returns `UnsupportedValue`
7. All existing tests pass (`make test`)
8. `make fmt` clean

## Design Alternatives Considered

1. **New AST node `OptionalPropertyAccess`**: Rejected — adding a flag to `PropertyAccess` is simpler and doesn't require updating the `AstNode` union type alias.
2. **`getattr(x, 'prop', None)` emission**: Rejected — `getattr` doesn't work on dicts, and `item()` in ForEach contexts returns dict-like objects.
3. **`x.get('prop') if x is not None else None` emission**: Rejected — more verbose than `(x or {}).get('prop')` with the same semantics for the dict case.

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests
git checkout -b feature/crp2-optional-chaining
# Implement: tokenizer → AST → parser → emitter (in this order)
# Run: make test && make fmt
git push -u fork feature/crp2-optional-chaining
```
