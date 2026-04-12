"""DSPy-based judge calibration with ManualCalibrator fallback.

When DSPy 3.x is installed, ``JudgeOptimizer`` wraps the LLMJudge as a DSPy
module and runs MIPROv2 or SIMBA optimisation against human-labelled
calibration pairs.

When DSPy is *not* installed (the common case during development),
``ManualCalibrator`` provides a lightweight fallback that selects the best
few-shot examples from a calibration set and produces an improved LLMJudge
with a richer prompt template.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge, JudgeProvider

# ---------------------------------------------------------------------------
# Calibration pair schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CalibrationPair:
    """A single human-labelled ADF-expression / Python-code pair."""

    adf_expression: str
    python_code: str
    human_score: float
    category: str = ""
    notes: str = ""

    def as_example_dict(self) -> dict[str, Any]:
        return {
            "input": self.adf_expression,
            "output": self.python_code,
            "score": self.human_score,
        }


def load_calibration_pairs(path: str | Path) -> list[CalibrationPair]:
    """Load calibration pairs from a JSON file.

    Expected schema::

        {
          "calibration_pairs": [
            {
              "adf_expression": "...",
              "python_code": "...",
              "human_score": 0.95,
              "category": "string",
              "notes": "optional"
            },
            ...
          ]
        }
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs: list[CalibrationPair] = []
    for item in data.get("calibration_pairs", []):
        pairs.append(
            CalibrationPair(
                adf_expression=item["adf_expression"],
                python_code=item["python_code"],
                human_score=float(item["human_score"]),
                category=item.get("category", ""),
                notes=item.get("notes", ""),
            )
        )
    return pairs


# ---------------------------------------------------------------------------
# Improved prompt template used by the ManualCalibrator
# ---------------------------------------------------------------------------

_CALIBRATED_CRITERIA = (
    "You are an expert judge for ADF-to-Python migration quality. "
    "Evaluate whether the Python output preserves the EXACT semantics of the "
    "original ADF expression. Pay careful attention to:\n"
    "  1. Type coercion — ADF functions like concat() auto-coerce to string; "
    "Python may need explicit str() calls.\n"
    "  2. Edge cases — null handling, empty strings, division-by-zero guards.\n"
    "  3. Function mapping — each ADF function must map to the correct Python "
    "equivalent (e.g., @toUpper → .upper(), @indexOf → .find()).\n"
    "  4. Nesting correctness — deeply nested expressions must preserve "
    "evaluation order and parenthesisation.\n"
    "  5. Parameter references — pipeline().parameters.X must map to the "
    "corresponding dbutils.widgets.get('X') call with proper coercion.\n"
    "  6. Activity output references — @activity('X').output.firstRow.col "
    "maps to dbutils.jobs.taskValues.get(taskKey='X', key='result')['firstRow']['col']. "
    "This is the CORRECT Databricks equivalent; do NOT penalise it.\n"
    "  7. Pipeline variables — @variables('X') maps to "
    "dbutils.jobs.taskValues.get(taskKey='set_variable_X', key='X'). "
    "This is the CORRECT Databricks equivalent; do NOT penalise it.\n"
    "  8. Integer division — ADF @div() maps to Python // (floor division). "
    "Nested arithmetic with correct operator precedence and // for div is CORRECT.\n"
    "\n"
    "Score 1.0 = perfect semantic equivalence.\n"
    "Score 0.7-0.9 = minor differences (e.g., extra whitespace, unnecessary "
    "str() wrapping) that do not change runtime behaviour.\n"
    "Score 0.3-0.6 = partial equivalence — some logic preserved, but at "
    "least one semantic difference.\n"
    "Score 0.0-0.2 = incorrect — the Python code does not reproduce the ADF "
    "expression's behaviour."
)

_CALIBRATED_TEMPLATE = (
    "=== ADF Expression ===\n{input}\n\n"
    "=== Python Translation ===\n{output}\n\n"
    "Evaluate semantic equivalence using the criteria above."
)


# ---------------------------------------------------------------------------
# ManualCalibrator — no DSPy required
# ---------------------------------------------------------------------------


