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
from lakeflow_migration_validator.scorecard import Scorecard

__all__ = ["evaluate", "evaluate_from_wkmigrate", "ConversionSnapshot", "Scorecard", "DimensionResult"]


def evaluate(snapshot: ConversionSnapshot) -> Scorecard:
    """Evaluate a conversion snapshot and return a Scorecard with the CCS.

    This is the generic entry point — takes a ConversionSnapshot built by any
    adapter (wkmigrate, or a future tool). No wkmigrate imports.
    """
    raise NotImplementedError("Week 1 Day 5 — implement after dimensions are done")


def evaluate_from_wkmigrate(source_pipeline: dict, prepared_workflow) -> Scorecard:
    """Convenience entry point for wkmigrate users.

    Imports the wkmigrate adapter, converts to ConversionSnapshot, then calls
    evaluate(). Requires the 'wkmigrate' extra to be installed.
    """
    from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate

    snapshot = from_wkmigrate(source_pipeline, prepared_workflow)
    return evaluate(snapshot)
