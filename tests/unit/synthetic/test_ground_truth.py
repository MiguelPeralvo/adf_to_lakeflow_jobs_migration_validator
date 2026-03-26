"""Unit tests for synthetic ground-truth suite orchestration."""

from dataclasses import replace

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite


def test_generate_builds_requested_number_of_pipelines():
    suite = GroundTruthSuite.generate(count=7, difficulty="simple", max_activities=5)

    assert len(suite.pipelines) == 7


def test_json_roundtrip_preserves_pipeline_count(tmp_path):
    suite = GroundTruthSuite.generate(count=5)
    path = tmp_path / "suite.json"

    suite.to_json(str(path))
    loaded = GroundTruthSuite.from_json(str(path))

    assert len(loaded.pipelines) == len(suite.pipelines)
    assert loaded.pipelines[0].description == suite.pipelines[0].description


def test_evaluate_converter_reports_perfect_when_converter_matches_expected_snapshot():
    suite = GroundTruthSuite.generate(count=4, difficulty="simple")
    by_name = {
        pipeline.adf_json["name"]: pipeline.expected_snapshot
        for pipeline in suite.pipelines
    }

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        return by_name[adf_json["name"]]

    report = suite.evaluate_converter(convert_fn)

    assert report.total == 4
    assert report.below_threshold == 0
    assert report.expression_mismatch_cases == 0
    assert report.min_score >= 90.0


def test_evaluate_converter_detects_expression_mismatches():
    suite = GroundTruthSuite.generate(count=3, difficulty="simple")
    by_name = {
        pipeline.adf_json["name"]: pipeline.expected_snapshot
        for pipeline in suite.pipelines
    }

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        expected = by_name[adf_json["name"]]
        return replace(expected, resolved_expressions=())

    report = suite.evaluate_converter(convert_fn)

    assert report.total == 3
    assert report.expression_mismatch_cases == 3
    assert all(case.expression_mismatches for case in report.cases)
