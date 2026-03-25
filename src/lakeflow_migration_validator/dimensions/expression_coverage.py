"""Expression coverage dimension."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot


def compute_expression_coverage(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of expression properties that were successfully resolved."""
    unsupported = [
        entry
        for entry in snapshot.not_translatable
        if "expression" in entry.get("message", "").lower()
        or "unsupported" in entry.get("message", "").lower()
    ]
    resolved = len(snapshot.resolved_expressions)
    total = resolved + len(unsupported)

    if total == 0:
        return 1.0, {"total": 0, "resolved": 0, "unsupported": []}

    return resolved / total, {
        "total": total,
        "resolved": resolved,
        "unsupported": unsupported,
    }
