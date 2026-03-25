"""Lakeflow Migration Validator (lmv).

Evaluates the fidelity, correctness, and completeness of ADF-to-Databricks
Lakeflow Jobs conversions produced by wkmigrate.

Public API::

    from lakeflow_migration_validator import evaluate_pipeline

    scorecard = evaluate_pipeline(source_pipeline, prepared_workflow)
    print(scorecard.score, scorecard.label)
"""

from lakeflow_migration_validator.scorecard import Scorecard
from lakeflow_migration_validator.dimensions import DimensionResult

__all__ = ["evaluate_pipeline", "Scorecard", "DimensionResult"]


def evaluate_pipeline(source_pipeline: dict, prepared_workflow) -> Scorecard:
    """Evaluate a conversion and return a Scorecard with the Conversion Confidence Score."""
    raise NotImplementedError("Phase 1 Week 1 — implement after TDD tests are written")
