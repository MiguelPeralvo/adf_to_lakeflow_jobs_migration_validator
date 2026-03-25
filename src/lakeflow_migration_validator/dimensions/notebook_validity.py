"""Notebook validity dimension."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot


def compute_notebook_validity(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of generated notebooks that compile without SyntaxError."""
    if not snapshot.notebooks:
        return 1.0, {"total": 0, "valid": 0, "errors": []}

    errors = []
    for notebook in snapshot.notebooks:
        try:
            compile(notebook.content, notebook.file_path, "exec")
        except (SyntaxError, ValueError, TypeError) as exc:
            errors.append({"file_path": notebook.file_path, "error": str(exc)})

    valid = len(snapshot.notebooks) - len(errors)
    return valid / len(snapshot.notebooks), {
        "total": len(snapshot.notebooks),
        "valid": valid,
        "errors": errors,
    }
