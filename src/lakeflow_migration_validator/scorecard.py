"""Scorecard — weighted aggregation of dimension results."""

from __future__ import annotations

from dataclasses import dataclass, field

from lakeflow_migration_validator.dimensions import DimensionResult


@dataclass(frozen=True, slots=True)
class Scorecard:
    """Weighted aggregation of dimension results into a single score."""

    weights: dict[str, float]
    results: dict[str, DimensionResult] = field(default_factory=dict)
    score: float = 0.0

    @classmethod
    def compute(cls, weights: dict[str, float], results: dict[str, DimensionResult]) -> Scorecard:
        total_weight = sum(weights.get(name, 0) for name in results)
        if total_weight == 0:
            return cls(weights=weights, results=results, score=0.0)
        raw = sum(results[name].score * weights.get(name, 0) for name in results if name in weights)
        score = (raw / total_weight) * 100
        return cls(weights=weights, results=results, score=score)

    @property
    def label(self) -> str:
        if self.score >= 90:
            return "HIGH_CONFIDENCE"
        if self.score >= 70:
            return "REVIEW_RECOMMENDED"
        return "MANUAL_INTERVENTION"

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results.values())

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "label": self.label,
            "dimensions": {
                name: {"score": r.score, "passed": r.passed, "details": r.details} for name, r in self.results.items()
            },
        }
