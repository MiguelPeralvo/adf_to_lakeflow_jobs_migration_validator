---
finding_id: W-10-revalidation-2026-04-17
kind: re-validation
related_to: W-10
severity: P2
area: for_each
session: LMV-AUTODEV-2026-04-17-crp11-harvest
wkmigrate_version_under_test: MiguelPeralvo/wkmigrate@pr/27-4-integration-tests@e21c1e3
status: still-open
---

# W-10 re-validation — ForEach items still drops expressions (post-CRP-11)

## Problem

Post-CRP-11 (e21c1e3), the `for_each` activity context still silently collapses expression-bearing `items` inputs to a placeholder. Only literal `@createArray('a','b','c')` survives.

Sweep numbers vs. the `golden_sets/expressions.json` 208-pair corpus:

| Category    | Resolved / total (for_each) |
|-------------|:---------------------------:|
| collection  | 8 / 41   (literal createArray only) |
| datetime    | 0 / 33 |
| logical     | 0 / 33 |
| math        | 0 / 34 |
| nested      | 0 / 33 |
| string      | 0 / 34 |
| **total**   | **8 / 208 (3.8%)** |

Aggregate: 200 expressions emit `not_translatable` warnings, 200 are replaced with placeholder notebooks.

## Status

Pre-existing `W-10` from the 2026-04-11 adversarial round. CRP-11 did not touch `ForEachActivity` translation. Confirmed not a regression, but also **not fixed** — every V3/V5 re-validation marked CRP0001 ForEach bodies as resolved only because the live CRP0001 corpus happens not to pass complex expressions to `items` (production pipelines use literal iteration sources). The golden-set sweep exposes the gap that operational pipelines hide.

## Suggested wkmigrate fix (unchanged from W-10 original)

`src/wkmigrate/translators/activity_translators/for_each_activity_translator.py`: pass `items` through `get_literal_or_expression()` before constructing the inner pipeline, instead of the current path that replaces non-literal items with a placeholder.

## Upstream trace

`ghanse/wkmigrate#27` (root). No existing lmv finding for post-CRP-11; this note is a session-stamped re-validation. Prior finding: `dev/findings/W-10.md` does not exist in repo — the W-10 entry lives only in `dev/wkmigrate-issue-map.json` with `signature_key: for_each_items_silent_placeholder`. Update `last_tested` there.

## Next action

Not filing as a new gh issue (duplicate of existing W-10). Update `dev/wkmigrate-issue-map.json`:

```json
{
  "id": "W-10",
  "last_tested": {
    "session": "LMV-AUTODEV-2026-04-17-crp11-harvest",
    "wkmigrate_ref": "MiguelPeralvo/wkmigrate@pr/27-4-integration-tests@e21c1e3",
    "corpus": "golden_sets/expressions.json (208 pairs, for_each context)",
    "result": "200/208 placeholder (8/208 literal createArray only). Status unchanged since V3."
  }
}
```
