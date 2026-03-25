"""TDD tests for the activity coverage dimension."""

import pytest

from lakeflow_migration_validator.dimensions.activity_coverage import compute_activity_coverage
from tests.unit.validation.conftest import make_snapshot, make_task


def test_all_activities_translated_returns_1():
    """A workflow with no placeholder activities scores 1.0."""
    snapshot = make_snapshot(tasks=[make_task("a"), make_task("b")])

    score, details = compute_activity_coverage(snapshot)

    assert score == 1.0
    assert details == {"total": 2, "covered": 2, "placeholders": []}


def test_all_activities_placeholder_returns_0():
    """A workflow where every task points to /UNSUPPORTED_ADF_ACTIVITY scores 0.0."""
    snapshot = make_snapshot(tasks=[make_task("a", True), make_task("b", True)])

    score, details = compute_activity_coverage(snapshot)

    assert score == 0.0
    assert details == {"total": 2, "covered": 0, "placeholders": ["a", "b"]}


def test_mixed_activities_returns_fraction():
    """3 real + 1 placeholder = 0.75."""
    snapshot = make_snapshot(
        tasks=[
            make_task("a"),
            make_task("b"),
            make_task("c"),
            make_task("missing", True),
        ]
    )

    score, _details = compute_activity_coverage(snapshot)

    assert score == pytest.approx(0.75)


def test_empty_workflow_returns_1():
    """A workflow with no activities scores 1.0 (vacuously true)."""
    snapshot = make_snapshot()

    score, details = compute_activity_coverage(snapshot)

    assert score == 1.0
    assert details == {"total": 0, "covered": 0, "placeholders": []}


def test_details_list_placeholder_task_keys():
    """The details dict lists the task_keys of placeholder activities."""
    snapshot = make_snapshot(tasks=[make_task("ok"), make_task("p1", True), make_task("p2", True)])

    _score, details = compute_activity_coverage(snapshot)

    assert details["placeholders"] == ["p1", "p2"]
