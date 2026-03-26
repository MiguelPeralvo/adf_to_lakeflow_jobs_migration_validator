"""Unit tests for the LLMJudge dimension primitive."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge


class _StubProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def judge(self, prompt: str, model: str | None = None):
        self.calls.append({"prompt": prompt, "model": model})
        return self.response


def test_llm_judge_passes_when_score_meets_threshold():
    provider = _StubProvider({"score": 0.9, "reasoning": "Looks equivalent"})
    judge = LLMJudge(
        name="semantic_equivalence",
        criteria="Outputs should be semantically equivalent.",
        input_template="Input={input}\nOutput={output}",
        provider=provider,
        threshold=0.8,
    )

    result = judge.evaluate("x", "y")

    assert result.passed is True
    assert result.score == 0.9
    assert result.details["reasoning"] == "Looks equivalent"
    assert provider.calls[0]["model"] == "claude-opus-4-6"


def test_llm_judge_fails_when_score_below_threshold():
    provider = _StubProvider({"score": 0.3, "reasoning": "Not equivalent"})
    judge = LLMJudge(
        name="semantic_equivalence",
        criteria="Outputs should be semantically equivalent.",
        input_template="Input={input}\nOutput={output}",
        provider=provider,
        threshold=0.7,
    )

    result = judge.evaluate("a", "b")

    assert result.passed is False
    assert result.score == 0.3


def test_llm_judge_build_prompt_includes_calibration_examples():
    provider = _StubProvider({"score": 1.0, "reasoning": "ok"})
    judge = LLMJudge(
        name="semantic_equivalence",
        criteria="equivalent",
        input_template="Input={input}; Output={output}",
        provider=provider,
        calibration_examples=(
            {"input": "@add(1,2)", "output": "(1 + 2)", "score": 1.0},
            {"input": "@div(1,2)", "output": "(1 / 2)", "score": 0.2},
        ),
    )

    judge.evaluate("I", "O")
    prompt = provider.calls[0]["prompt"]

    assert "Examples:" in prompt
    assert "@add(1,2)" in prompt
    assert "(1 / 2)" in prompt
    assert "Criteria: equivalent" in prompt


def test_llm_judge_clamps_out_of_range_score():
    provider = _StubProvider({"score": 2.3, "reasoning": "too high"})
    judge = LLMJudge(
        name="semantic_equivalence",
        criteria="equivalent",
        input_template="Input={input}; Output={output}",
        provider=provider,
        threshold=0.95,
    )

    result = judge.evaluate("I", "O")

    assert result.score == 1.0
    assert result.passed is True


def test_llm_judge_propagates_provider_errors():
    class _FailingProvider:
        def judge(self, _prompt: str, model: str | None = None):
            raise RuntimeError("provider failed")

    judge = LLMJudge(
        name="semantic_equivalence",
        criteria="equivalent",
        input_template="Input={input}; Output={output}",
        provider=_FailingProvider(),
    )

    with pytest.raises(RuntimeError, match="provider failed"):
        judge.evaluate("I", "O")
