"""Integration-style unit checks for Week 2 Day 9/10 flow."""

from dataclasses import replace

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.golden_set import materialize_golden_sets
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite
from lakeflow_migration_validator.synthetic.runner import run_synthetic_workflow


def test_day9_workflow_handles_50_pipeline_suite():
    suite = GroundTruthSuite.generate(count=50, difficulty="mixed", max_activities=6)
    by_name = {pipeline.adf_json["name"]: pipeline.expected_snapshot for pipeline in suite.pipelines}

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        expected = by_name[adf_json["name"]]
        return replace(expected, not_translatable=())

    result = run_synthetic_workflow(convert_fn, suite=suite, threshold=90.0)

    assert result.report.total == 50
    assert result.ccs_distribution["count"] == 50


def test_day10_materialization_supports_default_week2_sizes(tmp_path):
    paths = materialize_golden_sets(
        output_dir=str(tmp_path),
        expression_count=120,
        pipeline_count=50,
        difficulty="medium",
        max_activities=10,
    )

    suite = GroundTruthSuite.from_json(paths.pipelines_path)
    assert len(suite.pipelines) == 50
