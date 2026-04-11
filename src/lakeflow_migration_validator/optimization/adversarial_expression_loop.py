"""Expression-focused adversarial testing loop.

Instead of generating full ADF pipelines (expensive, structurally fragile),
generates adversarial ADF *expressions* via LLM and sweeps each one across
all 7 activity contexts using the proven ``activity_context_wrapper`` wrappers.

Each expression is tested 7 ways (SetVariable, Notebook, IfCondition, ForEach,
WebActivity, Lookup, Copy) giving 7x more signal per LLM call than the
pipeline-level ``AdversarialLoop``.

The loop:
1. GENERATE: LLM produces N adversarial ADF expressions targeting weak spots
2. SWEEP: Each expression is wrapped in all 7 activity contexts and converted
3. SCORE: Per-cell resolution is tracked (resolved / placeholder / error)
4. CLUSTER: Failures grouped by (expression_pattern, failing_contexts)
5. FEEDBACK: Failure patterns steer the next generation round
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.synthetic.activity_context_wrapper import (
    sweep_activity_contexts,
)

# Type alias for streaming events.
ExpressionLoopEvent = dict[str, Any]

_EXPRESSION_GENERATION_PROMPT = """You are an Azure Data Factory expression expert. Generate {count} distinct ADF expressions that are designed to stress-test a migration tool that converts ADF to Databricks.

Target these weak spots:
{weak_spots}

Rules:
- Each expression must start with @ (ADF convention)
- Use real ADF functions: concat, replace, toUpper, toLower, trim, substring, indexOf,
  add, sub, mul, div, mod, equals, greater, less, and, or, not, if, coalesce,
  createArray, length, first, last, split, join, formatDateTime, utcNow,
  pipeline().parameters.X, activity('Name').output.firstRow.Y, variables('name')
- Include deeply nested expressions (3+ levels of function calls)
- Include expressions with pipeline().parameters references (these require type coercion)
- Include expressions that mix string and math operations
- Vary complexity: some simple (1 function), some moderate (2-3 nested), some extreme (4+ nested)
- Make them realistic — patterns you'd see in real ADF pipelines

Output a JSON array of objects, each with:
- "adf_expression": the ADF expression string (with @ prefix)
- "category": one of "string", "math", "datetime", "logical", "collection", "nested"
- "difficulty": one of "simple", "moderate", "complex"

