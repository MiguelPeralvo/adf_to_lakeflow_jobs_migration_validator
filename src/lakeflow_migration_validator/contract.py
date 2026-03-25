"""ConversionSnapshot — the validator's tool-agnostic view of a conversion.

All dimensions operate on this contract. NO conversion-tool-specific imports.
Adapters (e.g., wkmigrate_adapter) produce ConversionSnapshot instances from
tool-specific types.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    """The validator's view of a single task in the converted workflow."""

    task_key: str
    is_placeholder: bool


@dataclass(frozen=True, slots=True)
class NotebookSnapshot:
    """The validator's view of a generated notebook."""

    file_path: str
    content: str


@dataclass(frozen=True, slots=True)
class SecretRef:
    """A (scope, key) pair declared in the conversion's secret instructions."""

    scope: str
    key: str


@dataclass(frozen=True, slots=True)
class DependencyRef:
    """A preserved task dependency in the converted workflow."""

    source_task: str
    target_task: str


@dataclass(frozen=True, slots=True)
class ExpressionPair:
    """An ADF expression and its generated Python translation."""

    adf_expression: str
    python_code: str


@dataclass(frozen=True, slots=True)
class ConversionSnapshot:
    """The validator's complete, tool-agnostic view of a conversion.

    Built by an adapter (e.g., ``wkmigrate_adapter.from_wkmigrate``). Dimensions
    only import this — never the conversion tool's own types.
    """

    tasks: tuple[TaskSnapshot, ...]
    notebooks: tuple[NotebookSnapshot, ...]
    secrets: tuple[SecretRef, ...]
    parameters: tuple[str, ...]
    dependencies: tuple[DependencyRef, ...]
    not_translatable: tuple[dict, ...] = ()
    resolved_expressions: tuple[ExpressionPair, ...] = ()
    source_pipeline: dict = field(default_factory=dict)
    total_source_dependencies: int = 0
