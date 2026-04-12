"""Unit tests for DSPy judge calibration with ManualCalibrator fallback."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from lakeflow_migration_validator.optimization.judge_optimizer import (
    CalibrationPair,
    JudgeOptimizer,
    ManualCalibrator,
    _select_diverse_examples,
    create_calibrator,
    load_calibration_pairs,
)


# ---------------------------------------------------------------------------
# Stub provider for tests — no real LLM calls
# ---------------------------------------------------------------------------


class _StubProvider:
    """Mimics JudgeProvider without making network calls."""

    def __init__(self, score: float = 0.85):
        self._score = score
        self.calls: list[dict] = []

    def judge(self, prompt: str, model: str | None = None):
        self.calls.append({"prompt": prompt, "model": model})
        return {"score": self._score, "reasoning": "stub"}


# ---------------------------------------------------------------------------
# CalibrationPair format tests
# ---------------------------------------------------------------------------


class TestCalibrationPairFormat:
    """Verify calibration pair schema and loading."""

    def test_calibration_pair_has_required_fields(self):
        pair = CalibrationPair(
            adf_expression="@add(1, 2)",
            python_code="(1 + 2)",
            human_score=1.0,
            category="math",
            notes="perfect",
        )
        assert pair.adf_expression == "@add(1, 2)"
        assert pair.python_code == "(1 + 2)"
        assert pair.human_score == 1.0
        assert pair.category == "math"
        assert pair.notes == "perfect"

    def test_calibration_pair_as_example_dict(self):
        pair = CalibrationPair(
            adf_expression="@toUpper('x')",
            python_code="str('x').upper()",
            human_score=0.9,
        )
        d = pair.as_example_dict()
        assert d == {
            "input": "@toUpper('x')",
            "output": "str('x').upper()",
            "score": 0.9,
        }

    def test_calibration_pair_defaults(self):
        pair = CalibrationPair(
            adf_expression="@x",
            python_code="x",
            human_score=0.5,
        )
        assert pair.category == ""
        assert pair.notes == ""

    def test_load_calibration_pairs_from_file(self, tmp_path: Path):
        path = tmp_path / "cal.json"
        path.write_text(
            json.dumps(
                {
                    "calibration_pairs": [
                        {
                            "adf_expression": "@add(1,2)",
                            "python_code": "(1 + 2)",
                            "human_score": 1.0,
                            "category": "math",
                            "notes": "perfect",
                        },
                        {
                            "adf_expression": "@div(9,2)",
                            "python_code": "(9 / 2)",
                            "human_score": 0.5,
                            "category": "math",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        pairs = load_calibration_pairs(path)

        assert len(pairs) == 2
        assert pairs[0].adf_expression == "@add(1,2)"
        assert pairs[0].human_score == 1.0
        assert pairs[0].category == "math"
        assert pairs[1].human_score == 0.5
        assert pairs[1].notes == ""

    def test_load_calibration_pairs_empty_file(self, tmp_path: Path):
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"calibration_pairs": []}), encoding="utf-8")

        pairs = load_calibration_pairs(path)

        assert pairs == []

    def test_load_golden_set_calibration_pairs(self):
        """Verify the actual golden_sets/calibration_pairs.json is valid."""
        golden_path = Path(__file__).resolve().parents[3] / "golden_sets" / "calibration_pairs.json"
        if not golden_path.exists():
            pytest.skip("calibration_pairs.json not found")

        pairs = load_calibration_pairs(golden_path)

        assert len(pairs) >= 20
        for pair in pairs:
            assert pair.adf_expression, "adf_expression must not be empty"
            assert pair.python_code, "python_code must not be empty"
            assert 0.0 <= pair.human_score <= 1.0, f"human_score {pair.human_score} out of [0, 1] range"
            assert pair.category, "category should be set for golden data"

    def test_golden_set_has_score_diversity(self):
        """Golden set must include low, mid, and high scores for calibration."""
        golden_path = Path(__file__).resolve().parents[3] / "golden_sets" / "calibration_pairs.json"
        if not golden_path.exists():
            pytest.skip("calibration_pairs.json not found")

        pairs = load_calibration_pairs(golden_path)
        scores = [p.human_score for p in pairs]

        assert any(s < 0.3 for s in scores), "Need at least one low-score pair"
        assert any(0.3 <= s <= 0.7 for s in scores), "Need at least one mid-score pair"
        assert any(s > 0.9 for s in scores), "Need at least one high-score pair"


# ---------------------------------------------------------------------------
# ManualCalibrator tests
# ---------------------------------------------------------------------------


class TestManualCalibrator:
    """ManualCalibrator loads examples and produces improved judge."""

    @pytest.fixture()
    def sample_pairs(self) -> list[CalibrationPair]:
        return [
            CalibrationPair("@add(1,2)", "(1 + 2)", 1.0, "math"),
            CalibrationPair("@div(9,2)", "(9 / 2)", 0.5, "math"),
            CalibrationPair("@toUpper('x')", "'x'.upper()", 0.9, "string"),
            CalibrationPair("@utcNow()", "datetime.now()", 0.4, "datetime"),
            CalibrationPair("@concat('a','b','c')", "str('a')+str('b')", 0.3, "string"),
            CalibrationPair("@equals(1,1)", "(1 == 1)", 1.0, "logical"),
        ]

    def test_manual_calibrator_loads_pairs(self, sample_pairs):
        cal = ManualCalibrator(sample_pairs)
        assert cal.calibration_pairs == sample_pairs

    def test_manual_calibrator_from_file(self, tmp_path: Path):
        path = tmp_path / "cal.json"
        path.write_text(
            json.dumps(
                {
                    "calibration_pairs": [
                        {
                            "adf_expression": "@add(1,2)",
                            "python_code": "(1 + 2)",
                            "human_score": 1.0,
                            "category": "math",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        cal = ManualCalibrator.from_file(path)

        assert len(cal.calibration_pairs) == 1
        assert cal.calibration_pairs[0].human_score == 1.0

    def test_manual_calibrator_selects_examples(self, sample_pairs):
        cal = ManualCalibrator(sample_pairs, max_examples=4)
        examples = cal.select_examples()

        assert len(examples) == 4
        # Each example must be a dict with input, output, score
        for ex in examples:
            assert "input" in ex
            assert "output" in ex
            assert "score" in ex
            assert isinstance(ex["score"], float)

    def test_manual_calibrator_selects_all_when_fewer_than_max(self, sample_pairs):
        cal = ManualCalibrator(sample_pairs, max_examples=20)
        examples = cal.select_examples()
        assert len(examples) == len(sample_pairs)

    def test_manual_calibrator_returns_empty_for_no_pairs(self):
        cal = ManualCalibrator([])
        examples = cal.select_examples()
        assert examples == ()

    def test_manual_calibrator_produces_optimized_judge(self, sample_pairs):
        provider = _StubProvider()
        cal = ManualCalibrator(sample_pairs, max_examples=5)
        judge = cal.to_optimized_judge(provider, threshold=0.75, model="chatgpt-5-4")

        assert judge.name == "semantic_equivalence"
        assert judge.threshold == 0.75
        assert judge.model == "chatgpt-5-4"
        assert 1 <= len(judge.calibration_examples) <= 5
        # Criteria should be the improved calibrated version
        assert "Type coercion" in judge.criteria
        assert "Edge cases" in judge.criteria

    def test_optimized_judge_evaluates_successfully(self, sample_pairs):
        provider = _StubProvider(score=0.88)
        cal = ManualCalibrator(sample_pairs)
        judge = cal.to_optimized_judge(provider)

        result = judge.evaluate("@add(1,2)", "(1 + 2)")

        assert result.score == 0.88
        assert result.passed is True
        assert len(provider.calls) == 1

    def test_optimized_judge_prompt_includes_calibration_examples(self, sample_pairs):
        provider = _StubProvider()
        cal = ManualCalibrator(sample_pairs, max_examples=3)
        judge = cal.to_optimized_judge(provider)

        judge.evaluate("@test", "test")
        prompt = provider.calls[0]["prompt"]

        assert "Examples:" in prompt
        assert "ADF Expression" in prompt
        assert "Python Translation" in prompt

    def test_select_diverse_examples_includes_score_range(self):
        pairs = [
            CalibrationPair("@a", "a", 1.0, "cat_a"),
            CalibrationPair("@b", "b", 0.9, "cat_b"),
            CalibrationPair("@c", "c", 0.5, "cat_c"),
            CalibrationPair("@d", "d", 0.2, "cat_d"),
            CalibrationPair("@e", "e", 0.0, "cat_e"),
        ]
        examples = _select_diverse_examples(pairs, max_examples=4)

        scores = [ex["score"] for ex in examples]
        # Must include at least one high and one low score
        assert any(s >= 0.9 for s in scores), "Should include a high-score example"
        assert any(s <= 0.3 for s in scores), "Should include a low-score example"


# ---------------------------------------------------------------------------
# JudgeOptimizer tests (DSPy not installed)
# ---------------------------------------------------------------------------


class TestJudgeOptimizerWithoutDSPy:
    """JudgeOptimizer must raise a helpful ImportError when DSPy is absent."""

    def test_optimizer_raises_import_error_without_dspy(self):
        """Instantiating JudgeOptimizer without DSPy must fail with guidance."""
        provider = _StubProvider()

        # Ensure dspy is not importable (it should not be in this env)
        with mock.patch.dict(sys.modules, {"dspy": None}):
            with pytest.raises(ImportError, match="DSPy 3.x is required"):
                JudgeOptimizer(provider)

    def test_import_error_mentions_manual_calibrator(self):
        provider = _StubProvider()

        with mock.patch.dict(sys.modules, {"dspy": None}):
            with pytest.raises(ImportError, match="ManualCalibrator"):
                JudgeOptimizer(provider)

    def test_import_error_mentions_pip_install(self):
        provider = _StubProvider()

        with mock.patch.dict(sys.modules, {"dspy": None}):
            with pytest.raises(ImportError, match="pip install dspy-ai"):
                JudgeOptimizer(provider)


# ---------------------------------------------------------------------------
# create_calibrator fallback
# ---------------------------------------------------------------------------


class TestCreateCalibrator:
    """create_calibrator should fall back to ManualCalibrator without DSPy."""

    def test_returns_manual_calibrator_without_dspy(self, tmp_path: Path):
        path = tmp_path / "cal.json"
        path.write_text(
            json.dumps(
                {
                    "calibration_pairs": [
                        {
                            "adf_expression": "@add(1,2)",
                            "python_code": "(1 + 2)",
                            "human_score": 1.0,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        with mock.patch.dict(sys.modules, {"dspy": None}):
            cal = create_calibrator(path, provider=_StubProvider())

        assert isinstance(cal, ManualCalibrator)

    def test_returns_manual_calibrator_when_no_provider(self, tmp_path: Path):
        path = tmp_path / "cal.json"
        path.write_text(
            json.dumps({"calibration_pairs": []}),
            encoding="utf-8",
        )

        cal = create_calibrator(path, provider=None)

        assert isinstance(cal, ManualCalibrator)
