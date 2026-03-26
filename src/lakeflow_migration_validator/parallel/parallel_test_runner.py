"""Parallel runner orchestrating ADF and Databricks output comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lakeflow_migration_validator import evaluate
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions import DimensionResult
from lakeflow_migration_validator.dimensions.parallel_equivalence import compute_parallel_equivalence
from lakeflow_migration_validator.parallel.adf_runner import ADFExecutionRunner
from lakeflow_migration_validator.parallel.comparator import ComparisonResult, OutputComparator
from lakeflow_migration_validator.scorecard import Scorecard


class DatabricksOutputRunner(Protocol):
    """Protocol for running Databricks and collecting output values by task key."""

    def run(self, pipeline_name: str, parameters: dict[str, str] | None = None) -> dict[str, str]:
        ...


@dataclass(frozen=True, slots=True)
class ParallelTestResult:
    """Full result of a parallel test run."""

    pipeline_name: str
    adf_outputs: dict[str, str]
    databricks_outputs: dict[str, str]
    comparisons: tuple[ComparisonResult, ...]
    equivalence_score: float
    scorecard: Scorecard


@dataclass(frozen=True, slots=True)
class ParallelTestRunner:
    """Run ADF + Databricks output collection and score equivalence."""

    adf_runner: ADFExecutionRunner
    databricks_runner: DatabricksOutputRunner
    comparator: OutputComparator = OutputComparator()
    threshold: float = 0.95

    def run(
        self,
        pipeline_name: str,
        parameters: dict[str, str] | None = None,
        *,
        snapshot: ConversionSnapshot | None = None,
    ) -> ParallelTestResult:
        payload = dict(parameters or {})
        adf_outputs = self.adf_runner.run(pipeline_name, parameters=payload)
        databricks_outputs = self.databricks_runner.run(pipeline_name, parameters=payload)

        comparisons = tuple(self.comparator.compare(adf_outputs, databricks_outputs))
        equivalence_score = self.comparator.score(list(comparisons))

        enriched_snapshot = _with_parallel_outputs(snapshot, adf_outputs, databricks_outputs)
        parallel_score, parallel_details = compute_parallel_equivalence(enriched_snapshot)

        parallel_result = DimensionResult(
            name="parallel_equivalence",
            score=parallel_score,
            passed=parallel_score >= self.threshold,
            details={
                **parallel_details,
                "comparator_score": equivalence_score,
            },
        )

        scorecard = _build_scorecard(snapshot, parallel_result)

        return ParallelTestResult(
            pipeline_name=pipeline_name,
            adf_outputs=adf_outputs,
            databricks_outputs=databricks_outputs,
            comparisons=comparisons,
            equivalence_score=equivalence_score,
            scorecard=scorecard,
        )


def _with_parallel_outputs(
    snapshot: ConversionSnapshot | None,
    adf_outputs: dict[str, str],
    databricks_outputs: dict[str, str],
) -> ConversionSnapshot:
    if snapshot is None:
        return ConversionSnapshot(
            tasks=(),
            notebooks=(),
            secrets=(),
            parameters=(),
            dependencies=(),
            expected_outputs=dict(databricks_outputs),
            adf_run_outputs=dict(adf_outputs),
        )

    return ConversionSnapshot(
        tasks=snapshot.tasks,
        notebooks=snapshot.notebooks,
        secrets=snapshot.secrets,
        parameters=snapshot.parameters,
        dependencies=snapshot.dependencies,
        not_translatable=snapshot.not_translatable,
        resolved_expressions=snapshot.resolved_expressions,
        source_pipeline=snapshot.source_pipeline,
        total_source_dependencies=snapshot.total_source_dependencies,
        expected_outputs=dict(databricks_outputs),
        adf_run_outputs=dict(adf_outputs),
    )


def _build_scorecard(snapshot: ConversionSnapshot | None, parallel_result: DimensionResult) -> Scorecard:
    if snapshot is None:
        return Scorecard.compute(
            {"parallel_equivalence": 1.0},
            {"parallel_equivalence": parallel_result},
        )

    base = evaluate(snapshot)
    results = dict(base.results)
    results["parallel_equivalence"] = parallel_result

    weights = dict(base.weights)
    weights.setdefault("parallel_equivalence", 0.0)
    return Scorecard.compute(weights, results)
