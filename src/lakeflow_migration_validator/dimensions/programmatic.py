"""ProgrammaticCheck — a dimension computed by a pure Python function."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from lakeflow_migration_validator.dimensions import DimensionResult


@dataclass(frozen=True, slots=True)
class ProgrammaticCheck:
    """A dimension computed by a pure Python function.

    The ``check_fn`` receives ``(input, output)`` and returns either a ``float``
    score (0.0-1.0) or a ``(float, dict)`` tuple with score and details.
    """

    name: str
    check_fn: Callable[[Any, Any], float | tuple[float, dict[str, Any]]]
    threshold: float = 0.0

    def evaluate(self, input: Any, output: Any) -> DimensionResult:
        result = self.check_fn(input, output)
        if isinstance(result, tuple):
            score, details = result
        else:
            score, details = result, {}
        return DimensionResult(
            name=self.name,
            score=score,
            passed=score >= self.threshold,
            details=details,
        )
