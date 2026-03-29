"""TDD tests for the control flow fidelity dimension."""

import pytest

from lakeflow_migration_validator.dimensions.control_flow_fidelity import compute_control_flow_fidelity
from tests.unit.validation.conftest import make_snapshot, make_task


def _pipeline_with_activities(*activities):
    """Build a source_pipeline dict with the given activities list."""
    return {"properties": {"activities": list(activities)}}


def _activity(name, act_type, **kwargs):
    """Build an activity dict."""
    return {"name": name, "type": act_type, **kwargs}


def test_no_activities_returns_1():
    """A pipeline with no activities scores 1.0 (vacuously true)."""
    snapshot = make_snapshot(source_pipeline={"properties": {"activities": []}})

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 1.0
    assert details == {"total": 0, "preserved": 0, "missing": []}


def test_no_control_flow_activities_returns_1():
    """A pipeline with only non-control-flow activities scores 1.0."""
    pipeline = _pipeline_with_activities(
        _activity("CopyData1", "Copy"),
        _activity("Lookup1", "Lookup"),
    )
    snapshot = make_snapshot(source_pipeline=pipeline)

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 1.0
    assert details == {"total": 0, "preserved": 0, "missing": []}


def test_all_control_flow_preserved_returns_1():
    """ForEach + IfCondition both present in tasks scores 1.0."""
    pipeline = _pipeline_with_activities(
        _activity("Loop1", "ForEach"),
        _activity("Branch1", "IfCondition"),
    )
    snapshot = make_snapshot(
        source_pipeline=pipeline,
        tasks=[make_task("Loop1"), make_task("Branch1")],
    )

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 1.0
    assert details == {"total": 2, "preserved": 2, "missing": []}


def test_missing_control_flow_returns_0():
    """ForEach in source but no matching task scores 0.0."""
    pipeline = _pipeline_with_activities(_activity("Loop1", "ForEach"))
    snapshot = make_snapshot(source_pipeline=pipeline, tasks=[])

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 0.0
    assert details == {"total": 1, "preserved": 0, "missing": ["Loop1"]}


def test_partial_preservation():
    """One of two control-flow activities missing gives 0.5."""
    pipeline = _pipeline_with_activities(
        _activity("Loop1", "ForEach"),
        _activity("Branch1", "IfCondition"),
    )
    snapshot = make_snapshot(
        source_pipeline=pipeline,
        tasks=[make_task("Loop1")],
    )

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == pytest.approx(0.5)
    assert details["missing"] == ["Branch1"]


def test_nested_control_flow_both_counted():
    """A ForEach containing an IfCondition counts both."""
    pipeline = _pipeline_with_activities(
        _activity(
            "OuterLoop",
            "ForEach",
            activities=[
                _activity("InnerBranch", "IfCondition"),
            ],
        )
    )
    snapshot = make_snapshot(
        source_pipeline=pipeline,
        tasks=[make_task("OuterLoop"), make_task("InnerBranch")],
    )

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 1.0
    assert details == {"total": 2, "preserved": 2, "missing": []}


def test_nested_control_flow_inner_missing():
    """Nested IfCondition missing while outer ForEach is present gives 0.5."""
    pipeline = _pipeline_with_activities(
        _activity(
            "OuterLoop",
            "ForEach",
            activities=[
                _activity("InnerBranch", "IfCondition"),
            ],
        )
    )
    snapshot = make_snapshot(
        source_pipeline=pipeline,
        tasks=[make_task("OuterLoop")],
    )

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == pytest.approx(0.5)
    assert details["missing"] == ["InnerBranch"]


def test_placeholder_task_not_counted_as_preserved():
    """A placeholder task for a control-flow activity does not count as preserved."""
    pipeline = _pipeline_with_activities(_activity("Loop1", "ForEach"))
    snapshot = make_snapshot(
        source_pipeline=pipeline,
        tasks=[make_task("Loop1", is_placeholder=True)],
    )

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 0.0
    assert details["missing"] == ["Loop1"]


def test_if_condition_branches_searched():
    """Control flow inside if_true_activities and if_false_activities is found."""
    pipeline = _pipeline_with_activities(
        _activity(
            "TopBranch",
            "IfCondition",
            if_true_activities=[
                _activity("TrueLoop", "ForEach"),
            ],
            if_false_activities=[
                _activity("FalseLoop", "ForEach"),
            ],
        )
    )
    snapshot = make_snapshot(
        source_pipeline=pipeline,
        tasks=[
            make_task("TopBranch"),
            make_task("TrueLoop"),
            make_task("FalseLoop"),
        ],
    )

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 1.0
    assert details == {"total": 3, "preserved": 3, "missing": []}


def test_empty_source_pipeline_returns_1():
    """An empty source_pipeline dict scores 1.0."""
    snapshot = make_snapshot(source_pipeline={})

    score, details = compute_control_flow_fidelity(snapshot)

    assert score == 1.0
    assert details == {"total": 0, "preserved": 0, "missing": []}
