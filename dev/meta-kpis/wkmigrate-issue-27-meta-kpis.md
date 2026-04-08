# X-Series: wkmigrate Issue #27 (Complex Expressions) Outcomes

These meta-KPIs measure how well lmv harnesses wkmigrate for **complex expressions** (the scope of upstream `ghanse/wkmigrate#27`). They are loaded by `/lmv-autodev` whenever the session input mentions issue 27, expressions, expression coverage, or one of the targeted weak spots.

> **Critical:** Every X-series KPI is meaningful **only within a fixed `wkmigrate_version_under_test`**. Comparisons across different wkmigrate refs do not measure progress — they measure wkmigrate version delta. Always pin the ref before computing baselines.

> Reference loaded by `/lmv-autodev` Phase 1 Part B (when relevant to session input).

## Soft gates (5% tolerance)

These can degrade by 5% before the ratchet flags them. **An X-series regression with no lmv code change is attributed to wkmigrate and produces a finding, not a failure** — see `SKILL.md` Ratchet Rules.

| ID | Meta-KPI | Target | Measurement | Predicts |
|----|----------|--------|-------------|----------|
| **X-1** | Mean `expression_coverage` across the expressions golden set | monotonic non-decrease for the same wkmigrate ref; session target ≥ 0.80 | `lmv batch --golden-set golden_sets/expressions.json --threshold 80`, then mean of `cases[*].dimensions.expression_coverage` | Direct proxy for wkmigrate #27 progress |
| **X-2** | Mean `semantic_equivalence` across the 200 golden expression pairs | ≥ 0.75 | `lmv batch-expressions --golden-set golden_sets/expressions.json` (new command, see L-8 in SKILL.md backlog) | Whether wkmigrate produces semantically correct Python, not just resolved |
| **X-6** | Per-category mean `expression_coverage` | string/math/datetime/logical/collection/nested all ≥ 0.70 | group `expressions.json` by `category`, compute mean per category from the X-1 batch | Catches "all strings, no datetime" drift |
| **X-7** | Time-to-detection after `POST /api/config/wkmigrate/apply` | ≤ 120 s from `apply` 200 to `regression-check` exit | wall-clock recorded in ledger | Operational KPI; bloat detector |
| **X-8** | Synthetic generator weak-spot hit rate | ≥ 0.60 of generated pipelines hit `expression_coverage < 0.75` | `lmv synthetic --count 20 --target nested_expressions` → `lmv validate` each → count hits | Adversarial generator health |

## Counters (must grow; not gates)

| ID | Meta-KPI | Target | Measurement | Why tracked |
|----|----------|--------|-------------|-------------|
| **X-3** | % of unsupported expressions attributable to a tracked finding | ≥ 0.90 | for each `not_translatable` entry from X-1, look up its signature in `dev/wkmigrate-issue-map.json`; hits / total | Traceability of failure modes |
| **X-4** | Findings filed by `lmv-autodev` with a reproduction snapshot | delta ≥ 1 per session | `gh issue list -R MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator --label "wkmigrate-feedback,filed-by:lmv-autodev" --json number` | Proves the feedback loop fires |
| **X-5** | Regressions caught after `apply` | every real regression flagged | `lmv history-diff` between baseline and post-apply runs on the same golden set; flag any pipeline-level dimension drop ≥ 0.05 | Whether lmv is doing its evaluator job |
| **X-9** | Findings closed by an upstream wkmigrate merge (journey) | n/a | for each open finding, check linked upstream `ghanse/wkmigrate` issue/PR state if present in `dev/wkmigrate-issue-map.json` | Convergence indicator |

## Targeted weak spots (from `synthetic/agent_generator.py:46`)

The X-series targets these failure-mode categories. Each weak spot maps to one or more entries in `dev/wkmigrate-issue-map.json`:

| Weak spot | Golden-set category | Upstream issue(s) |
|-----------|---------------------|-------------------|
| `nested_expressions` | nested | ghanse/wkmigrate#27 |
| `math_on_params` | math | ghanse/wkmigrate#27, #55 |
| `deep_nesting` | nested | ghanse/wkmigrate#27 |
| `complex_conditions` | logical | ghanse/wkmigrate#27 |
| `activity_output_chaining` | nested | ghanse/wkmigrate#27 |

## Cause attribution

When an X-series KPI regresses between two ratchet checks:

1. Compute `git diff --name-only <phase_start_sha> HEAD -- src/ tests/`.
2. If the diff is **empty**, attribute to **wkmigrate** → file a finding tagged `regression:wkmigrate-detected-by-lmv` and **continue**.
3. If the diff is **non-empty**, attribute to **lmv OR wkmigrate (ambiguous)** → escalate to the user via CHECKPOINT.

This is the central design point of `/lmv-autodev`. lmv exists to surface wkmigrate regressions; treating them as lmv failures would defeat the purpose.
