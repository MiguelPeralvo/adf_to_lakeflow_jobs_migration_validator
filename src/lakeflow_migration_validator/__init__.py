"""Lakeflow Migration Validator (lmv).

Evaluates the fidelity, correctness, and completeness of ADF-to-Databricks
Lakeflow Jobs conversions.

Two entry points:

* ``evaluate(snapshot)`` — generic, operates on ``ConversionSnapshot``.
  No wkmigrate dependency.
* ``evaluate_from_wkmigrate(source, prepared)`` — convenience wrapper that
  imports the wkmigrate adapter. Requires ``pip install lmv[wkmigrate]``.

Example::

    from lakeflow_migration_validator import evaluate
    from lakeflow_migration_validator.contract import ConversionSnapshot

    snapshot = ...  # built by an adapter or by hand
    scorecard = evaluate(snapshot)
    print(scorecard.score, scorecard.label)
"""

from typing import Any, Callable

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions import DimensionResult
from lakeflow_migration_validator.dimensions.activity_coverage import compute_activity_coverage
from lakeflow_migration_validator.dimensions.dependency_preservation import compute_dependency_preservation
from lakeflow_migration_validator.dimensions.execution import ExecutionRunner
from lakeflow_migration_validator.dimensions.expression_coverage import compute_expression_coverage
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.dimensions.not_translatable_ratio import compute_not_translatable_ratio
from lakeflow_migration_validator.dimensions.notebook_validity import compute_notebook_validity
from lakeflow_migration_validator.dimensions.parameter_completeness import compute_parameter_completeness
from lakeflow_migration_validator.dimensions.programmatic import ProgrammaticCheck
from lakeflow_migration_validator.dimensions.runtime_success import create_runtime_success_dimension
from lakeflow_migration_validator.dimensions.semantic_equivalence import create_semantic_equivalence_judge
from lakeflow_migration_validator.dimensions.secret_completeness import compute_secret_completeness
from lakeflow_migration_validator.scorecard import Scorecard

__all__ = [
    "evaluate",
    "evaluate_full",
    "evaluate_batch",
    "evaluate_from_wkmigrate",
    "ConversionSnapshot",
    "Scorecard",
    "DimensionResult",
]

_DEFAULT_WEIGHTS = {
    "activity_coverage": 0.25,
    "expression_coverage": 0.20,
    "dependency_preservation": 0.15,
    "notebook_validity": 0.15,
    "parameter_completeness": 0.10,
    "secret_completeness": 0.10,
    "not_translatable_ratio": 0.05,
    "semantic_equivalence": 0.0,
    "runtime_success": 0.0,
    "parallel_equivalence": 0.0,
}

_DIMENSIONS = [
    ProgrammaticCheck("activity_coverage", lambda _i, s: compute_activity_coverage(s), threshold=0.8),
    ProgrammaticCheck("expression_coverage", lambda _i, s: compute_expression_coverage(s), threshold=0.75),
    ProgrammaticCheck("dependency_preservation", lambda _i, s: compute_dependency_preservation(s), threshold=0.8),
    ProgrammaticCheck("notebook_validity", lambda _i, s: compute_notebook_validity(s), threshold=1.0),
    ProgrammaticCheck("parameter_completeness", lambda _i, s: compute_parameter_completeness(s), threshold=0.9),
    ProgrammaticCheck("secret_completeness", lambda _i, s: compute_secret_completeness(s), threshold=0.9),
    ProgrammaticCheck("not_translatable_ratio", lambda _i, s: compute_not_translatable_ratio(s), threshold=0.8),
]

_PROGRAMMATIC_DIMENSION_NAMES = {dimension.name for dimension in _DIMENSIONS}
if not _PROGRAMMATIC_DIMENSION_NAMES.issubset(set(_DEFAULT_WEIGHTS)):
    raise ValueError(
        "Dimension/weight configuration mismatch: "
        f"dimensions={sorted(_PROGRAMMATIC_DIMENSION_NAMES)} "
        f"weights={sorted(_DEFAULT_WEIGHTS)}"
    )


def evaluate(snapshot: ConversionSnapshot) -> Scorecard:
    """Evaluate a conversion snapshot and return a Scorecard with the CCS.

    This is the generic entry point — takes a ConversionSnapshot built by any
    adapter (wkmigrate, or a future tool). No wkmigrate imports.
    """
    results = _evaluate_programmatic_dimensions(snapshot)
    return Scorecard.compute(_DEFAULT_WEIGHTS, results)


