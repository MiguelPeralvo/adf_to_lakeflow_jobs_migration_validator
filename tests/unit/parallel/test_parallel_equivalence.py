"""Unit tests for parallel_equivalence dimension."""

from __future__ import annotations

from lakeflow_migration_validator.dimensions.parallel_equivalence import compute_parallel_equivalence
from tests.unit.validation.conftest import make_snapshot


def test_parallel_equivalence_no_adf_outputs_returns_vacuous_success():
    snapshot = make_snapshot(expected_outputs={"a": "1"})

    score, details = compute_parallel_equivalence(snapshot)

    assert score == 1.0
    assert details == {"status": "no_adf_outputs", "compared": 0}


def test_parallel_equivalence_no_comparable_activities_returns_vacuous_success():
    snapshot = make_snapshot(adf_run_outputs={"a": "1"})

    score, details = compute_parallel_equivalence(snapshot)

    assert score == 1.0
    assert details == {"status": "no_comparable_activities", "compared": 0}


def test_parallel_equivalence_full_match_scores_one():
    snapshot = make_snapshot(
        expected_outputs={"a": "1.0", "b": "2024-01-01T00:00:00+00:00"},
        adf_run_outputs={"a": "1.0000004", "b": "2024-01-01T00:00:00Z"},
    )

    score, details = compute_parallel_equivalence(snapshot)

    assert score == 1.0
    assert details["compared"] == 2
    assert details["matched"] == 2
    assert details["mismatches"] == []


def test_parallel_equivalence_partial_mismatch_reports_details():
    snapshot = make_snapshot(
        expected_outputs={"a": "1", "b": "2"},
        adf_run_outputs={"a": "1", "b": "3"},
    )

    score, details = compute_parallel_equivalence(snapshot)

    assert score == 0.5
    assert details["compared"] == 2
    assert details["matched"] == 1
    assert details["mismatches"] == [{"activity": "b", "adf": "3", "expected": "2"}]


def test_parallel_equivalence_missing_adf_activity_reports_details():
    snapshot = make_snapshot(
        expected_outputs={"a": "1", "b": "2"},
        adf_run_outputs={"a": "1"},
    )

    score, details = compute_parallel_equivalence(snapshot)

    assert score == 0.5
    assert details["compared"] == 2
    assert details["matched"] == 1
    assert details["mismatches"] == [{"activity": "b", "adf": None, "expected": "2"}]
