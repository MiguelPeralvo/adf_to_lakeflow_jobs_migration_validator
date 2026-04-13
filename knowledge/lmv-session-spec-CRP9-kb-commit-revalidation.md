# LMV Session Spec: CRP-9 + Knowledge Base Commit + Post-Fix Re-Validation

> Input spec for `/lmv-autodev`. Covers three tasks: (1) commit pending lmv knowledge base updates, (2) drive CRP-9 dependency parser fix in wkmigrate, (3) re-validate CRP0001 after CRP-8 + CRP-9 land.

## Context

After the V4 deep validation of CRP0001 (36 real ADF pipelines), three categories of work remain:

1. **lmv repo housekeeping**: 8 untracked fix spec files + 4 modified knowledge base files from V4 need committing. These document the full CRP-1 through CRP-9 fix specifications and updated failure modes / learnings.

2. **CRP-9 (W-26)**: The dependency parser incorrectly rejects valid `Succeeded` conditions for sibling activities inside IfCondition branches. Blocks notebook preparation for 15/36 CRP0001 pipelines (41.7%). Fix spec at `knowledge/wkmigrate-fix-spec-CRP9-dependency-parser-fix.md`. Uncommitted code changes already exist on `feature/crp9-dependency-parser-fix` in wkmigrate.

