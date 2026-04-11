# LLM Cost Model and Consumption Tracking

> Last updated: 2026-04-11 (auto-updated after adversarial loop runs)

## Databricks Serving Endpoints

All LLM calls go through Databricks Foundation Model API (FMAPI) serving endpoints.

### Endpoint Configuration
- **Base URL:** `${DATABRICKS_HOST}/serving-endpoints`
- **Auth:** Bearer token via `DATABRICKS_TOKEN`
- **Routing:** `{base_url}/{model_name}/invocations`

### Available Models

| Model ID | Provider | Use Case | Cost Tier | Tokens/$ (approx) |
|----------|----------|----------|-----------|-------------------|
| `databricks-claude-opus-4-6` | Anthropic via Databricks | Generation, high-stakes judge | $$$ | ~15K input, ~4K output |
| `databricks-claude-sonnet-4-6` | Anthropic via Databricks | Judge optimization trials | $$ | ~50K input, ~15K output |
| `databricks-gpt-5-4` | OpenAI via Databricks | Batch scoring, ground truth | $ | ~100K input, ~30K output |

### Cost Per Operation (estimated)

| Operation | Model | Input Tokens | Output Tokens | Cost/call |
|-----------|-------|-------------|---------------|-----------|
| Pipeline generation (plan) | Opus 4.6 | ~2K | ~4K | ~$0.08 |
| Pipeline generation (single) | Opus 4.6 | ~3K | ~8K | ~$0.15 |
| Semantic equivalence judge | Opus 4.6 | ~1K | ~0.5K | ~$0.03 |
| Ground truth prediction | GPT 5.4 | ~2K | ~0.5K | ~$0.01 |
| Judge optimization trial | Sonnet 4.6 | ~2K | ~1K | ~$0.02 |

## Consumption Log

### Adversarial Loop Run 1 (2026-04-11)
- **Duration:** 322s (5.4 min)
- **Rounds:** 2 of 20 planned (stopped by time budget)
- **Pipelines generated:** 10
- **LLM calls:** ~30 (1 plan + 10 generations + retry overhead per round × 2 rounds + planning)
- **Model:** `databricks-claude-opus-4-6`
- **Estimated cost:** ~$4.50 (30 calls × $0.15 avg)
- **Cost per failure found:** ~$0.45
- **Cost per new cluster:** ~$2.25

### Adversarial Loop Run 2 (2026-04-11, in progress)
- **Configuration:** 20 rounds, 10 pipelines/round, 300 LLM call budget
- **Model:** `databricks-claude-opus-4-6`
- **Projected cost:** ~$45 (300 calls × $0.15 avg)
- **Projected duration:** ~2 hours at current rate (~160s/round)

## Cost Optimization Rules

1. **Pipeline generation is the expensive operation** (~$0.15/pipeline with Opus). The conversion, scoring, and clustering are free (local compute).

2. **Each round costs:** 1 plan call + N pipeline calls = ~$0.08 + N × $0.15. For 10 pipelines/round: **~$1.58/round**.

3. **Switch to GPT 5.4 for broad exploration:** reduces per-pipeline cost to ~$0.03, but generated pipelines may be simpler/less realistic.

4. **The convergence_patience setting** is the main cost control: if set to 2, the loop stops after 2 rounds with no new clusters, saving the remaining budget.

5. **Time budget vs LLM budget:** At the current rate (160s/round), a 1-hour budget allows ~22 rounds. The LLM budget of 300 allows ~27 rounds (at 11 calls/round). So the LLM budget is usually not the binding constraint unless pipelines_per_round is high.

## Budget Allocation Recommendations

| Budget | Configuration | Expected Output |
|--------|--------------|-----------------|
| $5 | 3 rounds × 10 pipelines (Opus) | 2-3 failure clusters |
| $15 | 10 rounds × 10 pipelines (Opus) | 3-5 failure clusters |
| $45 | 20 rounds × 10 pipelines (Opus) | 5-8 failure clusters |
| $80 | 50 rounds × 10 pipelines (mixed Opus/GPT) | 8-12 failure clusters |

## Service Dependencies

```
lmv adversarial-loop
  └─ FMAPIJudgeProvider
       ├─ .complete() → databricks-claude-opus-4-6/invocations  [generation]
       ├─ .judge()    → databricks-gpt-5-4/invocations          [batch scoring]
       └─ .judge()    → databricks-claude-opus-4-6/invocations  [high-stakes]
  └─ wkmigrate (local)
       └─ translate_pipeline() → local CPU only (free)
  └─ Dimension scorers (local)
       └─ compute_*() → local CPU only (free)
```

The ONLY external cost is the FMAPI calls. Everything else (conversion, scoring, clustering, golden set export) is local.
