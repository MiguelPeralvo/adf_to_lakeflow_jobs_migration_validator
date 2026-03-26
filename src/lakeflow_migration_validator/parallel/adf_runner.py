"""ADF pipeline execution runner for parallel testing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable


TriggerRunFn = Callable[[str, dict[str, str]], str]
GetRunStatusFn = Callable[[str], str]
GetActivityOutputsFn = Callable[[str], dict[str, Any]]
SleepFn = Callable[[float], None]


@dataclass(frozen=True, slots=True)
class ADFExecutionRunner:
    """Trigger an ADF run, poll until completion, and collect activity outputs."""

    trigger_run_fn: TriggerRunFn
    get_run_status_fn: GetRunStatusFn
    get_activity_outputs_fn: GetActivityOutputsFn
    max_polls: int = 120
    poll_interval_seconds: float = 2.0
    sleep_fn: SleepFn = field(default=time.sleep, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.max_polls, int) or isinstance(self.max_polls, bool) or self.max_polls <= 0:
            raise ValueError("max_polls must be an integer > 0")
        if not isinstance(self.poll_interval_seconds, (int, float)) or self.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be a number >= 0")
        if not callable(self.sleep_fn):
            raise ValueError("sleep_fn must be callable")

    def run(self, pipeline_name: str, parameters: dict[str, str] | None = None) -> dict[str, str]:
        """Return normalized output payloads keyed by activity name."""
        payload = dict(parameters or {})

        try:
            run_id = self.trigger_run_fn(pipeline_name, payload)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"adf_trigger_failed: {exc}") from exc

        if not run_id:
            raise RuntimeError("adf_trigger_failed: empty run id")

        status = "UNKNOWN"
        for poll_idx in range(self.max_polls):
            status = str(self.get_run_status_fn(run_id)).upper()
            if status in {"SUCCEEDED", "SUCCESS"}:
                break
            if status in {"FAILED", "CANCELED", "CANCELLED"}:
                raise RuntimeError(f"adf_run_{status.lower()}: run_id={run_id}")
            if poll_idx == self.max_polls - 1:
                raise TimeoutError(f"adf_run_timeout: run_id={run_id}, status={status}")
            self.sleep_fn(self.poll_interval_seconds)

        try:
            raw_outputs = self.get_activity_outputs_fn(run_id)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"adf_output_collection_failed: {exc}") from exc

        if not isinstance(raw_outputs, dict) or not raw_outputs:
            raise RuntimeError(f"adf_outputs_missing: run_id={run_id}")

        normalized: dict[str, str] = {}
        for activity_name, output in sorted(raw_outputs.items(), key=lambda item: str(item[0])):
            normalized[str(activity_name)] = _stringify_output(output)
        return normalized


def _stringify_output(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return str(value)
