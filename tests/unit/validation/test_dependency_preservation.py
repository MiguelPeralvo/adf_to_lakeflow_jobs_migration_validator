"""TDD tests for the dependency preservation dimension."""

import pytest

from lakeflow_migration_validator.dimensions.dependency_preservation import compute_dependency_preservation
from tests.unit.validation.conftest import make_dep, make_snapshot


def test_all_deps_preserved_scores_1():
    """Every ADF depends_on entry has a corresponding IR Dependency."""
    snapshot = make_snapshot(
        dependencies=[make_dep("a", "b"), make_dep("b", "c")],
        total_source_dependencies=2,
    )

    score, details = compute_dependency_preservation(snapshot)

    assert score == 1.0
    assert details == {"total": 2, "preserved": 2}


def test_missing_dep_lowers_score():
    """An ADF depends_on entry with no matching IR task_key -> score < 1.0."""
    snapshot = make_snapshot(
        dependencies=[make_dep("a", "b")],
        total_source_dependencies=2,
    )

    score, details = compute_dependency_preservation(snapshot)

    assert score == pytest.approx(0.5)
    assert details == {"total": 2, "preserved": 1}


def test_no_deps_scores_1():
    """A pipeline with no depends_on entries scores 1.0."""
    snapshot = make_snapshot(dependencies=[], total_source_dependencies=0)

    score, details = compute_dependency_preservation(snapshot)

    assert score == 1.0
    assert details == {"total": 0, "preserved": 0}


def test_details_list_missing_deps():
    """The details dict lists which activities lost which dependencies."""
    snapshot = make_snapshot(
        dependencies=[make_dep("upstream", "downstream")],
        total_source_dependencies=3,
    )

    _score, details = compute_dependency_preservation(snapshot)

    assert details["total"] == 3
    assert details["preserved"] == 1
