"""Tests for prompt templates and test data generation."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.synthetic.prompt_templates import (
    PROMPT_TEMPLATES,
    list_templates,
    resolve_template,
)
from lakeflow_migration_validator.synthetic.test_data_generator import (
    SyntheticTestData,
    TestDataGenerator,
)


# --- Prompt Templates ---


def test_all_templates_have_required_fields():
    for key, template in PROMPT_TEMPLATES.items():
        assert "label" in template, f"Template {key} missing 'label'"
        assert "icon" in template, f"Template {key} missing 'icon'"
        assert "description" in template, f"Template {key} missing 'description'"
        assert "prompt" in template, f"Template {key} missing 'prompt'"
        assert "{count}" in template["prompt"], f"Template {key} prompt missing {{count}}"
        assert "{max_activities}" in template["prompt"], f"Template {key} prompt missing {{max_activities}}"


def test_resolve_template_fills_placeholders():
    resolved = resolve_template("complex_expressions", count=50, max_activities=15)
    assert "50" in resolved
    assert "15" in resolved
    assert "{count}" not in resolved
    assert "{max_activities}" not in resolved


def test_resolve_template_unknown_raises():
    with pytest.raises(ValueError, match="Unknown template"):
        resolve_template("nonexistent_template")


def test_list_templates_returns_all():
    templates = list_templates()
    assert len(templates) == len(PROMPT_TEMPLATES)
    for t in templates:
        assert "key" in t
        assert "label" in t
        assert "icon" in t
        assert "description" in t


def test_preset_templates_exist():
    expected = {
        "complex_expressions",
        "deep_nesting",
        "activity_mix",
        "math_on_params",
        "unsupported_types",
        "pipeline_invocation",
        "full_coverage",
    }
    assert set(PROMPT_TEMPLATES.keys()) == expected


# --- Test Data Generation ---


def test_generate_for_pipeline_with_copy():
    adf_json = {
        "name": "test_copy_pipeline",
        "properties": {
            "activities": [
                {"name": "copy_data", "type": "Copy", "input_dataset_definitions": []},
                {"name": "notebook", "type": "DatabricksNotebook"},
            ]
        },
    }
    gen = TestDataGenerator()
    data = gen.generate_for_pipeline(adf_json)

    assert data.pipeline_name == "test_copy_pipeline"
    assert len(data.source_files) == 1
    assert "copy_data_source.csv" in list(data.source_files.keys())[0]
    assert "id,name,value" in list(data.source_files.values())[0]
    assert "copy_data" in data.expected_outputs


def test_generate_for_pipeline_with_lookup():
    adf_json = {
        "name": "test_lookup_pipeline",
        "properties": {
            "activities": [
                {
                    "name": "get_config",
                    "type": "Lookup",
                    "source": {"sql_reader_query": "SELECT TOP 1 * FROM config_table"},
                },
            ]
        },
    }
    gen = TestDataGenerator()
    data = gen.generate_for_pipeline(adf_json)

    assert len(data.seed_sql) > 0
    assert any("CREATE TABLE" in s for s in data.seed_sql)
    assert any("INSERT INTO" in s for s in data.seed_sql)
    assert "get_config" in data.expected_outputs


def test_generate_for_pipeline_without_data_activities():
    adf_json = {
        "name": "test_no_data",
        "properties": {
            "activities": [
                {"name": "set_var", "type": "SetVariable"},
            ]
        },
    }
    gen = TestDataGenerator()
    data = gen.generate_for_pipeline(adf_json)

    assert len(data.source_files) == 0
    assert len(data.seed_sql) == 0
    assert "No data-reading" in data.setup_instructions


def test_generate_for_suite():
    pipelines = [
        {"name": f"pipe_{i}", "properties": {"activities": [{"name": f"copy_{i}", "type": "Copy"}]}} for i in range(3)
    ]
    gen = TestDataGenerator()
    results = gen.generate_for_suite(pipelines)

    assert len(results) == 3
    assert all(isinstance(r, SyntheticTestData) for r in results)


def test_synthetic_test_data_to_dict():
    data = SyntheticTestData(
        pipeline_name="test",
        source_files={"a.csv": "id\n1"},
        seed_sql=("INSERT INTO t VALUES (1);",),
        expected_outputs={"task_a": "result"},
        setup_instructions="1. Upload a.csv",
    )
    d = data.to_dict()
    assert d["pipeline_name"] == "test"
    assert isinstance(d["seed_sql"], list)
    assert len(d["source_files"]) == 1
