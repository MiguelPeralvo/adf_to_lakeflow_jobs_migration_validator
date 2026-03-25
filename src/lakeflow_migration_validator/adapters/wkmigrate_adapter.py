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
        task_key = activity.task.get("task_key")
        if not isinstance(task_key, str) or not task_key:
            raise ValueError("Missing or invalid task_key in prepared activity task.")
        tasks.append(
            TaskSnapshot(
                task_key=task_key,
                is_placeholder=(notebook_path == _PLACEHOLDER_PATH),
            )
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
        len(activity.get("depends_on") or activity.get("dependsOn") or [])
        for activity in adf_activities
    )

    expressions = []
    for task in prepared.pipeline.tasks:
        variable_name = getattr(task, "variable_name", None)
        variable_value = getattr(task, "variable_value", None)
        if (
            isinstance(variable_name, str)
            and variable_name
            and isinstance(variable_value, str)
            and variable_value
        ):
            expressions.append(
                ExpressionPair(
                    adf_expression=f"@variables('{variable_name}')",
                    python_code=variable_value,
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
