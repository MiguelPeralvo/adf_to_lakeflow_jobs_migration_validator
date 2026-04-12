# Convergence Plan: X-2 → 0.90+ (ACHIEVED on set_variable)

> Updated 2026-04-12 16:40 CEST. Steps 1-4 complete, Step 5 in progress.

## Current State (mid-session 2026-04-12)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| X-2 set_variable (v3 cal) | **0.944** | > 0.90 | **PASS** |
| X-2 lookup_query (v2 cal) | 0.895 | > 0.90 | v3 running |
| X-2 copy_query (v2 cal) | 0.890 | > 0.90 | v3 running |
| X-2 web_body (v2 cal) | 0.887 | > 0.90 | v3 running |
| X-2 if_condition (v2 cal) | 0.744 | > 0.70 | **PASS** |
| Pipeline CCS | 90.3 (175/175, 0% crash) | > 92 | GAP: 1.7 |
| Corpus size | 200 unique expressions + 175 pipelines | - |

## Key Finding: Judge Calibration Was the Bottleneck

The main blocker to convergence was NOT wkmigrate translation quality — it was LLM judge calibration. The judge didn't understand 3 Databricks conventions:
1. `@activity('X').output` → `dbutils.jobs.taskValues.get(taskKey='X', key='result')` 
2. `@variables('X')` → `dbutils.jobs.taskValues.get(taskKey='set_variable_X', key='X')`
3. `@div()` → `//` (integer division)

Adding calibration rules + 6 few-shot pairs pushed set_variable from 0.776 → 0.944 (+0.168).

**wkmigrate tip:** `pr/27-4-integration-tests @ b8c9be2` (W-23/W-24/W-25 done)
**lmv tip:** `main @ a6a1beb`
**alpha_1:** has PRs #1-5 merged (clean pr/27-0..4 base chain)

## The 5 Steps

### Step 1: Stable Full Re-Eval (200 expressions × 4 core contexts)

```bash
source .env && export DATABRICKS_HOST DATABRICKS_TOKEN
for ctx in set_variable notebook_base_param lookup_query copy_query; do
  poetry run lmv semantic-eval \
    --golden-set golden_sets/expression_loop_post_w16.json \
    --context $ctx \
    --model databricks-claude-sonnet-4-6 \
    --output golden_sets/semantic_eval_post_w25/${ctx}.json
done
```

**Purpose:** Get stable 200-sample measurements on the 4 reliable contexts post W-23/W-24/W-25 fixes. The 60-sample showed 0.750 but has high variance.

**Success:** All 4 contexts > 0.82 confirms the json.loads removal didn't regress.
**If regression confirmed:** Revert W-23 (json.loads removal) and keep W-24/W-25 only.

### Step 2: Grow Comparison Corpus for if_condition

The if_condition context only resolves comparison expressions (`@equals`, `@greater`, `@less`, `@not`). The current corpus has only 10 such expressions. Need 30-50 more.

```bash
# Add 40 comparison expressions targeting IfCondition patterns:
# - @equals(param, literal)
# - @greater(param, number) 
# - @and(comparison, comparison)
# - @or(comparison, comparison)
# - @not(comparison)
# - @greaterOrEquals / @lessOrEquals variants
```

Then re-run:
```bash
poetry run lmv semantic-eval \
  --golden-set golden_sets/expression_loop_post_w16.json \
  --context if_condition \
  --model databricks-claude-sonnet-4-6 \
  --output golden_sets/semantic_eval_post_w25/if_condition.json
```

**Target:** if_condition X-2 > 0.70 on the comparison-only subset.

### Step 3: Target String Category (weakest at 0.516)

String category is dragged down by `activity('X').output` references in string operations. After W-23 (json.loads removal), the emitted code is simpler. Need to:

1. Run expression-loop specifically targeting string + activity_output_chaining
2. Cluster failures — check if string-category low scores are from:
   - `firstRow` (should be fixed by W-17)
   - `variables()` naming (W-19, deferred)
   - Pure string functions that are wrong

```bash
poetry run lmv expression-loop --rounds 5 --expressions 20 \
  --weak-spots "activity_output_chaining" \
  --contexts set_variable \
  --time-budget 900 --llm-budget 50
```

### Step 4: Spawn /wkmigrate-autodev for Remaining Gaps

Based on Step 1-3 findings, write a focused spec and invoke:

```
/wkmigrate-autodev "<spec path>" --autonomy full-auto
```

Likely targets:
- If W-23 regressed: revert json.loads removal, implement conditional parse instead
- String category: whatever pattern emerges from Step 3 clustering
- if_condition: if compound predicates (@and/@or) still fail

### Step 5: Convergence Check + PR Follow-ups to alpha_1

After Step 4 fix lands:
1. Re-run full 7-context semantic-eval
2. Check convergence: X-2 > 0.90 on 4 core contexts
3. If converged: open follow-up PRs (#6-10) to alpha_1 with W-fix commits
4. If not: one more iteration (Tiers 3→4→5)

### Tier 6 (if needed): Second-Round Pipeline Generation

If convergence not reached after Step 5, generate a second batch of 175 pipelines using `golden_sets/adversarial_seeds_round1.json` and re-evaluate:

```bash
poetry run lmv synthetic --count 50 --mode llm \
  --prompt "$(cat golden_sets/adversarial_seeds_round1.json | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"prompt\"])')" \
  --output golden_sets/gen/adversarial_round2
```

## Key File Locations

| File | Purpose |
|------|---------|
| `golden_sets/expression_loop_post_w16.json` | Main corpus (210 expressions) |
| `golden_sets/big_pipeline_corpus.json` | 175 smart synthetic pipelines |
| `golden_sets/batch_results_175_pipelines.json` | Pipeline eval results |
| `golden_sets/semantic_eval_post_w17_w18.json` | Tier 1 baseline (0.808) |
| `golden_sets/semantic_eval_by_context/` | Per-context Tier 2 results |
| `golden_sets/adversarial_seeds_round1.json` | Tier 7 seeds for next gen round |
| `knowledge/wkmigrate-fix-spec-W23-auto.md` | Auto-clustered failure patterns |
| `dev/autodev-sessions/AUTONOMOUS-8H-2026-04-12.md` | Full session ledger |
| `scripts/cluster_low_scoring.py` | Clustering tool |
| `scripts/run_tier2_multi_context.sh` | 6-context sweep script |

## Constraints (always active)

- NEVER open a PR to ghanse/wkmigrate
- Push wkmigrate changes to `fork` only (MiguelPeralvo/wkmigrate)
- wkmigrate remote `origin` = ghanse (READ-ONLY), `fork` = MiguelPeralvo
- Backup branches exist: `fork/backup/alpha_1-pre-reset-2026-04-12`, `fork/backup/pre-autonomous-2026-04-12`
- alpha_1 was reset to `72265ba` then received PRs #1-5 during this session

## Architectural Decisions (from earlier sessions, still binding)

- pr/27-N is canonical (not alpha_1's phase merges)
- Op mapping (EQUAL_TO → ==) belongs in lmv L-F17 walker, NOT in wkmigrate IR
- W-21 fix: non-comparison IfCondition predicates emit `right=""` to skip pair emission
- W-23: json.loads removed from activity output (taskValues stores objects natively)
