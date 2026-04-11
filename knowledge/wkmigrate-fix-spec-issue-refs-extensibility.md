# wkmigrate Fix Spec: Issue References + Extensibility Breadcrumbs

> Self-contained specification for /wkmigrate-autodev. After issue #27 expression handling is complete, add issue-reference comments to the ExpressionContext enum so that future implementers of each activity type can find the relevant GitHub issue directly from the code.

## Problem

`ExpressionContext` in `src/wkmigrate/parsers/emission_config.py` already pre-declares contexts for activity types that don't have translators yet (AppendVariable, Wait, Filter, Switch, Until, ExecutePipeline, StoredProcedure). But there's no link from these enum values back to the GitHub issues that track their implementation. An implementer looking at `WAIT_SECONDS` has no breadcrumb to find ghanse/wkmigrate#63.

## Scope

- **Code change:** Add inline comments with issue URLs to the `ExpressionContext` enum values that correspond to unimplemented activity types.
- **No new functionality.** No new translators, no new expression handling. Purely documentation-level.

## What to Change

**File:** `src/wkmigrate/parsers/emission_config.py`

**In the `ExpressionContext` enum**, add a trailing comment with the GitHub issue URL to each context that maps to an unimplemented activity type:

| Enum Value | Issue URL |
|---|---|
| `APPEND_VARIABLE` | https://github.com/ghanse/wkmigrate/issues/64 |
| `COPY_STORED_PROC` | https://github.com/ghanse/wkmigrate/issues/3 |
| `SWITCH_ON` | https://github.com/ghanse/wkmigrate/issues/52 |
| `UNTIL_CONDITION` | https://github.com/ghanse/wkmigrate/issues/62 |
| `FILTER_CONDITION` | https://github.com/ghanse/wkmigrate/issues/65 |
| `EXECUTE_PIPELINE_PARAM` | https://github.com/ghanse/wkmigrate/issues/61 |
| `WAIT_SECONDS` | https://github.com/ghanse/wkmigrate/issues/63 |

Example diff:

```python
# Before:
APPEND_VARIABLE = "append_variable"
SWITCH_ON = "switch_on"

# After:
APPEND_VARIABLE = "append_variable"  # https://github.com/ghanse/wkmigrate/issues/64
SWITCH_ON = "switch_on"  # https://github.com/ghanse/wkmigrate/issues/52
```

**Do NOT add comments** to contexts that already have working translators (SET_VARIABLE, COPY_SOURCE_QUERY, FOREACH_ITEMS, IF_CONDITION, LOOKUP_QUERY, WEB_*, NOTEBOOK_PATH, etc.) — those are implemented and the issue links would be stale/confusing.

## Test Strategy

- `make fmt` — must pass (comments don't affect formatting)
- `make test` — must pass (no logic changes)
- No new tests needed

## Branch Strategy

```bash
git checkout pr/27-4-integration-tests
# Commit directly on this branch (trivial doc-only change) or:
git checkout -b pr/27-5-issue-refs
```

## Meta-KPIs

| ID | Gate | Target |
|----|------|--------|
| GR-1 | Unit test pass rate | 100% |
| GR-2 | Regression count | 0 |
| GR-3..4 | Lint compliance | 0 |

No issue-specific KPIs — this is a documentation-only change.
