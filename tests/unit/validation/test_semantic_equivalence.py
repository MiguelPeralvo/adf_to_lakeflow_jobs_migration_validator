"""Unit tests for semantic equivalence dimension helpers."""

from __future__ import annotations

import json

from lakeflow_migration_validator.dimensions.semantic_equivalence import (
    create_semantic_equivalence_judge,
    load_expression_calibration_examples,
)


class _Provider:
    def __init__(self):
        self.calls = []

    def judge(self, prompt: str, model: str | None = None):
        self.calls.append((prompt, model))
        return {"score": 0.88, "reasoning": "semantically equivalent"}


def test_load_expression_calibration_examples_uses_stable_order(tmp_path):
    path = tmp_path / "expressions.json"
    path.write_text(
        json.dumps(
            {
                "expressions": [
                    {"adf_expression": "@add(1,2)", "expected_python": "(1 + 2)", "category": "math"},
                    {"adf_expression": "@mul(2,3)", "expected_python": "(2 * 3)", "category": "math"},
                    {"adf_expression": "@toUpper('x')", "expected_python": "str('x').upper()", "category": "string"},
                ]
            }
        ),
        encoding="utf-8",
    )

    examples = load_expression_calibration_examples(path=str(path), sample_size=2)

    assert examples == (
        {"input": "@add(1,2)", "output": "(1 + 2)", "score": 1.0},
        {"input": "@mul(2,3)", "output": "(2 * 3)", "score": 1.0},
    )


def test_create_semantic_equivalence_judge_builds_configured_judge(tmp_path):
    path = tmp_path / "expressions.json"
    path.write_text(
        json.dumps(
            {
                "expressions": [
                    {"adf_expression": "@equals(1,1)", "expected_python": "(1 == 1)", "category": "logical"}
                ]
            }
        ),
        encoding="utf-8",
    )
    provider = _Provider()
    judge = create_semantic_equivalence_judge(
        provider,
        threshold=0.75,
        model="chatgpt-5-4",
        calibration_path=str(path),
        calibration_sample_size=1,
    )

    result = judge.evaluate("@equals(1,1)", "(1 == 1)")

    assert judge.name == "semantic_equivalence"
    assert judge.threshold == 0.75
    assert judge.model == "chatgpt-5-4"
    assert len(judge.calibration_examples) == 1
    assert result.score == 0.88
    assert provider.calls[0][1] == "chatgpt-5-4"
