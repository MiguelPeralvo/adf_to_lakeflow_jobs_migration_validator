# Implementation Sequence: 1 → 3 → 2

> **Order:** Build the Conversion Validator first, extract the Validator Factory second,
> build the Demo Factory Validator third.

---

## Why this order

### System 1 first (Conversion Validator)

| Reason | Detail |
|---|---|
| **Simpler domain** | ADF→Lakeflow is deterministic translation with one correct output per input. Quality dimensions are mostly programmatic (7 of 10). Lower ambiguity in what "correct" means. |
| **Existing test infrastructure** | wkmigrate has fixtures, integration tests, and a live ADF+Databricks environment already running. The validator adds scoring on top of existing patterns. |
| **Discovers abstractions** | Building a concrete validator reveals what a `Dimension`, `Scorecard`, and `GoldenSet` actually need to be — decisions that are hard to make in the abstract. |
| **Immediate value** | Every wkmigrate PR gets a Conversion Confidence Score. Quality gaps become visible before the factory exists. |

### System 3 second (Validator Factory)

| Reason | Detail |
|---|---|
| **Extracted from working code** | The factory's abstractions (`ProgrammaticCheck`, `LLMJudge`, `Scorecard`, `GoldenSet`, `Report`) are refactored out of System 1's concrete classes — not designed top-down. |
| **One concrete instance to generalize from** | System 1 provides the reference implementation. The factory must reproduce System 1's behavior exactly (regression test: run factory-produced validator, compare output to original). |
| **Ready for System 2** | When System 2 starts, the factory exists and can be consumed immediately. System 2 becomes the factory's first "customer that didn't build it" — the real test of abstraction quality. |

### System 2 last (Demo Factory Validator)

| Reason | Detail |
|---|---|
| **More complex domain** | Generative pipeline with subjective quality. Multiple artifact types. Existing 15-module evaluation framework to integrate with. Higher risk of over-engineering if attempted first. |
| **Benefits from factory** | The three new judges (spec-prompt alignment, artifact-spec alignment, cross-consistency) are expressed as factory-produced dimensions — no hand-wiring. |
| **Tests the factory** | If the factory's API can express System 2's validator without contortions, the abstraction is right. If not, the factory is extended before it's published. |
| **Existing coverage buys time** | The demo factory already has 1496 tests, LLM judges, a quality gate, and 16 golden seeds. It's not unvalidated — it's partially validated with specific gaps. Those gaps aren't urgent. |

---

## Phase plan

### Phase 1: Lakeflow Migration Validator (System 1) — 2 weeks

**Week 1:**
- Implement the 7 programmatic dimensions as standalone functions
- Implement `ConversionScorecard` class that computes the CCS
- Add scorecard assertions to existing unit tests
- Wire into CI: every test run logs the CCS

**Week 2:**
- Implement the semantic equivalence LLM judge (MLflow Tunable Judge)
- Calibrate against expression pairs from `set_variable_activities.json`
- Implement the execution dimension (wraps existing `test_databricks_execution.py` pattern)
- Golden set: curate 20-30 pipeline fixtures with expected scores

**Deliverable:** `ConversionScorecard` class in wkmigrate, usable in tests and CI.

### Phase 2: Validator Factory (System 3) — 2 weeks

**Week 3:**
- Extract `Dimension`, `ProgrammaticCheck`, `LLMJudge`, `ExecutionDimension` protocols/classes
  from System 1's concrete implementations
- Extract `Scorecard`, `GoldenSet`, `Report` data classes
- Extract `ValidatorFactory.create()` that wires everything together
- Package as a standalone library (or a subpackage if collocated)

**Week 4:**
- Implement MLflow tracking integration (`validator.track()`)
- Implement regression checking (`validator.regression_check()`)
- Regression test: produce System 1's validator via the factory, confirm identical scores
- Optional: implement `factory.optimize_judge()` DSPy integration
- Optional: implement `factory.generate_tests()` synthetic test generation

**Deliverable:** `validator-factory` library with `ValidatorFactory`, `Dimension` hierarchy,
`Scorecard`, `GoldenSet`, `Report`, MLflow tracking.

### Phase 3: Demo Factory Validator (System 2) — 2-3 weeks

**Week 5:**
- Implement `spec_prompt_alignment` LLM judge using the factory
- Calibrate against the 16 golden seeds (prompt.md + seed.yaml pairs)
- Implement `artifact_spec_alignment` LLM judge (mix of programmatic + LLM)
- Implement `cross_artifact_consistency` programmatic check

**Week 6:**
- Integrate with existing `PreReleaseQualityGate` (as a dimension)
- Wire into the nightly eval runner
- Add DQS to the CI quality gate
- Curate additional golden seeds if calibration requires it

**Week 7 (optional):**
- DSPy-optimize the three judges against human-labeled calibration data
- Synthetic test generation: use LLM to produce novel prompts that stress the pipeline
- A/B evaluation: compare DQS before/after pipeline changes

**Deliverable:** Demo Factory Validator integrated into the existing evaluation framework,
producing a Demo Quality Score alongside the existing quality gate.

---

## Dependency graph

```
Phase 1                    Phase 2                    Phase 3
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│  Conversion     │       │  Validator       │       │  Demo Factory   │
│  Validator      │──────→│  Factory         │──────→│  Validator      │
│  (System 1)     │ extract│  (System 3)     │ consume│  (System 2)    │
└─────────────────┘       └─────────────────┘       └─────────────────┘
        │                         │                         │
        ▼                         ▼                         ▼
  CCS in wkmigrate CI      validator-factory lib      DQS in demo factory CI
```

Each phase produces a usable deliverable. Phases are sequential (each depends on the
previous), but each phase's deliverable is independently valuable.

---

## Risk mitigations

| Risk | Phase | Mitigation |
|---|---|---|
| System 1's abstractions don't generalize | Phase 2 | Keep System 1's concrete classes alongside factory-produced ones. If the factory can't reproduce System 1's scores, the concrete classes remain authoritative. |
| Factory API is too rigid for System 2 | Phase 3 | The factory supports escape hatches (custom `Dimension` protocol implementations). System 2 can always implement a dimension that doesn't fit the built-in types. |
| LLM judge quality is poor | Phase 1-3 | Start with programmatic checks only. Add LLM judges incrementally, calibrated against human labels. A judge with < 0.7 human agreement is not promoted to CI. |
| DSPy optimization is too expensive | Phase 2 | DSPy integration is optional (opt-in per dimension). The factory works without DSPy. |
| Scope creep | All phases | Each phase has a concrete deliverable and a 2-week timebox. If a phase takes longer, cut the optional items (DSPy, synthetic generation, A/B testing). |
