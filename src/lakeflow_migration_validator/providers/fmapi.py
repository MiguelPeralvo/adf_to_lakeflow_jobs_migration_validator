"""Databricks FMAPI-backed implementation of the judge provider protocol."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib import request
from urllib.error import URLError


class FMAPIJudgeProvider:
    """JudgeProvider backed by Databricks Foundation Model API."""

    def __init__(
        self,
        endpoint: str,
        high_stakes_model: str = "claude-opus-4-6",
        batch_model: str = "chatgpt-5-4",
        timeout_seconds: int = 30,
        max_retries: int = 2,
        transport: Callable[[str, dict[str, Any], int], dict[str, Any]] | None = None,
    ):
        self.endpoint = endpoint
        self.high_stakes_model = high_stakes_model
        self.batch_model = batch_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._transport = transport or _default_transport

    def judge(self, prompt: str, model: str | None = None) -> dict[str, Any]:
        """Score prompt output with retry and strict response parsing."""
        selected_model = model or self.batch_model
        payload = {"model": selected_model, "prompt": prompt}
        last_error: Exception | None = None

        for _ in range(self.max_retries + 1):
            try:
                raw = self._transport(self.endpoint, payload, self.timeout_seconds)
                parsed = _parse_judge_response(raw)
                return {"score": parsed["score"], "reasoning": parsed["reasoning"]}
            except (URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                continue

        raise RuntimeError(f"FMAPI judge request failed after retries: {last_error}") from last_error


def _parse_judge_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate FMAPI judge payload."""
    if not isinstance(raw, dict):
        raise ValueError("FMAPI response must be a dict")
    if "score" not in raw or "reasoning" not in raw:
        raise ValueError("FMAPI response must contain score and reasoning")

    try:
        score = float(raw["score"])
    except (TypeError, ValueError) as exc:
        raise ValueError("FMAPI response score must be numeric") from exc

    return {
        "score": max(0.0, min(1.0, score)),
        "reasoning": str(raw["reasoning"]),
    }


def _default_transport(endpoint: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    """POST JSON payload and return JSON dict response."""
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as resp:
        raw_text = resp.read().decode("utf-8")
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("FMAPI response JSON must be an object")
    return data
