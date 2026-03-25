"""TDD tests for the not-translatable ratio dimension."""

import pytest

from lakeflow_migration_validator.dimensions.not_translatable_ratio import compute_not_translatable_ratio
from tests.unit.validation.conftest import make_snapshot, make_task


def test_no_warnings_scores_1():
    """An empty not_translatable list scores 1.0."""
    snapshot = make_snapshot(tasks=[make_task("a")], not_translatable=[])

    score, details = compute_not_translatable_ratio(snapshot)

    assert score == 1.0
    assert details["not_translatable_count"] == 0


def test_many_warnings_lowers_score():
    """A pipeline with many not_translatable entries scores below 1.0."""
    snapshot = make_snapshot(
        tasks=[make_task("a")],
        not_translatable=[{"message": "x"} for _ in range(4)],
    )

    score, details = compute_not_translatable_ratio(snapshot)

    assert score == pytest.approx(0.2)
    assert details["estimated_total_properties"] == 5


def test_details_include_entries():
    """The details dict includes the not_translatable list."""
    entries = [{"message": "A"}, {"message": "B"}]
    snapshot = make_snapshot(tasks=[make_task("a")], not_translatable=entries)

    _score, details = compute_not_translatable_ratio(snapshot)

    assert details["entries"] == entries
