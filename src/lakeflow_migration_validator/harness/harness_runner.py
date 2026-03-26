"""Harness orchestration for end-to-end conversion and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from lakeflow_migration_validator import evaluate, evaluate_full
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.harness.adf_connector import ADFConnector
from lakeflow_migration_validator.harness.fix_loop import FixLoop
from lakeflow_migration_validator.scorecard import Scorecard


@dataclass(frozen=True, slots=True)
class HarnessResult:
    """Result of a harness run."""

    pipeline_name: str
    scorecard: Scorecard
    snapshot: ConversionSnapshot
    fix_suggestions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    iterations: int = 1


class HarnessRunnerError(RuntimeError):
    """Deterministic harness failure with machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class HarnessRunner:
    """Fetch -> translate -> adapt -> evaluate orchestration for pipeline migrations."""

    def __init__(
        self,
        *,
        adf_connector: ADFConnector,
        wkmigrate_adapter: Callable[[dict, Any], ConversionSnapshot],
        judge_provider: JudgeProvider | None = None,
        max_iterations: int = 1,
        fix_loop: FixLoop | None = None,
    ):
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.adf_connector = adf_connector
        self.wkmigrate_adapter = wkmigrate_adapter
        self.judge_provider = judge_provider
        self.max_iterations = max_iterations
        self.fix_loop = fix_loop

    def run(self, pipeline_name: str) -> HarnessResult:
        """Run one pipeline through conversion and scoring."""
        try:
            pipeline_json = self.adf_connector.fetch_pipeline(pipeline_name)
        except KeyError as exc:
            raise HarnessRunnerError("PIPELINE_NOT_FOUND", pipeline_name) from exc
        except Exception as exc:  # pragma: no cover - defensive
            raise HarnessRunnerError("PIPELINE_FETCH_FAILED", str(exc)) from exc

        try:
            source_pipeline, prepared_workflow = self.adf_connector.translate_and_prepare(pipeline_json)
        except Exception as exc:
            raise HarnessRunnerError("TRANSLATION_FAILED", str(exc)) from exc

        try:
            snapshot = self.wkmigrate_adapter(source_pipeline, prepared_workflow)
        except Exception as exc:
            raise HarnessRunnerError("ADAPTER_FAILED", str(exc)) from exc

        if not isinstance(snapshot, ConversionSnapshot):
            raise HarnessRunnerError("ADAPTER_FAILED", "adapter must return ConversionSnapshot")

        scorecard = self._evaluate_snapshot(snapshot)

        fix_suggestions: list[dict[str, Any]] = []
        iterations = 1
        if self.fix_loop is not None:
            snapshot, scorecard, fix_suggestions = self.fix_loop.iterate(snapshot, scorecard)
            iterations = len(fix_suggestions) + 1
        elif self.max_iterations > 1 and self.judge_provider is not None:
            loop = FixLoop(
                judge_provider=self.judge_provider,
                max_iterations=1,
            )
            snapshot, scorecard, fix_suggestions = loop.iterate(snapshot, scorecard)
            iterations = len(fix_suggestions) + 1

        return HarnessResult(
            pipeline_name=pipeline_name,
            scorecard=scorecard,
            snapshot=snapshot,
            fix_suggestions=tuple(fix_suggestions),
            iterations=iterations,
        )

    def run_all(self, pipeline_names: list[str] | None = None) -> list[HarnessResult]:
        """Run harness for explicit pipelines, or all pipelines from connector."""
        names = pipeline_names if pipeline_names is not None else self.adf_connector.list_pipelines()
        return [self.run(name) for name in names]

    def _evaluate_snapshot(self, snapshot: ConversionSnapshot) -> Scorecard:
        if self.judge_provider is None:
            return evaluate(snapshot)
        return evaluate_full(snapshot, judge_provider=self.judge_provider)
