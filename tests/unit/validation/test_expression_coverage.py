"""TDD tests for the expression coverage dimension."""

import pytest

from lakeflow_migration_validator.dimensions.expression_coverage import compute_expression_coverage
from tests.unit.validation.conftest import make_expression, make_snapshot


def test_all_expressions_resolved_scores_1():
    """A pipeline with only SetVariableActivity tasks (all resolved) scores 1.0."""
    snapshot = make_snapshot(
        resolved_expressions=[
            make_expression(adf="@a", python="a"),
            make_expression(adf="@b", python="b"),
        ],
        not_translatable=[],
    )

    score, details = compute_expression_coverage(snapshot)

    assert score == 1.0
    assert details == {"total": 2, "resolved": 2, "unsupported": []}


def test_unsupported_expressions_lower_score():
    """not_translatable entries mentioning 'expression' reduce the score."""
    snapshot = make_snapshot(
        resolved_expressions=[make_expression()],
        not_translatable=[
            {"message": "Unsupported expression in activity"},
            {"message": "another issue"},
        ],
    )

    score, details = compute_expression_coverage(snapshot)

    assert score == pytest.approx(0.5)
    assert details["total"] == 2
    assert details["resolved"] == 1
    assert len(details["unsupported"]) == 1


def test_no_expressions_scores_1():
    """A pipeline with no expression properties scores 1.0."""
    snapshot = make_snapshot()

    score, details = compute_expression_coverage(snapshot)

    assert score == 1.0
    assert details == {"total": 0, "resolved": 0, "unsupported": []}