3. **Post-fix re-validation**: After CRP-8 (merged as MiguelPeralvo/wkmigrate#15) and CRP-9 land, re-validate the full CRP0001 corpus to confirm 100% semantic correctness + 100% notebook preparation success.

## Prerequisites

- CRP-8 (W-25 + W-27) merged into `pr/27-4-integration-tests` at `5ee2e1c` via PR #15
- CRP-9 uncommitted changes on `feature/crp9-dependency-parser-fix` in wkmigrate repo
- wkmigrate repo at `/Users/miguel.peralvo/Code/wkmigrate`, branch `pr/27-4-integration-tests`
- lmv repo at `/Users/miguel.peralvo/Code/adf_to_lakeflow_jobs_migration_validator`, branch `main`

## wkmigrate Version Under Test

- **Repo**: `MiguelPeralvo/wkmigrate`
- **Branch**: `pr/27-4-integration-tests`
- **Post-CRP-8 SHA**: `5ee2e1c`
- **Post-CRP-9 SHA**: TBD (after merge)

---

## Phase 1: Commit Pending lmv Knowledge Base Updates

### Modified files (4)

| File | Content |
|------|---------|
| `dev/wkmigrate-issue-map.json` | Updated failure signature catalog from V4 validation |
| `knowledge/INDEX.md` | Index updated with new fix spec entries |
| `knowledge/failure-modes.md` | Updated with W-25, W-26, W-27 failure modes |
| `knowledge/learnings.md` | V4 deep validation learnings (99.5% semantic, 5 runtime bugs) |

### Untracked files (8 fix specs)

| File | CRP | Description |
|------|-----|-------------|
| `knowledge/wkmigrate-fix-spec-CRP1-emitter-registry.md` | CRP-1 | 9 expression gaps (G-2..G-10) |
| `knowledge/wkmigrate-fix-spec-CRP2-optional-chaining.md` | CRP-2 | Optional chaining `?.` (G-1) |
| `knowledge/wkmigrate-fix-spec-CRP3-control-flow-translators.md` | CRP-3 | ExecutePipeline, Switch, Until (G-12, G-13, G-15) |
| `knowledge/wkmigrate-fix-spec-CRP4-leaf-translators.md` | CRP-4 | AppendVariable, Fail, etc. (G-11..G-18) |
| `knowledge/wkmigrate-fix-spec-CRP5-crp0001-integration-tests.md` | CRP-5 | Golden tests on 8 real Repsol pipelines |
| `knowledge/wkmigrate-fix-spec-CRP6-remaining-gaps.md` | CRP-6 | Final 6 gaps (G-19..G-24) |
| `knowledge/wkmigrate-fix-spec-CRP8-datetime-runtime-fixes.md` | CRP-8 | W-25 timezone mapping + W-27 string input (MERGED) |
| `knowledge/wkmigrate-fix-spec-CRP9-dependency-parser-fix.md` | CRP-9 | W-26 dependency parser fix (THIS SESSION) |

### Commit command

```bash
cd /Users/miguel.peralvo/Code/adf_to_lakeflow_jobs_migration_validator
gh auth switch --user MiguelPeralvo
git add knowledge/ dev/wkmigrate-issue-map.json
git commit -m "knowledge: add CRP-1 through CRP-9 fix specs + V4 deep validation learnings

8 new wkmigrate fix specifications documenting all gaps discovered in CRP0001
V4 deep validation. Updated failure modes, learnings, and issue map.

Co-authored-by: Isaac"
git push origin main
gh auth switch --user miguel-peralvo_data
```

---

## Phase 2: Drive CRP-9 (W-26) in wkmigrate

### Current State

The `feature/crp9-dependency-parser-fix` branch in wkmigrate already has uncommitted changes implementing the fix. These need to be reviewed, tested, committed, and pushed as a PR.

### Fix Summary

**W-26: `is_conditional_task` flag propagation bug (P1)**

Three sub-bugs:
- **A**: `_parse_dependency()` in `activity_translator.py` branches on `is_conditional_task` flag, but the flag applies to ALL dependencies equally. Sibling deps with `Succeeded` are rejected when `is_conditional_task=True`.
- **B**: Fix: branch on `outcome` field presence instead. Parent deps (with `outcome`) use TRUE/FALSE logic; sibling deps (with `dependency_conditions`) use standard SUCCEEDED logic.
- **C**: `get_base_task()` in `preparers/utils.py` crashes on `UnsupportedValue` objects in `depends_on`. Add defensive filter.

### Files to modify

| File | Action |
|------|--------|
| `src/wkmigrate/translators/activity_translators/activity_translator.py` | Rewrite `_parse_dependency()` |
| `src/wkmigrate/preparers/utils.py` | Add `UnsupportedValue` guard |
| `tests/unit/test_activity_translator.py` | New tests for sibling deps in IfCondition |
| `tests/unit/test_preparer.py` | New test for UnsupportedValue safety net |

### Workflow

```bash
cd /Users/miguel.peralvo/Code/wkmigrate
# Stash list should show CRP-9 changes, or they're already on the branch
git checkout feature/crp9-dependency-parser-fix
# Review, stage, test
make test
make integration  # CRP0001 tests — 15 previously-blocked should now pass
make fmt
# Commit, push, PR
gh auth switch --user MiguelPeralvo
git add <files>
git commit -m "fix: CRP-9 dependency parser accepts Succeeded conditions inside IfCondition branches (W-26)

Rewrite _parse_dependency() to branch on outcome field presence instead
of is_conditional_task flag. Add UnsupportedValue guard in get_base_task().

Fixes notebook preparation for 15/36 CRP0001 pipelines.

Co-authored-by: Isaac"
git push -u origin feature/crp9-dependency-parser-fix
gh pr create -R MiguelPeralvo/wkmigrate --base pr/27-4-integration-tests --title "fix: CRP-9 dependency parser fix (W-26)"
# Merge after review
gh auth switch --user miguel-peralvo_data
```

### Expected impact

| Metric | Before | After CRP-9 |
|--------|--------|-------------|
| CRP0001 notebook preparation | 21/36 (58.3%) | 36/36 (100%) |
| Blocked pipelines | 15 | 0 |
| Unsupported dependency warnings | 56 | ~4 (multi-condition only) |

### Full fix spec

See `knowledge/wkmigrate-fix-spec-CRP9-dependency-parser-fix.md` for complete root cause analysis, code changes, and test strategy.

---

## Phase 3: Post-Fix Re-Validation

After both CRP-8 and CRP-9 are merged into `pr/27-4-integration-tests`:

### 3a. Pull merged changes

```bash
cd /Users/miguel.peralvo/Code/wkmigrate
git checkout pr/27-4-integration-tests
git pull origin pr/27-4-integration-tests
```

### 3b. Run full test suite

```bash
make test          # Unit tests — all must pass
make integration   # CRP0001 integration — all 37+ must pass
```

### 3c. Validate CRP0001 semantic correctness (V5)

Re-run the V4 deep validation methodology on all 36 CRP0001 pipelines:

1. **Expression translation**: Verify 2,792/2,792 expressions translate (100%)
2. **Notebook syntax**: Verify all generated notebooks compile without error
3. **Semantic correctness**: Execute generated Python expressions with mock values — target 100% (was 99.5% before CRP-8)
4. **Notebook preparation**: Verify all 36 pipelines prepare into Databricks workflows (was 21/36 before CRP-9)

### 3d. Expected V5 results

| Metric | V4 (pre CRP-8/9) | V5 (target) |
|--------|-------------------|-------------|
| Expression translation | 2,792/2,792 (100%) | 2,792/2,792 (100%) |
| Notebook syntax | 125/125 (100%) | 125/125+ (100%) |
| Semantic correctness | 99.5% (14 real failures) | **100%** (0 real failures) |
| Notebook preparation | 21/36 (58.3%) | **36/36 (100%)** |
| Blocked pipelines | 15 | **0** |
| CCS score | 64.4% | **80%+** (after adapter wiring) |

### 3e. Update knowledge base

After V5 validation:
- Update `knowledge/learnings.md` with V5 results
- Update `knowledge/failure-modes.md` — mark W-25, W-26, W-27 as RESOLVED
- Update `dev/wkmigrate-issue-map.json` with closed findings
- Commit and push

---

## Meta-KPIs for This Session

### L-Series (lmv hygiene)

| ID | Target | Check |
|----|--------|-------|
| LR-1 | 100% unit test pass | `make test` in lmv repo |
| LA-1 | Adapter boundary invariant | Single wkmigrate import file |

### X-Series (wkmigrate outcomes, tied to `pr/27-4-integration-tests`)

| ID | Target | Check |
|----|--------|-------|
| X-CRP8 | 0 datetime runtime failures | W-25 + W-27 tests pass (ALREADY DONE via PR #15) |
| X-CRP9 | 36/36 notebook preparation | All CRP0001 pipelines prepare after W-26 fix |
| X-V5 | 100% semantic correctness | V5 deep validation shows 0 real failures |

### K-Series (knowledge base)

| ID | Target | Check |
|----|--------|-------|
| K-commit | All 12 pending files committed | `git status` shows clean working tree |
| K-freshness | learnings.md updated with V5 | Entry dated today |

---

## Autonomy Recommendation

**Semi-auto**: The lmv-side work (Phase 1) is safe to auto-commit. The wkmigrate-side work (Phase 2) has pre-written code but should be reviewed before PR. Phase 3 re-validation is read-only observation.

## Estimated Duration

- Phase 1: ~2 minutes (commit + push)
- Phase 2: ~15 minutes (review, test, PR, merge)
- Phase 3: ~30 minutes (full V5 re-validation)
- Total: ~45 minutes
