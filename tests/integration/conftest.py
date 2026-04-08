"""Integration fixtures for score-gate validation."""

from __future__ import annotations

import os

import pytest

from lakeflow_migration_validator import evaluate
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.scorecard import Scorecard


@pytest.fixture
def score_gate():
    """Return a scorer that optionally enforces minimum CCS in integration tests."""

    def _score(snapshot: ConversionSnapshot) -> Scorecard:
        enabled = os.getenv("LMV_ENABLE_SCORE_GATE", "0") == "1"
        min_score = float(os.getenv("LMV_MIN_SCORE", "70"))
        scorecard = evaluate(snapshot)
        if enabled and scorecard.score < min_score:
            pytest.fail(f"Integration score gate failed: score={scorecard.score:.2f} < min={min_score:.2f}")
        return scorecard

    return _score
