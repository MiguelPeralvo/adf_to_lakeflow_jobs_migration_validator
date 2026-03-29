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
    _extract_parameters,
    _is_adf_pipeline,
)


class _MockProvider:
    """Mock JudgeProvider that returns pre-configured responses."""

    def __init__(self, responses: list[dict] | None = None, completions: list[str] | None = None):
        self._responses = responses or []
        self._completions = completions or []
        self._call_idx = 0
        self._complete_idx = 0

    def judge(self, prompt: str, model: str | None = None) -> dict:
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
        else:
            resp = {"score": 0.5, "reasoning": "{}"}
        self._call_idx += 1
        return resp

    def complete(self, prompt: str, model: str | None = None, max_tokens: int = 4096) -> str:
        if self._complete_idx < len(self._completions):
            text = self._completions[self._complete_idx]
        else:
            text = "{}"
        self._complete_idx += 1
        return text


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


def test_is_adf_pipeline_valid():
    assert _is_adf_pipeline({"properties": {"activities": [{"name": "a", "type": "SetVariable"}]}})


def test_is_adf_pipeline_rejects_non_pipeline():
    assert not _is_adf_pipeline({"activity_coverage": 1.0})
    assert not _is_adf_pipeline({"foo": "bar"})
    assert not _is_adf_pipeline({"properties": {"activities": []}})


def test_is_adf_pipeline_top_level_activities():
    assert _is_adf_pipeline({"activities": [{"name": "a", "type": "Copy"}]})


def test_extract_parameters_dict_format():
    adf = {"properties": {"parameters": {"env": {"type": "String"}, "count": {"type": "Int"}}}}
    assert _extract_parameters(adf) == ("env", "count")


def test_extract_parameters_empty():
    assert _extract_parameters({"properties": {}}) == ()
    assert _extract_parameters({}) == ()


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
    plan_json = json.dumps({
        "count": 1,
        "pipelines": [
            {"name": "test_pipeline", "activity_count": 2, "activity_types": ["SetVariable", "DatabricksNotebook"],
             "stress_area": "nested_expressions", "expression_complexity": "nested", "parameters": ["env"]}
        ],
    })
    provider = _MockProvider(completions=[
        plan_json,           # plan phase
        _VALID_PIPELINE_JSON,  # pipeline generation
    ])
    gen = AgentPipelineGenerator(judge_provider=provider)
    pipelines = gen.generate(count=1)

    assert len(pipelines) == 1
    assert pipelines[0].adf_json["name"] == "test_pipeline"
    assert pipelines[0].difficulty == "llm"


def test_agent_generator_handles_invalid_llm_output():
    provider = _MockProvider(completions=[
        "{}",  # plan phase — empty, falls back to deterministic plan
        "I can't generate JSON sorry",
        "Still no JSON",
        "Nope",
    ])
    gen = AgentPipelineGenerator(judge_provider=provider, max_retries=2)
    pipelines = gen.generate(count=1)

    assert len(pipelines) == 0  # skipped because all retries failed


def test_agent_generator_retries_on_invalid_json():
    plan_json = json.dumps({
        "count": 1,
        "pipelines": [
            {"name": "test_pipeline", "activity_count": 2, "activity_types": ["SetVariable", "DatabricksNotebook"],
             "stress_area": "nested_expressions", "parameters": ["env"]}
        ],
    })
    provider = _MockProvider(completions=[
        plan_json,           # plan phase
        "not json",          # first attempt fails
        _VALID_PIPELINE_JSON,  # retry succeeds
    ])
    gen = AgentPipelineGenerator(judge_provider=provider, max_retries=1)
    pipelines = gen.generate(count=1)

    assert len(pipelines) == 1


def test_agent_generator_builds_expected_snapshot():
    plan_json = json.dumps({
        "count": 1,
        "pipelines": [
            {"name": "test_pipeline", "activity_count": 2, "activity_types": ["SetVariable", "DatabricksNotebook"],
             "stress_area": "nested_expressions", "parameters": ["env"]}
        ],
    })
    provider = _MockProvider(completions=[
        plan_json,
        _VALID_PIPELINE_JSON,
    ])
    gen = AgentPipelineGenerator(judge_provider=provider)
    pipelines = gen.generate(count=1)

    snapshot = pipelines[0].expected_snapshot
    assert len(snapshot.tasks) == 2
    assert snapshot.tasks[0].task_key == "set_var"
    assert not snapshot.tasks[0].is_placeholder
    assert snapshot.total_source_dependencies == 1


def test_agent_generator_rotates_weak_spots():
    plan_json = json.dumps({
        "count": 3,
        "pipelines": [
            {"name": "pipe_0", "activity_count": 1, "activity_types": ["SetVariable"],
             "stress_area": "nested_expressions", "parameters": ["env"]},
            {"name": "pipe_1", "activity_count": 1, "activity_types": ["SetVariable"],
             "stress_area": "math_on_params", "parameters": ["env"]},
            {"name": "pipe_2", "activity_count": 1, "activity_types": ["SetVariable"],
             "stress_area": "deep_nesting", "parameters": ["env"]},
        ],
    })
    completions = [plan_json]
    for i in range(3):
        completions.append(json.dumps({
            "name": f"pipe_{i}",
            "properties": {"activities": [{"name": f"a{i}", "type": "SetVariable", "depends_on": []}]},
        }))

    provider = _MockProvider(completions=completions)
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