def evaluate_full(
    snapshot: ConversionSnapshot,
    *,
    judge_provider: JudgeProvider | None = None,
    execution_runner: ExecutionRunner | None = None,
    weights: dict[str, float] | None = None,
    calibration_path: str | None = None,
    calibration_sample_size: int = 20,
) -> Scorecard:
    """Evaluate snapshot with optional agentic dimensions.

    Programmatic dimensions are always executed. Agentic dimensions are added only
    when the relevant provider/runner is supplied.

    Args:
        snapshot: The conversion snapshot to evaluate.
        judge_provider: Optional LLM provider for semantic equivalence judging.
        execution_runner: Optional runner for runtime success validation.
        weights: Optional custom weights dict. If not provided, uses default weights.
            To give agentic dimensions non-zero weight, supply a dict with
            'semantic_equivalence' and/or 'runtime_success' keys set > 0.
        calibration_path: Path to calibration examples JSON for semantic equivalence.
            If None, calibration is skipped.
        calibration_sample_size: Number of calibration examples to load (default 20).
    """
    results = _evaluate_programmatic_dimensions(snapshot)

    if judge_provider is not None:
        semantic_judge = create_semantic_equivalence_judge(
            judge_provider,
            calibration_path=calibration_path if calibration_path is not None else "",
            calibration_sample_size=calibration_sample_size if calibration_path is not None else 0,
        )
        results["semantic_equivalence"] = _evaluate_semantic_equivalence(snapshot, semantic_judge)

    if execution_runner is not None:
        runtime_dimension = create_runtime_success_dimension(execution_runner)
        results["runtime_success"] = runtime_dimension.evaluate(None, snapshot)

    if snapshot.adf_run_outputs:
        from lakeflow_migration_validator.dimensions.parallel_equivalence import (
            compute_parallel_equivalence,
        )

        parallel_score, parallel_details = compute_parallel_equivalence(snapshot)
        results["parallel_equivalence"] = DimensionResult(
            name="parallel_equivalence",
            score=parallel_score,
            passed=parallel_score >= 0.95,
            details=parallel_details,
        )

    effective_weights = {**_DEFAULT_WEIGHTS, **(weights or {})}
    return Scorecard.compute(effective_weights, results)


def evaluate_from_wkmigrate(source_pipeline: dict, prepared_workflow) -> Scorecard:
    """Convenience entry point for wkmigrate users.

    Imports the wkmigrate adapter, converts to ConversionSnapshot, then calls
    evaluate(). Requires the 'wkmigrate' extra to be installed.
    """
    from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate

    snapshot = from_wkmigrate(source_pipeline, prepared_workflow)
    return evaluate(snapshot)


def evaluate_batch(
    golden_set: Any,
    convert_fn: Callable[[dict], ConversionSnapshot],
    *,
    threshold: float = 90.0,
):
    """Evaluate a converter against a GroundTruthSuite/GoldenSet and return a Report."""
    from lakeflow_migration_validator.golden_set import GoldenSet
    from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite

    if isinstance(golden_set, GroundTruthSuite):
        suite = golden_set
    elif isinstance(golden_set, GoldenSet):
        suite = golden_set.pipelines
    else:
        raise TypeError("golden_set must be GroundTruthSuite or GoldenSet")
    return suite.evaluate_converter(convert_fn, threshold=threshold)


def _evaluate_programmatic_dimensions(snapshot: ConversionSnapshot) -> dict[str, DimensionResult]:
    results: dict[str, DimensionResult] = {}
    for dimension in _DIMENSIONS:
        results[dimension.name] = dimension.evaluate(None, snapshot)
    return results


def _evaluate_semantic_equivalence(snapshot: ConversionSnapshot, judge) -> DimensionResult:
    pairs = snapshot.resolved_expressions
    if not pairs:
        return DimensionResult(
            name="semantic_equivalence",
            score=1.0,
            passed=True,
            details={"evaluated": 0, "reasoning": []},
        )

    per_pair = [judge.evaluate(pair.adf_expression, pair.python_code) for pair in pairs]
    mean_score = sum(result.score for result in per_pair) / len(per_pair)
    return DimensionResult(
        name="semantic_equivalence",
        score=mean_score,
        passed=mean_score >= judge.threshold,
        details={
            "evaluated": len(per_pair),
            "reasoning": [result.details.get("reasoning", "") for result in per_pair],
            "model": judge.model,
        },
    )
