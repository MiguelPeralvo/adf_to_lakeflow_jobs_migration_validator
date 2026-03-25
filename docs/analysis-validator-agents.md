# Deep Analysis: Agentic Validator Systems

> **Context:** Three interconnected validator systems for (1) ADF-to-Lakeflow conversion
> quality, (2) prompt-to-spec-to-artifact quality in the demo factory, and (3) a
> meta-level validator factory that produces both.

---

## 1. ADF-to-Lakeflow Conversion Validator

### Problem statement

wkmigrate translates ADF pipelines into Databricks Lakeflow Jobs. Today, validation is
manual: a person eyeballs the translated IR, checks the generated notebooks, and runs the
job. The question is whether we can build an agent that automates this validation and,
critically, feeds back into an **iterative improvement loop** so that the conversion tool
itself gets better over time.

### What needs to be validated

Based on analysis of wkmigrate's output, there are 10 quality dimensions:

| Dimension | Type | How to measure |
|---|---|---|
| **Activity coverage** | Deterministic | `non_placeholder_tasks / total_tasks` |
| **Expression coverage** | Deterministic | `resolved_expressions / total_expression_properties` |
| **Dependency preservation** | Deterministic | `valid_dependencies / total_adf_depends_on` |
| **Notebook syntax validity** | Deterministic | `compile(nb.content, '<gen>', 'exec')` per notebook |
| **Secret completeness** | Deterministic | `dbutils.secrets.get` refs in code vs `SecretInstruction` list |
| **Parameter wiring** | Deterministic | `dbutils.widgets.get` refs vs `JobParameterDefinition` list |
| **Not-translatable count** | Deterministic | `len(pipeline.not_translatable)` |
| **Control flow fidelity** | Structural | ForEach/IfCondition tree shape matches ADF intent |
| **Semantic equivalence** | LLM-as-judge | Does the generated Python expression do what the ADF expression does? |
| **Runtime success** | Execution | Task `result_state == "SUCCESS"` on a real Databricks cluster |

The first 7 are **programmatic assertions** — cheap, deterministic, run on every commit.
Dimensions 8-9 need structural/semantic analysis. Dimension 10 requires a live cluster.

### Architecture options

#### Option A: Layered eval suite (recommended for near-term)

```
Layer 1: Programmatic assertions (CI, every commit)
  ├─ Compile-check all generated notebooks
  ├─ Assert activity/expression/dependency coverage scores
  ├─ Assert secret/parameter completeness
  └─ Aggregate into a Conversion Confidence Score

Layer 2: LLM-as-judge for semantic equivalence (nightly)
  ├─ For each expression: present ADF expression + generated Python
  ├─ Judge: "Does this Python code produce the same result as the ADF expression?"
  ├─ Use MLflow Tunable Judges calibrated against known-good pairs
  └─ Track regression via MLflow experiments

Layer 3: Execution validation (on-demand / weekly)
  ├─ Deploy generated job to Databricks
  ├─ Run with test parameters
  ├─ Assert per-task success
  └─ Compare task values against expected outputs (golden set)
```

**Tooling:** DeepEval (pytest-like eval runner) + MLflow (tracing, judge builder) + existing
test infrastructure. No new framework needed.

**Pros:** Incremental, uses existing patterns, each layer adds value independently.
**Cons:** No automatic improvement loop — a human must analyze failures and fix the code.

#### Option B: DSPy optimization loop (recommended for iterative improvement)

```
┌─────────────────────────────────────────────────┐
│  DSPy Program: ADF Expression → Python Code     │
│                                                   │
│  Module 1: parse_expression(adf_expr) → AST      │
│  Module 2: emit_python(ast, context) → code      │
│  Module 3: validate_output(code, adf_expr) → ok  │
│                                                   │
│  Metric: semantic_equivalence_score(gold, pred)  │
│  Optimizer: MIPROv2 or SIMBA                     │
└─────────────────────────────────────────────────┘
```

