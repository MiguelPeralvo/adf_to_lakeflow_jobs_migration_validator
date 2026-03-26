"""Unit tests for ConversionSnapshot serialization helpers."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.serialization import (
    snapshot_from_adf_payload,
    snapshot_from_dict,
    snapshot_to_dict,
)
from tests.unit.validation.conftest import (
    make_dep,
    make_expression,
    make_notebook,
    make_secret,
    make_snapshot,
    make_task,
)


def test_snapshot_round_trip_empty():
    """An empty snapshot round-trips through dict serialization without loss."""
    snapshot = make_snapshot()

    restored = snapshot_from_dict(snapshot_to_dict(snapshot))

    assert restored == snapshot


def test_snapshot_round_trip_full():
    """A fully populated snapshot round-trips through dict serialization."""
    snapshot = ConversionSnapshot(
        tasks=(make_task("task_a"), make_task("task_b", is_placeholder=True)),
        notebooks=(make_notebook("/n/one.py", "x = 1"), make_notebook("/n/two.py", "y = 2")),
        secrets=(make_secret("scope_a", "key_a"),),
        parameters=("param_a", "param_b"),
        dependencies=(make_dep("task_a", "task_b"),),
        not_translatable=({"activity": "unknown"},),
        resolved_expressions=(make_expression("@add(1,2)", "(1 + 2)"),),
        source_pipeline={"name": "pipe_full", "activities": [{"name": "task_a"}]},
        total_source_dependencies=1,
        expected_outputs={"task_a": "ok"},
        adf_run_outputs={"task_a": "ok"},
    )

    restored = snapshot_from_dict(snapshot_to_dict(snapshot))

    assert restored == snapshot


def test_snapshot_from_adf_payload_with_expected_snapshot():
    """ADF payload containing expected_snapshot must deserialize that nested snapshot."""
    expected = make_snapshot(tasks=[make_task("task_a")], notebooks=[make_notebook()])
    payload = {
        "name": "pipe_a",
        "expected_snapshot": snapshot_to_dict(expected),
    }

    restored = snapshot_from_adf_payload(payload)

    assert restored == expected


def test_snapshot_from_adf_payload_unknown_shape_wraps_as_source_pipeline():
    """Unknown ADF payload shape should be preserved in source_pipeline."""
    payload = {
        "name": "pipe_unknown",
        "properties": {"activities": [{"name": "a"}]},
    }

    snapshot = snapshot_from_adf_payload(payload)

    assert snapshot.tasks == ()
    assert snapshot.notebooks == ()
    assert snapshot.secrets == ()
    assert snapshot.parameters == ()
    assert snapshot.dependencies == ()
    assert snapshot.source_pipeline == payload