def _select_diverse_examples(
    pairs: list[CalibrationPair],
    max_examples: int = 10,
) -> tuple[dict[str, Any], ...]:
    """Select a diverse, informative subset of calibration examples.

    Strategy:
    - Always include at least one low-score example (< 0.5) so the judge
      learns what *bad* translations look like.
    - Always include at least one perfect example (1.0).
    - Maximise category diversity.
    - Prefer examples at the score boundaries (near 0.0, 0.5, 0.7, 1.0).
    """
    if not pairs:
        return ()
    if len(pairs) <= max_examples:
        return tuple(p.as_example_dict() for p in pairs)

    # Bucket by score range
    buckets: dict[str, list[CalibrationPair]] = {
        "perfect": [],
        "good": [],
        "partial": [],
        "bad": [],
    }
    for p in pairs:
        if p.human_score >= 0.95:
            buckets["perfect"].append(p)
        elif p.human_score >= 0.7:
            buckets["good"].append(p)
        elif p.human_score >= 0.4:
            buckets["partial"].append(p)
        else:
            buckets["bad"].append(p)

    selected: list[CalibrationPair] = []
    seen_categories: set[str] = set()

    # Guarantee at least one from each non-empty bucket
    for bucket_name in ("perfect", "bad", "partial", "good"):
        bucket = buckets[bucket_name]
        if not bucket:
            continue
        # Prefer an unseen category
        for p in bucket:
            if p.category and p.category not in seen_categories:
                selected.append(p)
                seen_categories.add(p.category)
                break
        else:
            selected.append(bucket[0])

    # Fill remaining slots with category-diverse picks
    remaining = [p for p in pairs if p not in selected]
    remaining.sort(key=lambda p: (p.category in seen_categories, abs(p.human_score - 0.5)))
    for p in remaining:
        if len(selected) >= max_examples:
            break
        selected.append(p)
        if p.category:
            seen_categories.add(p.category)

    # Sort by score descending so the judge sees perfect examples first
    selected.sort(key=lambda p: -p.human_score)

    return tuple(p.as_example_dict() for p in selected)


class ManualCalibrator:
    """Fallback calibrator that works without DSPy.

    Loads human-labelled calibration pairs, selects a diverse subset as
    few-shot examples, and returns an improved :class:`LLMJudge` with a
    richer prompt template.
    """

    def __init__(
        self,
        calibration_pairs: list[CalibrationPair],
        *,
        max_examples: int = 10,
    ) -> None:
        self._pairs = list(calibration_pairs)
        self._max_examples = max_examples
        self._selected_examples: tuple[dict[str, Any], ...] | None = None

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        max_examples: int = 10,
    ) -> ManualCalibrator:
        """Convenience constructor that loads pairs from a JSON file."""
        pairs = load_calibration_pairs(path)
        return cls(pairs, max_examples=max_examples)

    @property
    def calibration_pairs(self) -> list[CalibrationPair]:
        return list(self._pairs)

    def select_examples(self) -> tuple[dict[str, Any], ...]:
        """Select the best few-shot examples from the calibration set."""
        if self._selected_examples is None:
            self._selected_examples = _select_diverse_examples(
                self._pairs,
                max_examples=self._max_examples,
            )
        return self._selected_examples

    def to_optimized_judge(
        self,
        provider: JudgeProvider,
        *,
        threshold: float = 0.7,
        model: str = "databricks-claude-opus-4-6",
    ) -> LLMJudge:
        """Return an improved LLMJudge with calibrated prompt + examples."""
        examples = self.select_examples()
        return LLMJudge(
            name="semantic_equivalence",
            criteria=_CALIBRATED_CRITERIA,
            input_template=_CALIBRATED_TEMPLATE,
            provider=provider,
            calibration_examples=examples,
            threshold=threshold,
            model=model,
        )

    def evaluate_agreement(
        self,
        judge: LLMJudge,
    ) -> float:
        """Compute human-agreement score by evaluating all calibration pairs.

        Returns the mean absolute agreement (1 - |human_score - judge_score|)
        across all calibration pairs.  This requires actual LLM calls.
        """
        if not self._pairs:
            return 0.0

        agreements: list[float] = []
        for pair in self._pairs:
            result = judge.evaluate(pair.adf_expression, pair.python_code)
            agreement = 1.0 - abs(pair.human_score - result.score)
            agreements.append(agreement)

        return sum(agreements) / len(agreements)


# ---------------------------------------------------------------------------
# JudgeOptimizer — requires DSPy 3.x
# ---------------------------------------------------------------------------