The key insight: wkmigrate's expression emitter is essentially a **translation program**
(ADF expression language → Python). The function registry lambdas and the emitter's
special-case handling of `pipeline()`, `activity()`, `variables()` are hand-written rules.
DSPy could optimize the _prompts/instructions_ that guide an LLM to perform this translation
instead — or, more practically, DSPy could optimize the **semantic equivalence judge** that
validates the hand-written rules.

**Where DSPy fits best:**
- NOT replacing the deterministic parser/emitter (that would be slower and less reliable)
- YES optimizing the LLM judge that evaluates semantic equivalence
- YES generating new test cases (expressions) that stress-test the converter
- YES in a `Refine` loop that suggests code fixes when the judge identifies failures

**Tooling:** DSPy 3.x + MLflow integration (native in DSPy 3.0) + Databricks FMAPI for
LLM calls.

**Pros:** Automatic improvement of the judge, synthetic test generation, principled
optimization.
**Cons:** Framework lock-in for the DSPy-managed components, compilation cost (thousands of
LLM calls upfront), metric design burden.

#### Option C: Anthropic Bloom-style behavioral evaluation

Use Bloom's four-stage pipeline (Understand → Ideate → Rollout → Judge) to automatically
generate conversion evaluation scenarios:

1. **Understand:** Analyze wkmigrate's documented behavior and known limitations
2. **Ideate:** Generate ADF pipeline definitions that exercise edge cases (complex
   expressions, deep nesting, unusual activity types)
3. **Rollout:** Run each generated pipeline through wkmigrate's translator
4. **Judge:** Evaluate whether the translation is correct, using a calibrated judge

**Pros:** Automatic test generation, covers edge cases humans wouldn't think of.
**Cons:** Bloom is research-grade (not production-hardened), requires significant adaptation
to the wkmigrate domain.

### Recommended approach for wkmigrate

**Phase 1 (now):** Implement Option A — the layered eval suite. Add a `ConversionScorecard`
class that computes all 7 programmatic dimensions and returns a score. Wire it into CI.

**Phase 2 (next quarter):** Add Option B's judge optimization — use DSPy to build and
optimize a semantic equivalence judge, calibrated against the golden set of expression pairs
from `set_variable_activities.json`. Use `dspy.Refine` to auto-generate fix suggestions.

**Phase 3 (future):** Add Option C's synthetic test generation — use an LLM to generate
novel ADF pipelines that stress the converter, run them through the eval suite, and surface
failures for human review.

### Conversion Confidence Score formula

```python
score = (
    activity_coverage * 0.25
    + expression_coverage * 0.20
    + dependency_preservation * 0.15
    + notebook_validity * 0.15
    + parameter_completeness * 0.10
    + secret_completeness * 0.10
    + (1 - not_translatable_ratio) * 0.05
) * 100
```

A pipeline scoring 90+ is "high confidence" (auto-deploy). 70-90 is "review recommended."
Below 70 is "manual intervention required."

---

## 2. Prompt-to-Spec-to-Artifact Validator (Demo Factory)

### Problem statement

The business-multi-domain-demo-factory generates demos through a pipeline:
`NL prompt → DomainSpec (YAML) → Artifacts (data, dashboards, Genie rooms, apps)`.
Each stage can introduce quality issues. The demo factory already has a substantial
evaluation framework (15 modules, 1496 tests, LLM judges, quality gates). The question
is how to build an **agent validator** that evaluates the full pipeline end-to-end and
feeds into iterative improvement.

### What the demo factory already has

| Layer | Existing Capability |
|---|---|
| **Spec validation** | Pydantic v2 schema validation, FK validator, row count validator |
| **Artifact validation** | Post-deploy checks (Genie exists, dashboard published, app running) |
| **LLM judges** | Spec coherence, data quality, generation latency, artifact fidelity, app code quality |
| **Quality gate** | CI/CD gate comparing eval results vs baseline, blocks merge on regression |
| **Corpus testing** | 16 golden seeds, nightly regression suite |
| **A/B testing** | Prompt variant evaluation with MLflow |
| **Observability** | MLflow traces (AGENT/LLM/TOOL spans) on every operation |

### What's missing

