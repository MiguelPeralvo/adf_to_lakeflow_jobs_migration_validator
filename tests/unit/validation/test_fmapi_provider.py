"""Unit tests for FMAPIJudgeProvider."""

from __future__ import annotations

import json

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
    assert calls[0][0] == "https://example.test/fmapi/claude-opus-4-6/invocations"
    assert "messages" in calls[0][1]
    assert calls[0][2] == 11


def test_fmapi_provider_respects_explicit_model_override():
    def transport(endpoint, payload, _timeout):
        assert "claude-opus-4-6/invocations" in endpoint
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


def test_fmapi_provider_applies_retry_backoff(monkeypatch):
    attempts = {"count": 0}
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)

    def transport(_endpoint, _payload, _timeout):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimeoutError("retry")
        return {"score": 0.5, "reasoning": "ok"}

    monkeypatch.setattr("lakeflow_migration_validator.providers.fmapi.time.sleep", fake_sleep)

    provider = FMAPIJudgeProvider(endpoint="https://example.test/fmapi", max_retries=3, transport=transport)
    provider.judge("hello")

    assert sleeps == [0.5, 1.0]


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


def test_fmapi_provider_parses_chat_completions_shape():
    def transport(_endpoint, _payload, _timeout):
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"score": 0.66, "reasoning": "Parsed from chat completions"}',
                    }
                }
            ]
        }

    provider = FMAPIJudgeProvider(endpoint="https://example.test/fmapi", transport=transport)

    result = provider.judge("hello")

    assert result == {"score": 0.66, "reasoning": "Parsed from chat completions"}


def test_fmapi_provider_sends_auth_header_on_default_transport(monkeypatch):
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

        def read(self):
            return json.dumps({"score": 0.75, "reasoning": "ok"}).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["authorization"] = req.headers.get("Authorization")
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("lakeflow_migration_validator.providers.fmapi.request.urlopen", fake_urlopen)

    provider = FMAPIJudgeProvider(
        endpoint="https://example.test/fmapi",
        token="secret-token",
        timeout_seconds=7,
    )

    result = provider.judge("hello")

    assert result["score"] == 0.75
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["timeout"] == 7


def test_fmapi_provider_judge_high_stakes_uses_high_stakes_model():
    captured = {}

    def transport(endpoint, payload, _timeout):
        captured["endpoint"] = endpoint
        return {"score": 0.81, "reasoning": "used high-stakes route"}

    provider = FMAPIJudgeProvider(
        endpoint="https://example.test/fmapi",
        high_stakes_model="claude-opus-4-6",
        batch_model="chatgpt-5-4",
        transport=transport,
    )

    result = provider.judge_high_stakes("high-stakes prompt")

    assert "claude-opus-4-6/invocations" in captured["endpoint"]
    assert result["score"] == 0.81


def test_fmapi_provider_rejects_non_http_endpoint(monkeypatch):
    def fake_urlopen(_req, _timeout):
        raise AssertionError("urlopen should not be called for invalid endpoint scheme")

    monkeypatch.setattr("lakeflow_migration_validator.providers.fmapi.request.urlopen", fake_urlopen)

    provider = FMAPIJudgeProvider(endpoint="file:///tmp/fmapi.json")

    with pytest.raises(RuntimeError, match="FMAPI endpoint must use http or https"):
        provider.judge("hello")
