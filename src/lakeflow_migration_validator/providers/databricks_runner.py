"""Databricks execution runner adapter for ExecutionDimension."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class DatabricksJobRunner:
    """ExecutionRunner implementation backed by an injected run-and-wait function."""

    run_job_and_wait: Callable[[Any, dict[str, str]], dict[str, Any]]

    def run(self, output: Any, params: dict[str, str]) -> dict[str, Any]:
        raw = self.run_job_and_wait(output, params)
        return _normalize_task_results(raw)


def _normalize_task_results(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize different Databricks result shapes into task success/error mapping."""
    if not isinstance(raw, dict):
        raise ValueError("Databricks runner result must be a dict")

    tasks = raw.get("tasks")
    if isinstance(tasks, list):
        normalized: dict[str, dict[str, Any]] = {}
        for idx, task in enumerate(tasks):
            task_key = str(task.get("task_key") or f"task_{idx}")
            state = task.get("state", {})
            result_state = str(state.get("result_state", "")).upper()
            success = result_state == "SUCCESS"
            normalized[task_key] = {
                "success": success,
                "error": None if success else str(state.get("state_message", "task failed")),
            }
        return normalized

    normalized = {}
    for task_key, value in raw.items():
        if not isinstance(value, dict):
            raise ValueError(f"Task result for {task_key} must be a dict")
        success = value.get("success")
        if not isinstance(success, bool):
            raise ValueError(f"Task result for {task_key} must include a boolean 'success' flag")
        normalized[str(task_key)] = {
            "success": success,
            "error": value.get("error"),
        }
    return normalized