1. **End-to-end pipeline validator:** No single agent validates `prompt → spec → artifact`
   as a connected chain. Each stage is validated independently — a spec can pass validation
   but produce a bad dashboard, or a dashboard can be syntactically valid but semantically
   wrong for the prompt.

2. **Spec-prompt alignment judge:** Does the generated spec actually capture the user's
   intent? The conversation agent produces a spec, but there's no judge that compares the
   spec against the original NL prompt for completeness and accuracy.

3. **Artifact-spec alignment judge:** Does the generated dashboard/Genie room actually
   match the spec? A dashboard might be valid Lakeview JSON but miss tables or show wrong
   metrics.

4. **Cross-artifact consistency:** Do the Genie instructions, dashboard SQL, and app code
   all reference the same tables with consistent semantics?

### Architecture options

#### Option A: Three-judge pipeline (recommended)

```
Prompt ──→ [Judge 1: Spec Alignment] ──→ Spec ──→ [Judge 2: Artifact Alignment] ──→ Artifacts
                                           │
                                           └──→ [Judge 3: Cross-Artifact Consistency]
```

**Judge 1 — Spec-Prompt Alignment:**
- Input: (NL prompt, generated DomainSpec YAML)
- Criteria: Does the spec contain every entity, surface, and constraint mentioned in the
  prompt? Does it omit anything irrelevant? Is the complexity tier appropriate?
- Implementation: MLflow Tunable Judge calibrated against 16 golden seeds where prompt →
  spec mappings are known-good

**Judge 2 — Artifact-Spec Alignment:**
- Input: (DomainSpec YAML, generated artifact)
- Per artifact type:
  - Dashboard: Do SQL queries reference the tables in the spec? Do widget titles match
    spec page descriptions?
  - Genie: Are exposed tables exactly the spec's listed tables? Do instructions reference
    the domain correctly?
  - App: Does Streamlit code import and query the spec's tables?
- Implementation: Mix of programmatic assertions (table name matching, SQL parsing via
  sqlglot) and LLM judge for semantic checks

**Judge 3 — Cross-Artifact Consistency:**
- Input: (all generated artifacts for a single demo run)
- Criteria: Do all artifacts reference the same table names? Are column names consistent?
  Do Genie sample questions match dashboard content?
- Implementation: Programmatic (extract table/column references from each artifact, compute
  set intersection)

**Tooling:** MLflow Tunable Judges (native in the demo factory) + DeepEval for the pytest-
like runner + existing quality gate infrastructure.

#### Option B: DSPy-optimized generation pipeline

Wrap the demo factory's agentic pipeline (ConversationAgent → SpecCompositionAgent →
DashboardGenerationAgent → GenieConfigAgent) as DSPy modules and optimize end-to-end.

```python
class DemoGenerationPipeline(dspy.Module):
    def __init__(self):
        self.spec_generator = dspy.ChainOfThought("prompt -> domain_spec")
        self.dashboard_generator = dspy.ChainOfThought("domain_spec -> dashboard_json")
        self.genie_generator = dspy.ChainOfThought("domain_spec -> genie_config")

    def forward(self, prompt):
        spec = self.spec_generator(prompt=prompt)
        dashboard = self.dashboard_generator(domain_spec=spec.domain_spec)
        genie = self.genie_generator(domain_spec=spec.domain_spec)
        return dspy.Prediction(spec=spec, dashboard=dashboard, genie=genie)
```

Optimize with MIPROv2 using a composite metric that scores spec alignment + artifact
quality + cross-consistency.

**Pros:** Automatic prompt optimization across the entire pipeline. If the conversation
agent's prompts are suboptimal, DSPy will improve them.
**Cons:** Requires rewriting the pipeline in DSPy abstractions (significant refactor).
The demo factory's existing `ResilientLLM` + tool-calling architecture doesn't map cleanly
to DSPy modules. The agentic fallback chain (agentic → deterministic → minimal) is hard to
express in DSPy's optimization framework.

#### Option C: Eval-Driven Development with Braintrust

