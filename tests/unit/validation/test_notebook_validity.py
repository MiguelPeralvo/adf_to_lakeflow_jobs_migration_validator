"""TDD tests for the notebook validity dimension."""

import pytest

from lakeflow_migration_validator.dimensions.notebook_validity import compute_notebook_validity
from tests.unit.validation.conftest import make_notebook, make_snapshot


def test_valid_notebook_scores_1():
    """A single syntactically valid notebook scores 1.0."""
    snapshot = make_snapshot(notebooks=[make_notebook(content="x = 1\nprint(x)")])

    score, details = compute_notebook_validity(snapshot)

    assert score == 1.0
    assert details == {"total": 1, "valid": 1, "errors": []}


def test_invalid_notebook_scores_0():
    """A single notebook with a SyntaxError scores 0.0."""
    snapshot = make_snapshot(notebooks=[make_notebook(file_path="/nb/bad.py", content="if True print('x')")])

    score, details = compute_notebook_validity(snapshot)

    assert score == 0.0
    assert details["total"] == 1
    assert details["valid"] == 0
    assert len(details["errors"]) == 1
    assert details["errors"][0]["file_path"] == "/nb/bad.py"


def test_mixed_notebooks_returns_fraction():
    """2 valid + 1 invalid = 0.667."""
    snapshot = make_snapshot(
        notebooks=[
            make_notebook(file_path="/nb/ok1.py", content="a = 1"),
            make_notebook(file_path="/nb/ok2.py", content="b = 2"),
            make_notebook(file_path="/nb/bad.py", content="for i in range(3) print(i)"),
        ]
    )

    score, _details = compute_notebook_validity(snapshot)

    assert score == pytest.approx(2 / 3)


def test_no_notebooks_scores_1():
    """A workflow with no notebooks scores 1.0."""
    snapshot = make_snapshot()

    score, details = compute_notebook_validity(snapshot)

    assert score == 1.0
    assert details == {"total": 0, "valid": 0, "errors": []}


def test_details_list_error_file_paths():
    """The details dict lists file_path and error for each invalid notebook."""
    snapshot = make_snapshot(
        notebooks=[
            make_notebook(file_path="/nb/one.py", content="if True print('x')"),
            make_notebook(file_path="/nb/two.py", content="while True print('x')"),
        ]
    )

    _score, details = compute_notebook_validity(snapshot)
    file_paths = [error["file_path"] for error in details["errors"]]

    assert file_paths == ["/nb/one.py", "/nb/two.py"]
