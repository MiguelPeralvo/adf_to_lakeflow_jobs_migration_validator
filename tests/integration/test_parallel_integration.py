"""Marker-gated live integration for parallel ADF-vs-Databricks comparison."""

from __future__ import annotations

import json
import os
import shlex
import subprocess

import pytest

from lakeflow_migration_validator.parallel.adf_runner import ADFExecutionRunner
from lakeflow_migration_validator.parallel.parallel_test_runner import ParallelTestRunner

pytestmark = [pytest.mark.integration, pytest.mark.parallel]


_REQUIRED_ENV = {
    "LMV_RUN_PARALLEL_LIVE",
    "LMV_PARALLEL_PIPELINE_NAME",
    "LMV_PARALLEL_ADF_TRIGGER_CMD",
    "LMV_PARALLEL_ADF_STATUS_CMD",
    "LMV_PARALLEL_ADF_OUTPUTS_CMD",
    "LMV_PARALLEL_DATABRICKS_CMD",
}


def test_parallel_live_run_contract():
    if os.getenv("LMV_RUN_PARALLEL_LIVE", "0") != "1":
        pytest.skip("set LMV_RUN_PARALLEL_LIVE=1 to enable live parallel integration")

    missing = sorted(name for name in _REQUIRED_ENV if not os.getenv(name))
    if missing:
        pytest.skip(f"missing required env vars for live run: {missing}")

    def trigger(pipeline_name: str, parameters: dict[str, str]) -> str:
        payload = _run_json_command(
            os.environ["LMV_PARALLEL_ADF_TRIGGER_CMD"],
            {
                "pipeline_name": pipeline_name,
                "parameters": parameters,
            },
        )
        run_id = str(payload.get("run_id", ""))
        if not run_id:
            raise RuntimeError("trigger command did not return run_id")
        return run_id

    def status(run_id: str) -> str:
        payload = _run_json_command(os.environ["LMV_PARALLEL_ADF_STATUS_CMD"], {"run_id": run_id})
        return str(payload.get("status", "UNKNOWN"))

    def outputs(run_id: str) -> dict[str, object]:
        payload = _run_json_command(os.environ["LMV_PARALLEL_ADF_OUTPUTS_CMD"], {"run_id": run_id})
        values = payload.get("outputs")
        if not isinstance(values, dict):
            raise RuntimeError("outputs command did not return dict in 'outputs'")
        return {str(key): value for key, value in values.items()}

    class _DatabricksRunner:
        def run(self, pipeline_name: str, parameters: dict[str, str] | None = None) -> dict[str, object]:
            payload = _run_json_command(
                os.environ["LMV_PARALLEL_DATABRICKS_CMD"],
                {"pipeline_name": pipeline_name, "parameters": parameters or {}},
            )
            values = payload.get("outputs")
            if not isinstance(values, dict):
                raise RuntimeError("databricks command did not return dict in 'outputs'")
            return {str(key): value for key, value in values.items()}

    runner = ParallelTestRunner(
        adf_runner=ADFExecutionRunner(
            trigger_run_fn=trigger,
            get_run_status_fn=status,
            get_activity_outputs_fn=outputs,
        ),
        databricks_runner=_DatabricksRunner(),
    )

    result = runner.run(os.environ["LMV_PARALLEL_PIPELINE_NAME"])

    assert result.pipeline_name
    assert result.comparisons
    assert "parallel_equivalence" in result.scorecard.results
    assert 0.0 <= result.equivalence_score <= 1.0


def _run_json_command(command: str, payload: dict) -> dict:
    timeout_seconds = 30.0
    try:
        proc = subprocess.run(
            shlex.split(command),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"command timed out after {timeout_seconds}s ({command})") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"command failed ({command}): {proc.stderr.strip()}")
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"command did not return JSON ({command}): {proc.stdout!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"command returned non-object JSON ({command})")
    return parsed
