# Testing Strategies

> Last updated: 2026-04-11

## Strategy Selection Matrix

| Scenario | Strategy | CLI Command | Time | Cost |
|----------|----------|-------------|------|------|
| Quick smoke test | Golden set batch | `lmv batch --golden-set golden_sets/expressions.json` | 5s | Free |
| Regression gate | Regression check | `lmv regression-check --golden-set golden_sets/regression_pipelines.json` | 10s | Free |
| Expression sweep | Activity context sweep | `lmv sweep-activity-contexts --golden-set golden_sets/expressions.json` | 30s | Free |
| Targeted generation | LLM synthetic | `lmv synthetic --mode llm --preset complex_expressions --count 20` | 5min | ~$2 |
| Deep adversarial | Adversarial loop | `lmv adversarial-loop --rounds 10 --pipelines 10` | 30min | ~$15 |
| Overnight stress | Extended adversarial | `lmv adversarial-loop --rounds 50 --pipelines 20 --time-budget 28800` | 8hrs | ~$80 |
| Judge calibration | Optimize judge | `lmv optimize-judge --num-trials 30` | 20min | ~$10 |

## When to Use Each

### Golden Set Batch (free, instant)
- After every code change
- CI gate
- Baseline measurement before/after a wkmigrate branch swap

### Activity Context Sweep (free, 30s)
- After wkmigrate adopts `get_literal_or_expression()` in a new translator
- To measure per-context coverage (SetVariable vs Copy vs Lookup etc.)
- To verify W-9/W-10 fixes

### Adversarial Loop ($$, minutes-hours)
- After a wkmigrate milestone lands (new branch merged)
- To discover NEW failure modes not in the issue map
- To generate regression golden sets for CI

### Judge Optimization ($$, 20min)
- When the calibration pairs JSON grows (new human-labelled examples added)
- When judge disagreement is observed (score != human expectation)
- Before a deep adversarial run (optimize first, then use optimized judge)

## Adversarial Loop Configuration Guide

### Quick discovery run (find new bugs fast)
```bash
lmv adversarial-loop --rounds 5 --pipelines 10 --model databricks-claude-opus-4-6 \
  --golden-set-output golden_sets/quick_discovery.json
```

### Deep stress test (maximize coverage)
```bash
lmv adversarial-loop --rounds 20 --pipelines 20 --time-budget 7200 --llm-budget 500 \
  --weak-spots "nested_expressions,math_on_params,foreach_expression_items,complex_conditions,activity_output_chaining,parameterized_paths,deep_nesting,unsupported_types" \
  --golden-set-output golden_sets/deep_stress.json
```

### Budget-conscious run (GPT 5.4 for generation)
```bash
lmv adversarial-loop --rounds 10 --pipelines 10 --model databricks-gpt-5-4 \
  --golden-set-output golden_sets/budget_run.json
```

### Post-fix validation (verify a wkmigrate fix)
```bash
# 1. Swap branch
curl -sX POST http://localhost:8000/api/config/wkmigrate/apply \
  -d '{"repo":"MiguelPeralvo/wkmigrate","branch":"pr/27-3"}'
# 2. Run batch on the failure golden set
lmv batch --golden-set golden_sets/adversarial_loop_discovered.json --threshold 75
```

## Model Selection for Testing

| Operation | Primary Model | Secondary Model | Reasoning |
|-----------|--------------|-----------------|-----------|
| Pipeline generation | `databricks-claude-opus-4-6` | `databricks-gpt-5-4` | Opus produces more realistic, complex ADF |
| Semantic equivalence judge | `databricks-claude-opus-4-6` | `databricks-claude-sonnet-4-6` | High-stakes scoring needs best model |
| Judge optimization trials | `databricks-claude-sonnet-4-6` | `databricks-gpt-5-4` | Many trials; Sonnet is cost-effective |
| Fix suggestions | `databricks-claude-opus-4-6` | -- | Diagnosis needs deep reasoning |
| Ground truth prediction | `databricks-gpt-5-4` | -- | Simple heuristic task |

## Cost Optimization Tips

1. **Start with golden set batch** (free) to establish baseline before burning LLM budget
2. **Use GPT 5.4 for generation** when exploring broadly; switch to Opus for targeted deep probing
3. **Set convergence_patience=2** for quick runs; the loop stops early if it keeps finding the same bugs
4. **Export golden sets** from adversarial runs so future regression checks are free
5. **Optimize the judge once**, then reuse the optimized state for all subsequent runs
