"""Activity-context wrapper sweep (L-F5).

For each ADF activity type that wkmigrate adopts (or has deferred work for),
build a minimal valid ADF pipeline that injects a candidate ``adf_expression``
at that activity's expression-bearing property. Used to probe how wkmigrate
handles the same expression across different activity contexts.

The deferred wkmigrate#28 Lookup/Copy translator adoption work is the
primary target: until L-F5, the lmv golden set only ever wrapped expressions
as ``SetVariable.value``, which already adopted ``get_literal_or_expression``
in pr/27-1. The Lookup ``source.sql_reader_query`` and Copy
``source.sql_reader_query`` properties are NOT yet adopted upstream, so a
sweep across all 7 contexts surfaces the gap as a per-cell ``placeholder_count``
or ``not_translatable_count`` spike.

This module is intentionally pure (no wkmigrate imports) so the wrappers and
the ``sweep_activity_contexts`` helper run in the fast unit-test tier (LR-1).
The actual translation happens via a ``convert_fn`` argument the caller passes
in (typically ``adf_to_snapshot`` from the wkmigrate adapter, which is the
sole place wkmigrate is imported).

Provenance: ``dev/autodev-sessions/LMV-AUTODEV-2026-04-08-session2.md``
finding L-F5.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable


def _expression_node(value: str) -> dict[str, str]:
    """Build the canonical ADF expression-typed value dict."""
    return {"type": "Expression", "value": value}


def wrap_in_set_variable(adf_expression: str, name: str = "expr_test") -> dict[str, Any]:
    """Wrap *adf_expression* as a ``SetVariable.value`` (the baseline context).

    SetVariable was adopted in pr/27-1-expression-parser, so this is expected
    to resolve cleanly on alpha_1. Acts as a control row in the sweep.
    """
    return {
        "name": name,
        "activities": [
            {
                "name": "set_var",
                "type": "SetVariable",
                "depends_on": [],
                "variable_name": "result",
                "value": _expression_node(adf_expression),
            }
        ],
        "variables": {"result": {"type": "String"}},
    }


def wrap_in_if_condition(adf_expression: str, name: str = "expr_test") -> dict[str, Any]:
    """Wrap *adf_expression* as the ``IfCondition.expression`` predicate.

    wkmigrate's IfCondition translator expects a boolean expression. Non-boolean
    inputs probe the type-coercion / type-mismatch path: a math expression
    like ``@add(1, 2)`` injected here surfaces how wkmigrate handles a
    non-boolean predicate (NotTranslatableWarning, error, or silent coercion).

    The if_true / if_false branches are populated with a trivial
    DatabricksNotebook so wkmigrate has a non-empty body to wrap. Empty
    branches cause wkmigrate to fall back to a placeholder activity, which
    would obscure the predicate-translation signal we actually want to
    measure.
    """
    inner_notebook = {
        "name": "if_branch_noop",
        "type": "DatabricksNotebook",
        "depends_on": [],
        "notebook_path": "/Workspace/noop",
    }
    return {
        "name": name,
        "activities": [
            {
                "name": "if_cond",
                "type": "IfCondition",
                "depends_on": [],
                "expression": _expression_node(adf_expression),
                "if_true_activities": [inner_notebook],
                "if_false_activities": [dict(inner_notebook, name="if_branch_noop_else")],
            }
        ],
    }


def wrap_in_for_each(adf_expression: str, name: str = "expr_test") -> dict[str, Any]:
    """Wrap *adf_expression* as the ``ForEach.items`` array source.

    wkmigrate's ForEach translator expects an array. Non-array inputs probe
    how the items normaliser handles type mismatches (collection-category
    expressions are the natural fit; everything else is an adversarial probe).

    The inner activities array is populated with a trivial DatabricksNotebook
    so wkmigrate has a non-empty body to iterate over. Empty inner arrays
    cause wkmigrate to fall back to a placeholder activity, which would
    obscure the items-translation signal we actually want to measure.
    """
    return {
        "name": name,
        "activities": [
            {
                "name": "foreach",
                "type": "ForEach",
                "depends_on": [],
                "items": _expression_node(adf_expression),
                "activities": [
                    {
                        "name": "foreach_inner_noop",
                        "type": "DatabricksNotebook",
                        "depends_on": [],
                        "notebook_path": "/Workspace/noop",
                    }
                ],
            }
        ],
    }


def wrap_in_web_body(adf_expression: str, name: str = "expr_test") -> dict[str, Any]:
    """Wrap *adf_expression* as the ``WebActivity.body`` payload.

    WebActivity.body is a permissive string-typed field, so most expressions
    should resolve here. The url and method are also populated so wkmigrate
    can validate the activity shape.
    """
    return {
        "name": name,
        "activities": [
            {
                "name": "web",
                "type": "WebActivity",
                "depends_on": [],
                "url": "https://example.com/api",
                "method": "POST",
                "body": _expression_node(adf_expression),
                "headers": {},
            }
        ],
    }


def wrap_in_lookup_query(adf_expression: str, name: str = "expr_test") -> dict[str, Any]:
    """Wrap *adf_expression* as the ``Lookup.source.sql_reader_query`` property.

    **This is the primary L-F5 target.** The Lookup translator adoption is
    explicitly deferred per ``dev/pr-strategy-issue-27.md`` to proposed
    wkmigrate#28. So on alpha_1 this context is expected to either:

    - produce 0 resolved expressions (the property pass-through path), AND/OR
    - emit a placeholder_activity warning (the L-F12 surfacing path)

    Either signal lets ``sweep_activity_contexts`` quantify the deferred gap.
    """
    return {
        "name": name,
        "activities": [
            {
                "name": "lookup",
                "type": "Lookup",
                "depends_on": [],
                "first_row_only": True,
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": _expression_node(adf_expression),
                },
                "input_dataset_definitions": [
                    {
                        "name": "lookup_source",
                        "properties": {
                            "type": "AzureSqlTable",
                            "schema_type_properties_schema": "dbo",
                            "table": "config_table",
                        },
                        "linked_service_definition": {
                            "name": "sql_ls",
                            "properties": {
                                "type": "SqlServer",
                                "server": "demo.database.windows.net",
                                "database": "demo",
                            },
                        },
                    }
                ],
            }
        ],
    }


def wrap_in_copy_query(adf_expression: str, name: str = "expr_test") -> dict[str, Any]:
    """Wrap *adf_expression* as the ``Copy.source.sql_reader_query`` property.

    The other deferred wkmigrate#28 target. Same expectations as
    ``wrap_in_lookup_query``: pass-through behaviour and/or placeholder
    surfacing on alpha_1.

    A ``translator`` (TabularTranslator with one column mapping) is included
    because wkmigrate's Copy preparer raises ``ValueError("No column mapping
    provided for copy data task")`` when absent — the column mapping is a
    required field unrelated to the sql_reader_query expression we're
    actually probing. Providing a single trivial mapping lets the test get
    past validation and actually exercise the source.sql_reader_query
    translation path.
    """
    return {
        "name": name,
        "activities": [
            {
                "name": "copy",
                "type": "Copy",
                "depends_on": [],
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": _expression_node(adf_expression),
                },
                "sink": {"type": "AzureDatabricksDeltaLakeSink"},
                "translator": {
                    "type": "TabularTranslator",
                    "mappings": [
                        {
                            # wkmigrate's _parse_dataset_mapping requires sink.type
                            # (otherwise the Copy activity becomes UnsupportedValue,
                            # not because of the source.sql_reader_query at all). The
                            # original W-8 finding mistakenly attributed the resulting
                            # placeholder to the Expression-typed sql_reader_query path
                            # — providing a sink.type unblocks the Copy translator and
                            # lets the sweep actually exercise the source query field.
                            "source": {"name": "src_col"},
                            "sink": {"name": "tgt_col", "type": "string"},
                        }
                    ],
                },
                "input_dataset_definitions": [
                    {
                        "name": "copy_source",
                        "properties": {
                            "type": "AzureSqlTable",
                            "schema_type_properties_schema": "dbo",
                            "table": "src_table",
                        },
                        "linked_service_definition": {
                            "name": "sql_src_ls",
                            "properties": {
                                "type": "SqlServer",
                                "server": "demo.database.windows.net",
                                "database": "demo",
                            },
                        },
                    }
                ],
                "output_dataset_definitions": [
                    {
                        "name": "copy_sink",
                        "properties": {
                            "type": "AzureDatabricksDeltaLakeDataset",
                            "table": "tgt_table",
                        },
                        "linked_service_definition": {
                            "name": "delta_sink_ls",
                            "properties": {"type": "AzureBlobFS"},
                        },
                    }
                ],
            }
        ],
    }


def wrap_in_notebook_base_param(adf_expression: str, name: str = "expr_test") -> dict[str, Any]:
    """Wrap *adf_expression* as a ``DatabricksNotebook.base_parameters`` value.

    base_parameters expressions were adopted in pr/27-3-translator-adoption,
    so this should resolve cleanly on alpha_1 — another control row in the
    sweep alongside SetVariable.
    """
    return {
        "name": name,
        "activities": [
            {
                "name": "notebook",
                "type": "DatabricksNotebook",
                "depends_on": [],
                "notebook_path": "/Workspace/test_notebook",
                "base_parameters": {
                    "param_under_test": _expression_node(adf_expression),
                },
            }
        ],
    }


# Registry — drives ``sweep_activity_contexts``. Order is significant for the
# emitted report (control rows first, deferred-#28 targets last so they're
# easy to scan).
ACTIVITY_CONTEXTS: dict[str, Callable[[str, str], dict[str, Any]]] = {
    "set_variable": wrap_in_set_variable,
    "notebook_base_param": wrap_in_notebook_base_param,
    "if_condition": wrap_in_if_condition,
    "for_each": wrap_in_for_each,
    "web_body": wrap_in_web_body,
    "lookup_query": wrap_in_lookup_query,
    "copy_query": wrap_in_copy_query,
}


def _new_cell() -> dict[str, Any]:
    return {
        "total": 0,
        "resolved": 0,
        "placeholder_count": 0,
        "not_translatable_count": 0,
        "error_count": 0,
        "sample_failures": [],
    }


def _new_context_total() -> dict[str, int]:
    return {
        "total": 0,
        "resolved": 0,
        "placeholder_count": 0,
        "not_translatable_count": 0,
        "error_count": 0,
    }


def sweep_activity_contexts(
    corpus: Iterable[dict[str, Any]],
    convert_fn: Callable[[dict], Any],
    contexts: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Run a corpus of expression pairs through every activity context.

    For each (entry, context) pair, build the wrapped pipeline, run it
    through *convert_fn*, and aggregate per-cell + per-context counts of
    resolved expressions, placeholder warnings, other not_translatable
    entries, and errors.

    Args:
        corpus: iterable of dicts each containing at least ``adf_expression``
            and ``category`` keys (typically entries from
            ``golden_sets/expressions.json``).
        convert_fn: callable taking an ADF JSON dict and returning a
            ``ConversionSnapshot`` (typically
            ``lakeflow_migration_validator.adapters.wkmigrate_adapter.adf_to_snapshot``).
            Kept as a parameter so this module has no wkmigrate import and
            can run in the fast unit-test tier.
        contexts: explicit subset of ``ACTIVITY_CONTEXTS`` keys to exercise.
            Unknown names are silently skipped. Default: all contexts.

    Returns:
        ``{"by_cell": ..., "by_context": ..., "contexts_run": [...]}`` —
        ``by_cell`` is keyed ``"<category>,<context>"``, ``by_context`` is
        keyed by context name. Each cell records counters and up to 3
        sample failures (for cells with zero resolved expressions or any
        errors).
    """
    if contexts is None:
        selected = list(ACTIVITY_CONTEXTS.keys())
    else:
        selected = [c for c in contexts if c in ACTIVITY_CONTEXTS]

    by_cell: dict[str, dict[str, Any]] = defaultdict(_new_cell)
    by_context: dict[str, dict[str, int]] = defaultdict(_new_context_total)

    for entry in corpus:
        adf_expression = entry["adf_expression"]
        category = entry.get("category", "unknown")
        for context_name in selected:
            wrap_fn = ACTIVITY_CONTEXTS[context_name]
            cell_key = f"{category},{context_name}"
            cell = by_cell[cell_key]
            ctx_totals = by_context[context_name]

            cell["total"] += 1
            ctx_totals["total"] += 1

            try:
                pipeline = wrap_fn(adf_expression, name=f"{context_name}_{category}_test")
                snap = convert_fn(pipeline)
            except Exception as exc:  # noqa: BLE001  defensive: any wkmigrate failure
                cell["error_count"] += 1
                ctx_totals["error_count"] += 1
                if len(cell["sample_failures"]) < 3:
                    cell["sample_failures"].append(
                        {
                            "adf_expression": adf_expression,
                            "expected_python": entry.get("expected_python", ""),
                            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                        }
                    )
                continue

            resolved_count = len(snap.resolved_expressions)
            placeholder_count = sum(1 for nt in snap.not_translatable if nt.get("kind") == "placeholder_activity")
            not_translatable_count = len(snap.not_translatable)

            if resolved_count > 0:
                cell["resolved"] += 1
                ctx_totals["resolved"] += 1
            if placeholder_count > 0:
                cell["placeholder_count"] += 1
                ctx_totals["placeholder_count"] += 1
            if not_translatable_count > 0:
                cell["not_translatable_count"] += 1
                ctx_totals["not_translatable_count"] += 1

            if resolved_count == 0 and len(cell["sample_failures"]) < 3:
                cell["sample_failures"].append(
                    {
                        "adf_expression": adf_expression,
                        "expected_python": entry.get("expected_python", ""),
                        "not_translatable": [dict(nt) for nt in snap.not_translatable[:3]],
                    }
                )

    return {
        "by_cell": dict(by_cell),
        "by_context": dict(by_context),
        "contexts_run": selected,
    }
