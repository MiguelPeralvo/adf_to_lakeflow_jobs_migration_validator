"""LLMJudge — a dimension evaluated by an LLM via Databricks FMAPI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from lakeflow_migration_validator.dimensions import DimensionResult


class JudgeProvider(Protocol):
    """Protocol for calling an LLM judge via Databricks FMAPI."""

    def judge(self, prompt: str, model: str | None = None) -> dict[str, Any]:
        """Returns {"score": float, "reasoning": str}."""
        ...


@dataclass(frozen=True, slots=True)
class LLMJudge:
    """A dimension evaluated by an LLM judge via Databricks FMAPI.

    Uses Opus 4.6 for high-stakes calibration and nightly eval.
    Uses ChatGPT 5.4 for batch CI scoring.
    """

    name: str
    criteria: str
    input_template: str
    provider: JudgeProvider
    calibration_examples: tuple[dict, ...] = ()
    threshold: float = 0.7
    model: str = "claude-opus-4-6"

    def evaluate(self, input: Any, output: Any) -> DimensionResult:
        prompt = self._build_prompt(input, output)
        response = self.provider.judge(prompt, model=self.model)
        score = response.get("score", 0.0)
        return DimensionResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            details={"reasoning": response.get("reasoning", ""), "model": self.model},
        )

    def _build_prompt(self, input: Any, output: Any) -> str:
        examples_block = ""
        if self.calibration_examples:
            examples_block = "Examples:\n" + "\n".join(
                f"- Input: {ex['input']}\n  Output: {ex['output']}\n  Score: {ex['score']}"
                for ex in self.calibration_examples
            ) + "\n\n"

        return (
            f"You are an evaluation judge. Score the following output on a scale of 0.0 to 1.0.\n\n"
            f"Criteria: {self.criteria}\n\n"
            f"{examples_block}"
            f"{self.input_template.format(input=input, output=output)}\n\n"
            f'Respond with JSON: {{"score": <float>, "reasoning": "<explanation>"}}'
        )
