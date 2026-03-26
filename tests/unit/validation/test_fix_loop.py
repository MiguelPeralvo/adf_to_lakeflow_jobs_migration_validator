"""Unit tests for harness fix-loop iteration."""

from __future__ import annotations

from lakeflow_migration_validator.dimensions import DimensionResult
from lakeflow_migration_validator.harness.fix_loop import FixLoop
from lakeflow_migration_validator.scorecard import Scorecard
from tests.unit.validation.conftest import make_snapshot


class _Provider:
    def __init__(self):
        self.calls = []

    def judge(self, prompt: str, model: str | None = None):
        self.calls.append((prompt, model))
        if "diagnose" in prompt.lower():
            return {"score": 0.4, "reasoning": "missing parameter wiring"}
        return {"score": 0.6, "reasoning": "add dbutils.widgets.get('p') and map defaults"}


def _make_scorecard() -> Scorecard:
    results = {
        "z_dim": DimensionResult(name="z_dim", score=0.1, passed=False, details={}),
        "a_dim": DimensionResult(name="a_dim", score=0.1, passed=False, details={}),
        "b_dim": DimensionResult(name="b_dim", score=0.8, passed=True, details={}),
    }
    return Scorecard(weights={name: 1.0 for name in results}, results=results, score=33.3)


def test_fix_loop_selects_lowest_dimension_with_deterministic_tie_break():
    provider = _Provider()
    loop = FixLoop(judge_provider=provider, max_iterations=1)

    _updated_snapshot, _updated_scorecard, suggestions = loop.iterate(make_snapshot(), _make_scorecard())

    assert suggestions[0]["dimension"] == "a_dim"
    assert suggestions[0]["diagnosis"] == "missing parameter wiring"
    assert suggestions[0]["suggestion"] == "add dbutils.widgets.get('p') and map defaults"
    assert len(provider.calls) == 2


def test_fix_loop_is_noop_without_advance_callback():
    provider = _Provider()
    snapshot = make_snapshot()
    scorecard = _make_scorecard()

    loop = FixLoop(judge_provider=provider, max_iterations=3)
    updated_snapshot, updated_scorecard, suggestions = loop.iterate(snapshot, scorecard)

    assert updated_snapshot == snapshot
    assert updated_scorecard == scorecard
    assert len(suggestions) == 1


def test_fix_loop_runs_multiple_iterations_with_advance_callback():
    provider = _Provider()
    scorecard = _make_scorecard()
    snapshot = make_snapshot()
    calls = []

    def advance(_snapshot, _scorecard, suggestion, iteration):
        calls.append((suggestion["dimension"], iteration))
        improved = Scorecard(
            weights=scorecard.weights,
            results={
                "a_dim": DimensionResult(name="a_dim", score=1.0, passed=True, details={}),
                "z_dim": DimensionResult(name="z_dim", score=1.0, passed=True, details={}),
                "b_dim": DimensionResult(name="b_dim", score=1.0, passed=True, details={}),
            },
            score=100.0,
        )
        return _snapshot, improved

    loop = FixLoop(judge_provider=provider, max_iterations=3, advance_fn=advance)

    _updated_snapshot, updated_scorecard, suggestions = loop.iterate(snapshot, scorecard)

    assert len(calls) == 1
    assert len(suggestions) == 1
    assert updated_scorecard.score == 100.0
