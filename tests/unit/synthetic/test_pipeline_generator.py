"""Unit tests for synthetic pipeline generation."""

import pytest

from lakeflow_migration_validator.synthetic.pipeline_generator import PipelineGenerator


def test_generate_returns_requested_count_and_snapshot_consistency():
    generator = PipelineGenerator(mode="template")

    pipelines = generator.generate(count=6, difficulty="medium", max_activities=8)

    assert len(pipelines) == 6
    for synthetic in pipelines:
        activities = synthetic.adf_json["properties"]["activities"]
        assert 1 <= len(activities) <= 8
        assert len(synthetic.expected_snapshot.tasks) == len(activities)
        assert synthetic.expected_snapshot.total_source_dependencies == max(len(activities) - 1, 0)
        assert synthetic.description
        assert synthetic.difficulty == "medium"


def test_activity_type_filter_is_respected():
    generator = PipelineGenerator(mode="template")

    pipelines = generator.generate(count=4, activity_types=["SetVariable"], max_activities=5)

    for synthetic in pipelines:
        types = {activity["type"] for activity in synthetic.adf_json["properties"]["activities"]}
        assert types == {"SetVariable"}


def test_nested_expression_complexity_generates_nested_expressions():
    generator = PipelineGenerator(mode="template")

    pipelines = generator.generate(count=3, expression_complexity="nested", max_activities=4)

    flattened = [
        pair.adf_expression
        for synthetic in pipelines
        for pair in synthetic.expected_snapshot.resolved_expressions
    ]
    assert flattened
    assert all(expr.count("(") >= 3 for expr in flattened)


def test_invalid_mode_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported generator mode"):
        PipelineGenerator(mode="unsupported")


def test_invalid_expression_complexity_raises_value_error():
    generator = PipelineGenerator()

    with pytest.raises(ValueError, match="Unsupported expression complexity"):
        generator.generate(count=1, expression_complexity="impossible")


def test_adversarial_mode_marks_difficulty_as_adversarial():
    generator = PipelineGenerator(mode="adversarial")

    pipelines = generator.generate(count=2)

    assert {pipeline.difficulty for pipeline in pipelines} == {"adversarial"}
