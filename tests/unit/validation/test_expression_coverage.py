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
    assert details["total"] == 2
    assert details["resolved"] == 2
    assert details["unsupported"] == []
    assert details["measurable"] is True


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
    assert details["measurable"] is True


def test_non_expression_unsupported_entries_are_ignored():
    """Only not_translatable messages about expressions are counted."""
    snapshot = make_snapshot(
        resolved_expressions=[make_expression()],
        not_translatable=[
            {"message": "Unsupported activity type: WebActivity"},
            {"message": "Unsupported expression in activity"},
        ],
    )

    score, details = compute_expression_coverage(snapshot)

    assert score == pytest.approx(0.5)
    assert details["unsupported"] == [{"message": "Unsupported expression in activity"}]
    assert details["measurable"] is True


def test_no_expressions_in_source_scores_1_and_is_measurable():
    """A pipeline with no expression properties at all scores 1.0 (vacuous truth)."""
    snapshot = make_snapshot(source_pipeline={"activities": [{"name": "literal", "type": "DatabricksNotebook"}]})

    score, details = compute_expression_coverage(snapshot)

    assert score == 1.0
    assert details["total"] == 0
    assert details["resolved"] == 0
    assert details["unsupported"] == []
    assert details["measurable"] is True
    assert details.get("reason") == "no_expressions_in_source"


def test_source_has_expressions_but_extracted_none_is_unmeasurable():
    """Silent-empty case: source contains @-expressions but adapter extracted nothing.

    This is the L-F1/L-F12 cascade — wkmigrate produced an empty IR (or
    silently mapped activities to placeholders) and the adapter has nothing
    to count. Reporting 1.0 here is misleading; report 0.0 with
    measurable=False so downstream can flag it.
    """
    snapshot = make_snapshot(
        resolved_expressions=[],
        not_translatable=[],
        source_pipeline={
            "activities": [
                {
                    "name": "set_var",
                    "type": "SetVariable",
                    "value": {"type": "Expression", "value": "@concat('a', 'b')"},
                }
            ]
        },
    )

    score, details = compute_expression_coverage(snapshot)

    assert score == 0.0
    assert details["total"] == 0
    assert details["measurable"] is False
    assert "reason" in details
    assert "source" in details["reason"].lower()


def test_source_with_wrapped_properties_shape_is_also_inspected():
    """Expression detection walks into the {properties: {activities: [...]}} shape too."""
    snapshot = make_snapshot(
        resolved_expressions=[],
        not_translatable=[],
        source_pipeline={
            "name": "pipe",
            "properties": {
                "activities": [
                    {
                        "name": "if_cond",
                        "type": "IfCondition",
                        "expression": {"type": "Expression", "value": "@equals(1, 1)"},
                    }
                ]
            },
        },
    )

    score, details = compute_expression_coverage(snapshot)

    assert score == 0.0
    assert details["measurable"] is False
