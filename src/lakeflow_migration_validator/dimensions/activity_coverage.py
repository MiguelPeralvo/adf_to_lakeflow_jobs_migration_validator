"""Activity coverage dimension."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot


def compute_activity_coverage(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of tasks that are not placeholder activities."""
    total = len(snapshot.tasks)
    if total == 0:
        return 1.0, {"total": 0, "covered": 0, "placeholders": []}

    placeholders = [task.task_key for task in snapshot.tasks if task.is_placeholder]
    covered = total - len(placeholders)
    return covered / total, {
        "total": total,
        "covered": covered,
        "placeholders": placeholders,
    }
