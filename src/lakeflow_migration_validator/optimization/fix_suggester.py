"""Structured fix-suggestion engine for migration conversion improvements.

Ranks dimensions by weighted impact and uses an LLM judge to diagnose
issues and suggest concrete fixes.
"""

from __future__ import annotations

from dataclasses import dataclass

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.scorecard import Scorecard

_DEFAULT_WEIGHTS: dict[str, float] = {
    "activity_coverage": 0.25,
    "expression_coverage": 0.20,
    "dependency_preservation": 0.15,
    "notebook_validity": 0.15,
    "parameter_completeness": 0.10,
    "secret_completeness": 0.10,
    "not_translatable_ratio": 0.05,
    "control_flow_fidelity": 0.0,
    "semantic_equivalence": 0.0,
    "runtime_success": 0.0,
    "parallel_equivalence": 0.0,
}

_MAX_SUGGESTIONS = 3


@dataclass(frozen=True, slots=True)
class FixSuggestion:
    """A prioritised fix suggestion for a single dimension."""

    dimension: str
    score: float
    weight: float
    priority: int
    diagnosis: str
    suggestion: str


class FixSuggester:
    """Rank dimensions by impact and produce structured fix suggestions."""

    def __init__(
        self,
        judge_provider: JudgeProvider,
        *,
        model: str | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.judge_provider = judge_provider
        self.model = model
        self.weights = weights or _DEFAULT_WEIGHTS

    def suggest(
        self,
        snapshot: ConversionSnapshot,
        scorecard: Scorecard,
    ) -> list[FixSuggestion]:
        """Return up to 3 fix suggestions, sorted by priority (highest impact first)."""
        ranked = self._rank_dimensions(scorecard)
        suggestions: list[FixSuggestion] = []

        for priority, (dimension_name, score, weight) in enumerate(ranked[:_MAX_SUGGESTIONS], start=1):
            diagnosis = self._diagnose(snapshot, scorecard, dimension_name, score)
            suggestion_text = self._suggest_fix(snapshot, scorecard, dimension_name, diagnosis)
            suggestions.append(
                FixSuggestion(
                    dimension=dimension_name,
                    score=score,
                    weight=weight,
                    priority=priority,
                    diagnosis=diagnosis,
                    suggestion=suggestion_text,
                )
            )

        return suggestions

    def suggest_top(
        self,
        snapshot: ConversionSnapshot,
        scorecard: Scorecard,
    ) -> FixSuggestion | None:
        """Convenience method returning only the highest-priority suggestion."""
        suggestions = self.suggest(snapshot, scorecard)
        return suggestions[0] if suggestions else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rank_dimensions(self, scorecard: Scorecard) -> list[tuple[str, float, float]]:
        """Return failing dimensions sorted by impact ``(1 - score) * weight`` descending.

        Only dimensions with score < 1.0 are considered (i.e., imperfect).
        Ties are broken deterministically by dimension name ascending.
        """
        candidates: list[tuple[str, float, float, float]] = []
        for name, result in scorecard.results.items():
            weight = self.weights.get(name, 0.0)
            impact = (1.0 - result.score) * weight
            if impact > 0:
                candidates.append((name, result.score, weight, impact))

        candidates.sort(key=lambda c: (-c[3], c[0]))
        return [(name, score, weight) for name, score, weight, _impact in candidates]

    def _diagnose(
        self,
        snapshot: ConversionSnapshot,
        scorecard: Scorecard,
        dimension_name: str,
        dimension_score: float,
    ) -> str:
        prompt = (
            "Diagnose this migration conversion issue. "
            f"Lowest dimension: {dimension_name} score={dimension_score:.4f}. "
            f"CCS={scorecard.score:.2f}. "
            f"Tasks={len(snapshot.tasks)} Notebooks={len(snapshot.notebooks)}."
        )
        response = self.judge_provider.judge(prompt, model=self.model)
        return str(response.get("reasoning", ""))

    def _suggest_fix(
        self,
        snapshot: ConversionSnapshot,
        scorecard: Scorecard,
        dimension_name: str,
        diagnosis: str,
    ) -> str:
        prompt = (
            "Suggest a concrete migration fix. "
            f"Dimension={dimension_name}. Diagnosis={diagnosis}. "
            f"CCS={scorecard.score:.2f}. "
            f"Dependencies={len(snapshot.dependencies)} "
            f"Expressions={len(snapshot.resolved_expressions)}."
        )
        response = self.judge_provider.judge(prompt, model=self.model)
        return str(response.get("reasoning", ""))
