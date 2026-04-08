"""TDD tests for the pure-Python ADF JSON unwrap helper.

These tests intentionally do NOT import wkmigrate so they run in the
fast tier (LR-1) without requiring wkmigrate to be installed.
"""

from lakeflow_migration_validator.adapters.wkmigrate_adapter import unwrap_adf_pipeline


def test_unwrap_flattens_properties_wrapper():
    """{name, properties: {activities, parameters}} -> {name, activities, parameters}."""
    wrapped = {
        "name": "pipe",
        "properties": {
            "activities": [{"name": "a", "type": "SetVariable"}],
            "parameters": {"p1": {"type": "String"}},
        },
    }

    flat = unwrap_adf_pipeline(wrapped)

    assert flat == {
        "name": "pipe",
        "activities": [{"name": "a", "type": "SetVariable"}],
        "parameters": {"p1": {"type": "String"}},
    }


def test_unwrap_passes_through_already_flat():
    """A pipeline already in {name, activities, ...} form is returned unchanged."""
    flat = {
        "name": "pipe",
        "activities": [{"name": "a", "type": "SetVariable"}],
    }

    result = unwrap_adf_pipeline(flat)

    assert result == flat


def test_unwrap_passes_through_when_properties_missing():
    """A dict with no 'properties' key is returned unchanged."""
    payload = {"name": "pipe", "tasks": []}

    assert unwrap_adf_pipeline(payload) == payload


def test_unwrap_passes_through_when_properties_is_not_a_dict():
    """If 'properties' exists but isn't a dict, do not unwrap (defensive)."""
    payload = {"name": "pipe", "properties": "not-a-dict"}

    assert unwrap_adf_pipeline(payload) == payload


def test_unwrap_does_not_lose_top_level_keys():
    """Top-level siblings of 'properties' (like 'name', 'id') are preserved."""
    wrapped = {
        "name": "pipe",
        "id": "/subscriptions/.../pipelines/pipe",
        "type": "Microsoft.DataFactory/factories/pipelines",
        "properties": {
            "activities": [],
            "parameters": {},
        },
    }

    flat = unwrap_adf_pipeline(wrapped)

    assert flat["name"] == "pipe"
    assert flat["id"] == "/subscriptions/.../pipelines/pipe"
    assert flat["type"] == "Microsoft.DataFactory/factories/pipelines"
    assert flat["activities"] == []
    assert flat["parameters"] == {}
    assert "properties" not in flat


def test_unwrap_properties_wins_on_key_collision():
    """If a key exists at both top level and inside properties, properties wins.

    Real ADF JSON does not produce this collision, so the choice is mostly
    cosmetic. We pick 'properties wins' because that's where the canonical
    pipeline definition lives in Azure ADF's REST API shape.
    """
    wrapped = {
        "name": "pipe",
        "activities": [{"name": "stale_top_level"}],
        "properties": {
            "activities": [{"name": "canonical_inside_properties"}],
        },
    }

    flat = unwrap_adf_pipeline(wrapped)

    assert flat["activities"] == [{"name": "canonical_inside_properties"}]


def test_unwrap_returns_input_when_not_a_dict():
    """Non-dict inputs (e.g. None, list) are returned unchanged."""
    assert unwrap_adf_pipeline(None) is None
    assert unwrap_adf_pipeline([1, 2, 3]) == [1, 2, 3]
    assert unwrap_adf_pipeline("string") == "string"
