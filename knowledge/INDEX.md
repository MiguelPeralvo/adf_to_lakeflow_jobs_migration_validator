# LMV Knowledge Base

> Living wiki for ADF-to-Lakeflow Jobs migration validation. Agents consult this before acting and update it after learning. Modeled on Karpathy's LLM wiki approach.

## Structure

| File | Domain | When to Consult |
|------|--------|----------------|
| [adf-expressions.md](adf-expressions.md) | ADF expression syntax, semantics, and edge cases | Before generating/evaluating expressions |
| [adf-to-python-mappings.md](adf-to-python-mappings.md) | Canonical ADF function → Python translation rules | Before judging semantic equivalence |
| [wkmigrate-architecture.md](wkmigrate-architecture.md) | How wkmigrate works internally (IR, parsers, translators) | Before filing findings or planning fixes |
| [failure-modes.md](failure-modes.md) | Catalog of known failure patterns and their root causes | Before classifying adversarial loop results |
| [testing-strategies.md](testing-strategies.md) | Which testing approach to use for which scenario | Before starting an adversarial/sweep session |
| [lakeflow-jobs-patterns.md](lakeflow-jobs-patterns.md) | Databricks Lakeflow Jobs patterns and constraints | Before evaluating translation output quality |
| [cost-model.md](cost-model.md) | LLM API cost tracking per model and operation | After any LLM-consuming operation |
| [learnings.md](learnings.md) | Session-by-session discoveries (append-only log) | After every /lmv-autodev or adversarial session |
| [wkmigrate-fix-spec-W9-W10.md](wkmigrate-fix-spec-W9-W10.md) | Full fix spec for W-9 (Copy sql_reader_query) and W-10 (ForEach items) | When invoking /wkmigrate-autodev for these findings |
| [wkmigrate-fix-spec-W11-structural.md](wkmigrate-fix-spec-W11-structural.md) | Fix spec for W-11 (structural activity coverage gaps post W-9/W-10 fix) | When invoking /wkmigrate-autodev for structural resilience |
| [wkmigrate-fix-spec-W12-W13-copy-ifcondition.md](wkmigrate-fix-spec-W12-W13-copy-ifcondition.md) | Fix spec for W-12 (Copy query unreachable) + W-13 (IfCondition compound predicates) | When invoking /wkmigrate-autodev for remaining expression gaps |
| [wkmigrate-fix-spec-W14-parameter-activity-resolution.md](wkmigrate-fix-spec-W14-parameter-activity-resolution.md) | Fix spec for W-14 (best-effort resolution for undefined params/activities) | When invoking /wkmigrate-autodev for parameter resolution |
| [wkmigrate-fix-spec-W15-W16-join-variables.md](wkmigrate-fix-spec-W15-W16-join-variables.md) | Fix spec for W-15 (@join not supported) + W-16 (variables() not resolved) | The final 19.5% gap — fixes push adversarial rate from 80.5% to ~100% |
| [wkmigrate-fix-spec-W17-W18-W19-semantic-bugs.md](wkmigrate-fix-spec-W17-W18-W19-semantic-bugs.md) | Fix spec for W-17 (firstRow flattening) + W-18 (missing type coercion) + W-19 (variables taskKey) | Semantic correctness bugs — expressions resolve but produce wrong Python |
| [wkmigrate-fix-spec-issue-refs-extensibility.md](wkmigrate-fix-spec-issue-refs-extensibility.md) | Add GitHub issue reference comments to ExpressionContext enum | Documentation-only — breadcrumbs for future activity type implementers |

## Usage Protocol

### Before acting (Phase 0.5 in /lmv-autodev):
1. Read `INDEX.md` to identify relevant pages
2. Read the 1-3 most relevant pages for the task at hand
3. Use the knowledge to inform plan, generation config, and judge criteria

### After learning (Phase 5.5 in /lmv-autodev):
1. If a new failure mode was discovered → update `failure-modes.md`
2. If an expression mapping was clarified → update `adf-to-python-mappings.md`
3. If a cost observation was made → update `cost-model.md`
4. Always append to `learnings.md` with date + session ID + key insight

## Freshness

Each page has a `Last updated:` header. Pages older than 7 days should be reviewed for staleness when consulted. The adversarial loop auto-updates `failure-modes.md` and `cost-model.md`.
