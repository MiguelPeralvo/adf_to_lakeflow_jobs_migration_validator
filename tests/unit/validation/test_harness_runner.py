"""Unit tests for harness orchestration runner."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.harness.harness_runner import (
    HarnessRunner,
    HarnessRunnerError,
)
from lakeflow_migration_validator.scorecard import Scorecard
from tests.unit.validation.conftest import make_snapshot, make_task


class _Connector:
    def __init__(self):
        self.pipelines = {
            "pipe_a": {"name": "pipe_a"},
            "pipe_b": {"name": "pipe_b"},
        }

    def list_pipelines(self) -> list[str]:
        return sorted(self.pipelines)

    def fetch_pipeline(self, name: str) -> dict:
        if name not in self.pipelines:
            raise KeyError(name)
        return self.pipelines[name]

    def translate_and_prepare(self, pipeline_json: dict) -> tuple[dict, object]:
        return pipeline_json, {"prepared": pipeline_json["name"]}


def test_harness_run_fetches_translates_adapts_and_scores():
    connector = _Connector()
    snapshot = make_snapshot(tasks=[make_task("a")])

    def adapter(source_pipeline: dict, prepared_workflow: object):
        assert source_pipeline["name"] == "pipe_a"
        assert prepared_workflow == {"prepared": "pipe_a"}
        return snapshot

    runner = HarnessRunner(adf_connector=connector, wkmigrate_adapter=adapter)

    result = runner.run("pipe_a")

    assert result.pipeline_name == "pipe_a"
    assert result.snapshot == snapshot
    assert isinstance(result.scorecard, Scorecard)
    assert result.iterations == 1


def test_harness_run_all_uses_connector_listing_by_default():
    connector = _Connector()

    def adapter(source_pipeline: dict, _prepared_workflow: object):
        return make_snapshot(tasks=[make_task(source_pipeline["name"])])

    runner = HarnessRunner(adf_connector=connector, wkmigrate_adapter=adapter)

    results = runner.run_all()

    assert [item.pipeline_name for item in results] == ["pipe_a", "pipe_b"]


def test_harness_run_all_uses_explicit_pipeline_names():
    connector = _Connector()

    def adapter(source_pipeline: dict, _prepared_workflow: object):
        return make_snapshot(tasks=[make_task(source_pipeline["name"])])

    runner = HarnessRunner(adf_connector=connector, wkmigrate_adapter=adapter)

    results = runner.run_all(["pipe_b"])

    assert [item.pipeline_name for item in results] == ["pipe_b"]


def test_harness_run_reports_pipeline_not_found_deterministically():
    runner = HarnessRunner(adf_connector=_Connector(), wkmigrate_adapter=lambda *_: make_snapshot())

    with pytest.raises(HarnessRunnerError, match="PIPELINE_NOT_FOUND"):
        runner.run("missing")


def test_harness_run_reports_translation_failure_deterministically():
    class _BrokenConnector(_Connector):
        def translate_and_prepare(self, pipeline_json: dict) -> tuple[dict, object]:
            raise RuntimeError(f"cannot translate {pipeline_json['name']}")

    runner = HarnessRunner(adf_connector=_BrokenConnector(), wkmigrate_adapter=lambda *_: make_snapshot())

    with pytest.raises(HarnessRunnerError, match="TRANSLATION_FAILED"):
        runner.run("pipe_a")


def test_harness_run_reports_adapter_failure_deterministically():
    def broken_adapter(_source_pipeline: dict, _prepared_workflow: object):
        raise TypeError("adapter mismatch")

    runner = HarnessRunner(adf_connector=_Connector(), wkmigrate_adapter=broken_adapter)

    with pytest.raises(HarnessRunnerError, match="ADAPTER_FAILED"):
        runner.run("pipe_a")
