# L-Series: lmv General Meta-KPIs

These are the **always-included** baseline meta-KPIs for any `/lmv-autodev` session. They protect lmv's own integrity (test pass rate, lint compliance, the adapter boundary invariant). They are independent of which wkmigrate ref is under test.

> Reference loaded by `/lmv-autodev` Phase 1 Part B.

## Hard gates (zero tolerance — any move away from target = HARD STOP)

| ID | Meta-KPI | Target | Measurement |
|----|----------|--------|-------------|
| **LR-1** | Unit test pass rate (fast tier) | 100% | `make test` |
| **LR-2** | Regression count (fast tier) | 0 | failed-test count from LR-1 |
| **LA-1** | **Adapter boundary invariant**: exactly 1 file imports `wkmigrate.*` | 1 | ```Grep '^(from\|import) wkmigrate' src tests \| grep -v adapters/wkmigrate_adapter.py``` must be empty |
| **LA-2** | Contract frozen: `ConversionSnapshot` and child dataclasses remain `@dataclass(frozen=True, slots=True)` | 100% | grep + AST check on `src/lakeflow_migration_validator/contract.py` |
| **LT-3** | Regression pipelines pass | exit 0 | `lmv regression-check --golden-set golden_sets/regression_pipelines.json --threshold 90` |

## Soft gates (5% tolerance)

| ID | Meta-KPI | Target | Measurement |
|----|----------|--------|-------------|
| **LR-3** | Unit test pass rate (full tier) | 100% | `make test-all` (requires wkmigrate installed) |
| **LR-4** | Ruff compliance | 0 errors | `poetry run ruff check src tests` |
| **LR-5** | Black compliance | 0 diffs | `poetry run black --check src tests` |
| **LR-6** | mypy (informational) | no new errors | `poetry run mypy src` |
| **LA-3** | Graceful degradation preserved (startup OK with no providers) | clean | smoke run with no `DATABRICKS_HOST` / `AZURE_*` env vars |
| **LA-4** | Hot-swap endpoint healthy | 200 OK | smoke `POST /api/config/wkmigrate/apply` |
| **LA-5** | `evaluate_full` survives missing judge | passes | existing tests in `tests/unit/validation/test_llm_judge.py`, `test_evaluate_pipeline.py` |
| **LT-1** | Test count delta | ≥ 0 | pytest-collected count must not decrease |
| **LT-2** | Golden-set integrity (`count == len(expressions)`, all 6 categories present) | 100% | JSON parse of `golden_sets/expressions.json` |
| **LD-1** | Public API docstrings on new fns | 100% | review at PR time |
| **LD-2** | `docs/architecture.md` updated when layers change | yes | review at PR time |

## Notes

- **LA-1 is the most important invariant.** lmv's entire tool-agnostic contract rests on the fact that only `src/lakeflow_migration_validator/adapters/wkmigrate_adapter.py` imports `wkmigrate.*`. Breaking it implicitly couples every dimension to wkmigrate's data model and defeats the factory-extractable design.
- **`make test` (LR-1) is the fast tier**: it skips `test_wkmigrate_adapter.py` and `test_cli.py` so it does not require wkmigrate to be installed. **`make test-all` (LR-3) is the full tier** and runs everything.
- These KPIs are **wkmigrate-version-agnostic**. X-series KPIs (in `wkmigrate-issue-27-meta-kpis.md`) are pinned to a `wkmigrate_version_under_test`; these are not.
