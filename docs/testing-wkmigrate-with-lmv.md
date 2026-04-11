# Testing wkmigrate with LMV — Complete Guide

> How to use the Lakeflow Migration Validator (lmv) to generate deep golden sets, stress-test wkmigrate's issue #27 (complex expressions) for hours, and feed findings back to `/wkmigrate-autodev`.

---

## Table of Contents

1. [Quick Start — 5 Commands](#quick-start)
2. [CLI Reference](#cli-reference)
3. [UI Reference](#ui-reference)
4. [Deep Testing Strategies for Issue #27](#deep-testing-issue-27)
5. [Agents + DSPy for Sophisticated Testing](#agents-and-dspy)
6. [Feeding Findings Back to wkmigrate](#feeding-findings-back)

---

## Quick Start

```bash
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude

# 1. Generate 50 adversarial pipelines targeting complex expressions (LLM mode)
PYTHONPATH=src poetry run lmv synthetic --count 50 --mode llm \
  --preset complex_expressions --output /tmp/gen_complex.json

# 2. Generate 50 more targeting math on parameters
PYTHONPATH=src poetry run lmv synthetic --count 50 --mode llm \
  --preset math_on_params --output /tmp/gen_math.json

# 3. Sweep all expressions through all 7 activity contexts
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions_adversarial.json \
  --output /tmp/sweep_results.json

# 4. Batch evaluate a generated pipeline set
PYTHONPATH=src poetry run lmv batch \
  --golden-set /tmp/gen_complex.json --threshold 80

# 5. Validate a single pipeline with full scorecard
PYTHONPATH=src poetry run lmv validate \
  --adf-json tests/fixtures/sample_pipeline.json
```

---

## CLI Reference

### Core Evaluation Commands

#### `lmv validate` — Score one pipeline

```bash
PYTHONPATH=src poetry run lmv validate --adf-json <path>
```

Runs a single ADF pipeline through wkmigrate → ConversionSnapshot → 7 dimensions → CCS score.

**Output:** JSON with `ccs_score`, `dimensions` breakdown (activity_coverage, expression_coverage, dependency_preservation, notebook_validity, parameter_completeness, secret_completeness, not_translatable_ratio).

#### `lmv validate-folder` — Batch score a folder

```bash
PYTHONPATH=src poetry run lmv validate-folder \
  --folder path/to/pipelines/ --threshold 80 --glob "*.json"
```

Scores every matching JSON file. Exits 0 if mean ≥ threshold, 1 otherwise.

#### `lmv batch` — Evaluate against a golden set

```bash
PYTHONPATH=src poetry run lmv batch \
  --golden-set golden_sets/pipelines.json --threshold 80
```

Evaluates a structured golden set (has `pipelines` or `expressions` key) and reports aggregate stats (mean, min, max, p10, p90, count below threshold).

#### `lmv regression-check` — CI gate

```bash
PYTHONPATH=src poetry run lmv regression-check \
  --golden-set golden_sets/regression_pipelines.json --threshold 90
```

Exit 0 if passes, exit 1 if regresses. Used in CI/CD.

---

### Expression-Focused Commands

#### `lmv sweep-activity-contexts` — The #27 workhorse

```bash
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions_adversarial.json \
  --contexts set_variable,copy_query,lookup_query,for_each,if_condition,web_body,notebook_base_param \
  --output /tmp/sweep.json
```

For each `(expression, activity_context)` pair:
1. Wraps the expression into a minimal ADF pipeline at the context's expression-bearing property
2. Runs it through wkmigrate via `adf_to_snapshot`
3. Counts resolved expressions, placeholder warnings, dropped-field warnings, errors

**7 Available Contexts:**

| Context | ADF Property | Issue #27 Relevance |
|---------|-------------|---------------------|
| `set_variable` | SetVariable.value | **Baseline** — already adopted, should be 100% resolved |
| `notebook_base_param` | Notebook.base_parameters.X | Adopted in pr/27-3, should resolve |
| `if_condition` | IfCondition.expression | Boolean predicates — tests op decomposition |
| `for_each` | ForEach.items | Array expressions — only `@createArray(...)` resolves |
| `web_body` | WebActivity.body | String/JSON expressions |
| `lookup_query` | Lookup.source.sql_reader_query | **W-7 target** — crashes on alpha_1, fixed on pr/27-3 |
| `copy_query` | Copy.source.sql_reader_query | **W-9 target** — silently dropped on ALL branches |

**Interpreting output:**

```json
{
  "by_context": {
    "set_variable": {"total": 28, "resolved": 28, "placeholder_count": 0, "error_count": 0},
    "lookup_query": {"total": 28, "resolved": 0, "placeholder_count": 0, "error_count": 28},
    "copy_query":   {"total": 28, "resolved": 0, "placeholder_count": 0, "not_translatable_count": 28}
  },
  "by_cell": {
    "string,set_variable": {"total": 10, "resolved": 10, ...},
    "math,copy_query":     {"total": 7,  "resolved": 0, "sample_failures": [...]}
  }
}
```

- `error_count` > 0 → wkmigrate CRASHED (W-7 territory)
- `not_translatable_count` > 0 with 0 resolved → wkmigrate DROPPED the field (W-9 territory)
- `placeholder_count` > 0 → wkmigrate couldn't handle the expression in this context

---

### Synthetic Generation Commands

#### `lmv synthetic` — Generate test pipelines

```bash
# Template mode (fast, deterministic, no LLM)
PYTHONPATH=src poetry run lmv synthetic \
  --count 100 --mode template --difficulty complex \
  --output /tmp/template_pipelines.json

# LLM mode (creative, varied, targets weak spots)
PYTHONPATH=src poetry run lmv synthetic \
  --count 50 --mode llm \
  --preset complex_expressions \
  --output /tmp/llm_pipelines.json

# LLM mode with custom prompt
PYTHONPATH=src poetry run lmv synthetic \
  --count 30 --mode llm \
  --prompt "Generate pipelines with 5+ nested @concat calls wrapping @pipeline().parameters references inside @if predicates" \
  --output /tmp/custom_pipelines.json

# With test data generation (CSV + SQL for Copy/Lookup activities)
PYTHONPATH=src poetry run lmv synthetic \
  --count 10 --mode llm --preset activity_mix \
  --test-data --output /tmp/with_testdata.json
```

**Available Presets:**

| Preset | Focus | Issue #27 Relevance |
|--------|-------|---------------------|
| `complex_expressions` | 3+ levels nesting, concat + formatDateTime + params + activity output | **HIGH** — tests deep expression resolution |
| `deep_nesting` | ForEach → IfCondition → ForEach control flow | **HIGH** — tests control flow expression handling |
| `math_on_params` | `@add(pipeline().parameters.count, 2)` patterns | **HIGH** — tests W-3 type coercion |
| `activity_mix` | All 7 supported types with dependency chains | **MEDIUM** — exercises all translator paths |
| `unsupported_types` | 50/50 supported/unsupported activities | LOW — tests placeholder generation |
| `pipeline_invocation` | ExecutePipeline cross-pipeline orchestration | LOW — separate from #27 |

---

### Comparison Commands

#### `lmv status` — Show available capabilities

```bash
PYTHONPATH=src poetry run lmv status
```

Reports which providers are configured: wkmigrate (always), judge (needs API key), harness, parallel.

#### `lmv history` — Show activity log

```bash
PYTHONPATH=src poetry run lmv history --limit 20
PYTHONPATH=src poetry run lmv history --pipeline "etl_daily_load"
```

---

## UI Reference

Start the UI:

```bash
cd apps/lmv
# Backend (port 8000)
poetry run uvicorn backend.main:app --reload --port 8000

# Frontend (port 5173)
cd frontend && npm run dev
```

Then open http://localhost:5173

### Pages

| Page | What It Does | Issue #27 Workflow |
|------|-------------|-------------------|
| **Validate** (`#/validate`) | Upload ADF JSON → score via wkmigrate → CCS % + dimension breakdown | Validate individual failing pipelines from sweep |
| **Expression** (`#/expression`) | Judge one ADF expr vs Python code → semantic equivalence score | Compare wkmigrate output against hand-written expected Python |
| **Synthetic** (`#/synthetic`) | Generate pipelines: pick mode/preset/count, stream results | Generate 50-200 pipelines targeting complex_expressions preset |
| **Batch** (`#/batch`) | Upload golden set → batch score → stats table | Run full golden set evaluation, find regressions |
| **Harness** (`#/harness`) | End-to-end pipeline fix loop | Run one pipeline through generate → evaluate → fix cycle |
| **Parallel** (`#/parallel`) | ADF vs Databricks side-by-side comparison | Compare ADF execution outputs against Databricks |
| **History** (`#/history`) | Past runs from SQLite activity log | Track score evolution over time |

### Synthetic Page Workflow (Most Relevant for Issue #27)

1. Select **Mode: LLM**
2. Select **Preset: Complex Expressions** (or Math on Parameters)
3. Set **Count: 50** (or more — each takes 5-10 seconds)
4. Click **Generate** — watch streaming progress
5. When done: scores appear per-pipeline, failures are highlighted
6. Export the generated golden set for future regression use

### Expression Page Workflow

1. Paste an ADF expression: `@concat('SELECT * FROM ', pipeline().parameters.tableName)`
2. Paste expected Python: `str('SELECT * FROM ') + str(dbutils.widgets.get('tableName'))`
3. Click **Judge** → get semantic equivalence score (0.0-1.0)
4. Run 6 Quick Tests (all categories at once)

---

## Deep Testing Strategies for Issue #27

### Strategy 1: Exhaustive Expression Sweep (minutes → hours)

Generate a large expression corpus, then sweep all contexts:

```bash
# Step 1: Generate 500 expressions covering all categories
PYTHONPATH=src poetry run python -c "
from lakeflow_migration_validator.synthetic.expression_generator import ExpressionGenerator
import json

gen = ExpressionGenerator()
cases = gen.generate(count=500)
corpus = {
    'count': len(cases),
    'expressions': [
        {'adf_expression': c.adf_expression, 'category': c.category, 'expected_python': c.expected_python}
        for c in cases
    ]
}
json.dump(corpus, open('/tmp/big_expression_corpus.json', 'w'), indent=2)
print(f'Generated {len(cases)} expression pairs')
"

# Step 2: Sweep all 7 contexts (500 × 7 = 3500 evaluations)
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set /tmp/big_expression_corpus.json \
  --output /tmp/big_sweep.json

# Step 3: Analyze failures
PYTHONPATH=src poetry run python -c "
import json
data = json.load(open('/tmp/big_sweep.json'))
for ctx, stats in sorted(data['by_context'].items()):
    pct = stats['resolved'] / max(stats['total'], 1) * 100
    print(f'{ctx:25s}  {stats[\"resolved\"]:4d}/{stats[\"total\"]:4d}  ({pct:.0f}%)  err={stats[\"error_count\"]}  nt={stats[\"not_translatable_count\"]}')
"
```

### Strategy 2: LLM-Generated Deep Pipelines (hours)

Generate hundreds of complex pipelines and batch-evaluate:

```bash
# Generate 200 pipelines across all issue-27-relevant presets (takes ~30 min with LLM)
for preset in complex_expressions deep_nesting math_on_params; do
  PYTHONPATH=src poetry run lmv synthetic \
    --count 70 --mode llm --preset $preset \
    --output /tmp/gen_${preset}.json
  echo "Done: $preset"
done

# Merge into one golden set
PYTHONPATH=src poetry run python -c "
import json, glob
all_pipelines = []
for f in glob.glob('/tmp/gen_*.json'):
    data = json.load(open(f))
    if 'pipelines' in data:
        all_pipelines.extend(data['pipelines'])
merged = {'pipelines': all_pipelines}
json.dump(merged, open('/tmp/merged_issue27_golden.json', 'w'), indent=2)
print(f'Merged {len(all_pipelines)} pipelines')
"

# Batch evaluate (scores each pipeline through all 7 dimensions)
PYTHONPATH=src poetry run lmv batch \
  --golden-set /tmp/merged_issue27_golden.json --threshold 70
```

### Strategy 3: Custom Adversarial Prompts (targeted hours)

Write prompts that specifically target known weak spots:

```bash
# Target W-2: pipeline().parameters in non-notebook contexts
PYTHONPATH=src poetry run lmv synthetic --count 50 --mode llm --prompt "
Generate pipelines where EVERY SetVariable, IfCondition predicate, and Copy source
path uses @pipeline().parameters.X references (never literal values). Include parameters
with types String, Int, Float, Bool. Each pipeline should have 5-8 activities with
dependency chains where downstream activities consume upstream SetVariable outputs
via @activity('SetVar1').output.pipelineReturnValue.value.
" --output /tmp/gen_w2_stress.json

# Target W-3: math on typed parameters
PYTHONPATH=src poetry run lmv synthetic --count 50 --mode llm --prompt "
Generate pipelines with intensive math on pipeline parameters. Use patterns like:
- @add(mul(pipeline().parameters.batch_size, pipeline().parameters.multiplier), 1)
- @div(pipeline().parameters.total_records, pipeline().parameters.partition_count)
- @mod(add(pipeline().parameters.offset, pipeline().parameters.page_size), 1000)
- @sub(pipeline().parameters.max_retries, activity('GetAttempt').output.firstRow.attempt)
All parameters should be declared as Int or Float type. Each pipeline 5-10 activities.
" --output /tmp/gen_w3_stress.json

# Target W-9: Copy activities with sql_reader_query expressions
PYTHONPATH=src poetry run lmv synthetic --count 50 --mode llm --prompt "
Generate pipelines where every Copy activity has a source.sql_reader_query property
that is an ADF expression (not a literal string). Use patterns like:
- @concat('SELECT * FROM ', pipeline().parameters.schema, '.', pipeline().parameters.table)
- @concat('SELECT TOP ', string(pipeline().parameters.limit), ' * FROM audit_log WHERE date > ''', formatDateTime(utcNow(), 'yyyy-MM-dd'), '''')
Include AzureSqlSource type with proper linked_service_definitions. Each pipeline 3-6 activities.
" --output /tmp/gen_w9_stress.json
```

### Strategy 4: Continuous Overnight Run (8+ hours)

```bash
#!/bin/bash
# overnight_stress.sh — run in background: nohup ./overnight_stress.sh &

OUTPUT_DIR=/tmp/lmv_overnight_$(date +%Y%m%d_%H%M%S)
mkdir -p $OUTPUT_DIR

cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude

# Phase 1: Generate (2-3 hours)
for i in $(seq 1 10); do
  for preset in complex_expressions deep_nesting math_on_params activity_mix; do
    PYTHONPATH=src poetry run lmv synthetic \
      --count 25 --mode llm --preset $preset \
      --output $OUTPUT_DIR/gen_${preset}_batch${i}.json 2>&1 | tee -a $OUTPUT_DIR/gen.log
  done
done

# Phase 2: Merge all generated pipelines
PYTHONPATH=src poetry run python -c "
import json, glob
all_pipelines = []
for f in sorted(glob.glob('$OUTPUT_DIR/gen_*.json')):
    try:
        data = json.load(open(f))
        if 'pipelines' in data:
            all_pipelines.extend(data['pipelines'])
    except Exception as e:
        print(f'Skip {f}: {e}')
merged = {'pipelines': all_pipelines}
json.dump(merged, open('$OUTPUT_DIR/merged_all.json', 'w'), indent=2)
print(f'Merged {len(all_pipelines)} pipelines')
"

# Phase 3: Batch evaluate all (1-2 hours for 1000 pipelines)
PYTHONPATH=src poetry run lmv batch \
  --golden-set $OUTPUT_DIR/merged_all.json --threshold 60 \
  > $OUTPUT_DIR/batch_results.json 2>&1

# Phase 4: Sweep adversarial expressions (30 min)
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions_adversarial.json \
  --output $OUTPUT_DIR/sweep_adversarial.json

# Phase 5: Summary
echo "=== OVERNIGHT RUN COMPLETE ===" | tee -a $OUTPUT_DIR/summary.txt
echo "Generated: $(find $OUTPUT_DIR -name 'gen_*.json' | wc -l) files" | tee -a $OUTPUT_DIR/summary.txt
echo "Results: $OUTPUT_DIR/batch_results.json" | tee -a $OUTPUT_DIR/summary.txt
echo "Sweep: $OUTPUT_DIR/sweep_adversarial.json" | tee -a $OUTPUT_DIR/summary.txt
```

### Strategy 5: Branch Comparison (pr/27-3 vs alpha_1)

```bash
# Test alpha_1
cd /Users/miguel/Code/wkmigrate && git checkout alpha_1
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions_adversarial.json \
  --output /tmp/sweep_alpha1.json

# Test pr/27-3
cd /Users/miguel/Code/wkmigrate && git checkout pr/27-3-translator-adoption
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions_adversarial.json \
  --output /tmp/sweep_pr273.json

# Compare
PYTHONPATH=src poetry run python -c "
import json
a = json.load(open('/tmp/sweep_alpha1.json'))['by_context']
b = json.load(open('/tmp/sweep_pr273.json'))['by_context']
print(f'{\"Context\":25s}  {\"alpha_1\":>12s}  {\"pr/27-3\":>12s}  {\"Delta\":>8s}')
print('-' * 60)
for ctx in sorted(set(a) | set(b)):
    ar = a.get(ctx, {}).get('resolved', 0)
    at = a.get(ctx, {}).get('total', 1)
    br = b.get(ctx, {}).get('resolved', 0)
    bt = b.get(ctx, {}).get('total', 1)
    print(f'{ctx:25s}  {ar:4d}/{at:4d}  {br:4d}/{bt:4d}  {br-ar:+4d}')
"
```

---

## Agents + DSPy for Sophisticated Testing

### What's Already Built

lmv already has two DSPy-connected components:

1. **`optimization/judge_optimizer.py`** — Wraps the LLM judge as a DSPy module. When DSPy 3.x is installed, `JudgeOptimizer` runs MIPROv2/SIMBA against `golden_sets/calibration_pairs.json` (20 human-labelled scores) to optimize the judge's prompt and few-shot selection. When DSPy is not installed, `ManualCalibrator` selects the best few-shot examples without optimization.

2. **`synthetic/agent_generator.py`** — Three-phase LLM pipeline: plan → generate → validate. Uses `_WEAK_SPOTS` (8 converter failure modes) to bias generation toward known gaps.

### Architecture for Deep Agent-Based Testing

The key insight: **multiple specialized agents working in a feedback loop** can test wkmigrate from angles no single-pass generator can reach.

#### Agent 1: Adversarial Generator (DSPy-optimized)

```
┌─────────────────────────────────────────────────────┐
│  DSPy Module: AdversarialExpressionGenerator        │
│                                                     │
│  Signature:                                         │
│    weak_spot: str → adf_expression: str             │
│                                                     │
│  Metric: failure_rate on sweep_activity_contexts    │
│    (higher = better at finding bugs)                │
│                                                     │
│  Optimizer: MIPROv2 over 100 labeled examples       │
│    from golden_sets/calibration_pairs.json          │
└─────────────────────────────────────────────────────┘
```

**How it works:**
- Input: a weak_spot name (e.g., "nested_expressions", "math_on_params")
- Output: an ADF expression that maximally stresses that weak spot
- DSPy optimizes the generation prompt to maximize the **failure rate** (expressions that produce placeholders, crashes, or dropped fields = "good" adversarial examples)
- After optimization, the generator produces hundreds of maximally-adversarial expressions per weak spot

```python
# Pseudo-code for DSPy-optimized adversarial generator
import dspy

class AdversarialGen(dspy.Module):
    def __init__(self):
        self.generate = dspy.ChainOfThought("weak_spot -> adf_expression")

    def forward(self, weak_spot):
        return self.generate(weak_spot=weak_spot)

# Metric: does this expression fail when swept through activity contexts?
def adversarial_metric(example, prediction):
    expr = prediction.adf_expression
    snap = adf_to_snapshot(wrap_in_set_variable(expr))
    # Score = 1.0 if wkmigrate FAILED, 0.0 if it resolved fine
    return 1.0 if len(snap.resolved_expressions) == 0 else 0.0

# Optimize with MIPROv2
optimizer = dspy.MIPROv2(metric=adversarial_metric, num_candidates=50)
optimized_gen = optimizer.compile(AdversarialGen(), trainset=seed_examples)
```

#### Agent 2: Semantic Oracle (DSPy-optimized judge)

```
┌─────────────────────────────────────────────────────┐
│  DSPy Module: SemanticEquivalenceJudge              │
│                                                     │
│  Signature:                                         │
│    adf_expression: str, python_code: str            │
│    → score: float, failure_modes: list[str]         │
│                                                     │
│  Metric: correlation with human_score on            │
│    golden_sets/calibration_pairs.json               │
│                                                     │
│  Optimizer: MIPROv2 or BootstrapFewShot             │
│    (20 calibration pairs → optimal prompt + demos)  │
└─────────────────────────────────────────────────────┘
```

**How it works:**
- Already partially implemented in `optimization/judge_optimizer.py`
- DSPy finds the prompt + few-shot selection that maximally correlates with human judgements
- Once optimized, the judge can evaluate thousands of expression pairs with high accuracy
- Failure modes are structured: `function_not_mapped`, `type_coercion_missing`, `nesting_depth_exceeded`, etc.

#### Agent 3: Coverage Maximizer (multi-agent orchestration)

```
┌────────────────────────────────────────────────────────────────────┐
│  Orchestrator Loop (runs for hours)                                │
│                                                                    │
│  1. Agent 1 generates 100 adversarial expressions                  │
│  2. sweep_activity_contexts runs them through all 7 contexts       │
│  3. Agent 2 judges each (expression, wkmigrate_output) pair        │
│  4. Failures are clustered by failure_mode                         │
│  5. New weak_spots discovered → fed back to Agent 1                │
│  6. Repeat until coverage plateaus or budget exhausted             │
│                                                                    │
│  Output: findings.json (new W-findings for /wkmigrate-autodev)     │
└────────────────────────────────────────────────────────────────────┘
```

This is the **closed-loop adversarial testing** that the current system lacks. It evolves its attack surface as it discovers new failure modes.

#### Agent 4: Mutation Tester

```
┌─────────────────────────────────────────────────────┐
│  Takes a PASSING pipeline and mutates it:           │
│                                                     │
│  Mutations:                                         │
│  - Inject @pipeline().parameters.X into literals    │
│  - Nest an expression one level deeper              │
│  - Replace activity type with unsupported one       │
│  - Add dependency cycle                             │
│  - Change sql_reader_query from literal to expr     │
│                                                     │
│  Goal: find MINIMAL failing cases (delta debugging) │
│  Output: minimal_failing_pipelines.json             │
└─────────────────────────────────────────────────────┘
```

### Concrete Implementation Plan

#### Phase 1: DSPy Judge Optimization (2 hours)

```bash
# Install DSPy
poetry add dspy-ai --group dev

# Run the existing optimizer against calibration pairs
PYTHONPATH=src poetry run python -c "
from lakeflow_migration_validator.optimization.judge_optimizer import JudgeOptimizer
from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge, JudgeProvider

provider = JudgeProvider.from_env()  # needs ANTHROPIC_API_KEY or similar
optimizer = JudgeOptimizer(provider)
result = optimizer.optimize('golden_sets/calibration_pairs.json')
print(f'Optimized prompt quality: {result.quality_score}')
result.save('golden_sets/optimized_judge.json')
"
```

#### Phase 2: Adversarial Generator with DSPy (4 hours)

```python
# New file: src/lakeflow_migration_validator/optimization/adversarial_optimizer.py

import dspy
from lakeflow_migration_validator.adapters.wkmigrate_adapter import adf_to_snapshot
from lakeflow_migration_validator.synthetic.activity_context_wrapper import (
    wrap_in_set_variable, wrap_in_copy_query, wrap_in_lookup_query,
    sweep_activity_contexts, ACTIVITY_CONTEXTS,
)

class GenerateAdversarialExpression(dspy.Signature):
    """Generate an ADF expression that will FAIL translation in at least one activity context."""
    weak_spot = dspy.InputField(desc="Which converter weakness to target")
    category = dspy.InputField(desc="Expression category: string, math, datetime, logical, collection, nested")
    adf_expression = dspy.OutputField(desc="A valid ADF @expression that stresses the weak spot")

class AdversarialGenerator(dspy.Module):
    def __init__(self):
        self.gen = dspy.ChainOfThought(GenerateAdversarialExpression)

    def forward(self, weak_spot, category):
        return self.gen(weak_spot=weak_spot, category=category)

def failure_metric(example, prediction, trace=None):
    """Score 1.0 if the expression fails in at least 2 activity contexts."""
    expr = prediction.adf_expression
    if not expr.startswith("@"):
        return 0.0
    corpus = [{"adf_expression": expr, "category": "test"}]
    try:
        result = sweep_activity_contexts(corpus, adf_to_snapshot,
                                          contexts=["set_variable", "copy_query", "lookup_query"])
        failures = sum(1 for ctx in result["by_context"].values()
                      if ctx["resolved"] == 0 and ctx["total"] > 0)
        return min(failures / 3.0, 1.0)  # normalize to [0, 1]
    except Exception:
        return 0.5  # crashed = partially adversarial

# Seed examples (from expressions_adversarial.json targets)
seed_examples = [
    dspy.Example(
        weak_spot="math_on_params",
        category="math",
        adf_expression="@add(pipeline().parameters.count, 1)"
    ).with_inputs("weak_spot", "category"),
    # ... more seeds from the W-2/W-3/W-10 pairs
]

# Optimize
optimizer = dspy.MIPROv2(metric=failure_metric, num_candidates=30, max_bootstrapped_demos=5)
optimized = optimizer.compile(AdversarialGenerator(), trainset=seed_examples)

# Generate at scale
for weak_spot in ["nested_expressions", "math_on_params", "activity_output_chaining"]:
    for category in ["string", "math", "nested", "logical"]:
        result = optimized(weak_spot=weak_spot, category=category)
        print(f"{weak_spot}/{category}: {result.adf_expression}")
```

#### Phase 3: Closed-Loop Agent Orchestration (ongoing)

```python
# New file: src/lakeflow_migration_validator/agents/adversarial_loop.py

class AdversarialTestingLoop:
    """Run for hours: generate → evaluate → cluster → target → repeat."""

    def __init__(self, generator, evaluator, max_rounds=100):
        self.generator = generator  # DSPy-optimized AdversarialGenerator
        self.evaluator = evaluator  # sweep_activity_contexts + judge
        self.findings = []
        self.max_rounds = max_rounds
        self.weak_spot_scores = {}  # track which spots yield failures

    def run(self, budget_hours=8):
        """Main loop. Each round:
        1. Pick the highest-yield weak_spot
        2. Generate 50 expressions targeting it
        3. Sweep all contexts
        4. Judge failures
        5. Cluster new failure modes
        6. Update weak_spot_scores
        7. Emit findings for any new cluster
        """
        for round_num in range(self.max_rounds):
            # Pick target based on failure rate (explore-exploit)
            target = self._select_target()

            # Generate
            expressions = self._generate_batch(target, count=50)

            # Evaluate
            results = self._evaluate(expressions)

            # Cluster and file findings
            new_findings = self._cluster_failures(results)
            self.findings.extend(new_findings)

            # Update targeting scores
            self._update_scores(target, results)

            # Save checkpoint
            self._checkpoint(round_num)

    def _select_target(self):
        """UCB1-style explore-exploit over weak spots."""
        ...

    def _generate_batch(self, target, count):
        """Use DSPy-optimized generator for this weak spot."""
        ...

    def _evaluate(self, expressions):
        """Sweep + judge."""
        ...

    def _cluster_failures(self, results):
        """Group by failure_mode, emit new W-findings for unknown clusters."""
        ...
```

### DSPy Optimization Targets (Most to Least Impact)

| What to Optimize | Metric | Impact |
|-----------------|--------|--------|
| **Adversarial expression generator** | failure_rate across sweep contexts | Finds more bugs per expression |
| **Semantic equivalence judge** | correlation with human_score | More accurate scoring → less noise |
| **Pipeline complexity planner** | coverage of activity-type × expression-category space | Fewer redundant pipelines |
| **Failure-mode classifier** | agreement with manually-labelled failure_modes | Better clustering → cleaner findings |
| **Fix-sketch generator** | acceptance rate by /wkmigrate-autodev | Faster upstream fixes |

### Multi-Agent Architecture (Claude Code Agents)

Use Claude Code's `Agent` tool with `isolation: "worktree"` for parallel testing:

```
┌──────────────────────────────────────────────────────────────┐
│  Main Session                                                 │
│                                                               │
│  Agent 1 (worktree): Generate 100 expressions × category     │
│  Agent 2 (worktree): Generate 100 pipelines × preset         │
│  Agent 3 (foreground): Sweep + judge + cluster                │
│  Agent 4 (background): File findings as GH issues             │
│                                                               │
│  All agents write to /tmp/lmv_session_<id>/                   │
│  Main session merges results into golden_sets/                │
└──────────────────────────────────────────────────────────────┘
```

This leverages Claude Code's native parallel agent infrastructure to run generation + evaluation concurrently.

---

## Feeding Findings Back to wkmigrate

### From Sweep Results → Filed Issue

```bash
# 1. Run sweep, save results
PYTHONPATH=src poetry run lmv sweep-activity-contexts \
  --golden-set golden_sets/expressions_adversarial.json \
  --output /tmp/sweep.json

# 2. Extract failures by context
PYTHONPATH=src poetry run python -c "
import json
data = json.load(open('/tmp/sweep.json'))
for cell_key, cell in data['by_cell'].items():
    if cell['sample_failures']:
        print(f'\\n=== {cell_key} ({cell[\"resolved\"]}/{cell[\"total\"]}) ===')
        for f in cell['sample_failures'][:3]:
            print(f'  ADF: {f[\"adf_expression\"]}')
            if 'error' in f:
                print(f'  ERR: {f[\"error\"]}')
            if 'not_translatable' in f:
                for nt in f['not_translatable']:
                    print(f'  NT:  {nt.get(\"kind\")}: {nt.get(\"message\", \"\")[:100]}')
"

# 3. File as lmv issue (if new cluster found)
gh issue create -R MiguelPeralvo/adf_to_lakeflow_jobs_migration_validator \
  --title "[expressions] <description> (W-N)" \
  --label "wkmigrate-feedback,filed-by:lmv-autodev,area:expressions,kind:bug" \
  --body "$(cat dev/findings/W-N.md)"

# 4. Update issue map
# Edit dev/wkmigrate-issue-map.json → add new failure_signature entry

# 5. Hand off to /wkmigrate-autodev in a separate session
# Paste the handoff command from dev/wkmigrate-handoff-ledger.md
```

### The Full Feedback Loop

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  lmv sweep  │────▶│  File W-N    │────▶│ /wkmigrate-     │
│  (evaluate) │     │  (lmv issue) │     │  autodev (fix)  │
└─────────────┘     └──────────────┘     └────────┬────────┘
       ▲                                           │
       │                                           ▼
       │                                 ┌─────────────────┐
       └─────────────────────────────────│  git checkout    │
         hot-swap wkmigrate ref          │  <fixed-branch>  │
         re-validate (Phase 4.5)         └─────────────────┘
```

---

## Golden Set File Schemas

### `expressions.json` / `expressions_adversarial.json`

```json
{
  "count": 28,
  "expressions": [
    {
      "adf_expression": "@concat('a', 'b')",       // Required
      "category": "string",                         // Required: string|math|datetime|logical|collection|nested
      "expected_python": "str('a') + str('b')",     // Required
      "axis": "n_ary_concat",                       // Optional (adversarial only)
      "rationale": "Tests N-ary concat...",         // Optional (adversarial only)
      "referenced_params": [{"name": "x", "type": "String"}],  // Optional
      "targets": ["W-2", "W-3"]                     // Optional
    }
  ]
}
```

### `pipelines.json`

```json
{
  "pipelines": [
    {
      "adf_json": { "name": "...", "activities": [...] },
      "description": "...",
      "difficulty": "simple|medium|complex",
      "expected_snapshot": { "tasks": [...], ... }
    }
  ]
}
```

### `calibration_pairs.json`

```json
{
  "count": 20,
  "calibration_pairs": [
    {
      "adf_expression": "@concat('hello', 'world')",
      "python_code": "str('hello') + str('world')",
      "human_score": 1.0,
      "category": "string",
      "notes": "Perfect translation"
    }
  ]
}
```

---

## Environment Setup

```bash
# Required: wkmigrate installed (for adf_to_snapshot)
cd /Users/miguel/Code/wkmigrate
poetry install

# Required: lmv dependencies
cd /Users/miguel/Code/adf_to_lakeflow_jobs_migration_validator_claude
poetry install

# Optional: DSPy for optimization
poetry add dspy-ai --group dev

# Optional: LLM judge (for semantic equivalence scoring)
export ANTHROPIC_API_KEY=...  # or OPENAI_API_KEY

# Optional: Azure credentials (for adf-download, parallel testing)
export AZURE_TENANT_ID=...
export AZURE_CLIENT_ID=...
export AZURE_CLIENT_SECRET=...
```

### Verify Setup

```bash
PYTHONPATH=src poetry run lmv status
# Should show: wkmigrate=available, judge=available (if API key set)
```