class JudgeOptimizer:
    """Wrap LLMJudge as a DSPy module and optimise with MIPROv2 or SIMBA.

    Raises :class:`ImportError` if DSPy is not installed.
    """

    def __init__(
        self,
        provider: JudgeProvider,
        *,
        optimizer: str = "MIPROv2",
        model: str = "databricks-claude-opus-4-6",
        threshold: float = 0.7,
    ) -> None:
        try:
            import dspy  # noqa: F401
        except ImportError:
            raise ImportError(
                "DSPy 3.x is required for JudgeOptimizer. "
                "Install it with: pip install dspy-ai>=3.0\n"
                "For a DSPy-free alternative, use ManualCalibrator instead:\n"
                "  from lakeflow_migration_validator.optimization.judge_optimizer "
                "import ManualCalibrator"
            ) from None

        self._dspy = dspy
        self._provider = provider
        self._optimizer_name = optimizer
        self._model = model
        self._threshold = threshold
        self._optimized_program: Any = None

    def optimize(
        self,
        calibration_pairs: list[CalibrationPair],
        metric_fn: Callable[..., float] | None = None,
    ) -> None:
        """Run DSPy optimisation against human-labelled calibration pairs.

        Parameters
        ----------
        calibration_pairs:
            Human-labelled expression pairs with ground-truth scores.
        metric_fn:
            A callable ``(example, prediction) -> float`` used by DSPy to
            evaluate the judge quality.  If *None*, a default agreement
            metric is used.
        """
        dspy = self._dspy

        # Build DSPy examples
        examples = []
        for pair in calibration_pairs:
            ex = dspy.Example(
                adf_expression=pair.adf_expression,
                python_code=pair.python_code,
                human_score=pair.human_score,
            ).with_inputs("adf_expression", "python_code")
            examples.append(ex)

        if metric_fn is None:

            def metric_fn(example, prediction, trace=None):
                predicted = float(prediction.score)
                expected = float(example.human_score)
                return 1.0 - abs(predicted - expected)

        # Build DSPy module wrapping the judge prompt
        class JudgeModule(dspy.Module):
            def __init__(self_module):
                super().__init__()
                self_module.judge = dspy.ChainOfThought("adf_expression, python_code -> score, reasoning")

            def forward(self_module, adf_expression, python_code):
                return self_module.judge(
                    adf_expression=adf_expression,
                    python_code=python_code,
                )

        module = JudgeModule()

        # Select optimizer
        if self._optimizer_name == "MIPROv2":
            optimizer = dspy.MIPROv2(metric=metric_fn, auto="light")
        elif self._optimizer_name == "SIMBA":
            optimizer = dspy.SIMBA(metric=metric_fn)
        else:
            raise ValueError(f"Unknown optimizer: {self._optimizer_name!r}. " f"Supported: 'MIPROv2', 'SIMBA'.")

        self._optimized_program = optimizer.compile(
            module,
            trainset=examples,
        )

    def to_optimized_judge(self) -> LLMJudge:
        """Return an LLMJudge with DSPy-optimised instructions and demos.

        Must call :meth:`optimize` first.
        """
        if self._optimized_program is None:
            raise RuntimeError("Call optimize() before to_optimized_judge(). " "No optimisation has been run yet.")

        # Extract the optimised instruction and demos from the DSPy program
        program = self._optimized_program

        # Try to extract improved instructions from the optimised program
        instructions = _CALIBRATED_CRITERIA
        demos: list[dict[str, Any]] = []

        # DSPy stores optimised predictors with demos
        for _name, predictor in program.named_predictors():
            if hasattr(predictor, "demos") and predictor.demos:
                for demo in predictor.demos:
                    demos.append(
                        {
                            "input": getattr(demo, "adf_expression", ""),
                            "output": getattr(demo, "python_code", ""),
                            "score": float(getattr(demo, "human_score", 1.0)),
                        }
                    )
            # Extract optimised extended signature instruction if available
            if hasattr(predictor, "extended_signature") and hasattr(predictor.extended_signature, "instructions"):
                instructions = predictor.extended_signature.instructions

        calibration_examples = tuple(demos) if demos else ()

        return LLMJudge(
            name="semantic_equivalence",
            criteria=instructions,
            input_template=_CALIBRATED_TEMPLATE,
            provider=self._provider,
            calibration_examples=calibration_examples,
            threshold=self._threshold,
            model=self._model,
        )


# ---------------------------------------------------------------------------
# Convenience: auto-select best available calibrator
# ---------------------------------------------------------------------------


def create_calibrator(
    calibration_path: str | Path,
    provider: JudgeProvider | None = None,
    *,
    optimizer: str = "MIPROv2",
    max_examples: int = 10,
) -> ManualCalibrator | JudgeOptimizer:
    """Return the best available calibrator.

    If DSPy is installed and *provider* is given, returns a
    :class:`JudgeOptimizer`.  Otherwise falls back to
    :class:`ManualCalibrator`.
    """
    try:
        import dspy  # noqa: F401

        if provider is not None:
            return JudgeOptimizer(provider, optimizer=optimizer)
    except ImportError:
        pass

    return ManualCalibrator.from_file(calibration_path, max_examples=max_examples)
