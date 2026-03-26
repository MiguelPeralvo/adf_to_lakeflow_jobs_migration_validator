"""ConversionSnapshot fixture builders — NO wkmigrate imports.

All core dimension tests use these builders to construct test data.
"""

from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    DependencyRef,
    ExpressionPair,
    NotebookSnapshot,
    SecretRef,
    TaskSnapshot,
)


def make_snapshot(
    tasks=(),
    notebooks=(),
    secrets=(),
    parameters=(),
    dependencies=(),
    not_translatable=(),
    resolved_expressions=(),
    source_pipeline=None,
    total_source_dependencies=0,
    expected_outputs=None,
    adf_run_outputs=None,
) -> ConversionSnapshot:
    return ConversionSnapshot(
        tasks=tuple(tasks),
        notebooks=tuple(notebooks),
        secrets=tuple(secrets),
        parameters=tuple(parameters),
        dependencies=tuple(dependencies),
        not_translatable=tuple(not_translatable),
        resolved_expressions=tuple(resolved_expressions),
        source_pipeline=source_pipeline or {},
        total_source_dependencies=total_source_dependencies,
        expected_outputs=dict(expected_outputs or {}),
        adf_run_outputs=dict(adf_run_outputs or {}),
    )


def make_task(task_key="task_1", is_placeholder=False):
    return TaskSnapshot(task_key=task_key, is_placeholder=is_placeholder)


def make_notebook(file_path="/notebooks/nb.py", content="# valid python\nx = 1"):
    return NotebookSnapshot(file_path=file_path, content=content)


def make_secret(scope="default", key="secret_key"):
    return SecretRef(scope=scope, key=key)


def make_dep(source="upstream", target="downstream"):
    return DependencyRef(source_task=source, target_task=target)


def make_expression(adf="@concat('a', 'b')", python="str('a') + str('b')"):
    return ExpressionPair(adf_expression=adf, python_code=python)
