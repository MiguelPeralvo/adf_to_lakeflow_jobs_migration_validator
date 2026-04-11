"""DSPy-optimized semantic equivalence judge for ADF->Python translations.

Wraps the semantic equivalence evaluation as a proper DSPy program with:
- Typed signatures for input/output
- Chain-of-thought reasoning
- Multi-aspect evaluation (type coercion, nesting, function mapping, edge cases)
- Agreement metric against human-labelled calibration pairs
- MIPROv2 optimization for prompt/demo selection
- Export to LLMJudge for integration with the rest of lmv
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from lakeflow_migration_validator.dimensions.llm_judge import (
    DimensionResult,
    JudgeProvider,
    LLMJudge,
)
from lakeflow_migration_validator.optimization.judge_optimizer import (
    _CALIBRATED_CRITERIA,
    _CALIBRATED_TEMPLATE,
    load_calibration_pairs,
)

# ---------------------------------------------------------------------------
# DSPy import guard — module works as documentation without dspy installed
# ---------------------------------------------------------------------------

try:
    import dspy

    _HAS_DSPY = True
except ImportError:
    dspy = None  # type: ignore[assignment]
    _HAS_DSPY = False

# ---------------------------------------------------------------------------
# Failure mode taxonomy
# ---------------------------------------------------------------------------

FAILURE_MODES: tuple[str, ...] = (
    "type_coercion_missing",
    "function_mapping_wrong",
    "nesting_order_broken",
    "parameter_reference_broken",
    "null_handling_missing",
    "edge_case_unhandled",
    "semantically_correct",
)
"""Canonical set of failure modes for semantic equivalence evaluation."""


def _validate_failure_modes(modes: Sequence[str]) -> list[str]:
    """Return only modes that are in the canonical FAILURE_MODES set."""
    return [m for m in modes if m in FAILURE_MODES]


# ---------------------------------------------------------------------------
# DSPy Signature — defined only when DSPy is available
# ---------------------------------------------------------------------------


def _build_signature_class():
    """Build the SemanticEquivalenceSignature DSPy Signature class.

    Deferred construction so the module can be imported without dspy.
    """
    if not _HAS_DSPY:
        return None

    class SemanticEquivalenceSignature(dspy.Signature):
        """Evaluate whether a Python translation preserves the exact semantics
        of an ADF expression. Consider type coercion, function mapping, nesting
        correctness, parameter references, null handling, and edge cases.
        Score 1.0 = perfect semantic equivalence, 0.0 = completely wrong."""

        adf_expression: str = dspy.InputField(desc="The original ADF expression to evaluate against")
        python_code: str = dspy.InputField(desc="The Python translation to evaluate")
        category: str = dspy.InputField(
            desc="Expression category (string, math, datetime, logical, nested, collection, parameter)",
            default="",
        )
        score: float = dspy.OutputField(desc="Semantic equivalence score from 0.0 to 1.0")
        reasoning: str = dspy.OutputField(desc="Step-by-step explanation of the evaluation")
        failure_modes: list[str] = dspy.OutputField(
            desc=("List of failure modes found. Must be from: " + ", ".join(FAILURE_MODES))
        )

    return SemanticEquivalenceSignature


# Store reference so tests can check it
SemanticEquivalenceSignature = _build_signature_class()


# ---------------------------------------------------------------------------
# Multi-aspect DSPy Module
# ---------------------------------------------------------------------------


def _build_multi_aspect_judge():
    """Build the MultiAspectJudge DSPy Module.

    Deferred construction so the module can be imported without dspy.
    """
    if not _HAS_DSPY:
        return None

    Signature = _build_signature_class()

    class MultiAspectJudge(dspy.Module):
        """DSPy module that evaluates ADF->Python semantic equivalence.

        Uses ChainOfThought to reason through multiple evaluation aspects:
        - Type coercion correctness
        - Function mapping accuracy
        - Nesting/evaluation order
        - Parameter reference handling
        - Null/edge case handling
        """

        def __init__(self):
            super().__init__()
            self.judge = dspy.ChainOfThought(Signature)

        def forward(
            self,
            adf_expression: str,
            python_code: str,
            category: str = "",
        ):
            result = self.judge(
                adf_expression=adf_expression,
                python_code=python_code,
                category=category,
            )
            # Validate and sanitize failure_modes
            if hasattr(result, "failure_modes") and result.failure_modes:
                raw_modes = result.failure_modes
                if isinstance(raw_modes, str):
                    # DSPy may return a comma-separated string
                    raw_modes = [m.strip() for m in raw_modes.split(",")]
                result.failure_modes = _validate_failure_modes(raw_modes)
            return result

    return MultiAspectJudge


MultiAspectJudge = _build_multi_aspect_judge()


# ---------------------------------------------------------------------------
# Agreement metric
# ---------------------------------------------------------------------------


class AgreementMetric:
    """Callable metric for DSPy optimization: measures agreement with human labels.

    Computes: 1 - |human_score - predicted_score|, with a +0.1 bonus when
    predicted failure_modes match the expected failure category.
    """

    # Map categories to their most likely failure mode
    _CATEGORY_TO_FAILURE: dict[str, str] = {
        "string": "type_coercion_missing",
        "math": "type_coercion_missing",
        "datetime": "function_mapping_wrong",
        "logical": "function_mapping_wrong",
        "nested": "nesting_order_broken",
        "collection": "function_mapping_wrong",
        "parameter": "parameter_reference_broken",
    }

    def __call__(
        self,
        example: Any,
        prediction: Any,
        trace: Any = None,
    ) -> float:
        """Compute agreement between prediction and human label.

        Parameters
        ----------
        example:
            DSPy example with ``human_score`` and optionally ``category``.
        prediction:
            DSPy prediction with ``score`` and optionally ``failure_modes``.
        trace:
            Unused; required by DSPy metric signature.

        Returns
        -------
        float
            Agreement score in [0.0, 1.1] (can exceed 1.0 with bonus).
        """
        # Extract scores
        try:
            predicted_score = float(prediction.score)
        except (TypeError, ValueError, AttributeError):
            predicted_score = 0.0

        try:
            human_score = float(example.human_score)
        except (TypeError, ValueError, AttributeError):
            human_score = 0.0

        # Base agreement: 1 - absolute difference
        agreement = 1.0 - abs(human_score - predicted_score)

        # Bonus for matching failure category
        bonus = 0.0
        category = getattr(example, "category", "")
        expected_mode = self._CATEGORY_TO_FAILURE.get(category, "")

        if expected_mode and human_score < 0.8:
            # Only award bonus when human says translation is imperfect
            failure_modes = getattr(prediction, "failure_modes", [])
            if isinstance(failure_modes, str):
                failure_modes = [m.strip() for m in failure_modes.split(",")]
            if expected_mode in failure_modes:
                bonus = 0.1

        return min(1.0, agreement + bonus)


# ---------------------------------------------------------------------------
# Optimization result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Results from a DSPy judge optimization run."""

    train_agreement: float
    dev_agreement: float
    improvement_over_baseline: float
    num_trials: int
    best_demos: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    optimized_instructions: str = ""


