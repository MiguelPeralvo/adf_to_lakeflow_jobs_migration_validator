"""Control flow fidelity dimension."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot

_CONTROL_FLOW_TYPES = {"ForEach", "IfCondition"}


def _collect_control_flow(activities: list[dict]) -> list[str]:
    """Recursively collect names of ForEach/IfCondition activities."""
    found: list[str] = []
    for activity in activities:
        act_type = activity.get("type", "")
        if act_type in _CONTROL_FLOW_TYPES:
            found.append(activity.get("name", ""))
        # Recurse into children regardless of parent type
        found.extend(_collect_control_flow(activity.get("activities", [])))
        found.extend(_collect_control_flow(activity.get("if_true_activities", [])))
        found.extend(_collect_control_flow(activity.get("if_false_activities", [])))
    return found


def compute_control_flow_fidelity(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of source control-flow activities preserved in the converted workflow."""
    activities = snapshot.source_pipeline.get("properties", {}).get("activities", [])
    if not activities:
        activities = snapshot.source_pipeline.get("activities", [])
    cf_names = _collect_control_flow(activities)
    total = len(cf_names)
    if total == 0:
        return 1.0, {"total": 0, "preserved": 0, "missing": []}

    task_keys = {t.task_key for t in snapshot.tasks if not t.is_placeholder}
    missing = [name for name in cf_names if name not in task_keys]
    preserved = total - len(missing)
    return preserved / total, {"total": total, "preserved": preserved, "missing": missing}
