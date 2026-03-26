"""Regression baseline checks for Week 3 batch evaluation."""

from __future__ import annotations

import json

import pytest

from lakeflow_migration_validator import evaluate_batch
from lakeflow_migration_validator.golden_set import GoldenSet, load_pipeline_golden_set, materialize_golden_sets
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite


def test_evaluate_batch_accepts_ground_truth_suite():
    suite = GroundTruthSuite.generate(count=5, difficulty="simple")
    by_name = {pipeline.adf_json["name"]: pipeline.expected_snapshot for pipeline in suite.pipelines}

    def convert_fn(adf_json):
        return by_name[adf_json["name"]]

    report = evaluate_batch(suite, convert_fn, threshold=90.0)

    assert report.total == 5
    assert report.below_threshold == 0
    assert report.min_score >= 90.0


def test_evaluate_batch_accepts_golden_set(tmp_path):
    paths = materialize_golden_sets(output_dir=str(tmp_path), expression_count=8, pipeline_count=6, difficulty="simple")
    golden = GoldenSet.load(paths.expressions_path, paths.pipelines_path)
    by_name = {pipeline.adf_json["name"]: pipeline.expected_snapshot for pipeline in golden.pipelines.pipelines}

    def convert_fn(adf_json):
        return by_name[adf_json["name"]]

    report = evaluate_batch(golden, convert_fn)

    assert report.total == 6
    assert report.expression_mismatch_cases == 0


def test_evaluate_batch_raises_for_unknown_input_type():
    with pytest.raises(TypeError, match="GroundTruthSuite or GoldenSet"):
        evaluate_batch(object(), lambda _adf: None)


def test_regression_scores_do_not_regress_from_curated_baseline():
    with open("golden_sets/regression_pipelines.json", encoding="utf-8") as handle:
        baseline_payload = json.load(handle)

    source_suite = load_pipeline_golden_set("golden_sets/pipelines.json")
    allowed_names = {item["pipeline_name"] for item in baseline_payload["cases"]}
    curated = tuple(p for p in source_suite.pipelines if p.adf_json["name"] in allowed_names)
    suite = GroundTruthSuite(pipelines=curated)

    by_name = {pipeline.adf_json["name"]: pipeline.expected_snapshot for pipeline in suite.pipelines}

    def convert_fn(adf_json):
        return by_name[adf_json["name"]]

    report = evaluate_batch(suite, convert_fn, threshold=90.0)

    assert report.total == baseline_payload["fixture_count"]

    case_ranges = {item["pipeline_name"]: item for item in baseline_payload["cases"]}
    for case in report.cases:
        limits = case_ranges[case.pipeline_name]
        assert limits["min_score"] <= case.score <= limits["max_score"]

    baseline = baseline_payload["baseline"]
    distribution = report.ccs_distribution()
    assert report.mean_score >= baseline["mean_score"]
    assert report.min_score >= baseline["min_score"]
    assert distribution["p10"] >= baseline["p10"]
    assert distribution["p90"] >= baseline["p90"]
