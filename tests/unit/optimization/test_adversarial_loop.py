"""Tests for the closed-loop adversarial testing orchestrator.

All tests run without wkmigrate or LLM calls — everything is mocked.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    ExpressionPair,
    NotebookSnapshot,
    TaskSnapshot,
)
from lakeflow_migration_validator.optimization.adversarial_loop import (
    AdversarialLoop,
    LoopConfig,
    LoopResult,
    RoundResult,
    export_as_golden_set,
)
from lakeflow_migration_validator.synthetic.agent_generator import (
    FailureRecord,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _MockProvider:
    """Mock JudgeProvider that returns pre-configured responses."""

    def __init__(self, completions: list[str] | None = None):
        self._completions = completions or []
        self._complete_idx = 0
        self.call_count = 0

    def judge(self, prompt: str, model: str | None = None) -> dict:
        self.call_count += 1
        return {"score": 0.5, "reasoning": "{}"}

    def complete(self, prompt: str, model: str | None = None, max_tokens: int = 4096) -> str:
        self.call_count += 1
        if self._complete_idx < len(self._completions):
            text = self._completions[self._complete_idx]
        else:
            text = "{}"
        self._complete_idx += 1
        return text


_VALID_PIPELINE_JSON = json.dumps(
    {
        "name": "test_pipeline",
        "properties": {
            "parameters": {"env": {"type": "String"}},
            "variables": {"result": {"type": "String"}},
            "activities": [
                {
                    "name": "set_var",
                    "type": "SetVariable",
                    "dependsOn": [],
                    "typeProperties": {
                        "variableName": "result",
                        "value": {
                            "type": "Expression",
                            "value": "@concat('hello', pipeline().parameters.env)",
                        },
                    },
                },
                {
                    "name": "notebook_run",
                    "type": "DatabricksNotebook",
                    "dependsOn": [{"activity": "set_var", "dependencyConditions": ["Succeeded"]}],
                    "typeProperties": {"notebookPath": "/test/notebook"},
                },
            ],
        },
    }
)

_PLAN_JSON = json.dumps(
    {
        "count": 2,
        "pipelines": [
            {
                "name": "adv_pipeline_001",
                "activity_count": 3,
                "activity_types": ["SetVariable", "DatabricksNotebook"],
                "stress_area": "nested_expressions",
                "expression_complexity": "nested",
                "parameters": ["env"],
            },
            {
                "name": "adv_pipeline_002",
                "activity_count": 2,
                "activity_types": ["SetVariable", "IfCondition"],
                "stress_area": "complex_conditions",
                "expression_complexity": "deeply_nested",
                "parameters": ["threshold"],
            },
        ],
    }
)


def _make_snapshot(
    *,
    tasks: tuple[TaskSnapshot, ...] | None = None,
    parameters: tuple[str, ...] = ("env",),
    expressions: tuple[ExpressionPair, ...] = (),
    not_translatable: tuple[dict, ...] = (),
    total_deps: int = 0,
) -> ConversionSnapshot:
    """Create a minimal ConversionSnapshot for testing."""
    return ConversionSnapshot(
        tasks=tasks or (TaskSnapshot(task_key="task_1", is_placeholder=False),),
        notebooks=(
            NotebookSnapshot(
                file_path="/tmp/test.py",
                content="x = 1\n",
            ),
        ),
        secrets=(),
        parameters=parameters,
        dependencies=(),
        not_translatable=not_translatable,
        resolved_expressions=expressions,
        source_pipeline={},
        total_source_dependencies=total_deps,
    )


def _passing_convert_fn(adf_json: dict) -> ConversionSnapshot:
    """A convert_fn that always returns a perfect snapshot."""
    return _make_snapshot(
        expressions=(ExpressionPair(adf_expression="@concat('a','b')", python_code="'a'+'b'"),),
    )


def _failing_convert_fn(adf_json: dict) -> ConversionSnapshot:
    """A convert_fn that returns a snapshot with failures."""
    return _make_snapshot(
        tasks=(
            TaskSnapshot(task_key="task_1", is_placeholder=True),
            TaskSnapshot(task_key="task_2", is_placeholder=True),
        ),
        not_translatable=(
            {"message": "unsupported function concat"},
            {"message": "(type: ForEach) was substituted"},
        ),
    )


def _crashing_convert_fn(adf_json: dict) -> ConversionSnapshot:
    """A convert_fn that raises an exception."""
    raise RuntimeError("wkmigrate crashed")


# ---------------------------------------------------------------------------
# LoopConfig tests
# ---------------------------------------------------------------------------


class TestLoopConfig:
    """Test LoopConfig defaults and validation."""

    def test_defaults(self):
        cfg = LoopConfig()
        assert cfg.max_rounds == 10
        assert cfg.pipelines_per_round == 10
        assert cfg.convergence_patience == 3
        assert cfg.max_time_seconds == 3600.0
        assert cfg.max_llm_calls == 500
        assert cfg.failure_threshold == 0.75
        assert "nested_expressions" in cfg.target_weak_spots
        assert cfg.golden_set_output_path is None
        assert cfg.issue_map_path == "dev/wkmigrate-issue-map.json"

    def test_custom_values(self):
        cfg = LoopConfig(
            max_rounds=5,
            pipelines_per_round=20,
            convergence_patience=2,
            max_time_seconds=7200.0,
            max_llm_calls=1000,
            failure_threshold=0.5,
        )
        assert cfg.max_rounds == 5
        assert cfg.pipelines_per_round == 20
        assert cfg.convergence_patience == 2
        assert cfg.max_time_seconds == 7200.0
        assert cfg.max_llm_calls == 1000
        assert cfg.failure_threshold == 0.5

    def test_frozen(self):
        cfg = LoopConfig()
        with pytest.raises(Exception):
            cfg.max_rounds = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RoundResult and LoopResult dataclass tests
# ---------------------------------------------------------------------------


class TestRoundResult:
    """Test RoundResult dataclass."""

    def test_construction(self):
        result = RoundResult(
            round_number=1,
            pipelines_generated=10,
            pipelines_failed=2,
            conversions_attempted=8,
            failures_found=3,
            new_clusters=1,
            cluster_signatures=("unsupported_function:concat",),
            worst_dimension="expression_coverage",
            mean_scores={"expression_coverage": 0.6, "activity_coverage": 0.9},
            elapsed_seconds=12.5,
            llm_calls_used=15,
        )
        assert result.round_number == 1
        assert result.pipelines_generated == 10
        assert result.new_clusters == 1
        assert result.cluster_signatures == ("unsupported_function:concat",)
        assert result.worst_dimension == "expression_coverage"

    def test_frozen(self):
        result = RoundResult(
            round_number=1,
            pipelines_generated=0,
            pipelines_failed=0,
            conversions_attempted=0,
            failures_found=0,
            new_clusters=0,
            cluster_signatures=(),
            worst_dimension="none",
        )
        with pytest.raises(Exception):
            result.round_number = 2  # type: ignore[misc]


class TestLoopResult:
    """Test LoopResult dataclass."""

    def test_construction(self):
        result = LoopResult(
            rounds_completed=3,
            total_pipelines=30,
            total_failures=5,
            unique_clusters=2,
            termination_reason="converged",
            round_results=(),
            all_failures=(),
            discovered_signatures={"sig_a": 3, "sig_b": 2},
            golden_set_path=None,
            elapsed_seconds=100.0,
        )
        assert result.rounds_completed == 3
        assert result.termination_reason == "converged"
        assert result.unique_clusters == 2

    def test_termination_reasons(self):
        for reason in ("max_rounds", "converged", "time_budget", "llm_budget"):
            result = LoopResult(
                rounds_completed=1,
                total_pipelines=10,
                total_failures=0,
                unique_clusters=0,
                termination_reason=reason,
                round_results=(),
                all_failures=(),
            )
            assert result.termination_reason == reason


# ---------------------------------------------------------------------------
# _should_stop tests
# ---------------------------------------------------------------------------


class TestShouldStop:
    """Test the termination logic."""

    def _make_loop(self, **config_kwargs) -> AdversarialLoop:
        provider = _MockProvider()
        return AdversarialLoop(
            provider,
            convert_fn=_passing_convert_fn,
            config=LoopConfig(**config_kwargs),
        )

    def test_stops_on_convergence(self):
        loop = self._make_loop(convergence_patience=3)
        # 3 rounds with no new clusters
        results = [
            RoundResult(
                round_number=i,
                pipelines_generated=10,
                pipelines_failed=0,
                conversions_attempted=10,
                failures_found=0,
                new_clusters=0,
                cluster_signatures=(),
                worst_dimension="none",
            )
            for i in range(1, 4)
        ]
        start_time = time.monotonic()
        should_stop, reason = loop._should_stop(results, start_time)
        assert should_stop is True
        assert reason == "converged"

    def test_does_not_stop_before_patience(self):
        loop = self._make_loop(convergence_patience=3)
        # Only 2 rounds with no new clusters — not enough
        results = [
            RoundResult(
                round_number=i,
                pipelines_generated=10,
                pipelines_failed=0,
                conversions_attempted=10,
                failures_found=0,
                new_clusters=0,
                cluster_signatures=(),
                worst_dimension="none",
            )
            for i in range(1, 3)
        ]
        start_time = time.monotonic()
        should_stop, reason = loop._should_stop(results, start_time)
        assert should_stop is False

    def test_does_not_stop_if_new_clusters_in_window(self):
        loop = self._make_loop(convergence_patience=3)
        results = [
            RoundResult(
                round_number=1,
                pipelines_generated=10,
                pipelines_failed=0,
                conversions_attempted=10,
                failures_found=2,
                new_clusters=1,  # New cluster in first round
                cluster_signatures=("sig_a",),
                worst_dimension="expression_coverage",
            ),
            RoundResult(
                round_number=2,
                pipelines_generated=10,
                pipelines_failed=0,
                conversions_attempted=10,
                failures_found=0,
                new_clusters=0,
                cluster_signatures=(),
                worst_dimension="none",
            ),
            RoundResult(
                round_number=3,
                pipelines_generated=10,
                pipelines_failed=0,
                conversions_attempted=10,
                failures_found=0,
                new_clusters=0,
                cluster_signatures=(),
                worst_dimension="none",
            ),
        ]
        start_time = time.monotonic()
        should_stop, reason = loop._should_stop(results, start_time)
        # Patience window is last 3 — round 1 had a new cluster
        assert should_stop is False

    def test_stops_on_time_budget(self):
        loop = self._make_loop(max_time_seconds=0.001)
        results = [
            RoundResult(
                round_number=1,
                pipelines_generated=10,
                pipelines_failed=0,
                conversions_attempted=10,
                failures_found=5,
                new_clusters=2,
                cluster_signatures=("a", "b"),
                worst_dimension="expression_coverage",
            ),
        ]
        # Use a start_time far in the past
        start_time = time.monotonic() - 10.0
        should_stop, reason = loop._should_stop(results, start_time)
        assert should_stop is True
        assert reason == "time_budget"

    def test_stops_on_llm_budget(self):
        loop = self._make_loop(max_llm_calls=5)
        loop._llm_calls = 5  # Exhaust budget
        results = [
            RoundResult(
                round_number=1,
                pipelines_generated=10,
                pipelines_failed=0,
                conversions_attempted=10,
                failures_found=0,
                new_clusters=0,
                cluster_signatures=(),
                worst_dimension="none",
            ),
        ]
        start_time = time.monotonic()
        should_stop, reason = loop._should_stop(results, start_time)
        assert should_stop is True
        assert reason == "llm_budget"


# ---------------------------------------------------------------------------
# _classify_failure tests
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    """Test failure classification against issue map."""

    def _make_loop_with_issue_map(self, signatures: list[dict]) -> AdversarialLoop:
        provider = _MockProvider()
        loop = AdversarialLoop(
            provider,
            convert_fn=_passing_convert_fn,
            config=LoopConfig(),
        )
        loop._issue_map = {"failure_signatures": signatures}
        return loop

    def test_matches_concat_signature(self):
        loop = self._make_loop_with_issue_map(
            [
                {
                    "signature_key": "unsupported_function:concat",
                    "regex": "(?i)unsupported.*function.*concat|@concat",
                    "match_target": "not_translatable.message",
                },
            ]
        )
        snapshot = _make_snapshot(
            not_translatable=({"message": "unsupported function concat in expression"},),
        )
        result = loop._classify_failure(
            {"name": "test"},
            {"expression_coverage": 0.3},
            snapshot,
        )
        assert result == "unsupported_function:concat"

    def test_matches_foreach_signature(self):
        loop = self._make_loop_with_issue_map(
            [
                {
                    "signature_key": "for_each_items_silent_placeholder",
                    "regex": "(?i)\\(type:\\s*ForEach\\)",
                    "match_target": "not_translatable.message",
                },
            ]
        )
        snapshot = _make_snapshot(
            not_translatable=({"message": "(type: ForEach) was substituted with placeholder"},),
        )
        result = loop._classify_failure(
            {"name": "test"},
            {"activity_coverage": 0.5},
            snapshot,
        )
        assert result == "for_each_items_silent_placeholder"

    def test_no_match_returns_none(self):
        loop = self._make_loop_with_issue_map(
            [
                {
                    "signature_key": "unsupported_function:concat",
                    "regex": "(?i)unsupported.*function.*concat",
                    "match_target": "not_translatable.message",
                },
            ]
        )
        snapshot = _make_snapshot(not_translatable=())
        result = loop._classify_failure(
            {"name": "test"},
            {"expression_coverage": 0.9},
            snapshot,
        )
        assert result is None

    def test_empty_issue_map(self):
        loop = self._make_loop_with_issue_map([])
        snapshot = _make_snapshot(
            not_translatable=({"message": "some error"},),
        )
        result = loop._classify_failure(
            {"name": "test"},
            {"expression_coverage": 0.3},
            snapshot,
        )
        assert result is None

    def test_exception_match_target(self):
        loop = self._make_loop_with_issue_map(
            [
                {
                    "signature_key": "pipeline_adapter_recursion",
                    "regex": "(?i)recursionerror|maximum recursion depth",
                    "match_target": "exception",
                },
            ]
        )
        # The regex matches against the pipeline JSON string
        adf_json = {"name": "test", "error": "RecursionError: maximum recursion depth exceeded"}
        snapshot = _make_snapshot()
        result = loop._classify_failure(
            adf_json,
            {"activity_coverage": 0.0},
            snapshot,
        )
        assert result == "pipeline_adapter_recursion"


# ---------------------------------------------------------------------------
# export_as_golden_set tests
# ---------------------------------------------------------------------------


class TestExportAsGoldenSet:
    """Test golden set export functionality."""

    def test_produces_valid_json(self):
        failures = [
            FailureRecord(
                pipeline_name="test_pipeline_001",
                dimension="expression_coverage",
                score=0.3,
                error="Below threshold",
                adf_json={
                    "name": "test_pipeline_001",
                    "properties": {
                        "activities": [
                            {
                                "name": "set_var",
                                "type": "SetVariable",
                                "typeProperties": {
                                    "value": {
                                        "type": "Expression",
                                        "value": "@concat('a', 'b')",
                                    },
                                },
                            }
                        ],
                    },
                },
            ),
            FailureRecord(
                pipeline_name="test_pipeline_002",
                dimension="activity_coverage",
                score=0.5,
                error="Below threshold",
                adf_json={"name": "test_pipeline_002", "properties": {"activities": []}},
            ),
        ]

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        result_path = export_as_golden_set(failures, output_path)
        assert result_path == output_path

        content = json.loads(Path(output_path).read_text())
        assert content["count"] == 2
        assert content["source"] == "adversarial_loop"
        assert len(content["expressions"]) == 2

        # First entry should have extracted the expression
        first = content["expressions"][0]
        assert first["adf_expression"] == "@concat('a', 'b')"
        assert first["category"] == "expression_coverage"
        assert first["pipeline_name"] == "test_pipeline_001"
        assert first["expected_dimensions"] == {"expression_coverage": 1.0}

        # Cleanup
        Path(output_path).unlink()

    def test_empty_failures(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        export_as_golden_set([], output_path)
        content = json.loads(Path(output_path).read_text())
        assert content["count"] == 0
        assert content["expressions"] == []

        Path(output_path).unlink()

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / "nested" / "dir" / "golden.json")
            failures = [
                FailureRecord(
                    pipeline_name="p1",
                    dimension="notebook_validity",
                    score=0.0,
                    error="crash",
                    adf_json={},
                ),
            ]
            result_path = export_as_golden_set(failures, output_path)
            assert Path(result_path).exists()
            content = json.loads(Path(result_path).read_text())
            assert content["count"] == 1


# ---------------------------------------------------------------------------
# Single round with mocked generator + converter
# ---------------------------------------------------------------------------


class TestSingleRound:
    """Test a full round with mocked dependencies."""

    def test_round_with_passing_conversions(self):
        """All pipelines pass — no failures, no clusters."""
        # Provider returns valid plan + valid pipelines
        provider = _MockProvider(completions=[_PLAN_JSON, _VALID_PIPELINE_JSON, _VALID_PIPELINE_JSON])
        loop = AdversarialLoop(
            provider,
            convert_fn=_passing_convert_fn,
            config=LoopConfig(max_rounds=1, pipelines_per_round=2),
        )
        result = loop.run()

        assert result.rounds_completed == 1
        assert result.termination_reason == "max_rounds"
        assert result.total_failures == 0
        assert result.unique_clusters == 0

    def test_round_with_failing_conversions(self):
        """All pipelines fail conversion checks — failures recorded."""
        provider = _MockProvider(completions=[_PLAN_JSON, _VALID_PIPELINE_JSON, _VALID_PIPELINE_JSON])
        loop = AdversarialLoop(
            provider,
            convert_fn=_failing_convert_fn,
            config=LoopConfig(
                max_rounds=1,
                pipelines_per_round=2,
                failure_threshold=0.75,
            ),
        )
        result = loop.run()

        assert result.rounds_completed == 1
        assert result.total_failures > 0
        assert len(result.all_failures) > 0

    def test_round_with_crashing_converter(self):
        """Converter crashes — recorded as conversion_crash failure."""
        provider = _MockProvider(completions=[_PLAN_JSON, _VALID_PIPELINE_JSON, _VALID_PIPELINE_JSON])
        loop = AdversarialLoop(
            provider,
            convert_fn=_crashing_convert_fn,
            config=LoopConfig(max_rounds=1, pipelines_per_round=2),
        )
        result = loop.run()

        assert result.rounds_completed == 1
        assert result.total_failures > 0
        crash_failures = [f for f in result.all_failures if f.dimension == "conversion_crash"]
        assert len(crash_failures) > 0

    def test_convergence_stops_loop(self):
        """Loop stops when no new clusters for patience rounds."""
        provider = _MockProvider(completions=[_PLAN_JSON] + [_VALID_PIPELINE_JSON] * 30)
        loop = AdversarialLoop(
            provider,
            convert_fn=_passing_convert_fn,
            config=LoopConfig(
                max_rounds=10,
                pipelines_per_round=2,
                convergence_patience=3,
            ),
        )
        result = loop.run()

        assert result.termination_reason == "converged"
        assert result.rounds_completed == 3

    def test_llm_budget_stops_loop(self):
        """Loop stops when LLM call budget is exhausted."""
        provider = _MockProvider(completions=[_PLAN_JSON] + [_VALID_PIPELINE_JSON] * 100)
        loop = AdversarialLoop(
            provider,
            convert_fn=_passing_convert_fn,
            config=LoopConfig(
                max_rounds=50,
                pipelines_per_round=5,
                max_llm_calls=3,
                convergence_patience=50,
            ),
        )
        result = loop.run()

        # Should stop due to llm budget (3 calls = plan + 2 pipelines)
        # or convergence — either way it should not run all 50 rounds
        assert result.rounds_completed < 50

    def test_stream_yields_events(self):
        """run_stream yields proper event types."""
        provider = _MockProvider(completions=[_PLAN_JSON, _VALID_PIPELINE_JSON, _VALID_PIPELINE_JSON])
        loop = AdversarialLoop(
            provider,
            convert_fn=_passing_convert_fn,
            config=LoopConfig(max_rounds=1, pipelines_per_round=2),
        )

        events = list(loop.run_stream())
        event_types = [e["type"] for e in events]

        assert "round_start" in event_types
        assert "pipeline_result" in event_types
        assert "round_end" in event_types
        assert "complete" in event_types

        # Check round_start has expected fields
        round_start = next(e for e in events if e["type"] == "round_start")
        assert round_start["round"] == 1
        assert "config" in round_start

        # Check complete event has result
        complete = next(e for e in events if e["type"] == "complete")
        assert isinstance(complete["result"], LoopResult)

    def test_golden_set_export_on_completion(self):
        """When golden_set_output_path is set, failures are exported."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        provider = _MockProvider(completions=[_PLAN_JSON, _VALID_PIPELINE_JSON, _VALID_PIPELINE_JSON])
        loop = AdversarialLoop(
            provider,
            convert_fn=_failing_convert_fn,
            config=LoopConfig(
                max_rounds=1,
                pipelines_per_round=2,
                golden_set_output_path=output_path,
            ),
        )
        result = loop.run()

        if result.total_failures > 0:
            assert result.golden_set_path == output_path
            content = json.loads(Path(output_path).read_text())
            assert content["source"] == "adversarial_loop"
            assert content["count"] > 0

        Path(output_path).unlink(missing_ok=True)
