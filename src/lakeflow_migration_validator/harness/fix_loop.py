"""Fix-loop orchestration for iterative conversion improvements."""

from __future__ import annotations

from typing import Any, Callable

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.scorecard import Scorecard

AdvanceFn = Callable[
    [ConversionSnapshot, Scorecard, dict[str, Any], int],
    tuple[ConversionSnapshot, Scorecard],
]


class FixLoop:
    """Score -> diagnose -> suggest fix, with optional iterative advance callback."""

    def __init__(
        self,
        judge_provider: JudgeProvider,
        *,
        max_iterations: int = 3,
        model: str | None = None,
        advance_fn: AdvanceFn | None = None,
    ):
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.judge_provider = judge_provider
        self.max_iterations = max_iterations
        self.model = model
        self.advance_fn = advance_fn

    def iterate(
        self,
        snapshot: ConversionSnapshot,
        scorecard: Scorecard,
    ) -> tuple[ConversionSnapshot, Scorecard, list[dict[str, Any]]]:
        """Run fix-loop iterations and return updated state plus suggestions."""
        current_snapshot = snapshot
        current_scorecard = scorecard
        suggestions: list[dict[str, Any]] = []

        for iteration in range(1, self.max_iterations + 1):
            target = _lowest_dimension(current_scorecard)
            if target is None:
                break
            dimension_name, dimension_score = target

            diagnosis = self._diagnose(current_snapshot, current_scorecard, dimension_name, dimension_score)
            suggestion_text = self._suggest_fix(
                current_snapshot,
                current_scorecard,
                dimension_name,
                diagnosis,
            )

            suggestion = {
                "iteration": iteration,
                "dimension": dimension_name,
                "score": dimension_score,
                "diagnosis": diagnosis,
                "suggestion": suggestion_text,
            }
            suggestions.append(suggestion)

            if self.advance_fn is None:
                break

            current_snapshot, current_scorecard = self.advance_fn(
                current_snapshot,
                current_scorecard,
                suggestion,
                iteration,
            )
            if current_scorecard.all_passed:
                break

        return current_snapshot, current_scorecard, suggestions

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
            f"Dependencies={len(snapshot.dependencies)} Expressions={len(snapshot.resolved_expressions)}."
        )
        response = self.judge_provider.judge(prompt, model=self.model)
        return str(response.get("reasoning", ""))


def _lowest_dimension(scorecard: Scorecard) -> tuple[str, float] | None:
    """Return the lowest-scoring dimension using deterministic tie-break by name."""
    if not scorecard.results:
        return None

    ranked = sorted(
        ((name, result.score) for name, result in scorecard.results.items()),
        key=lambda item: (item[1], item[0]),
    )
    return ranked[0]
