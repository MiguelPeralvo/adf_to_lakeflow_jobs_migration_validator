"""Unit tests for Day 9 synthetic runner workflow."""

from dataclasses import replace

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite
from lakeflow_migration_validator.synthetic.runner import run_synthetic_workflow


def test_run_synthetic_workflow_reports_distribution_for_perfect_converter():
    suite = GroundTruthSuite.generate(count=8, difficulty="simple", max_activities=5)
    by_name = {pipeline.adf_json["name"]: pipeline.expected_snapshot for pipeline in suite.pipelines}

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        return by_name[adf_json["name"]]

    result = run_synthetic_workflow(convert_fn, suite=suite, threshold=90.0)

    assert result.report.total == 8
    assert result.report.below_threshold == 0
    assert result.failures == ()
    assert result.ccs_distribution["count"] == 8
    assert result.ccs_distribution["min"] >= 90.0


def test_run_synthetic_workflow_triages_expression_failures():
    suite = GroundTruthSuite.generate(count=6, difficulty="simple", max_activities=5)
    by_name = {pipeline.adf_json["name"]: pipeline.expected_snapshot for pipeline in suite.pipelines}

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        expected = by_name[adf_json["name"]]
        return replace(expected, resolved_expressions=())

    result = run_synthetic_workflow(convert_fn, suite=suite, threshold=90.0)

    assert result.report.total == 6
    assert result.report.expression_mismatch_cases == 6
    assert len(result.failures) == 6
    assert all("expression_mismatch" in failure.reasons for failure in result.failures)
