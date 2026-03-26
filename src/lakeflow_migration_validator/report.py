"""Reporting models for batch conversion evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CaseReport:
    """Per-pipeline converter evaluation result."""

    pipeline_name: str
    description: str
    difficulty: str
    score: float
    label: str
    ccs_below_threshold: bool
    expression_mismatches: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class Report:
    """Aggregate report for a ground-truth converter evaluation."""

    total: int
    threshold: float
    mean_score: float
    min_score: float
    max_score: float
    below_threshold: int
    expression_mismatch_cases: int
    cases: tuple[CaseReport, ...]

    def to_dict(self) -> dict:
        """Return a JSON-serializable report representation."""
        return {
            "total": self.total,
            "threshold": self.threshold,
            "mean_score": self.mean_score,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "below_threshold": self.below_threshold,
            "expression_mismatch_cases": self.expression_mismatch_cases,
            "cases": [asdict(case) for case in self.cases],
        }
