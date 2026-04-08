"""Unit tests for the structured fix-suggestion engine."""

from __future__ import annotations

from lakeflow_migration_validator.dimensions import DimensionResult
from lakeflow_migration_validator.optimization.fix_suggester import (
    FixSuggester,
    FixSuggestion,
    _DEFAULT_WEIGHTS,
)
from lakeflow_migration_validator.scorecard import Scorecard
from tests.unit.validation.conftest import make_snapshot


class _MockJudge:
    def judge(self, prompt: str, model: str | None = None) -> dict:
        return {"score": 0.5, "reasoning": f"Mock: {prompt[:30]}"}


def _make_weights(*names: str) -> dict[str, float]:
    """Return a weight dict for the given dimension names, all equal."""
    return {name: _DEFAULT_WEIGHTS.get(name, 0.10) for name in names}


def test_all_passing_returns_empty():
    """When every dimension scores 1.0, there is nothing to fix."""
    weights = _make_weights("activity_coverage", "expression_coverage")
    results = {
        "activity_coverage": DimensionResult(name="activity_coverage", score=1.0, passed=True, details={}),
        "expression_coverage": DimensionResult(name="expression_coverage", score=1.0, passed=True, details={}),
    }
    scorecard = Scorecard.compute(weights, results)

    suggester = FixSuggester(_MockJudge(), weights=weights)
    suggestions = suggester.suggest(make_snapshot(), scorecard)

    assert suggestions == []


def test_one_failing_dimension():
    """A single imperfect dimension yields exactly one suggestion at priority 1."""
    weights = _make_weights("activity_coverage", "expression_coverage")
    results = {
        "activity_coverage": DimensionResult(name="activity_coverage", score=0.5, passed=False, details={}),
        "expression_coverage": DimensionResult(name="expression_coverage", score=1.0, passed=True, details={}),
    }
    scorecard = Scorecard.compute(weights, results)

    suggester = FixSuggester(_MockJudge(), weights=weights)
    suggestions = suggester.suggest(make_snapshot(), scorecard)

    assert len(suggestions) == 1
    s = suggestions[0]
    assert isinstance(s, FixSuggestion)
    assert s.dimension == "activity_coverage"
    assert s.score == 0.5
    assert s.priority == 1
    assert s.diagnosis.startswith("Mock:")
    assert s.suggestion.startswith("Mock:")


def test_multiple_failing_sorted_by_impact():
    """Dimensions are ranked by (1 - score) * weight descending."""
    weights = {
        "activity_coverage": 0.25,
        "expression_coverage": 0.20,
        "notebook_validity": 0.15,
    }
    results = {
        # impact = (1 - 0.8) * 0.25 = 0.05
        "activity_coverage": DimensionResult(name="activity_coverage", score=0.8, passed=True, details={}),
        # impact = (1 - 0.3) * 0.20 = 0.14
        "expression_coverage": DimensionResult(name="expression_coverage", score=0.3, passed=False, details={}),
        # impact = (1 - 0.2) * 0.15 = 0.12
        "notebook_validity": DimensionResult(name="notebook_validity", score=0.2, passed=False, details={}),
    }
    scorecard = Scorecard.compute(weights, results)

    suggester = FixSuggester(_MockJudge(), weights=weights)
    suggestions = suggester.suggest(make_snapshot(), scorecard)

    assert len(suggestions) == 3
    assert suggestions[0].dimension == "expression_coverage"
    assert suggestions[0].priority == 1
    assert suggestions[1].dimension == "notebook_validity"
    assert suggestions[1].priority == 2
    assert suggestions[2].dimension == "activity_coverage"
    assert suggestions[2].priority == 3


def test_suggest_top_returns_highest_priority():
    """suggest_top is a convenience wrapper for the #1 priority suggestion."""
    weights = {
        "activity_coverage": 0.25,
        "expression_coverage": 0.20,
    }
    results = {
        "activity_coverage": DimensionResult(name="activity_coverage", score=0.4, passed=False, details={}),
        "expression_coverage": DimensionResult(name="expression_coverage", score=0.5, passed=False, details={}),
    }
    scorecard = Scorecard.compute(weights, results)

    suggester = FixSuggester(_MockJudge(), weights=weights)
    top = suggester.suggest_top(make_snapshot(), scorecard)

    assert top is not None
    assert top.priority == 1
    # (1 - 0.4) * 0.25 = 0.15 > (1 - 0.5) * 0.20 = 0.10
    assert top.dimension == "activity_coverage"


def test_suggest_top_returns_none_when_all_pass():
    """suggest_top returns None when there are no actionable suggestions."""
    weights = _make_weights("activity_coverage")
    results = {
        "activity_coverage": DimensionResult(name="activity_coverage", score=1.0, passed=True, details={}),
    }
    scorecard = Scorecard.compute(weights, results)

    suggester = FixSuggester(_MockJudge(), weights=weights)
    assert suggester.suggest_top(make_snapshot(), scorecard) is None


def test_mock_judge_returns_expected_format():
    """Verify the mock judge returns the expected structure used by FixSuggester."""
    judge = _MockJudge()
    response = judge.judge("test prompt for validation", model=None)
    assert "score" in response
    assert "reasoning" in response
    assert isinstance(response["score"], float)
    assert isinstance(response["reasoning"], str)


def test_max_three_suggestions():
    """Even with many failing dimensions, at most 3 suggestions are returned."""
    weights = {
        "activity_coverage": 0.25,
        "expression_coverage": 0.20,
        "dependency_preservation": 0.15,
        "notebook_validity": 0.15,
        "parameter_completeness": 0.10,
    }
    results = {name: DimensionResult(name=name, score=0.1, passed=False, details={}) for name in weights}
    scorecard = Scorecard.compute(weights, results)

    suggester = FixSuggester(_MockJudge(), weights=weights)
    suggestions = suggester.suggest(make_snapshot(), scorecard)

    assert len(suggestions) == 3
    assert [s.priority for s in suggestions] == [1, 2, 3]


def test_zero_weight_dimensions_excluded():
    """Dimensions with weight 0 never produce suggestions, even if score < 1.0."""
    weights = {
        "activity_coverage": 0.25,
        "semantic_equivalence": 0.0,
    }
    results = {
        "activity_coverage": DimensionResult(name="activity_coverage", score=1.0, passed=True, details={}),
        "semantic_equivalence": DimensionResult(name="semantic_equivalence", score=0.0, passed=False, details={}),
    }
    scorecard = Scorecard.compute(weights, results)

    suggester = FixSuggester(_MockJudge(), weights=weights)
    suggestions = suggester.suggest(make_snapshot(), scorecard)

    assert suggestions == []
