"""Tests for the LLM-powered agent pipeline generator."""

from __future__ import annotations

import json

import pytest

from lakeflow_migration_validator.synthetic.agent_generator import (
    AgentPipelineGenerator,
    FailureFeedback,
    FailureRecord,
    GenerationConfig,
    _estimate_ground_truth,
    _extract_json,
)


class _MockProvider:
    """Mock JudgeProvider that returns pre-configured responses."""

    def __init__(self, responses: list[dict] | None = None):
        self._responses = responses or []
        self._call_idx = 0

    def judge(self, prompt: str, model: str | None = None) -> dict:
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
        else:
            resp = {"score": 0.5, "reasoning": "{}"}
        self._call_idx += 1
        return resp


_VALID_PIPELINE_JSON = json.dumps({
    "name": "test_pipeline",
    "properties": {
        "parameters": {"env": {"type": "String"}},
        "activities": [
            {
                "name": "set_var",
                "type": "SetVariable",
                "depends_on": [],
                "variable_name": "result",
                "value": {"type": "Expression", "value": "@concat('hello', pipeline().parameters.env)"},
            },
            {
                "name": "notebook",
                "type": "DatabricksNotebook",
                "depends_on": [{"activity": "set_var", "dependency_conditions": ["Succeeded"]}],
                "notebook_path": "/notebooks/etl",
            },
        ],
    },
})


def test_extract_json_from_plain_json():
    assert _extract_json('{"name": "test"}') == {"name": "test"}


def test_extract_json_from_markdown_code_block():
    text = "```json\n{\"name\": \"test\"}\n```"
    assert _extract_json(text) == {"name": "test"}


def test_extract_json_from_mixed_text():
    text = "Here is the pipeline:\n{\"name\": \"test\"}\nDone."
    assert _extract_json(text) == {"name": "test"}


def test_extract_json_returns_none_for_invalid():
    assert _extract_json("not json at all") is None
    assert _extract_json("") is None
    assert _extract_json(None) is None


def test_estimate_ground_truth_all_supported():
    adf = {"properties": {"activities": [
        {"name": "a", "type": "SetVariable"},
        {"name": "b", "type": "DatabricksNotebook"},
    ]}}
    gt = _estimate_ground_truth(adf)
    assert gt["activity_coverage"] == 1.0


def test_estimate_ground_truth_with_unsupported():
    adf = {"properties": {"activities": [
        {"name": "a", "type": "SetVariable"},
        {"name": "b", "type": "AzureFunctionActivity"},
    ]}}
    gt = _estimate_ground_truth(adf)
    assert gt["activity_coverage"] == 0.5


def test_estimate_ground_truth_empty_pipeline():
    gt = _estimate_ground_truth({"properties": {"activities": []}})
    assert gt["activity_coverage"] == 0.0


def test_agent_generator_calls_provider():
    provider = _MockProvider([
        {"score": 0.9, "reasoning": _VALID_PIPELINE_JSON},
        {"score": 0.8, "reasoning": json.dumps({"activity_coverage": 1.0})},
    ])
    gen = AgentPipelineGenerator(judge_provider=provider)
    pipelines = gen.generate(count=1)

    assert len(pipelines) == 1
    assert pipelines[0].adf_json["name"] == "test_pipeline"
    assert pipelines[0].difficulty == "llm"
    assert "nested_expressions" in pipelines[0].description


def test_agent_generator_handles_invalid_llm_output():
    provider = _MockProvider([
        {"score": 0.5, "reasoning": "I can't generate JSON sorry"},
        {"score": 0.5, "reasoning": "Still no JSON"},
        {"score": 0.5, "reasoning": "Nope"},
    ])
    gen = AgentPipelineGenerator(judge_provider=provider, max_retries=2)
    pipelines = gen.generate(count=1)

    assert len(pipelines) == 0  # skipped because all retries failed


def test_agent_generator_retries_on_invalid_json():
    provider = _MockProvider([
        {"score": 0.5, "reasoning": "not json"},
        {"score": 0.9, "reasoning": _VALID_PIPELINE_JSON},
        {"score": 0.8, "reasoning": json.dumps({"activity_coverage": 1.0})},
    ])
    gen = AgentPipelineGenerator(judge_provider=provider, max_retries=1)
    pipelines = gen.generate(count=1)

    assert len(pipelines) == 1


def test_agent_generator_builds_expected_snapshot():
    provider = _MockProvider([
        {"score": 0.9, "reasoning": _VALID_PIPELINE_JSON},
        {"score": 0.8, "reasoning": json.dumps({"activity_coverage": 1.0})},
    ])
    gen = AgentPipelineGenerator(judge_provider=provider)
    pipelines = gen.generate(count=1)

    snapshot = pipelines[0].expected_snapshot
    assert len(snapshot.tasks) == 2
    assert snapshot.tasks[0].task_key == "set_var"
    assert not snapshot.tasks[0].is_placeholder
    assert snapshot.total_source_dependencies == 1


def test_agent_generator_rotates_weak_spots():
    responses = []
    for i in range(6):
        responses.extend([
            {"score": 0.9, "reasoning": json.dumps({"name": f"pipe_{i}", "properties": {"activities": [{"name": f"a{i}", "type": "SetVariable", "depends_on": []}]}})},
            {"score": 0.8, "reasoning": json.dumps({"activity_coverage": 1.0})},
        ])

    provider = _MockProvider(responses)
    config = GenerationConfig(
        target_weak_spots=("nested_expressions", "math_on_params", "deep_nesting"),
    )
    gen = AgentPipelineGenerator(judge_provider=provider)
    pipelines = gen.generate(count=3, config=config)

    descriptions = [p.description for p in pipelines]
    assert "nested_expressions" in descriptions[0]
    assert "math_on_params" in descriptions[1]
    assert "deep_nesting" in descriptions[2]


def test_failure_feedback_records_and_suggests():
    fb = FailureFeedback()
    fb.record(FailureRecord(pipeline_name="p1", dimension="expression_coverage", score=0.3, error="unsupported"))
    fb.record(FailureRecord(pipeline_name="p2", dimension="expression_coverage", score=0.4, error="unsupported"))
    fb.record(FailureRecord(pipeline_name="p3", dimension="activity_coverage", score=0.5, error="placeholder"))

    config = fb.suggest_config()
    assert "nested_expressions" in config.target_weak_spots or "math_on_params" in config.target_weak_spots
    assert config.include_unsupported  # activity_coverage failures suggest unsupported types


def test_failure_feedback_empty_returns_default():
    fb = FailureFeedback()
    config = fb.suggest_config()
    assert config == GenerationConfig()
