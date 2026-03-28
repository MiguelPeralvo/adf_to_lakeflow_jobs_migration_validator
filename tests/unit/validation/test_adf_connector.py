"""Tests for ADFConnector — both callable injection and from_credentials."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.harness.adf_connector import ADFConnector


def test_callable_injection_list_pipelines():
    """Injected list_pipelines_fn is called correctly."""
    connector = ADFConnector(list_pipelines_fn=lambda: ["pipe_a", "pipe_b"])
    assert connector.list_pipelines() == ["pipe_a", "pipe_b"]


def test_callable_injection_fetch_pipeline():
    """Injected fetch_pipeline_fn receives the pipeline name."""
    connector = ADFConnector(fetch_pipeline_fn=lambda name: {"name": name})
    assert connector.fetch_pipeline("test")["name"] == "test"


def test_callable_injection_translate_and_prepare():
    """Injected translate_prepare_fn receives the pipeline JSON."""
    connector = ADFConnector(
        translate_prepare_fn=lambda json: (json, {"prepared": True})
    )
    source, prepared = connector.translate_and_prepare({"name": "test"})
    assert source["name"] == "test"
    assert prepared["prepared"] is True


def test_unconfigured_list_raises():
    """list_pipelines raises when not configured."""
    connector = ADFConnector()
    with pytest.raises(NotImplementedError, match="list_pipelines"):
        connector.list_pipelines()


def test_unconfigured_fetch_raises():
    """fetch_pipeline raises when not configured."""
    connector = ADFConnector()
    with pytest.raises(NotImplementedError, match="fetch_pipeline"):
        connector.fetch_pipeline("x")


def test_unconfigured_translate_raises():
    """translate_and_prepare raises when not configured."""
    connector = ADFConnector()
    with pytest.raises(NotImplementedError, match="translate_and_prepare"):
        connector.translate_and_prepare({})


def test_from_credentials_raises_without_wkmigrate(monkeypatch):
    """from_credentials raises ImportError when wkmigrate is not installed."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "wkmigrate" in name:
            raise ImportError("no wkmigrate")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    with pytest.raises(ImportError, match="wkmigrate"):
        ADFConnector.from_credentials(
            tenant_id="t", client_id="c", client_secret="s",
            subscription_id="sub", resource_group="rg", factory_name="f",
        )
