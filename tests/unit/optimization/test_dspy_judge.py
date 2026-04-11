"""Unit tests for DSPy semantic equivalence judge module.

Tests work without DSPy installed — all DSPy functionality is mocked.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from lakeflow_migration_validator.optimization.dspy_judge import (
    FAILURE_MODES,
    AgreementMetric,
    DSPyJudgeOptimizer,
    OptimizationResult,
    _validate_failure_modes,
    evaluate_judge_quality,
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
# Failure modes taxonomy tests
# ---------------------------------------------------------------------------


class TestFailureModes:
    """Verify failure_modes enum consistency."""

    def test_failure_modes_is_tuple(self):
        assert isinstance(FAILURE_MODES, tuple)

    def test_failure_modes_count(self):
        assert len(FAILURE_MODES) == 7

    def test_semantically_correct_is_included(self):
        assert "semantically_correct" in FAILURE_MODES

    def test_all_expected_modes_present(self):
        expected = {
            "type_coercion_missing",
            "function_mapping_wrong",
            "nesting_order_broken",
            "parameter_reference_broken",
            "null_handling_missing",
            "edge_case_unhandled",
            "semantically_correct",
        }
        assert set(FAILURE_MODES) == expected

    def test_validate_failure_modes_filters_invalid(self):
        result = _validate_failure_modes(["type_coercion_missing", "bogus_mode", "nesting_order_broken"])
        assert result == ["type_coercion_missing", "nesting_order_broken"]

    def test_validate_failure_modes_empty_input(self):
        assert _validate_failure_modes([]) == []

    def test_validate_failure_modes_all_valid(self):
        result = _validate_failure_modes(list(FAILURE_MODES))
        assert result == list(FAILURE_MODES)

    def test_validate_failure_modes_all_invalid(self):
        result = _validate_failure_modes(["foo", "bar", "baz"])
        assert result == []


# ---------------------------------------------------------------------------
# AgreementMetric tests
# ---------------------------------------------------------------------------


class TestAgreementMetric:
    """AgreementMetric computes correct agreement scores."""

    @pytest.fixture()
    def metric(self) -> AgreementMetric:
        return AgreementMetric()

    def test_perfect_agreement(self, metric):
        example = SimpleNamespace(human_score=0.9, category="string")
        prediction = SimpleNamespace(score=0.9, failure_modes=[])

        result = metric(example, prediction)

        assert result == pytest.approx(1.0)

    def test_complete_disagreement(self, metric):
        example = SimpleNamespace(human_score=1.0, category="math")
        prediction = SimpleNamespace(score=0.0, failure_modes=[])

        result = metric(example, prediction)

        assert result == pytest.approx(0.0)

    def test_partial_disagreement(self, metric):
        example = SimpleNamespace(human_score=0.8, category="string")
        prediction = SimpleNamespace(score=0.5, failure_modes=[])

        result = metric(example, prediction)

        assert result == pytest.approx(0.7)

    def test_bonus_for_matching_failure_category(self, metric):
        # category="string" maps to "type_coercion_missing"
        # human_score < 0.8 triggers bonus check
        example = SimpleNamespace(human_score=0.5, category="string")
        prediction = SimpleNamespace(score=0.5, failure_modes=["type_coercion_missing"])

        result = metric(example, prediction)

        # Base: 1.0 - |0.5 - 0.5| = 1.0, bonus +0.1, capped at 1.0
        assert result == pytest.approx(1.0)

    def test_bonus_only_when_human_score_below_threshold(self, metric):
        # human_score >= 0.8 means no bonus even if modes match
        example = SimpleNamespace(human_score=0.9, category="string")
        prediction = SimpleNamespace(score=0.9, failure_modes=["type_coercion_missing"])

        result = metric(example, prediction)

        # No bonus: human_score >= 0.8
        assert result == pytest.approx(1.0)

    def test_bonus_with_imperfect_score_match(self, metric):
        # category="nested" maps to "nesting_order_broken"
        example = SimpleNamespace(human_score=0.3, category="nested")
        prediction = SimpleNamespace(score=0.5, failure_modes=["nesting_order_broken"])

        result = metric(example, prediction)

        # Base: 1.0 - |0.3 - 0.5| = 0.8, bonus +0.1 = 0.9
        assert result == pytest.approx(0.9)

    def test_no_bonus_for_wrong_failure_mode(self, metric):
        example = SimpleNamespace(human_score=0.3, category="nested")
        prediction = SimpleNamespace(score=0.5, failure_modes=["type_coercion_missing"])

        result = metric(example, prediction)

        # Base: 0.8, no bonus
        assert result == pytest.approx(0.8)

    def test_handles_missing_attributes(self, metric):
        example = SimpleNamespace(human_score=0.7)
        prediction = SimpleNamespace(score=0.7)

        result = metric(example, prediction)

        assert result == pytest.approx(1.0)

    def test_handles_invalid_score_type(self, metric):
        example = SimpleNamespace(human_score="not_a_number", category="")
        prediction = SimpleNamespace(score="also_not", failure_modes=[])

        result = metric(example, prediction)

        # Both parse to 0.0, so agreement = 1.0 - |0 - 0| = 1.0
        assert result == pytest.approx(1.0)

    def test_failure_modes_as_comma_string(self, metric):
        example = SimpleNamespace(human_score=0.3, category="nested")
        prediction = SimpleNamespace(score=0.5, failure_modes="nesting_order_broken, type_coercion_missing")

        result = metric(example, prediction)

        # Base: 0.8, bonus +0.1 for matching nesting_order_broken
        assert result == pytest.approx(0.9)

    def test_trace_parameter_ignored(self, metric):
        example = SimpleNamespace(human_score=0.5, category="")
        prediction = SimpleNamespace(score=0.5, failure_modes=[])

        # trace should be ignored
        result = metric(example, prediction, trace="some_trace_value")

        assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# OptimizationResult dataclass tests
# ---------------------------------------------------------------------------


class TestOptimizationResult:
    """OptimizationResult is a frozen dataclass with correct fields."""

    def test_creation(self):
        result = OptimizationResult(
            train_agreement=0.85,
            dev_agreement=0.78,
            improvement_over_baseline=0.12,
            num_trials=20,
            best_demos=({"adf_expression": "@x", "python_code": "x", "score": 1.0},),
            optimized_instructions="Evaluate carefully.",
        )

        assert result.train_agreement == 0.85
        assert result.dev_agreement == 0.78
        assert result.improvement_over_baseline == 0.12
        assert result.num_trials == 20
        assert len(result.best_demos) == 1
        assert result.optimized_instructions == "Evaluate carefully."

    def test_frozen(self):
        result = OptimizationResult(
            train_agreement=0.85,
            dev_agreement=0.78,
            improvement_over_baseline=0.12,
            num_trials=20,
        )

        with pytest.raises(AttributeError):
            result.train_agreement = 0.99  # type: ignore[misc]

    def test_defaults(self):
        result = OptimizationResult(
            train_agreement=0.8,
            dev_agreement=0.7,
            improvement_over_baseline=0.1,
            num_trials=10,
        )

        assert result.best_demos == ()
        assert result.optimized_instructions == ""

    def test_has_slots(self):
        assert hasattr(OptimizationResult, "__slots__")


# ---------------------------------------------------------------------------
# DSPyJudgeOptimizer tests — without DSPy
# ---------------------------------------------------------------------------


class TestDSPyJudgeOptimizerWithoutDSPy:
    """DSPyJudgeOptimizer must raise ImportError without DSPy."""

    def test_raises_import_error_without_dspy(self):
        provider = _StubProvider()

        with mock.patch.dict(sys.modules, {"dspy": None}):
            with mock.patch(
                "lakeflow_migration_validator.optimization.dspy_judge._HAS_DSPY",
                False,
            ):
                with pytest.raises(ImportError, match="DSPy 3.x is required"):
                    DSPyJudgeOptimizer(provider)

    def test_error_mentions_manual_calibrator(self):
        provider = _StubProvider()

        with mock.patch.dict(sys.modules, {"dspy": None}):
            with mock.patch(
                "lakeflow_migration_validator.optimization.dspy_judge._HAS_DSPY",
                False,
            ):
                with pytest.raises(ImportError, match="ManualCalibrator"):
                    DSPyJudgeOptimizer(provider)

    def test_error_mentions_pip_install(self):
        provider = _StubProvider()

        with mock.patch.dict(sys.modules, {"dspy": None}):
            with mock.patch(
                "lakeflow_migration_validator.optimization.dspy_judge._HAS_DSPY",
                False,
            ):
                with pytest.raises(ImportError, match="pip install dspy-ai"):
                    DSPyJudgeOptimizer(provider)


# ---------------------------------------------------------------------------
# DSPyJudgeOptimizer.to_judge — pre-optimize error
# ---------------------------------------------------------------------------


class TestDSPyJudgeOptimizerToJudge:
    """to_judge() must error if optimize() was never called."""

    def test_to_judge_before_optimize_raises(self):
        provider = _StubProvider()

        with mock.patch(
            "lakeflow_migration_validator.optimization.dspy_judge._HAS_DSPY",
            True,
        ):
            # Patch dspy import at module level so __init__ passes
            opt = object.__new__(DSPyJudgeOptimizer)
            opt._provider = provider
            opt._optimizer_name = "MIPROv2"
            opt._model = "claude-sonnet-4-6"
            opt._num_trials = 20
            opt._optimized_program = None
            opt._optimization_result = None
            opt._metric = AgreementMetric()

            with pytest.raises(RuntimeError, match="Call optimize"):
                opt.to_judge()


# ---------------------------------------------------------------------------
# evaluate_judge_quality tests
# ---------------------------------------------------------------------------


class TestEvaluateJudgeQuality:
    """evaluate_judge_quality works with a mock judge."""

    def _write_calibration_file(self, tmp_path: Path) -> Path:
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
                            "notes": "int div",
                        },
                        {
                            "adf_expression": "@toUpper('x')",
                            "python_code": "'x'.upper()",
                            "human_score": 0.9,
                            "category": "string",
                            "notes": "ok",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_returns_overall_and_per_category(self, tmp_path: Path):
        from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge

        provider = _StubProvider(score=0.8)
        judge = LLMJudge(
            name="test",
            criteria="test",
            input_template="{input} {output}",
            provider=provider,
        )

        cal_path = self._write_calibration_file(tmp_path)
        result = evaluate_judge_quality(judge, cal_path)

        assert "overall" in result
        assert "math" in result
        assert "string" in result

    def test_overall_is_mean_agreement(self, tmp_path: Path):
        from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge

        # Provider always returns 0.8
        provider = _StubProvider(score=0.8)
        judge = LLMJudge(
            name="test",
            criteria="test",
            input_template="{input} {output}",
            provider=provider,
        )

        cal_path = self._write_calibration_file(tmp_path)
        result = evaluate_judge_quality(judge, cal_path)

        # Agreements: 1-|1.0-0.8|=0.8, 1-|0.5-0.8|=0.7, 1-|0.9-0.8|=0.9
        expected_overall = (0.8 + 0.7 + 0.9) / 3
        assert result["overall"] == pytest.approx(expected_overall)

    def test_per_category_agreement(self, tmp_path: Path):
        from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge

        provider = _StubProvider(score=0.8)
        judge = LLMJudge(
            name="test",
            criteria="test",
            input_template="{input} {output}",
            provider=provider,
        )

        cal_path = self._write_calibration_file(tmp_path)
        result = evaluate_judge_quality(judge, cal_path)

        # math: mean(0.8, 0.7) = 0.75
        assert result["math"] == pytest.approx(0.75)
        # string: 0.9
        assert result["string"] == pytest.approx(0.9)

    def test_empty_calibration_returns_zero(self, tmp_path: Path):
        from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge

        provider = _StubProvider()
        judge = LLMJudge(
            name="test",
            criteria="test",
            input_template="{input} {output}",
            provider=provider,
        )

        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"calibration_pairs": []}), encoding="utf-8")

        result = evaluate_judge_quality(judge, path)

        assert result == {"overall": 0.0}

    def test_perfect_judge_gets_perfect_score(self, tmp_path: Path):
        """A judge that always matches human scores gets 1.0 agreement."""
        from lakeflow_migration_validator.dimensions.llm_judge import LLMJudge

        # Write a single pair with human_score=0.75
        path = tmp_path / "single.json"
        path.write_text(
            json.dumps(
                {
                    "calibration_pairs": [
                        {
                            "adf_expression": "@x",
                            "python_code": "x",
                            "human_score": 0.75,
                            "category": "math",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        provider = _StubProvider(score=0.75)
        judge = LLMJudge(
            name="test",
            criteria="test",
            input_template="{input} {output}",
            provider=provider,
        )

        result = evaluate_judge_quality(judge, path)

        assert result["overall"] == pytest.approx(1.0)
