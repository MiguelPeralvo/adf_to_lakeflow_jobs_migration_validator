"""Unit tests for FMAPIJudgeProvider."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.providers.fmapi import FMAPIJudgeProvider


def test_fmapi_provider_uses_batch_model_by_default():
    calls = []

    def transport(endpoint, payload, timeout):
        calls.append((endpoint, payload, timeout))
        return {"score": 0.5, "reasoning": "default route"}

    provider = FMAPIJudgeProvider(
        endpoint="https://example.test/fmapi",
        batch_model="chatgpt-5-4",
        high_stakes_model="claude-opus-4-6",
        timeout_seconds=11,
        transport=transport,
    )

    result = provider.judge("hello")

    assert result == {"score": 0.5, "reasoning": "default route"}
    assert calls[0][0] == "https://example.test/fmapi"
    assert calls[0][1]["model"] == "chatgpt-5-4"
    assert calls[0][2] == 11


def test_fmapi_provider_respects_explicit_model_override():
    def transport(_endpoint, payload, _timeout):
        assert payload["model"] == "claude-opus-4-6"
        return {"score": 0.9, "reasoning": "manual override"}

    provider = FMAPIJudgeProvider(endpoint="https://example.test/fmapi", transport=transport)

    result = provider.judge("hello", model="claude-opus-4-6")

    assert result["score"] == 0.9


def test_fmapi_provider_retries_then_succeeds():
    attempts = {"count": 0}

    def transport(_endpoint, _payload, _timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimeoutError("temporary")
        return {"score": 0.77, "reasoning": "recovered"}

    provider = FMAPIJudgeProvider(endpoint="https://example.test/fmapi", max_retries=3, transport=transport)

    result = provider.judge("hello")

    assert attempts["count"] == 3
    assert result["score"] == 0.77


def test_fmapi_provider_raises_on_invalid_payload():
    def transport(_endpoint, _payload, _timeout):
        return {"reasoning": "missing score"}

    provider = FMAPIJudgeProvider(endpoint="https://example.test/fmapi", transport=transport)

    with pytest.raises(RuntimeError, match="failed after retries"):
        provider.judge("hello")


def test_fmapi_provider_clamps_score_to_unit_interval():
    def transport(_endpoint, _payload, _timeout):
        return {"score": "4.5", "reasoning": "too high"}

    provider = FMAPIJudgeProvider(endpoint="https://example.test/fmapi", transport=transport)

    result = provider.judge("hello")

    assert result["score"] == 1.0
