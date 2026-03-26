"""Unit tests for Day 10 golden set materialization."""

import json

from lakeflow_migration_validator.golden_set import (
    GoldenSet,
    load_expression_golden_set,
    load_pipeline_golden_set,
    materialize_golden_sets,
)


def test_materialize_golden_sets_writes_both_files(tmp_path):
    paths = materialize_golden_sets(
        output_dir=str(tmp_path),
        expression_count=14,
        pipeline_count=9,
        difficulty="simple",
        max_activities=4,
    )

    with open(paths.expressions_path, encoding="utf-8") as handle:
        expressions_payload = json.load(handle)
    with open(paths.pipelines_path, encoding="utf-8") as handle:
        pipelines_payload = json.load(handle)

    assert expressions_payload["count"] == 14
    assert len(expressions_payload["expressions"]) == 14
    assert len(pipelines_payload["pipelines"]) == 9


def test_loaders_read_materialized_golden_sets(tmp_path):
    paths = materialize_golden_sets(
        output_dir=str(tmp_path),
        expression_count=10,
        pipeline_count=7,
        difficulty="simple",
        max_activities=3,
    )

    expressions = load_expression_golden_set(paths.expressions_path)
    pipelines = load_pipeline_golden_set(paths.pipelines_path)
    golden = GoldenSet.load(paths.expressions_path, paths.pipelines_path)

    assert len(expressions) == 10
    assert len(pipelines.pipelines) == 7
    assert len(golden.expressions) == 10
    assert len(golden.pipelines.pipelines) == 7
