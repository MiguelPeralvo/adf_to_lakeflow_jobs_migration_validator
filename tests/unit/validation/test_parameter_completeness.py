"""TDD tests for the parameter completeness dimension."""

import pytest

from lakeflow_migration_validator.dimensions.parameter_completeness import compute_parameter_completeness
from tests.unit.validation.conftest import make_notebook, make_snapshot


def test_all_params_defined_scores_1():
    """Every dbutils.widgets.get reference has a matching JobParameterDefinition."""
    snapshot = make_snapshot(
        notebooks=[
            make_notebook(
                content="x = dbutils.widgets.get('foo')\ny = dbutils.widgets.get('bar')"
            )
        ],
        parameters=("foo", "bar"),
    )

    score, details = compute_parameter_completeness(snapshot)

    assert score == 1.0
    assert details["missing"] == []
    assert details["referenced"] == ["bar", "foo"]


def test_missing_param_lowers_score():
    """A notebook references param 'X' but pipeline.parameters has no 'X' -> score < 1.0."""
    snapshot = make_snapshot(
        notebooks=[make_notebook(content="dbutils.widgets.get('x')\ndbutils.widgets.get('y')")],
        parameters=("x",),
    )

    score, details = compute_parameter_completeness(snapshot)

    assert score == pytest.approx(0.5)
    assert details["missing"] == ["y"]


def test_no_widget_references_scores_1():
    """A notebook with no dbutils.widgets.get calls scores 1.0."""
    snapshot = make_snapshot(notebooks=[make_notebook(content="x = 1")], parameters=("foo",))

    score, details = compute_parameter_completeness(snapshot)

    assert score == 1.0
    assert details["referenced"] == []
    assert details["missing"] == []


def test_details_list_missing_params():
    """The details dict lists the missing parameter names."""
    snapshot = make_snapshot(
        notebooks=[make_notebook(content="dbutils.widgets.get('a')\ndbutils.widgets.get('b')")],
        parameters=("a",),
    )

    _score, details = compute_parameter_completeness(snapshot)

    assert details["missing"] == ["b"]


def test_multiple_notebooks_aggregate_references():
    """References across all notebooks are collected, not just the first."""
    snapshot = make_snapshot(
        notebooks=[
            make_notebook(file_path="/nb/one.py", content="dbutils.widgets.get('first')"),
            make_notebook(file_path="/nb/two.py", content="dbutils.widgets.get('second')"),
        ],
        parameters=("first",),
    )

    score, details = compute_parameter_completeness(snapshot)

    assert score == pytest.approx(0.5)
    assert details["referenced"] == ["first", "second"]
    assert details["missing"] == ["second"]


def test_widget_pattern_supports_hyphens_and_whitespace():
    """Widget names with non-word chars and spacing are detected."""
    snapshot = make_snapshot(
        notebooks=[make_notebook(content='dbutils.widgets.get( "my-param" )')],
        parameters=("my-param",),
    )

    score, details = compute_parameter_completeness(snapshot)

    assert score == 1.0
    assert details["referenced"] == ["my-param"]