Output ONLY valid JSON. No markdown, no explanation.
{extra_instructions}"""

_FEEDBACK_PROMPT_SECTION = """
IMPORTANT: Previous rounds found these patterns cause failures in the migration tool.
Generate MORE expressions like these — they are the most valuable for finding bugs:
{failure_patterns}
"""


@dataclass(frozen=True, slots=True)
class ExpressionLoopConfig:
    """Configuration for the expression-focused adversarial loop."""

    max_rounds: int = 10
    expressions_per_round: int = 20
    convergence_patience: int = 3
    max_time_seconds: float = 3600.0
    max_llm_calls: int = 100
    contexts: tuple[str, ...] | None = None  # None = all 7
    target_weak_spots: tuple[str, ...] = (
        "nested_expressions",
        "math_on_params",
        "complex_conditions",
        "activity_output_chaining",
        "parameterized_paths",
    )
    golden_set_output_path: str | None = None


@dataclass(frozen=True, slots=True)
class ExpressionRoundResult:
    """Summary of a single expression adversarial round."""

    round_number: int
    expressions_generated: int
    total_cells: int
    cells_resolved: int
    cells_failed: int
    new_failure_patterns: int
    failure_pattern_keys: tuple[str, ...]
    per_context_rates: dict[str, float]
    elapsed_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class ExpressionLoopResult:
    """Final summary of the expression adversarial loop."""

    rounds_completed: int
    total_expressions: int
    total_cells: int
    total_resolved: int
    overall_resolution_rate: float
    unique_failure_patterns: int
    termination_reason: str
    round_results: tuple[ExpressionRoundResult, ...]
    discovered_patterns: dict[str, int] = field(default_factory=dict)
    per_context_rates: dict[str, float] = field(default_factory=dict)
    golden_set_path: str | None = None
    elapsed_seconds: float = 0.0


_WEAK_SPOT_DESCRIPTIONS = {
    "nested_expressions": "Deeply nested functions: @concat(formatDateTime(utcNow(),'yyyy-MM-dd'), '/', pipeline().parameters.env)",
    "math_on_params": "Math on pipeline parameters: @add(mul(pipeline().parameters.count, 2), 1) — requires int() coercion",
    "complex_conditions": "Compound boolean predicates: @and(greater(pipeline().parameters.threshold, 50), not(equals(pipeline().parameters.env, 'prod')))",
    "activity_output_chaining": "Upstream activity references: @activity('Lookup').output.firstRow.config_value",
    "parameterized_paths": "Expressions in file paths: @concat(pipeline().parameters.container, '/', formatDateTime(utcNow(), 'yyyy/MM/dd'))",
    "foreach_array_expressions": "Array-producing expressions: @createArray(concat('item_', pipeline().parameters.suffix), 'static_item')",
    "type_coercion_edges": "Mixed-type operations: @concat(string(add(pipeline().parameters.count, 1)), '_suffix')",
}


class AdversarialExpressionLoop:
    """Expression-focused adversarial testing orchestrator.

    Generates adversarial ADF expressions, sweeps them across activity contexts,
    and feeds failure patterns back to generate harder expressions.
    """

    def __init__(
        self,
        provider: JudgeProvider,
        *,
        convert_fn: Callable[[dict], Any],
        config: ExpressionLoopConfig | None = None,
        model: str | None = None,
    ):
        self._provider = provider
        self._convert_fn = convert_fn
        self._config = config or ExpressionLoopConfig()
        self._model = model
        self._llm_calls = 0
        self._all_expressions: list[dict] = []
        self._failure_patterns: dict[str, int] = {}
        self._context_resolved: dict[str, int] = {}
        self._context_total: dict[str, int] = {}

    def run(self) -> ExpressionLoopResult:
        """Run the full loop synchronously."""
        result: ExpressionLoopResult | None = None
        for event in self.run_stream():
            if event["type"] == "complete":
                result = event["result"]
        assert result is not None  # noqa: S101
        return result

    def run_stream(self):
        """Yield events for UI streaming."""
        start_time = time.monotonic()
        round_results: list[ExpressionRoundResult] = []

        for round_num in range(1, self._config.max_rounds + 1):
            yield {
                "type": "round_start",
                "round": round_num,
                "expressions_per_round": self._config.expressions_per_round,
            }

            round_result, events = self._run_round(round_num, start_time)
            yield from events
            round_results.append(round_result)

            yield {"type": "round_end", "result": round_result}

            should_stop, reason = self._should_stop(round_results, start_time)
            if should_stop:
                result = self._build_result(round_results, reason, start_time)
                yield {"type": "complete", "result": result}
                return

        result = self._build_result(round_results, "max_rounds", start_time)
        yield {"type": "complete", "result": result}

    def _run_round(self, round_num: int, loop_start: float) -> tuple[ExpressionRoundResult, list[ExpressionLoopEvent]]:
        """Execute a single round: generate expressions, sweep, cluster."""
        events: list[ExpressionLoopEvent] = []
        round_start = time.monotonic()

        # Generate expressions
        expressions = self._generate_expressions()
        self._all_expressions.extend(expressions)

        if not expressions:
            return (
                ExpressionRoundResult(
                    round_number=round_num,
                    expressions_generated=0,
                    total_cells=0,
                    cells_resolved=0,
                    cells_failed=0,
                    new_failure_patterns=0,
                    failure_pattern_keys=(),
                    per_context_rates={},
                    elapsed_seconds=time.monotonic() - round_start,
                ),
                events,
            )

        events.append(
            {
                "type": "generated",
                "round": round_num,
                "count": len(expressions),
                "categories": _count_categories(expressions),
            }
        )

        # Sweep through all activity contexts
        contexts = list(self._config.contexts) if self._config.contexts else None
        sweep_result = sweep_activity_contexts(expressions, self._convert_fn, contexts=contexts)

        # Aggregate results
        by_context = sweep_result.get("by_context", {})
        total_cells = 0
        cells_resolved = 0
        per_context_rates: dict[str, float] = {}

        for ctx_name, ctx_data in by_context.items():
            ctx_total = ctx_data.get("total", 0)
            ctx_resolved = ctx_data.get("resolved", 0)
            total_cells += ctx_total
            cells_resolved += ctx_resolved
            self._context_total[ctx_name] = self._context_total.get(ctx_name, 0) + ctx_total
            self._context_resolved[ctx_name] = self._context_resolved.get(ctx_name, 0) + ctx_resolved
            per_context_rates[ctx_name] = ctx_resolved / ctx_total if ctx_total else 0.0

        cells_failed = total_cells - cells_resolved

        # Cluster failures by expression pattern + failing context
        new_patterns: list[str] = []
        by_cell = sweep_result.get("by_cell", {})
        for cell_key, cell_data in by_cell.items():
            if cell_data.get("resolved", 0) == 0 and cell_data.get("total", 0) > 0:
                # This (category, context) pair has failures
                failures = cell_data.get("sample_failures", [])
                for failure in failures:
                    expr = failure.get("adf_expression", "")
                    pattern = _extract_failure_pattern(expr)
                    if pattern:
                        full_key = f"{cell_key}:{pattern}"
                        prev = self._failure_patterns.get(full_key, 0)
                        self._failure_patterns[full_key] = prev + 1
                        if prev == 0:
                            new_patterns.append(full_key)
                            events.append(
                                {
                                    "type": "new_pattern",
                                    "pattern": full_key,
                                    "expression": expr[:80],
                                    "cell": cell_key,
                                }
                            )

        round_elapsed = time.monotonic() - round_start
        round_result = ExpressionRoundResult(
            round_number=round_num,
            expressions_generated=len(expressions),
            total_cells=total_cells,
            cells_resolved=cells_resolved,
            cells_failed=cells_failed,
            new_failure_patterns=len(new_patterns),
            failure_pattern_keys=tuple(new_patterns),
            per_context_rates=per_context_rates,
            elapsed_seconds=round_elapsed,
        )
        return round_result, events

    def _generate_expressions(self) -> list[dict]:
        """Use LLM to generate adversarial expressions."""
        weak_spot_text = "\n".join(f"- {_WEAK_SPOT_DESCRIPTIONS.get(ws, ws)}" for ws in self._config.target_weak_spots)

        extra = ""
        if self._failure_patterns:
            top_patterns = sorted(self._failure_patterns, key=self._failure_patterns.get, reverse=True)[:5]  # type: ignore[arg-type]
            pattern_text = "\n".join(f"- {p}" for p in top_patterns)
            extra = _FEEDBACK_PROMPT_SECTION.format(failure_patterns=pattern_text)

        prompt = _EXPRESSION_GENERATION_PROMPT.format(
            count=self._config.expressions_per_round,
            weak_spots=weak_spot_text,
            extra_instructions=extra,
        )

        self._llm_calls += 1
        try:
            if hasattr(self._provider, "complete"):
                raw = self._provider.complete(prompt, model=self._model, max_tokens=8192)
            else:
                response = self._provider.judge(prompt, model=self._model)
                raw = response.get("reasoning", "")
            expressions = _parse_expression_list(raw)
            return _enrich_with_referenced_params(expressions)
        except Exception:
            return []

    def _should_stop(self, results: list[ExpressionRoundResult], start_time: float) -> tuple[bool, str]:
        """Check termination criteria."""
        elapsed = time.monotonic() - start_time
        if elapsed >= self._config.max_time_seconds:
            return True, "time_budget"
        if self._llm_calls >= self._config.max_llm_calls:
            return True, "llm_budget"
        if len(results) >= self._config.convergence_patience:
            recent = results[-self._config.convergence_patience :]
            if all(r.new_failure_patterns == 0 for r in recent):
                return True, "converged"
        return False, ""

    def _build_result(
        self,
        round_results: list[ExpressionRoundResult],
        reason: str,
        start_time: float,
    ) -> ExpressionLoopResult:
        """Build the final result and optionally export golden set."""
        total_cells = sum(r.total_cells for r in round_results)
        total_resolved = sum(r.cells_resolved for r in round_results)

        per_context_rates = {}
        for ctx_name in self._context_total:
            total = self._context_total[ctx_name]
            resolved = self._context_resolved[ctx_name]
            per_context_rates[ctx_name] = resolved / total if total else 0.0

        golden_set_path = None
        if self._config.golden_set_output_path and self._all_expressions:
            golden_set_path = _export_expression_golden_set(self._all_expressions, self._config.golden_set_output_path)

        return ExpressionLoopResult(
            rounds_completed=len(round_results),
            total_expressions=len(self._all_expressions),
            total_cells=total_cells,
            total_resolved=total_resolved,
            overall_resolution_rate=total_resolved / total_cells if total_cells else 0.0,
            unique_failure_patterns=len(self._failure_patterns),
            termination_reason=reason,
            round_results=tuple(round_results),
            discovered_patterns=dict(self._failure_patterns),
            per_context_rates=per_context_rates,
            golden_set_path=golden_set_path,
            elapsed_seconds=time.monotonic() - start_time,
        )


def _parse_expression_list(raw: str) -> list[dict]:
    """Parse LLM output into a list of expression dicts."""
    if not raw:
        return []
    # Strip markdown code blocks
    raw = re.sub(r"```json?\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)
    raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find a JSON array
        match = re.search(r"\[[\s\S]*\]", raw)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                return []
        else:
            return []

    if isinstance(parsed, list):
        return [
            e for e in parsed if isinstance(e, dict) and "adf_expression" in e and isinstance(e["adf_expression"], str)
        ]
    return []


def _enrich_with_referenced_params(expressions: list[dict]) -> list[dict]:
    """Extract pipeline().parameters.X references and add referenced_params.

    The activity context wrappers use ``referenced_params`` to inject parameter
    definitions into the synthetic pipeline so wkmigrate's resolver can map
    ``pipeline().parameters.X`` to ``dbutils.widgets.get('X')``. Without this,
    expressions referencing parameters fail silently.
    """
    param_pattern = re.compile(r"pipeline\(\)\.parameters\.(\w+)")
    for expr_dict in expressions:
        adf = expr_dict.get("adf_expression", "")
        params = param_pattern.findall(adf)
        if params:
            expr_dict["referenced_params"] = [{"name": p, "type": "String"} for p in sorted(set(params))]
    return expressions


def _extract_failure_pattern(expr: str) -> str | None:
    """Extract a classifiable pattern from a failing expression."""
    if not expr:
        return None
    # Extract the outermost function name
    match = re.match(r"@(\w+)\(", expr)
    if match:
        func = match.group(1).lower()
        # Check for nested complexity
        depth = expr.count("(")
        if "pipeline().parameters" in expr:
            return f"{func}+params+depth{depth}"
        if "activity(" in expr:
            return f"{func}+activity_ref+depth{depth}"
        return f"{func}+depth{depth}"
    if "pipeline().parameters" in expr:
        return "bare_param_ref"
    return "unknown"


def _count_categories(expressions: list[dict]) -> dict[str, int]:
    """Count expressions by category."""
    counts: dict[str, int] = {}
    for e in expressions:
        cat = e.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts


def _export_expression_golden_set(expressions: list[dict], output_path: str) -> str:
    """Write generated expressions as a golden set JSON."""
    from pathlib import Path

    output = {
        "count": len(expressions),
        "source": "adversarial_expression_loop",
        "expressions": expressions,
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2))
    return str(path)
