"""Databricks FMAPI-backed implementation of the judge provider protocol."""

from __future__ import annotations

import json
import math
import time
from typing import Any, Callable
from urllib import request
from urllib.error import URLError
from urllib.parse import urlparse


class FMAPIJudgeProvider:
    """JudgeProvider backed by Databricks Foundation Model API."""

    def __init__(
        self,
        endpoint: str,
        high_stakes_model: str = "databricks-claude-opus-4-6",
        batch_model: str = "databricks-chatgpt-5-4",
        timeout_seconds: int = 30,
        max_retries: int = 2,
        token: str | None = None,
        transport: Callable[[str, dict[str, Any], int], dict[str, Any]] | None = None,
    ):
        self.endpoint = endpoint
        self.high_stakes_model = high_stakes_model
        self.batch_model = batch_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        if transport is None:
            self._transport = lambda endpoint, payload, timeout: _default_transport(
                endpoint,
                payload,
                timeout,
                token=token,
            )
        else:
            self._transport = transport

    def judge(self, prompt: str, model: str | None = None) -> dict[str, Any]:
        """Score prompt output with retry and strict response parsing."""
        selected_model = model or self.high_stakes_model
        endpoint_url = f"{self.endpoint.rstrip('/')}/{selected_model}/invocations"
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                raw = self._transport(endpoint_url, payload, self.timeout_seconds)
                parsed = _parse_judge_response(raw)
                return {"score": parsed["score"], "reasoning": parsed["reasoning"]}
            except (URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    backoff = min(0.5 * (2 ** attempt), 8.0)
                    time.sleep(backoff)
                continue

        raise RuntimeError(f"FMAPI judge request failed after retries: {last_error}") from last_error

    def judge_high_stakes(self, prompt: str) -> dict[str, Any]:
        """Convenience method that always routes to the high-stakes model."""
        return self.judge(prompt, model=self.high_stakes_model)

    def complete(self, prompt: str, model: str | None = None, max_tokens: int = 4096) -> str:
        """Raw LLM completion — returns text content without score/reasoning parsing.

        Use this for generation tasks (e.g. synthetic pipeline generation) where
        the LLM output is not a judge response.
        """
        selected_model = model or self.high_stakes_model
        endpoint_url = f"{self.endpoint.rstrip('/')}/{selected_model}/invocations"
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                raw = self._transport(endpoint_url, payload, self.timeout_seconds)
                return _extract_content(raw)
            except (URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    backoff = min(0.5 * (2 ** attempt), 8.0)
                    time.sleep(backoff)
                continue

        raise RuntimeError(f"FMAPI complete request failed after retries: {last_error}") from last_error


def _extract_content(raw: dict[str, Any]) -> str:
    """Extract raw text content from an FMAPI response.

    Handles both response formats:
    - Chat Completions: ``{"choices": [{"message": {"content": "..."}}]}``
    - Anthropic Messages: ``{"content": [{"type": "text", "text": "..."}]}``
    """
    if not isinstance(raw, dict):
        raise ValueError("FMAPI response must be a dict")

    # Chat Completions format (OpenAI-compatible)
    if "choices" in raw:
        choices = raw["choices"]
        if not isinstance(choices, list) or not choices:
            raise ValueError("FMAPI choices must be a non-empty list")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        # content could be a list of content blocks (multimodal)
        if isinstance(content, list):
            return "".join(
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        raise ValueError("FMAPI message content has unexpected type")

    # Anthropic Messages / Responses format
    if "content" in raw:
        content = raw["content"]
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        raise ValueError("FMAPI content has unexpected type")

    # Fallback: check for a top-level "text" or "output" field
    if "text" in raw:
        return str(raw["text"])
    if "output" in raw and isinstance(raw["output"], str):
        return raw["output"]

    raise ValueError(f"Cannot extract content from FMAPI response (keys: {list(raw.keys())})")


def _parse_judge_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate FMAPI judge payload."""
    if not isinstance(raw, dict):
        raise ValueError("FMAPI response must be a dict")

    # Databricks FMAPI chat-completions shape:
    # {"choices": [{"message": {"content": "{\"score\": 0.9, \"reasoning\": \"...\"}"}}]}
    if "choices" in raw:
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("FMAPI choices must be a non-empty list")
        first = choices[0]
        if not isinstance(first, dict):
            raise ValueError("FMAPI choice must be an object")
        message = first.get("message", {})
        if not isinstance(message, dict):
            raise ValueError("FMAPI message must be an object")
        content = message.get("content")
        if not isinstance(content, str):
            raise ValueError("FMAPI message content must be a JSON string")
        try:
            raw = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("FMAPI message content must be valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("FMAPI message content JSON must be an object")

    if "score" not in raw or "reasoning" not in raw:
        raise ValueError("FMAPI response must contain score and reasoning")

    try:
        score = float(raw["score"])
    except (TypeError, ValueError) as exc:
        raise ValueError("FMAPI response score must be numeric") from exc

    if math.isnan(score):
        raise ValueError("FMAPI response score must be numeric") from None

    return {
        "score": max(0.0, min(1.0, score)),
        "reasoning": str(raw["reasoning"]),
    }


def _default_transport(
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST JSON payload and return JSON dict response."""
    scheme = urlparse(endpoint).scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("FMAPI endpoint must use http or https")

    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(
        endpoint,
        data=body,
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_seconds) as resp:
        raw_text = resp.read().decode("utf-8")
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("FMAPI response JSON must be an object")
    return data
