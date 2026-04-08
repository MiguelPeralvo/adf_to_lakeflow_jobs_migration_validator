"""TDD tests for the Scorecard aggregation."""

from lakeflow_migration_validator.dimensions import DimensionResult
from lakeflow_migration_validator.scorecard import Scorecard


def test_perfect_scores_produce_100():
    """All dimensions at 1.0 with any weights -> score 100."""
    results = {
        "a": DimensionResult(name="a", score=1.0, passed=True),
        "b": DimensionResult(name="b", score=1.0, passed=True),
    }
    sc = Scorecard.compute({"a": 0.5, "b": 0.5}, results)
    assert sc.score == 100.0


def test_zero_scores_produce_0():
    """All dimensions at 0.0 -> score 0."""
    results = {
        "a": DimensionResult(name="a", score=0.0, passed=False),
        "b": DimensionResult(name="b", score=0.0, passed=False),
    }
    sc = Scorecard.compute({"a": 0.5, "b": 0.5}, results)
    assert sc.score == 0.0


def test_weighted_aggregation_is_correct():
    """Specific dimension scores with known weights produce expected aggregate."""
    results = {
        "a": DimensionResult(name="a", score=0.8, passed=True),
        "b": DimensionResult(name="b", score=0.6, passed=True),
    }
    sc = Scorecard.compute({"a": 0.75, "b": 0.25}, results)
    expected = ((0.8 * 0.75 + 0.6 * 0.25) / 1.0) * 100
    assert abs(sc.score - expected) < 0.01


def test_label_high_confidence_above_90():
    """Score >= 90 -> 'HIGH_CONFIDENCE'."""
    results = {"a": DimensionResult(name="a", score=0.95, passed=True)}
    sc = Scorecard.compute({"a": 1.0}, results)
    assert sc.label == "HIGH_CONFIDENCE"


def test_label_review_recommended_70_to_89():
    """Score 70-89 -> 'REVIEW_RECOMMENDED'."""
    results = {"a": DimensionResult(name="a", score=0.8, passed=True)}
    sc = Scorecard.compute({"a": 1.0}, results)
    assert sc.label == "REVIEW_RECOMMENDED"


def test_label_manual_intervention_below_70():
    """Score < 70 -> 'MANUAL_INTERVENTION'."""
    results = {"a": DimensionResult(name="a", score=0.5, passed=False)}
    sc = Scorecard.compute({"a": 1.0}, results)
    assert sc.label == "MANUAL_INTERVENTION"


def test_all_passed_true_when_all_above_threshold():
    """all_passed is True when every dimension passes its threshold."""
    results = {
        "a": DimensionResult(name="a", score=0.9, passed=True),
        "b": DimensionResult(name="b", score=0.8, passed=True),
    }
    sc = Scorecard.compute({"a": 0.5, "b": 0.5}, results)
    assert sc.all_passed is True


def test_all_passed_false_when_any_below_threshold():
    """all_passed is False when any dimension is below its threshold."""
    results = {
        "a": DimensionResult(name="a", score=0.9, passed=True),
        "b": DimensionResult(name="b", score=0.3, passed=False),
    }
    sc = Scorecard.compute({"a": 0.5, "b": 0.5}, results)
    assert sc.all_passed is False


def test_to_dict_is_serializable():
    """to_dict() returns a JSON-serializable dict."""
    import json

    results = {"a": DimensionResult(name="a", score=0.9, passed=True)}
    sc = Scorecard.compute({"a": 1.0}, results)
    d = sc.to_dict()
    json.dumps(d)  # should not raise
    assert "score" in d
    assert "label" in d
    assert "dimensions" in d
