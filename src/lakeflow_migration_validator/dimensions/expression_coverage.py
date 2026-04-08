"""Expression coverage dimension."""

from __future__ import annotations

from typing import Any

from lakeflow_migration_validator.contract import ConversionSnapshot


def _source_contains_expressions(value: Any) -> bool:
    """Recursively check whether *value* contains any ADF expression literal.

    ADF expressions are encoded in the source JSON as dicts of the form
    ``{"type": "Expression", "value": "@..."}``. This walker returns True
    on the first such dict it finds at any depth.

    Used by ``compute_expression_coverage`` to distinguish "no expressions
    in source" (vacuously fully covered, score 1.0) from "source has
    expressions but the adapter extracted none" (silent-empty, score 0.0
    with measurable=False — see L-F1/L-F2/L-F12 in
    ``dev/autodev-sessions/LMV-AUTODEV-2026-04-08.md``).
    """
    if isinstance(value, dict):
        if value.get("type") == "Expression" and "value" in value:
            return True
        return any(_source_contains_expressions(child) for child in value.values())
    if isinstance(value, list):
        return any(_source_contains_expressions(child) for child in value)
    return False


def compute_expression_coverage(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of expression properties that were successfully resolved.

    Returns ``(score, details)`` where:

    - ``score`` is in ``[0.0, 1.0]``.
    - ``details["measurable"]`` is a boolean: True when the score is a
      faithful measurement, False when the snapshot has no resolved nor
      unsupported expressions but the source pipeline *does* contain
      ``@``-expressions (a silent-empty case caused by an upstream adapter
      bug or a wkmigrate translator gap — see L-F1, L-F12). When measurable
      is False the score is reported as ``0.0`` and ``details["reason"]``
      explains why.
    """
    unsupported = [entry for entry in snapshot.not_translatable if "expression" in entry.get("message", "").lower()]
    resolved = len(snapshot.resolved_expressions)
    total = resolved + len(unsupported)

    if total == 0:
        # Vacuous case — distinguish "no expressions in source" (vacuously
        # 100% covered) from "evaluator could not measure" (silent-empty).
        if _source_contains_expressions(snapshot.source_pipeline):
            return 0.0, {
                "total": 0,
                "resolved": 0,
                "unsupported": [],
                "measurable": False,
                "reason": "source_has_expressions_but_adapter_extracted_none",
            }
        return 1.0, {
            "total": 0,
            "resolved": 0,
            "unsupported": [],
            "measurable": True,
            "reason": "no_expressions_in_source",
        }

    return resolved / total, {
        "total": total,
        "resolved": resolved,
        "unsupported": unsupported,
        "measurable": True,
    }
