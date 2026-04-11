# wkmigrate alpha_1 → pr/27-N Replay Handoff

> **Purpose.** Input document for `/wkmigrate-autodev` to percolate alpha_1-only work into the canonical `pr/27-N` branch sequence. Written by `/lmv-autodev` session on 2026-04-09 after the architectural decision that **pr/27-N is canonical** (not alpha_1's phase merges).
>
> **Target consumer.** A separate Claude session running `/wkmigrate-autodev` against `MiguelPeralvo/wkmigrate`.
>
> **Repo path.** `/Users/miguel/Code/wkmigrate` — fork: `MiguelPeralvo/wkmigrate`, upstream: `ghanse/wkmigrate`
>
> **Date of analysis.** 2026-04-09 (alpha_1 at `f68f324`, pr/27-3 at `3d8c541`, pr/27-4 at tip of same series)

---

## Architectural Decision (2026-04-09)

**pr/27-N (pr/27-0 → pr/27-1 → pr/27-2 → pr/27-3 → pr/27-4)** is the canonical issue #27 implementation.

**alpha_1** independently merged the abandoned `feature/27-phase*` branches, then grew additional work on top. That work does NOT exist on the pr/27-N series. It must be replayed (ported) as new commits on top of the relevant pr/27 branch so the pr/27-N series can stand alone as the complete implementation.

**Do NOT** merge pr/27-3 into alpha_1 (attempted 2026-04-09, produced 17 conflicts from parallel implementations). Instead, port alpha_1's unique enhancements forward to pr/27-N.

---

## What pr/27-N Already Has (DO NOT RE-PORT)

The pr/27 series covers:

| Branch | Content |
|--------|---------|
| `pr/27-0-expression-docs` | Design docs, meta-KPIs, PR strategy |
| `pr/27-1-expression-parser` | ADF expression AST/tokenizer/parser, `expression_emitter.py` (PythonEmitter), `expression_functions.py` (47-fn registry), `get_literal_or_expression()` shared utility, `ResolvedExpression` dataclass, `ExpressionContext` enum |
| `pr/27-2-datetime-emission` | `runtime/datetime_helpers.py`, format_converter (ADF .NET → Python strftime), `_wkmigrate_format_datetime()` helper |
| `pr/27-3-translator-adoption` | All leaf translators wired to use `get_literal_or_expression()`: SetVariable, Notebook.base_parameters, WebActivity.url/body/headers, ForEach.items, IfCondition.expression, Lookup.source_query (`_resolve_source_query`). Also `EmissionConfig`, `emission_config` param threading. |
| `pr/27-4-integration-tests` | Expression integration test suite |

---

## What alpha_1 Has That pr/27-N Does NOT — The Replay Candidates

These are the alpha_1-only commits that contain **unique work** not covered by pr/27-N's existing content. They must be ported to the appropriate pr/27 branch.

### Group A: Configurable Expression Emission Architecture (4 commits)

**Target branch:** `pr/27-3-translator-adoption` (or a new `pr/27-3.1-emission-architecture`)

| SHA | Subject | Files | Lines |
|-----|---------|-------|-------|
| `7dba1bf` | feat: add configurable expression emission architecture | 7 files | +853/−44 |
| `14adf75` | feat: thread emission_config through translator chain (H1 fix) | 9 files | +121/−56 |
| `1c1d0fe` | test: add emission config, strategy router, and Spark SQL emitter tests | 1 file | +167 |
| `5929f67` | feat: add integration testing meta-KPIs and emission integration tests | 2 files | +240/−1 |

**What these add:**

1. **`emission_config.py`** — `EmissionStrategy` enum (16 strategies: `notebook_python`, `spark_sql`, etc.), `ExpressionContext` enum (25 contexts), `EmissionConfig` frozen dataclass.
2. **`emitter_protocol.py`** — `EmitterProtocol` ABC + `EmittedExpression` dataclass.
3. **`strategy_router.py`** — `StrategyRouter` that dispatches expression emission to the correct emitter based on `(strategy, context)` lookup; falls back to Python for unmapped pairs.
4. **`spark_sql_emitter.py`** — `SparkSqlEmitter` implementing `EmitterProtocol` for SQL-safe contexts (e.g., `Lookup.source_query` where the output must be a SQL string, not Python code).
5. **`format_converter.py`** — ADF .NET datetime format → Spark SQL datetime format conversion (separate from the Python strftime conversion in pr/27-2).
6. **H1 fix (14adf75):** threads `emission_config` parameter through the entire translator chain: `translate_pipeline() → translate_activities_with_context() → visit_activity() → _dispatch_activity() → _topological_visit() → leaf translators → get_literal_or_expression()`. When `emission_config` is provided, expressions route through `StrategyRouter`; when `None`, behavior is unchanged (backward compat).
7. **Tests (1c1d0fe):** 24 new unit tests covering all emission architecture components.
8. **Integration tests (5929f67):** 9 integration tests requiring live ADF, covering SQL emission, strategy override, and Python fallback.

**Key insight for porting:** pr/27-3 already HAS `emission_config.py` and the threading, but in a simpler form (less strategies, less contexts). Alpha_1's version is richer. The port should **extend** pr/27-3's `emission_config.py` rather than replace it.

**Known issue in alpha_1's implementation (from previous `/lmv-autodev` analysis):**
- The `StrategyRouter` + 18 `EmissionStrategy` values are premature complexity — no translator currently uses anything other than `notebook_python`. The H1 bug (emission_config never threaded) was the actual problem, and once fixed, only `notebook_python` is ever active. Consider simplifying during port: keep `EmissionConfig` + the threading, but collapse the strategy/router to 2-3 strategies max (Python, SQL, JSON array).

---

### Group B: Expression Resolver Redesign + Translator Adoption (3 commits)

**Target branch:** `pr/27-3-translator-adoption` (these overlap with pr/27-3's content — port only the DELTA)

| SHA | Subject | Files | Lines |
|-----|---------|-------|-------|
| `040bcc4` | feat: redesign expression resolver API with shared utility | 3 files | +111/−21 |
| `3b24c74` | feat: adopt resolved expressions across notebook web and foreach | 6 files | +145/−76 |
| `550149f` | fix: address round2 expression review feedback | 20 files | +886/−102 |

**Context:** These are earlier versions of what pr/27-3 eventually polished. The `550149f` commit is the big one (886 insertions) and includes:
- `code_generator.py` changes for JDBC read queries
- `expression_ast.py` / `expression_parser.py` / `expression_tokenizer.py` refinements
- `expression_functions.py` additions (30+ lines)
- `datetime_helpers.py` expansion (50+ lines)
- Full test expansions across unit + integration

**Key porting question:** pr/27-3 may already have absorbed much of this. The `/wkmigrate-autodev` session should `git diff pr/27-3..alpha_1 -- <file>` per file to identify only the **net-new content** in alpha_1's versions. Likely candidates for net-new:
- Extra function entries in `expression_functions.py` (alpha_1 has more registered functions)
- Extra test cases in `test_expression_emitter.py` (alpha_1 has 237 lines vs pr/27-3's 148)
- Integration test infrastructure in `tests/integration/conftest.py` (ADF factory fixture)

---

### Group C: Bug Fixes (3 commits)

**Target branch:** whichever pr/27-N branch touches the relevant file

| SHA | Subject | Files | Lines | Target |
|-----|---------|-------|-------|--------|
| `e422849` | fix: address infra-discovered numeric, escaping, and azure auth bugs | 6 files | +86/−8 | pr/27-1 (expression_functions) + pr/27-3 (code_generator) |
| `939e4c3` | fix: address all lint, type, and formatting issues on alpha | 7 files | +28/−42 | pr/27-3 (widest surface) |
| `0dda6f5` | fix: integration test fixes for live ADF validation | 2 files | +17/−8 | pr/27-4 (integration tests) |

**Details of `e422849` (the most important one):**
- `expression_functions.py`: numeric literal handling fixes, string escaping fixes
- `workspace_definition_store.py`: Azure auth credential propagation fix
- Tests added for each fix

---

### Group D: Documentation + Planning (5 commits, LOWEST PRIORITY)

| SHA | Subject | Files |
|-----|---------|-------|
| `4955d04` | feat: add wkmigrate-autodev skill and dev planning docs | dev/ |
| `9ea6e3d` | docs: add autodev session ledger for issue 27 | dev/ |
| `34a19c0` | docs: add EX/PR meta-KPI series, PR strategy, and Lorenzo/Repsol artifacts | dev/ |
| `d911d83` | docs: add GD-11..14 and PR-2f..k meta-KPIs for doc/PR body substance | dev/ |
| `760a630` | docs: add comprehensive PR body drafts for the 5-PR issue #27 sequence | dev/ |

These are `dev/` directory docs. They're useful for context but don't change any `src/` or `tests/` code. Port if there's time; skip if not.

---

## The alpha_1-only Phase Commits (DO NOT PORT — superseded)

These 17+ commits represent the original `feature/27-phase*` implementation that has been **superseded** by the polished pr/27-N series. They should NOT be ported:

```
3927671 feat: add phase 1 ADF expression AST tokenizer and parser
947c747 feat: phase 2 expression emitter and parser integration
ca27508 feat: phase 3 add datetime runtime helpers for expressions
2702bf0 feat: phase 4 extend expression support across activities
19e82c9 test: phase 5 add integration coverage for complex expressions
0f731e8 integration: merge fork/feature/27-phase1-complex-expression-parser into alpha
1a88249 integration: merge fork/feature/27-phase2-expression-emitter into alpha
3084ba9 integration: merge fork/feature/27-phase3-datetime-runtime into alpha
710f50b integration: merge fork/feature/27-phase4-activity-expression-support into alpha
2de03ce integration: merge fork/feature/27-phase5-expression-integration-tests into alpha
26eef92 fix: address phase1 parser feedback
2641bc3 fix: address phase2 review feedback
6cc3b51 fix: address phase3 review feedback
3ec5596 fix: address phase4 review feedback
5672cef test: use pytest.raises for invalid timezone case (×3)
f8c37e7/f1d44ab/3fa5c27/9280f2a/9678fb5 (earlier iterative versions, superseded by 040bcc4/3b24c74)
```

Why superseded: pr/27-1 through pr/27-4 are the polished rewrites of phases 1-5 with ghanse's review feedback already incorporated.

---

## Porting Strategy

### Recommended Order

1. **Group C bug fixes first** — smallest, highest ROI, least conflict risk. Cherry-pick `e422849` onto pr/27-1 (expression_functions fixes) and pr/27-3 (code_generator). Cherry-pick `939e4c3` onto pr/27-3 for the lint fixes. Cherry-pick `0dda6f5` onto pr/27-4 for integration test fixes.

2. **Group A emission architecture second** — this is the big value-add. Port as a sequence of new commits on top of pr/27-3. The pr/27-3 branch already has a simpler `emission_config.py` and basic threading — the port should *extend* that, not replace it. Consider collapsing the 16 strategies to 2-3 per the design note above.

3. **Group B resolver redesign deltas third** — diff each file between alpha_1 and pr/27-3, extract only net-new content (functions, tests, lines). This is the most surgical.

4. **Group D docs last** (optional) — copy `dev/` files, adapt if needed.

### Branch Strategy

All ports target `MiguelPeralvo/wkmigrate` branches. Do NOT open PRs against `ghanse/wkmigrate` (the user explicitly prohibited this in the previous session).

Push to:
- `pr/27-1-expression-parser` for Group C expression_functions fixes
- `pr/27-3-translator-adoption` for Group A (emission arch) + Group B (resolver deltas) + Group C (lint)
- `pr/27-4-integration-tests` for Group C integration test fixes + Group B integration test additions

After all ports land, the pr/27-N series will be feature-complete with everything alpha_1 had, plus pr/27-N's own polish.

### Verification

After each port group:
```bash
cd /Users/miguel/Code/wkmigrate
poetry run pytest tests/unit -q --tb=no    # Must pass 100%
poetry run black --check .                  # Must be clean
poetry run ruff check .                     # Must be clean
poetry run mypy .                           # No new errors
```

After ALL ports complete:
```bash
# From the lmv repo, hot-swap to the ported pr/27-3 or pr/27-4
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions.json \
  --contexts set_variable,copy_query,lookup_query \
  --output /tmp/sweep_post_port.json
# Expected: copy_query still shows dropped_expression_field (W-9 isn't fixed by porting)
# Expected: set_variable still resolves 200/200
# Expected: lookup_query — W-7 is already fixed on pr/27-3 (200/200 resolved)
```

---

## Known Findings (W-series) and Their Port Impact

| Finding | Status on pr/27-3 | Port relevance |
|---------|-------------------|----------------|
| **W-7** (Lookup crash) | **Fixed** — `_resolve_source_query` uses `get_literal_or_expression()` | Already on pr/27-3; no port needed |
| **W-9** (Copy drops sql_reader_query) | **Open** — `_parse_sql_format_options` missing key | NOT fixed by porting (the gap exists on both). Needs a new commit on pr/27-3 extending `_parse_sql_format_options`. See handoff command in `dev/wkmigrate-handoff-ledger.md` W-9 block. |
| **W-11 candidate** (IfCondition op enum leaks `EQUAL_TO`) | Untested on pr/27-3 | May be fixed by the Group B port if `if_condition_activity_translator.py` changes include op-name normalisation |
| **W-12 candidate** (math lambda instead of static int()) | Untested on pr/27-3 | May be affected by Group A emission architecture (if StrategyRouter provides a cleaner coercion path) |

---

## `/wkmigrate-autodev` Invocation Command

Paste this into a new Claude session to start the replay:

```text
/wkmigrate-autodev dev/wkmigrate-alpha1-replay-handoff.md --autonomy semi-auto

This is a PORT session, not a net-new implementation session. The input file
(dev/wkmigrate-alpha1-replay-handoff.md in the lmv repo at
/Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude) contains
the full inventory of alpha_1-only commits that need to land on the pr/27-N
branch series.

Key constraints:
- pr/27-N is canonical (decided 2026-04-09)
- Push to MiguelPeralvo/wkmigrate branches only (no PRs to ghanse/wkmigrate)
- Run `make fmt` and `make test` after every commit
- Consider simplifying the 16-strategy StrategyRouter to 2-3 strategies
- The alpha_1 phase merges are superseded — do NOT port them

Start with Group C bug fixes (smallest, highest ROI), then Group A emission
architecture, then Group B resolver deltas. Group D docs are optional.

Acceptance: `poetry run pytest tests/unit -q --tb=no` + lint clean on the
final pr/27-3 and pr/27-4 tips.
```

---

## Reference: Full alpha_1-only Commit List (chronological, oldest first)

```
3927671 feat: add phase 1 ADF expression AST tokenizer and parser          ← SUPERSEDED
947c747 feat: phase 2 expression emitter and parser integration             ← SUPERSEDED
ca27508 feat: phase 3 add datetime runtime helpers for expressions          ← SUPERSEDED
2702bf0 feat: phase 4 extend expression support across activities           ← SUPERSEDED
19e82c9 test: phase 5 add integration coverage for complex expressions      ← SUPERSEDED
3fa5c27 feat: redesign expression resolver API with shared utility          ← iterative (final: 040bcc4)
9280f2a feat: adopt resolved expressions across notebook web and foreach    ← iterative (final: 3b24c74)
f1d44ab feat: redesign expression resolver API with shared utility          ← iterative (final: 040bcc4)
f8c37e7 feat: redesign expression resolver API with shared utility          ← iterative (final: 040bcc4)
9678fb5 test: align expression integration assertions with resolved expressions ← SUPERSEDED
040bcc4 feat: redesign expression resolver API with shared utility          ← GROUP B (port delta only)
3b24c74 feat: adopt resolved expressions across notebook web and foreach    ← GROUP B (port delta only)
550149f fix: address round2 expression review feedback                      ← GROUP B (big, port delta only)
e422849 fix: address infra-discovered numeric, escaping, and azure auth bugs ← GROUP C ✓ PORT
26eef92 fix: address phase1 parser feedback                                 ← SUPERSEDED
2641bc3 fix: address phase2 review feedback                                 ← SUPERSEDED
6cc3b51 fix: address phase3 review feedback                                 ← SUPERSEDED
3ec5596 fix: address phase4 review feedback                                 ← SUPERSEDED
5672cef test: use pytest.raises for invalid timezone case (×3)              ← SUPERSEDED
0f731e8 integration: merge fork/feature/27-phase1-complex-expression-parser ← SUPERSEDED
1a88249 integration: merge fork/feature/27-phase2-expression-emitter        ← SUPERSEDED
3084ba9 integration: merge fork/feature/27-phase3-datetime-runtime          ← SUPERSEDED
710f50b integration: merge fork/feature/27-phase4-activity-expression-support ← SUPERSEDED
2de03ce integration: merge fork/feature/27-phase5-expression-integration-tests ← SUPERSEDED
939e4c3 fix: address all lint, type, and formatting issues on alpha         ← GROUP C ✓ PORT
7dba1bf feat: add configurable expression emission architecture             ← GROUP A ✓ PORT
14adf75 feat: thread emission_config through translator chain (H1 fix)      ← GROUP A ✓ PORT
1c1d0fe test: add emission config, strategy router, and Spark SQL emitter tests ← GROUP A ✓ PORT
5929f67 feat: add integration testing meta-KPIs and emission integration tests ← GROUP A ✓ PORT
0dda6f5 fix: integration test fixes for live ADF validation                 ← GROUP C ✓ PORT
4955d04 feat: add wkmigrate-autodev skill and dev planning docs             ← GROUP D (optional)
9ea6e3d docs: add autodev session ledger for issue 27                       ← GROUP D (optional)
34a19c0 docs: add EX/PR meta-KPI series, PR strategy, and artifacts        ← GROUP D (optional)
d911d83 docs: add GD-11..14 and PR-2f..k meta-KPIs                         ← GROUP D (optional)
760a630 docs: add comprehensive PR body drafts for the 5-PR sequence        ← GROUP D (optional)
969e74d docs: add AD-series adoption depth meta-KPIs and property audit     ← GROUP D (optional)
f68f324 docs: add BR-series brevity meta-KPIs and measurement tooling       ← GROUP D (optional)
```

**Summary: 10 commits to port (Group A: 4, Group B: 3, Group C: 3), 17+ to skip (superseded), 7 optional (docs).**
