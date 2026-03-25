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

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions import DimensionResult
from lakeflow_migration_validator.dimensions.activity_coverage import compute_activity_coverage
from lakeflow_migration_validator.dimensions.dependency_preservation import compute_dependency_preservation
from lakeflow_migration_validator.dimensions.expression_coverage import compute_expression_coverage
from lakeflow_migration_validator.dimensions.not_translatable_ratio import compute_not_translatable_ratio
from lakeflow_migration_validator.dimensions.notebook_validity import compute_notebook_validity
from lakeflow_migration_validator.dimensions.parameter_completeness import compute_parameter_completeness
from lakeflow_migration_validator.dimensions.programmatic import ProgrammaticCheck
from lakeflow_migration_validator.dimensions.secret_completeness import compute_secret_completeness
from lakeflow_migration_validator.scorecard import Scorecard

__all__ = ["evaluate", "evaluate_from_wkmigrate", "ConversionSnapshot", "Scorecard", "DimensionResult"]

_DEFAULT_WEIGHTS = {
    "activity_coverage": 0.25,
    "expression_coverage": 0.20,
    "dependency_preservation": 0.15,
    "notebook_validity": 0.15,
    "parameter_completeness": 0.10,
    "secret_completeness": 0.10,
    "not_translatable_ratio": 0.05,
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

_DIMENSION_NAMES = {dimension.name for dimension in _DIMENSIONS}
if _DIMENSION_NAMES != set(_DEFAULT_WEIGHTS):
    raise ValueError(
        "Dimension/weight configuration mismatch: "
        f"dimensions={sorted(_DIMENSION_NAMES)} "
        f"weights={sorted(_DEFAULT_WEIGHTS)}"
    )


def evaluate(snapshot: ConversionSnapshot) -> Scorecard:
    """Evaluate a conversion snapshot and return a Scorecard with the CCS.

    This is the generic entry point — takes a ConversionSnapshot built by any
    adapter (wkmigrate, or a future tool). No wkmigrate imports.
    """
    results: dict[str, DimensionResult] = {}
    for dimension in _DIMENSIONS:
        results[dimension.name] = dimension.evaluate(None, snapshot)
    return Scorecard.compute(_DEFAULT_WEIGHTS, results)


def evaluate_from_wkmigrate(source_pipeline: dict, prepared_workflow) -> Scorecard:
    """Convenience entry point for wkmigrate users.

    Imports the wkmigrate adapter, converts to ConversionSnapshot, then calls
    evaluate(). Requires the 'wkmigrate' extra to be installed.
    """
    from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate

    snapshot = from_wkmigrate(source_pipeline, prepared_workflow)
    return evaluate(snapshot)