# ---------------------------------------------------------------------------
# DSPy Judge Optimizer
# ---------------------------------------------------------------------------


class DSPyJudgeOptimizer:
    """Full DSPy optimization pipeline for the semantic equivalence judge.

    Wraps calibration pair loading, train/dev split, MIPROv2/SIMBA
    optimization, and export to LLMJudge.

    Raises
    ------
    ImportError
        If DSPy 3.x is not installed.
    """

    def __init__(
        self,
        provider: JudgeProvider,
        *,
        optimizer: str = "MIPROv2",
        model: str = "databricks-claude-sonnet-4-6",
        num_trials: int = 20,
    ) -> None:
        if not _HAS_DSPY:
            raise ImportError(
                "DSPy 3.x is required for DSPyJudgeOptimizer. "
                "Install it with: pip install dspy-ai>=3.0\n"
                "For a DSPy-free alternative, use ManualCalibrator instead:\n"
                "  from lakeflow_migration_validator.optimization.judge_optimizer "
                "import ManualCalibrator"
            )

        self._provider = provider
        self._optimizer_name = optimizer
        self._model = model
        self._num_trials = num_trials
        self._optimized_program: Any = None
        self._optimization_result: OptimizationResult | None = None
        self._metric = AgreementMetric()

    def optimize(self, calibration_path: str | Path) -> OptimizationResult:
        """Run DSPy optimization against human-labelled calibration pairs.

        Loads pairs from the given path, splits 80/20 into train/dev,
        runs the configured optimizer, and returns metrics.

        Parameters
        ----------
        calibration_path:
            Path to golden_sets/calibration_pairs.json or equivalent.

        Returns
        -------
        OptimizationResult
            Metrics from the optimization run.
        """
        pairs = load_calibration_pairs(calibration_path)
        if not pairs:
            raise ValueError(f"No calibration pairs found at {calibration_path}")

        # Build DSPy examples
        examples = []
        for pair in pairs:
            ex = dspy.Example(
                adf_expression=pair.adf_expression,
                python_code=pair.python_code,
                category=pair.category,
                human_score=pair.human_score,
            ).with_inputs("adf_expression", "python_code", "category")
            examples.append(ex)

        # 80/20 train/dev split
        split_idx = max(1, int(len(examples) * 0.8))
        trainset = examples[:split_idx]
        devset = examples[split_idx:]

        # Build the module
        module = MultiAspectJudge()

        # Compute baseline score on dev before optimization
        baseline_scores = []
        for ex in devset:
            pred = module(
                adf_expression=ex.adf_expression,
                python_code=ex.python_code,
                category=ex.category,
            )
            baseline_scores.append(self._metric(ex, pred))
        baseline_agreement = sum(baseline_scores) / len(baseline_scores) if baseline_scores else 0.0

        # Select optimizer
        if self._optimizer_name == "MIPROv2":
            optimizer = dspy.MIPROv2(
                metric=self._metric,
                auto="light",
                num_trials=self._num_trials,
            )
        elif self._optimizer_name == "SIMBA":
            optimizer = dspy.SIMBA(
                metric=self._metric,
                max_steps=self._num_trials,
            )
        else:
            raise ValueError(f"Unknown optimizer: {self._optimizer_name!r}. " f"Supported: 'MIPROv2', 'SIMBA'.")

        # Run optimization
        self._optimized_program = optimizer.compile(
            module,
            trainset=trainset,
            eval_kwargs={"devset": devset},
        )

        # Evaluate optimized program on train and dev
        train_scores = []
        for ex in trainset:
            pred = self._optimized_program(
                adf_expression=ex.adf_expression,
                python_code=ex.python_code,
                category=ex.category,
            )
            train_scores.append(self._metric(ex, pred))

        dev_scores = []
        for ex in devset:
            pred = self._optimized_program(
                adf_expression=ex.adf_expression,
                python_code=ex.python_code,
                category=ex.category,
            )
            dev_scores.append(self._metric(ex, pred))

        train_agreement = sum(train_scores) / len(train_scores) if train_scores else 0.0
        dev_agreement = sum(dev_scores) / len(dev_scores) if dev_scores else 0.0

        # Extract demos and instructions from optimized program
        demos: list[dict[str, Any]] = []
        instructions = ""
        for _name, predictor in self._optimized_program.named_predictors():
            if hasattr(predictor, "demos") and predictor.demos:
                for demo in predictor.demos:
                    demos.append(
                        {
                            "adf_expression": getattr(demo, "adf_expression", ""),
                            "python_code": getattr(demo, "python_code", ""),
                            "score": float(getattr(demo, "human_score", 1.0)),
                            "category": getattr(demo, "category", ""),
                        }
                    )
            if hasattr(predictor, "extended_signature") and hasattr(predictor.extended_signature, "instructions"):
                instructions = predictor.extended_signature.instructions

        self._optimization_result = OptimizationResult(
            train_agreement=train_agreement,
            dev_agreement=dev_agreement,
            improvement_over_baseline=dev_agreement - baseline_agreement,
            num_trials=self._num_trials,
            best_demos=tuple(demos),
            optimized_instructions=instructions,
        )

        return self._optimization_result

    def to_judge(self) -> LLMJudge:
        """Export the optimized program as an LLMJudge.

        Must call :meth:`optimize` first.

        Returns
        -------
        LLMJudge
            Judge configured with optimized instructions and demonstrations.
        """
        if self._optimized_program is None or self._optimization_result is None:
            raise RuntimeError("Call optimize() before to_judge(). " "No optimization has been run yet.")

        result = self._optimization_result
        criteria = result.optimized_instructions or _CALIBRATED_CRITERIA

        # Convert demos to the format LLMJudge expects
        calibration_examples = tuple(
            {
                "input": d.get("adf_expression", ""),
                "output": d.get("python_code", ""),
                "score": d.get("score", 1.0),
            }
            for d in result.best_demos
        )

        return LLMJudge(
            name="semantic_equivalence",
            criteria=criteria,
            input_template=_CALIBRATED_TEMPLATE,
            provider=self._provider,
            calibration_examples=calibration_examples,
            threshold=0.7,
            model=self._model,
        )

    def save(self, path: str | Path) -> None:
        """Save the optimized program state to disk.

        Parameters
        ----------
        path:
            File path for the saved state (JSON format).
        """
        if self._optimized_program is None:
            raise RuntimeError("Nothing to save — call optimize() first.")

        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # Save DSPy program state
        state_path = save_path.with_suffix(".dspy")
        self._optimized_program.save(str(state_path))

        # Also save metadata as JSON for easy inspection
        meta = {
            "optimizer": self._optimizer_name,
            "model": self._model,
            "num_trials": self._num_trials,
            "dspy_state_path": str(state_path),
        }
        if self._optimization_result:
            meta["train_agreement"] = self._optimization_result.train_agreement
            meta["dev_agreement"] = self._optimization_result.dev_agreement
            meta["improvement_over_baseline"] = self._optimization_result.improvement_over_baseline
            meta["optimized_instructions"] = self._optimization_result.optimized_instructions
            meta["best_demos"] = list(self._optimization_result.best_demos)

        save_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, provider: JudgeProvider) -> DSPyJudgeOptimizer:
        """Reload a saved DSPyJudgeOptimizer from disk.

        Parameters
        ----------
        path:
            Path to the saved metadata JSON file.
        provider:
            JudgeProvider for the reconstructed optimizer.

        Returns
        -------
        DSPyJudgeOptimizer
            Optimizer with restored state.
        """
        if not _HAS_DSPY:
            raise ImportError("DSPy 3.x is required to load a saved DSPyJudgeOptimizer.")

        load_path = Path(path)
        meta = json.loads(load_path.read_text(encoding="utf-8"))

        instance = cls(
            provider=provider,
            optimizer=meta.get("optimizer", "MIPROv2"),
            model=meta.get("model", "databricks-claude-sonnet-4-6"),
            num_trials=meta.get("num_trials", 20),
        )

        # Restore the DSPy program state
        dspy_state_path = meta.get("dspy_state_path", "")
        if dspy_state_path and Path(dspy_state_path).exists():
            module = MultiAspectJudge()
            module.load(dspy_state_path)
            instance._optimized_program = module

        # Restore optimization result
        if "train_agreement" in meta:
            instance._optimization_result = OptimizationResult(
                train_agreement=meta["train_agreement"],
                dev_agreement=meta["dev_agreement"],
                improvement_over_baseline=meta.get("improvement_over_baseline", 0.0),
                num_trials=meta.get("num_trials", 20),
                best_demos=tuple(meta.get("best_demos", ())),
                optimized_instructions=meta.get("optimized_instructions", ""),
            )

        return instance


