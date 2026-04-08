"""Serialization helpers for ConversionSnapshot."""

from __future__ import annotations

from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    DependencyRef,
    ExpressionPair,
    NotebookSnapshot,
    SecretRef,
    TaskSnapshot,
)


def snapshot_from_dict(payload: dict) -> ConversionSnapshot:
    """Build a ConversionSnapshot from a plain dict payload."""
    return ConversionSnapshot(
        tasks=tuple(
            TaskSnapshot(task_key=item["task_key"], is_placeholder=bool(item["is_placeholder"]))
            for item in payload.get("tasks", [])
        ),
        notebooks=tuple(
            NotebookSnapshot(file_path=item["file_path"], content=item["content"])
            for item in payload.get("notebooks", [])
        ),
        secrets=tuple(SecretRef(scope=item["scope"], key=item["key"]) for item in payload.get("secrets", [])),
        parameters=tuple(payload.get("parameters", [])),
        dependencies=tuple(
            DependencyRef(source_task=item["source_task"], target_task=item["target_task"])
            for item in payload.get("dependencies", [])
        ),
        not_translatable=tuple(payload.get("not_translatable", [])),
        resolved_expressions=tuple(
            ExpressionPair(adf_expression=item["adf_expression"], python_code=item["python_code"])
            for item in payload.get("resolved_expressions", [])
        ),
        source_pipeline=payload.get("source_pipeline", {}),
        total_source_dependencies=int(payload.get("total_source_dependencies", 0)),
        expected_outputs=dict(payload.get("expected_outputs", {})),
        adf_run_outputs=dict(payload.get("adf_run_outputs", {})),
    )


def snapshot_to_dict(snapshot: ConversionSnapshot) -> dict:
    """Convert a ConversionSnapshot to plain dict form."""
    return {
        "tasks": [{"task_key": task.task_key, "is_placeholder": task.is_placeholder} for task in snapshot.tasks],
        "notebooks": [
            {"file_path": notebook.file_path, "content": notebook.content} for notebook in snapshot.notebooks
        ],
        "secrets": [{"scope": secret.scope, "key": secret.key} for secret in snapshot.secrets],
        "parameters": list(snapshot.parameters),
        "dependencies": [
            {"source_task": dep.source_task, "target_task": dep.target_task} for dep in snapshot.dependencies
        ],
        "not_translatable": list(snapshot.not_translatable),
        "resolved_expressions": [
            {"adf_expression": pair.adf_expression, "python_code": pair.python_code}
            for pair in snapshot.resolved_expressions
        ],
        "source_pipeline": dict(snapshot.source_pipeline),
        "total_source_dependencies": snapshot.total_source_dependencies,
        "expected_outputs": dict(snapshot.expected_outputs),
        "adf_run_outputs": dict(snapshot.adf_run_outputs),
    }


def snapshot_from_adf_payload(payload: dict) -> ConversionSnapshot:
    """Best-effort ConversionSnapshot conversion from adf-like payloads."""
    if "tasks" in payload and "notebooks" in payload:
        return snapshot_from_dict(payload)
    if "expected_snapshot" in payload and isinstance(payload["expected_snapshot"], dict):
        return snapshot_from_dict(payload["expected_snapshot"])

    return ConversionSnapshot(
        tasks=(),
        notebooks=(),
        secrets=(),
        parameters=(),
        dependencies=(),
        source_pipeline=payload,
    )
