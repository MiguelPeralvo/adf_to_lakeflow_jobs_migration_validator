"""Not-translatable ratio dimension."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot


def compute_not_translatable_ratio(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Inverse ratio of not-translatable warnings to estimated total properties."""
    count = len(snapshot.not_translatable)
    estimated_properties = max(len(snapshot.tasks) * 5, 1)
    ratio = count / estimated_properties
    return max(0.0, 1.0 - ratio), {
        "not_translatable_count": count,
        "estimated_total_properties": estimated_properties,
        "entries": list(snapshot.not_translatable),
    }
