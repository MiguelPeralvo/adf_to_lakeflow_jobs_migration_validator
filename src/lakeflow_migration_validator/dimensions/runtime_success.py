"""Runtime success dimension builder backed by ExecutionDimension."""

from __future__ import annotations

from lakeflow_migration_validator.dimensions.execution import ExecutionDimension, ExecutionRunner


def create_runtime_success_dimension(
    runner: ExecutionRunner,
    *,
    threshold: float = 1.0,
    test_params: dict[str, str] | None = None,
) -> ExecutionDimension:
    """Create the concrete runtime success dimension."""
    return ExecutionDimension(
        name="runtime_success",
        runner=runner,
        test_params=dict(test_params or {}),
        threshold=threshold,
    )
