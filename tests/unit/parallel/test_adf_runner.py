"""Unit tests for ADFExecutionRunner."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.parallel.adf_runner import ADFExecutionRunner


def test_adf_runner_success_with_polling_and_output_normalization():
    calls: list[tuple[str, object]] = []
    status_values = iter(["InProgress", "SUCCEEDED"])

    def trigger(pipeline_name: str, params: dict[str, str]) -> str:
        calls.append(("trigger", (pipeline_name, dict(params))))
        return "run-1"

    def get_status(run_id: str) -> str:
        calls.append(("status", run_id))
        return next(status_values)

    def get_outputs(run_id: str) -> dict:
        calls.append(("outputs", run_id))
        return {"activity_b": {"x": 1}, "activity_a": 2}

    sleep_calls: list[float] = []
    runner = ADFExecutionRunner(
        trigger_run_fn=trigger,
        get_run_status_fn=get_status,
        get_activity_outputs_fn=get_outputs,
        max_polls=5,
        poll_interval_seconds=0.01,
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    outputs = runner.run("pipe_a", parameters={"p": "1"})

    assert outputs == {
        "activity_a": "2",
        "activity_b": '{"x":1}',
    }
    assert calls[0] == ("trigger", ("pipe_a", {"p": "1"}))
    assert sleep_calls == [0.01]


def test_adf_runner_raises_on_trigger_failure():
    runner = ADFExecutionRunner(
        trigger_run_fn=lambda _name, _params: (_ for _ in ()).throw(RuntimeError("boom")),
        get_run_status_fn=lambda _run_id: "SUCCEEDED",
        get_activity_outputs_fn=lambda _run_id: {"a": "1"},
    )

    with pytest.raises(RuntimeError, match="adf_trigger_failed"):
        runner.run("pipe_a")


def test_adf_runner_raises_on_timeout():
    sleep_calls: list[float] = []
    runner = ADFExecutionRunner(
        trigger_run_fn=lambda _name, _params: "run-1",
        get_run_status_fn=lambda _run_id: "InProgress",
        get_activity_outputs_fn=lambda _run_id: {"a": "1"},
        max_polls=2,
        poll_interval_seconds=0.5,
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    with pytest.raises(TimeoutError, match="adf_run_timeout"):
        runner.run("pipe_a")

    assert sleep_calls == [0.5]


def test_adf_runner_raises_on_terminal_failed_status():
    runner = ADFExecutionRunner(
        trigger_run_fn=lambda _name, _params: "run-1",
        get_run_status_fn=lambda _run_id: "FAILED",
        get_activity_outputs_fn=lambda _run_id: {"a": "1"},
    )

    with pytest.raises(RuntimeError, match="adf_run_failed"):
        runner.run("pipe_a")


def test_adf_runner_raises_on_missing_outputs():
    runner = ADFExecutionRunner(
        trigger_run_fn=lambda _name, _params: "run-1",
        get_run_status_fn=lambda _run_id: "SUCCEEDED",
        get_activity_outputs_fn=lambda _run_id: {},
    )

    with pytest.raises(RuntimeError, match="adf_outputs_missing"):
        runner.run("pipe_a")