Use Braintrust's EDD methodology:
1. Define evaluations as working specifications for each pipeline stage
2. Every change is tested against the eval suite before merging
3. Production failures are automatically converted into new eval cases via Loop
4. The eval suite grows organically from real usage

**Pros:** Industry-proven methodology, Loop automates scorer creation.
**Cons:** Vendor dependency (Braintrust is proprietary), adds another platform alongside
MLflow (the demo factory already uses MLflow extensively).

### Recommended approach for the demo factory

**Option A (three-judge pipeline)** is the best fit because:
- It builds on the existing evaluation infrastructure (MLflow judges, quality gate)
- It fills the specific gaps (spec-prompt alignment, artifact-spec alignment, cross-
  consistency) without requiring an architecture rewrite
- The 16 golden seeds provide immediate calibration data
- It integrates with the existing nightly eval runner and CI quality gate

For **iterative improvement**, use DSPy **selectively** — not to rewrite the pipeline, but
to optimize the three judges themselves:
- Use `dspy.SIMBA` or `MIPROv2` to optimize the judge prompts against human-labeled
  calibration data
- This is a "DSPy for eval" pattern: the judges are DSPy programs, the generation pipeline
  stays as-is

---

## 3. Validator Factory

### Problem statement

Both validators above (and future ones) share common patterns: defining quality dimensions,
building scorers (programmatic + LLM judge), calibrating against golden sets, tracking
regression, and feeding failures back into improvement loops. A **validator factory** would
abstract these patterns so that producing a new validator for a new domain is a
configuration task, not a development task.

### What a validator factory needs to produce

