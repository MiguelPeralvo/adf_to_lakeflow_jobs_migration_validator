"""Integration-style tests for the score-gate fixture contract."""

from __future__ import annotations

import pytest

from lakeflow_migration_validator.contract import ConversionSnapshot, NotebookSnapshot, SecretRef, TaskSnapshot


def _high_quality_snapshot() -> ConversionSnapshot:
    return ConversionSnapshot(
        tasks=(TaskSnapshot(task_key="task_a", is_placeholder=False),),
        notebooks=(NotebookSnapshot(file_path="/n.py", content="x=1"),),
        secrets=(SecretRef(scope="s", key="k"),),
        parameters=(),
        dependencies=(),
        not_translatable=(),
        resolved_expressions=(),
    )


def _low_quality_snapshot() -> ConversionSnapshot:
    return ConversionSnapshot(
        tasks=(
            TaskSnapshot(task_key="task_a", is_placeholder=True),
            TaskSnapshot(task_key="task_b", is_placeholder=True),
        ),
        notebooks=(NotebookSnapshot(file_path="/n.py", content="if True print('bad')"),),
        secrets=(),
        parameters=(),
        dependencies=(),
        not_translatable=(
            {"message": "unsupported expression"},
            {"message": "unsupported expression"},
        ),
        resolved_expressions=(),
    )


@pytest.mark.integration
def test_score_gate_passes_when_enabled_and_score_is_high(monkeypatch, score_gate):
    monkeypatch.setenv("LMV_ENABLE_SCORE_GATE", "1")
    monkeypatch.setenv("LMV_MIN_SCORE", "70")

    gated = score_gate
    result = gated(_high_quality_snapshot())

    assert result.score >= 70.0


@pytest.mark.integration
def test_score_gate_fails_when_enabled_and_score_is_low(monkeypatch, score_gate):
    monkeypatch.setenv("LMV_ENABLE_SCORE_GATE", "1")
    monkeypatch.setenv("LMV_MIN_SCORE", "70")

    with pytest.raises(pytest.fail.Exception, match="Integration score gate failed"):
        score_gate(_low_quality_snapshot())


@pytest.mark.integration
def test_score_gate_is_noop_when_disabled(monkeypatch, score_gate):
    monkeypatch.setenv("LMV_ENABLE_SCORE_GATE", "0")

    result = score_gate(_low_quality_snapshot())

    assert result.score < 70.0
