"""Parameter completeness dimension."""

from __future__ import annotations

import re

from lakeflow_migration_validator.contract import ConversionSnapshot

_WIDGET_GET_PATTERN = re.compile(r"dbutils\.widgets\.get\(\s*['\"]([^'\"]+)['\"]\s*\)")


def compute_parameter_completeness(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of dbutils.widgets.get references that have matching parameters."""
    defined = set(snapshot.parameters)
    referenced = set()
    for notebook in snapshot.notebooks:
        for match in _WIDGET_GET_PATTERN.finditer(notebook.content):
            referenced.add(match.group(1))

    if not referenced:
        return 1.0, {"defined": sorted(defined), "referenced": [], "missing": []}

    missing = referenced - defined
    score = (len(referenced) - len(missing)) / len(referenced)
    return score, {
        "defined": sorted(defined),
        "referenced": sorted(referenced),
        "missing": sorted(missing),
    }
