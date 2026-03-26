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

    def ccs_distribution(self) -> dict[str, int | float]:
        """Return CCS distribution stats from case scores."""
        scores = sorted(case.score for case in self.cases)
        if not scores:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "median": 0.0,
                "p10": 0.0,
                "p25": 0.0,
                "p75": 0.0,
                "p90": 0.0,
            }
        count = len(scores)
        mean_score = sum(scores) / count
        return {
            "count": count,
            "min": scores[0],
            "max": scores[-1],
            "mean": mean_score,
            "median": _percentile(scores, 0.5),
            "p10": _percentile(scores, 0.10),
            "p25": _percentile(scores, 0.25),
            "p75": _percentile(scores, 0.75),
            "p90": _percentile(scores, 0.90),
        }

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
            "ccs_distribution": self.ccs_distribution(),
            "cases": [asdict(case) for case in self.cases],
        }


def _percentile(sorted_scores: list[float], quantile: float) -> float:
    """Compute percentile with linear interpolation on sorted values."""
    if not sorted_scores:
        return 0.0
    if len(sorted_scores) == 1:
        return sorted_scores[0]
    index = (len(sorted_scores) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(sorted_scores) - 1)
    fraction = index - lower
    return sorted_scores[lower] * (1 - fraction) + sorted_scores[upper] * fraction
