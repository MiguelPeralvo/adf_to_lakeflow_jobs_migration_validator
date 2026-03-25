"""wkmigrate adapter — the ONLY file that imports wkmigrate types.

If wkmigrate renames a field or restructures a class, only this file breaks.
"""

from __future__ import annotations

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
    for activity in prepared.activities:
        notebook_path = activity.task.get("notebook_task", {}).get("notebook_path", "")
        tasks.append(
            TaskSnapshot(
                task_key=activity.task.get("task_key", "unknown"),
                is_placeholder=(notebook_path == _PLACEHOLDER_PATH),
            )
        )

    notebooks = tuple(
        NotebookSnapshot(file_path=notebook.file_path, content=notebook.content)
        for notebook in prepared.all_notebooks
    )

    secrets = tuple(SecretRef(scope=secret.scope, key=secret.key) for secret in prepared.all_secrets)

    params = []
    if prepared.pipeline.parameters:
        for parameter in prepared.pipeline.parameters:
            params.append(parameter.get("name", ""))

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

    adf_activities = source_pipeline.get("activities") or source_pipeline.get("properties", {}).get("activities", [])
    total_source_dependencies = sum(len(activity.get("depends_on", [])) for activity in adf_activities)

    expressions = []
    for task in prepared.pipeline.tasks:
        if hasattr(task, "variable_value") and hasattr(task, "variable_name"):
            expressions.append(
                ExpressionPair(
                    adf_expression=f"@variables('{task.variable_name}')",
                    python_code=task.variable_value,
                )
            )

    return ConversionSnapshot(
        tasks=tuple(tasks),
        notebooks=notebooks,
        secrets=secrets,
        parameters=tuple(params),
        dependencies=tuple(dependencies),
        not_translatable=tuple(prepared.pipeline.not_translatable),
        resolved_expressions=tuple(expressions),
        source_pipeline=source_pipeline,
        total_source_dependencies=total_source_dependencies,
    )
