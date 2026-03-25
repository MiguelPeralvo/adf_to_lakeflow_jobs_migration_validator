"""Quality dimension protocols and result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class DimensionResult:
    """Result of evaluating a single quality dimension."""

    name: str
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


class Dimension(Protocol):
    """Protocol for a quality dimension that can evaluate an input/output pair."""

    name: str
    threshold: float

    def evaluate(self, input: Any, output: Any) -> DimensionResult: ...
