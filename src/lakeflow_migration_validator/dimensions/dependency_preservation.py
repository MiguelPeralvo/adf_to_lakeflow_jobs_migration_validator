"""Dependency preservation dimension."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot


def compute_dependency_preservation(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of source dependencies that were preserved in the conversion."""
    if snapshot.total_source_dependencies == 0:
        return 1.0, {"total": 0, "preserved": 0}

    preserved = len(snapshot.dependencies)
    score = preserved / snapshot.total_source_dependencies
    return min(score, 1.0), {
        "total": snapshot.total_source_dependencies,
        "preserved": preserved,
    }
