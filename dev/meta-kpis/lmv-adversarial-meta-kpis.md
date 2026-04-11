# A-Series: Adversarial Loop Health Meta-KPIs

These measure the effectiveness and efficiency of the adversarial testing loop itself. Loaded by `/lmv-autodev` when the session involves adversarial testing, loop optimization, or generation quality assessment.

> Reference loaded by `/lmv-autodev` Phase 1 Part B (when session involves adversarial loop).

## Effectiveness KPIs (soft gates, 5% tolerance)

| ID | Meta-KPI | Target | Measurement | Predicts |
|----|----------|--------|-------------|----------|
| **A-1** | Failure discovery rate | ≥ 0.60 of generated pipelines trigger at least one dimension below threshold | `total_failures / total_pipelines` from LoopResult | Whether the generator is targeting weak spots effectively |
| **A-2** | Unique cluster discovery per round | ≥ 0.5 new clusters/round in early rounds (1-5) | `sum(round.new_clusters for first 5 rounds) / 5` | Diversity of failure modes being discovered |
| **A-3** | Cluster attribution rate | ≥ 0.80 of failures match a known signature in issue_map | `sum(discovered_signatures.values()) / total_failures` | Whether the issue map is comprehensive |
| **A-4** | Golden set yield | ≥ 10 exportable failures per run | `len(LoopResult.all_failures)` | Whether runs produce reusable regression tests |

## Efficiency KPIs (soft gates, 10% tolerance)

| ID | Meta-KPI | Target | Measurement | Predicts |
|----|----------|--------|-------------|----------|
| **A-5** | Cost per failure | ≤ $0.50/failure with Opus, ≤ $0.10/failure with GPT | `estimated_cost / total_failures` | Budget sustainability |
| **A-6** | Time per round | ≤ 180s/round with 10 pipelines | `round_result.elapsed_seconds` | Whether runs fit in CI windows |
| **A-7** | Convergence efficiency | Terminate before 80% of budget spent if converged | `rounds_at_convergence / max_rounds < 0.8` | Whether patience setting is well-tuned |
| **A-8** | LLM call efficiency | ≤ 12 LLM calls per round (1 plan + 10 gen + 1 retry) | `round_result.llm_calls_used / rounds_completed` | Retry overhead control |

## Generation Quality KPIs (informational, no gate)

| ID | Meta-KPI | Target | Measurement | Predicts |
|----|----------|--------|-------------|----------|
| **A-9** | Pipeline parse success rate | ≥ 0.90 | `pipelines_generated / (pipelines_generated + pipelines_failed)` | LLM output quality (JSON validity) |
| **A-10** | Expression complexity per pipeline | ≥ 2 expressions per generated pipeline | sample 10 pipelines, count Expression-typed fields | Whether generator produces expression-heavy pipelines |
| **A-11** | Activity type diversity | ≥ 4 distinct activity types per round | count unique `type` fields across round's pipelines | Broad coverage vs. repetitive patterns |
| **A-12** | Weak spot coverage | All configured weak spots hit at least once per 5 rounds | count which weak spots appear in cluster signatures | Whether targeting is balanced |

## Baseline (from Run 1, 2026-04-11)

| ID | Value | Notes |
|----|-------|-------|
| A-1 | 1.0 (10/10) | Perfect — all pipelines found bugs |
| A-2 | 1.0 (2 new in round 1, 0 in round 2) | Only 2 rounds completed |
| A-3 | 0.50 (5/10 matched known signatures) | Half attributed, half "activity_coverage" generic |
| A-5 | ~$0.45/failure | With Opus 4.6 |
| A-6 | ~160s/round | With 10 pipelines on Opus 4.6 |
| A-9 | 1.0 (10/10) | No parse failures |

## Notes

- A-1 being 1.0 (100% failure rate) is expected in early runs when known gaps dominate. As wkmigrate improves, A-1 should naturally decrease — at that point, it becomes a signal that the weak spot list needs updating.
- A-3 < 1.0 indicates gaps in `dev/wkmigrate-issue-map.json`. After a run, inspect unattributed failures and add new signatures.
- A-5 cost target assumes Opus for generation. If switching to GPT 5.4, the target tightens to ≤ $0.10/failure.
