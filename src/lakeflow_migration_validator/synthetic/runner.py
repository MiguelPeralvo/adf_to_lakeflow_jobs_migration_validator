"""Day 9 synthetic runner workflow utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.report import Report
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite


@dataclass(frozen=True, slots=True)
class TriageFailure:
    """A pipeline case that failed score or expression checks."""

    pipeline_name: str
    score: float
    reasons: tuple[str, ...]
    expression_mismatches: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class SyntheticRunResult:
    """Result of running synthetic stress tests over a converter."""

    report: Report
    ccs_distribution: dict[str, float]
    failures: tuple[TriageFailure, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "report": self.report.to_dict(),
            "ccs_distribution": self.ccs_distribution,
            "failures": [asdict(item) for item in self.failures],
        }


def run_synthetic_workflow(
    convert_fn: Callable[[dict], ConversionSnapshot],
    *,
    suite: GroundTruthSuite | None = None,
    count: int = 75,
    threshold: float = 90.0,
    **generate_kwargs,
) -> SyntheticRunResult:
    """Generate synthetic suite, evaluate converter, and triage failures."""
    active_suite = suite if suite is not None else GroundTruthSuite.generate(count=count, **generate_kwargs)
    report = active_suite.evaluate_converter(convert_fn, threshold=threshold)
    failures = tuple(_triage_failures(report))
    return SyntheticRunResult(
        report=report,
        ccs_distribution=report.ccs_distribution(),
        failures=failures,
    )


def _triage_failures(report: Report) -> list[TriageFailure]:
    triaged: list[TriageFailure] = []
    for case in report.cases:
        reasons: list[str] = []
        if case.ccs_below_threshold:
            reasons.append("ccs_below_threshold")
        if case.expression_mismatches:
            reasons.append("expression_mismatch")
        if not reasons:
            continue
        triaged.append(
            TriageFailure(
                pipeline_name=case.pipeline_name,
                score=case.score,
                reasons=tuple(reasons),
                expression_mismatches=case.expression_mismatches,
            )
        )
    return triaged
