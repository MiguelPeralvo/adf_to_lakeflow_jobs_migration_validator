"""ExecutionDimension — a dimension that deploys and runs on a real environment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from lakeflow_migration_validator.dimensions import DimensionResult


class ExecutionRunner(Protocol):
    """Protocol for running a prepared workflow and collecting results."""

    def run(self, output: Any, params: dict[str, str]) -> dict[str, Any]:
        """Returns {task_key: {"success": bool, "error": str | None}}."""
        ...


@dataclass(frozen=True, slots=True)
class ExecutionDimension:
    """A dimension that deploys and runs the output on a real Databricks environment."""

    name: str
    runner: ExecutionRunner
    test_params: dict[str, str] = field(default_factory=dict)
    threshold: float = 1.0

    def evaluate(self, input: Any, output: Any) -> DimensionResult:
        try:
            results = self.runner.run(output, params=dict(self.test_params))
        except Exception as exc:
            return DimensionResult(
                name=self.name,
                score=0.0,
                passed=False,
                details={"error": str(exc)},
            )
        if not results:
            return DimensionResult(
                name=self.name, score=0.0, passed=False, details={"error": "no tasks returned"}
            )
        successes = sum(1 for r in results.values() if r.get("success"))
        score = successes / len(results)
        return DimensionResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            details={"task_results": results},
        )