Given a **domain specification** (what system we're validating), the factory produces:

```
ValidatorFactory.create(
    domain="adf_to_lakeflow",
    input_type=ADFPipeline,
    output_type=PreparedWorkflow,
    quality_dimensions=[
        ProgrammaticDimension("activity_coverage", compute_fn=...),
        ProgrammaticDimension("notebook_validity", compute_fn=...),
        LLMJudgeDimension("semantic_equivalence", criteria="...", calibration_set=...),
        ExecutionDimension("runtime_success", runner=DatabricksJobRunner),
    ],
    golden_set=load_golden_pipelines(),
    scorecard_weights={...},
) -> Validator
```

The produced `Validator` has:
- `.evaluate(input, output) -> Scorecard` — run all dimensions, return scores
- `.evaluate_batch(pairs) -> Report` — run on a corpus, compute aggregates
- `.regression_check(current, baseline) -> bool` — CI gate
- `.suggest_improvements(failures) -> list[Suggestion]` — optional LLM-powered fix hints
- `.track(experiment_name)` — log to MLflow

### Architecture options

#### Option A: Configuration-driven factory (recommended)

A Python library with a declarative API:

```python
from validator_factory import ValidatorFactory, Dimension, LLMJudge, ProgrammaticCheck

factory = ValidatorFactory(
    tracking_backend="mlflow",         # or "braintrust", "langsmith"
    llm_provider="databricks_fmapi",   # or "anthropic", "openai"
)

wkmigrate_validator = factory.create(
    name="adf_to_lakeflow",
    dimensions=[
        ProgrammaticCheck(
            name="notebook_validity",
            check_fn=lambda output: all(
                _compiles(nb.content) for nb in output.all_notebooks
            ),
        ),
        LLMJudge(
            name="semantic_equivalence",
            criteria="Does the Python expression produce the same result as the ADF expression?",
            input_template="ADF: {adf_expression}\nPython: {python_expression}",
            calibration_examples=[...],
            model="claude-sonnet-4-6",
        ),
    ],
    scorecard=Scorecard(weights={"notebook_validity": 0.3, "semantic_equivalence": 0.7}),
    golden_set=GoldenSet.from_json("tests/resources/golden_pipelines.json"),
)

demo_factory_validator = factory.create(
    name="prompt_to_artifact",
    dimensions=[
        LLMJudge(name="spec_prompt_alignment", ...),
        LLMJudge(name="artifact_spec_alignment", ...),
        ProgrammaticCheck(name="cross_artifact_consistency", ...),
    ],
    ...
)
```

**Pros:** Simple, no framework lock-in, easy to understand and extend.
**Cons:** No automatic optimization — judges are static unless manually improved.

#### Option B: DSPy-native factory

Every validator is a DSPy program. The factory compiles validators using DSPy optimizers:

```python
class ValidatorModule(dspy.Module):
    def __init__(self, dimensions: list[DimensionModule]):
        self.dimensions = dimensions

    def forward(self, input, output):
        scores = {}
        for dim in self.dimensions:
            scores[dim.name] = dim(input=input, output=output)
        return dspy.Prediction(scorecard=scores)

# Factory optimizes the judge prompts
factory = DSPyValidatorFactory(optimizer="MIPROv2")
validator = factory.compile(
    ValidatorModule(dimensions=[...]),
    trainset=golden_set,
    metric=judge_human_agreement,
)
```

**Pros:** Judges improve automatically via DSPy optimization. The "evaluation of evaluators"
problem is addressed by optimizing judge-human agreement.
**Cons:** Full DSPy lock-in. Every judge must be a DSPy module. Compilation cost.

#### Option C: Databricks-native factory (MLflow + Agent Bricks)

Use Databricks' own evaluation infrastructure:
- **MLflow Tunable Judges** for LLM-as-judge dimensions
- **Agent Bricks** for automatic synthetic test generation
- **MLflow evaluate** for batch scoring
- **Judge Builder UI** for non-developer judge creation

```python
from mlflow.evaluators import make_judge
from databricks.agents import AgentBricks

# Create a judge from natural language criteria
equiv_judge = make_judge(
    name="semantic_equivalence",
    criteria="The Python code must produce identical output to the ADF expression "
             "for all possible input values",
    examples=calibration_examples,
)

# Auto-generate test cases
test_suite = AgentBricks.generate_tests(
    task_description="Translate ADF expressions to Python for Databricks notebooks",
    enterprise_data=adf_pipeline_corpus,
)

# Run evaluation
results = mlflow.evaluate(
    model=wkmigrate_translator,
    data=test_suite,
    evaluators=[equiv_judge, notebook_validity_check],
)
```

**Pros:** Native Databricks integration (where both wkmigrate and demo factory run),
no additional framework, visual Judge Builder for non-developers, Agent Bricks generates
tests automatically.
**Cons:** Vendor lock-in to Databricks, less flexible than a custom factory.

### Recommended approach

**Hybrid: Option A (configuration-driven factory) with Option C (Databricks-native) as
the backend.**

The factory provides the Python API and abstraction. Internally, it delegates to:
- MLflow Tunable Judges for LLM-as-judge dimensions
- MLflow evaluate for batch scoring and tracking
- Agent Bricks for synthetic test generation (when available)
- DSPy for judge optimization (optional, opt-in per dimension)

This avoids full lock-in to any single framework while leveraging the strongest capabilities
of each.

---

## Comparative Framework Analysis

### Which framework for which role?

| Role | Best fit | Runner-up | Why |
|---|---|---|---|
| **Eval runner** (pytest-like) | DeepEval | Braintrust | pytest integration, 50+ metrics, agent trace eval |
| **LLM judges** | MLflow Tunable Judges | Braintrust Loop | Native Databricks, calibratable with SME feedback |
| **Judge optimization** | DSPy MIPROv2/SIMBA | — | Only framework that optimizes judge prompts systematically |
| **Synthetic test generation** | Agent Bricks | Bloom (Anthropic) | Enterprise-data-aware, task-specific |
| **Production monitoring** | MLflow 3 | LangSmith | Already used in both projects |
| **Agent framework** (if needed) | Claude Agent SDK | LangGraph | Self-eval built in, minimal framework overhead |
| **Eval-driven development** | Braintrust EDD | DeepEval | Coined the methodology, Loop automates scorer creation |
| **Safety/adversarial** | Patronus AI | Inspect AI | Generative Simulators, Percival auto-fix |

### Decision matrix for the three validators

| Capability | Conversion Validator | Demo Factory Validator | Validator Factory |
|---|---|---|---|
| **Programmatic checks** | 7 dimensions | 4 existing + 1 new | Factory method: `ProgrammaticCheck(fn)` |
| **LLM judges** | 1 (semantic equiv) | 3 (alignment + consistency) | Factory method: `LLMJudge(criteria)` |
| **Golden set** | Expression pairs from fixtures | 16 curated seeds | Factory method: `GoldenSet.from_json()` |
| **Optimization** | DSPy for judge only | DSPy for judges only | Optional per-dimension |
| **Execution tests** | Databricks cluster | Databricks workspace | Factory method: `ExecutionDimension(runner)` |
| **Tracking** | MLflow | MLflow | Configurable backend |
| **CI gate** | Conversion Confidence Score | Existing quality gate | `validator.regression_check()` |

---

## Implementation Roadmap

### Phase 1: Conversion Scorecard (wkmigrate, 1-2 weeks)

Add a `ConversionScorecard` class to wkmigrate that computes the 7 programmatic dimensions
for any `PreparedWorkflow`. Wire into the existing test suite as an assertion helper.
No new dependencies.

```python
scorecard = ConversionScorecard.evaluate(prepared_workflow, source_pipeline)
assert scorecard.confidence >= 0.85
assert scorecard.notebook_validity == 1.0
```

### Phase 2: Three-judge pipeline (demo factory, 2-3 weeks)

Add `SpecPromptAlignmentJudge`, `ArtifactSpecAlignmentJudge`, and
`CrossArtifactConsistencyChecker` to `src/demo_factory/evaluation/`. Calibrate against the
16 golden seeds. Integrate into the nightly eval runner.

### Phase 3: Validator factory library (shared, 2-3 weeks)

Extract the common patterns from Phases 1-2 into a standalone Python package
(`validator-factory`) with the configuration-driven API described above. Both wkmigrate
and demo factory validators become instances of the factory.

### Phase 4: DSPy judge optimization (both projects, 1-2 weeks)

For each LLM judge, wrap it as a DSPy module and optimize the judge prompt using
MIPROv2 against human-labeled calibration data. Track optimization runs in MLflow.

### Phase 5: Synthetic test generation (both projects, 1-2 weeks)

Use Agent Bricks (or an LLM-based generator) to produce novel test cases that stress
each validator. Feed failures back into the golden set.

---

## Key Design Decisions

### 1. DSPy: optimize judges, not the converter

DSPy is powerful but has real limitations for production agent systems (framework lock-in,
modularity assumptions, compilation cost). The sweet spot is using DSPy to optimize the
**evaluation layer** (judges and test generators), not the production pipeline itself.
wkmigrate's deterministic parser/emitter should stay deterministic. The demo factory's
agentic pipeline should stay in its current architecture. But the judges that evaluate
their outputs can be DSPy-optimized programs.

### 2. MLflow as the tracking backbone

Both projects already use MLflow. The validator factory should log all evaluation results
to MLflow experiments, enabling cross-run comparison, regression detection, and the
Tunable Judges workflow. No need to introduce Braintrust or LangSmith as additional
platforms.

### 3. Programmatic assertions first, LLM judges second

The "evaluation of evaluators" problem is real — even frontier LLM judges are unreliable
on many dimensions. The validator factory should enforce a layered approach: programmatic
checks run first (cheap, deterministic, trustworthy), LLM judges run second (for
subjective dimensions where programmatic checks are insufficient), and human review runs
periodically (for calibration).

### 4. The factory produces validators, not frameworks

The validator factory should be a library, not a framework. It produces validator instances
that are plain Python objects with `.evaluate()` and `.regression_check()` methods.
Validators can be used in pytest, CI pipelines, notebooks, or production monitoring —
they don't impose architectural constraints on the systems they validate.

### 5. Golden sets grow from failures

Both validators start with curated golden sets (expression fixtures for wkmigrate, 16
seeds for demo factory). Over time, the golden sets should grow from production failures:
when a conversion or generation fails in the wild, the failure case is added to the golden
set. This is the Braintrust "eval-driven development" pattern applied without the Braintrust
platform.