# ---------------------------------------------------------------------------
# Standalone evaluation function
# ---------------------------------------------------------------------------


def evaluate_judge_quality(
    judge: LLMJudge,
    calibration_path: str | Path,
) -> dict[str, float]:
    """Evaluate an LLMJudge against human-labelled calibration pairs.

    Returns per-category agreement scores plus an overall mean agreement.
    Useful for comparing baseline vs optimized judge performance.

    Parameters
    ----------
    judge:
        The LLMJudge to evaluate.
    calibration_path:
        Path to the calibration pairs JSON file.

    Returns
    -------
    dict[str, float]
        Keys are category names + "overall". Values are mean agreement
        scores (1 - |human_score - predicted_score|).
    """
    pairs = load_calibration_pairs(calibration_path)
    if not pairs:
        return {"overall": 0.0}

    category_scores: dict[str, list[float]] = {}
    all_scores: list[float] = []

    for pair in pairs:
        result: DimensionResult = judge.evaluate(pair.adf_expression, pair.python_code)
        agreement = 1.0 - abs(pair.human_score - result.score)
        all_scores.append(agreement)

        cat = pair.category or "uncategorized"
        if cat not in category_scores:
            category_scores[cat] = []
        category_scores[cat].append(agreement)

    output: dict[str, float] = {}
    for cat, scores in sorted(category_scores.items()):
        output[cat] = sum(scores) / len(scores) if scores else 0.0

    output["overall"] = sum(all_scores) / len(all_scores) if all_scores else 0.0

    return output
