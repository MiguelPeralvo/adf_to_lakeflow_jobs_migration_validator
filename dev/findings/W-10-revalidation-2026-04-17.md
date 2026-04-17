---
finding_id: W-10-revalidation-2026-04-17
kind: re-validation
related_to: W-10
severity: P3
area: for_each
session: LMV-AUTODEV-2026-04-17-crp11-harvest
wkmigrate_version_under_test: MiguelPeralvo/wkmigrate@pr/27-4-integration-tests@e21c1e3
status: behavior-confirmed-no-wkmigrate-action
revised: 2026-04-17 (post-harvest annotation)
---

# W-10 re-validation — ForEach items placeholder (post-CRP-11, behavior unchanged)

> **⚠️ Revised 2026-04-17** — This draft originally framed the 200/208
> placeholder ratio as "W-10 still open". That framing contradicts the
> existing diagnosis already recorded in `dev/wkmigrate-issue-map.json`
> for `id: W-10`, where the finding's `status` is
> `mis-diagnosed-corpus-mismatch`.
>
> Per the issue-map's `diagnosis_correction` block
> (session `WKMIGRATE-AUTODEV-2026-04-08`):
>
> > ADF ForEach.items must evaluate to an array. The corpus uses
> > expressions like `@toUpper('abc')`, `@add(1,2)`, `@equals(1,1)` — these
> > are scalars, so wkmigrate correctly produces a placeholder rather than
> > emitting nonsense. The 33 `collection`-category entries are mostly
> > transformations OF arrays (`@length`, `@first`, `@empty`), not bare
> > arrays, so they are valid `length`/`first`/`empty` fixtures but NOT
> > valid ForEach items. Bare `@createArray(...)` IS handled correctly by
> > alpha_1's `_parse_for_each_items`; the 8 pairs that DO resolve are the
> > literal `createArray` entries, confirming this.
>
> So the 200/208 ratio is **correct behavior**, not a bug. The real
> follow-up is **W-6** (structured `failure_mode` tags on
> `NotTranslatableWarning`): the generic "did not recognise activity type"
> warning mis-attributes the failure when the type WAS recognised but the
> items expression returned a scalar. That's a P3 messaging improvement,
> not a P2 bug.
>
> `wkmigrate_action_required: None for W-10 itself.` Keep this re-validation
> entry only for the session-stamped snapshot (proves CRP-11 did not
> change the shape) and for bumping `last_tested` to `e21c1e3`.

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

Pre-existing `W-10` from the 2026-04-11 adversarial round. CRP-11 did not touch `ForEachActivity` translation. The 200/208 placeholder count reflects the corpus-mismatch documented in the issue-map (most golden-set pairs are scalar-valued or array-transforming expressions — not bare arrays, which is what `ForEach.items` requires). Confirmed not a regression AND not actionable as a wkmigrate bug.

## Suggested wkmigrate fix

~~`src/wkmigrate/translators/activity_translators/for_each_activity_translator.py`: pass `items` through `get_literal_or_expression()` before constructing the inner pipeline, instead of the current path that replaces non-literal items with a placeholder.~~

**Correction (2026-04-17):** The suggested fix above is superseded by the
`diagnosis_correction` block in `dev/wkmigrate-issue-map.json` for `W-10`.
`_parse_for_each_items` in alpha_1+ already resolves bare `@createArray(...)`
correctly; the sweep shows this (8/208 resolve cleanly). The remaining
200/208 are scalars and array-transforming expressions that are not valid
ForEach items in ADF semantics either — wkmigrate placeholders them
defensively, which is the correct conservative behavior. The messaging
improvement (more specific `failure_mode='items_expression_not_array'`
warning) is folded into W-6, not W-10.

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
