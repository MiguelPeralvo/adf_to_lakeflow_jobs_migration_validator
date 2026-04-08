"""wkmigrate adapter — the ONLY file that imports wkmigrate types.

If wkmigrate renames a field or restructures a class, only this file breaks.
"""

from __future__ import annotations

from typing import Any

from wkmigrate.models.workflows.artifacts import PreparedWorkflow

from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    DependencyRef,
    ExpressionPair,
    NotebookSnapshot,
    SecretRef,
    TaskSnapshot,
)

_PLACEHOLDER_PATH = "/UNSUPPORTED_ADF_ACTIVITY"


def unwrap_adf_pipeline(payload: Any) -> Any:
    """Flatten Azure-native ADF JSON ``{name, properties: {...}}`` shape.

    wkmigrate's ``translate_pipeline`` expects the *flattened* shape
    ``{name, activities, parameters, ...}``. Azure ADF's REST API and the
    ``Get Pipeline`` factory client return the *wrapped* shape
    ``{name, properties: {activities, parameters, ...}}``. When the wrapped
    shape is fed straight into ``translate_pipeline``, the resulting
    ``Pipeline`` IR has zero tasks (silently — no warning is emitted).

    This helper unwraps the ``properties`` envelope so callers can pass
    either shape to ``adf_to_snapshot`` or to wkmigrate directly.

    The function is intentionally pure (no wkmigrate imports) so it lives
    in the fast unit-test tier. Non-dict inputs are returned unchanged for
    defensive symmetry with the rest of the adapter.
    """
    if not isinstance(payload, dict):
        return payload
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return payload
    flat = {k: v for k, v in payload.items() if k != "properties"}
    flat.update(properties)
    return flat


def adf_to_snapshot(payload: dict) -> ConversionSnapshot:
    """One-shot: take raw ADF pipeline JSON, return a ``ConversionSnapshot``.

    Centralises the four-step chain (unwrap → translate → prepare → adapt)
    so individual call sites in ``cli.py`` / ``api.py`` / ``mcp_server.py``
    don't have to duplicate it. Honours the LA-1 invariant by keeping all
    wkmigrate imports inside this module.

    Accepts either the flat ``{name, activities, ...}`` shape or the
    Azure-native wrapped ``{name, properties: {...}}`` shape; the unwrap
    happens transparently. The original ``payload`` is preserved as the
    snapshot's ``source_pipeline`` so downstream dimensions can still
    inspect the original ADF JSON.
    """
    # Imports are local because they fail when wkmigrate isn't installed
    # (graceful degradation, LA-3). The adapter is the only allowed file
    # for these imports per LA-1.
    from wkmigrate.preparers.preparer import prepare_workflow
    from wkmigrate.translators.pipeline_translators.pipeline_translator import (
        translate_pipeline,
    )

    flat_payload = unwrap_adf_pipeline(payload)
    pipeline_ir = translate_pipeline(flat_payload)
    prepared = prepare_workflow(pipeline_ir)
    return from_wkmigrate(payload, prepared)


def from_wkmigrate(source_pipeline: dict, prepared_workflow) -> ConversionSnapshot:
    """Convert wkmigrate PreparedWorkflow into the validator's generic contract.

    Args:
        source_pipeline: Raw ADF pipeline JSON.
        prepared_workflow: wkmigrate ``PreparedWorkflow`` instance.

    Returns:
        A ``ConversionSnapshot`` suitable for passing to ``evaluate()``.
    """
    prepared: PreparedWorkflow = prepared_workflow

    tasks = []
    placeholder_warnings: list[dict] = []
    for activity in prepared.activities:
        notebook_path = activity.task.get("notebook_task", {}).get("notebook_path", "")
        task_key = activity.task.get("task_key")
        if not isinstance(task_key, str) or not task_key:
            raise ValueError("Missing or invalid task_key in prepared activity task.")
        is_placeholder = notebook_path == _PLACEHOLDER_PATH
        tasks.append(
            TaskSnapshot(
                task_key=task_key,
                is_placeholder=is_placeholder,
            )
        )
        if is_placeholder:
            # L-F12: surface placeholder activities into not_translatable so
            # dimensions (expression_coverage, not_translatable_ratio) can
            # see them and downstream consumers can attribute the gap to
            # an unrecognised wkmigrate translator instead of "no
            # expressions in source" (the silent-empty case from L-F2).
            placeholder_warnings.append(
                {
                    "kind": "placeholder_activity",
                    "task_key": task_key,
                    "property": task_key,
                    "message": (
                        f"Activity '{task_key}' was substituted with a placeholder "
                        f"DatabricksNotebookActivity (wkmigrate did not recognise the "
                        f"source ADF activity type)."
                    ),
                }
            )

    notebooks = tuple(
        NotebookSnapshot(file_path=notebook.file_path, content=notebook.content) for notebook in prepared.all_notebooks
    )

    secrets = tuple(SecretRef(scope=secret.scope, key=secret.key) for secret in prepared.all_secrets)

    params = []
    if prepared.pipeline.parameters:
        for parameter in prepared.pipeline.parameters:
            name = parameter.get("name")
            if name:
                params.append(name)

    dependencies = []
    for task in prepared.pipeline.tasks:
        if task.depends_on:
            for dependency in task.depends_on:
                dependencies.append(
                    DependencyRef(
                        source_task=dependency.task_key,
                        target_task=task.task_key,
                    )
                )

    activities_top = source_pipeline.get("activities")
    adf_activities = (
        activities_top if activities_top is not None else source_pipeline.get("properties", {}).get("activities", [])
    )
    total_source_dependencies = sum(
        len(activity.get("depends_on") or activity.get("dependsOn") or []) for activity in adf_activities
    )

    expressions = []
    for task in prepared.pipeline.tasks:
        variable_name = getattr(task, "variable_name", None)
        variable_value = getattr(task, "variable_value", None)
        if isinstance(variable_name, str) and variable_name and isinstance(variable_value, str) and variable_value:
            expressions.append(
                ExpressionPair(
                    adf_expression=f"@variables('{variable_name}')",
                    python_code=variable_value,
                )
            )

    # Merge wkmigrate's pipeline-level warnings with the L-F12 placeholder
    # warnings we synthesised above. Placeholder warnings come last so they
    # appear in source-order beneath any pipeline-level translation warnings.
    all_not_translatable = tuple(prepared.pipeline.not_translatable) + tuple(placeholder_warnings)

    return ConversionSnapshot(
        tasks=tuple(tasks),
        notebooks=notebooks,
        secrets=secrets,
        parameters=tuple(params),
        dependencies=tuple(dependencies),
        not_translatable=all_not_translatable,
        resolved_expressions=tuple(expressions),
        source_pipeline=source_pipeline,
        total_source_dependencies=total_source_dependencies,
    )
