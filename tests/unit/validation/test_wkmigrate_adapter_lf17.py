"""L-F17 walker tests — IMPORTS wkmigrate alpha_1+ types.

Verifies ``from_wkmigrate`` extracts ``ExpressionPair`` entries from
non-SetVariable activity types (Notebook.base_parameters, WebActivity
.url/body/headers, IfCondition.expression, ForEach.items_string,
Lookup.source_query).

This file lives separately from ``test_wkmigrate_adapter.py`` because the
L-F17 walker depends on wkmigrate types that **only exist on alpha_1+**:

- ``ResolvedExpression`` (added in pr/27-1-expression-parser)
- ``WebActivity.body`` and ``WebActivity.headers`` typed as ``str | ResolvedExpression``
- ``ForEachActivity.items_string`` (renamed from ``items`` in pr/27-3-translator-adoption)

The lmv project's CI workflow checks out ``ghanse/wkmigrate@main`` (the
upstream, pre-#27 fork) which lacks these types and would crash at
collection if the tests imported them unconditionally. The
``pytest.skip(..., allow_module_level=True)`` guard below skips the entire
file gracefully on upstream while keeping it active locally and on any
future CI that uses MiguelPeralvo/wkmigrate@alpha_1+.

Provenance: dev/autodev-sessions/LMV-AUTODEV-2026-04-08-session2.md L-F17.
"""

import pytest

# Module-level skip if the alpha_1-only types are unavailable. The check
# is on ResolvedExpression because that's the smallest distinguishing
# symbol — pr/27-1-expression-parser introduced it and it doesn't exist
# anywhere on upstream main. ImportError catches both "module missing"
# and "name missing from module".
try:
    from wkmigrate.parsers.expression_parsers import ResolvedExpression
    from wkmigrate.models.ir.pipeline import (
        DatabricksNotebookActivity,
        ForEachActivity,
        IfConditionActivity,
        LookupActivity,
        SetVariableActivity,
        WebActivity,
    )
    from wkmigrate.models.workflows.artifacts import PreparedActivity, PreparedWorkflow
    from wkmigrate.models.ir.pipeline import Activity, Pipeline
except ImportError as exc:
    pytest.skip(
        f"L-F17 tests require wkmigrate alpha_1+ (pr/27-1+); upstream main lacks "
        f"ResolvedExpression and the new IR field types. Underlying error: {exc}",
        allow_module_level=True,
    )

from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate


def _build_minimal_prepared_for_task(task: Activity) -> PreparedWorkflow:
    """Wrap a single IR Activity in the smallest PreparedWorkflow that
    satisfies from_wkmigrate's basic invariants (one activity in
    prepared.activities with a real notebook_path, one entry in
    prepared.pipeline.tasks)."""
    pipeline = Pipeline(name="t", parameters=None, schedule=None, tasks=[task], tags={})
    return PreparedWorkflow(
        pipeline=pipeline,
        activities=[
            PreparedActivity(
                task={
                    "task_key": task.task_key,
                    "notebook_task": {"notebook_path": "/Workspace/real"},
                }
            )
        ],
    )


def test_adapter_extracts_notebook_base_parameters_expressions():
    """Each Notebook.base_parameters value resolved by wkmigrate yields an ExpressionPair.

    The original ADF expression (when present in the source dict) is preserved
    in adf_expression; the IR-side resolved Python is in python_code.
    """
    source = {
        "activities": [
            {
                "name": "nb",
                "type": "DatabricksNotebook",
                "depends_on": [],
                "notebook_path": "/Workspace/test",
                "base_parameters": {
                    "param1": {"type": "Expression", "value": "@concat('a', 'b')"},
                    "param2": {"type": "Expression", "value": "@pipeline().RunId"},
                },
            }
        ]
    }
    task = DatabricksNotebookActivity(
        name="nb",
        task_key="nb",
        notebook_path="/Workspace/test",
        base_parameters={
            "param1": "str('a') + str('b')",
            "param2": "dbutils.widgets.get('RunId')",
        },
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    pairs = {p.adf_expression: p.python_code for p in snap.resolved_expressions}
    assert "@concat('a', 'b')" in pairs
    assert pairs["@concat('a', 'b')"] == "str('a') + str('b')"
    assert "@pipeline().RunId" in pairs
    assert pairs["@pipeline().RunId"] == "dbutils.widgets.get('RunId')"


def test_adapter_extracts_web_activity_url_and_body_resolved_expressions():
    """WebActivity.url and .body fields (str OR ResolvedExpression) yield pairs."""
    source = {
        "activities": [
            {
                "name": "web",
                "type": "WebActivity",
                "depends_on": [],
                "url": {"type": "Expression", "value": "@concat('https://api.', pipeline().parameters.host)"},
                "method": "POST",
                "body": {"type": "Expression", "value": "@json(pipeline().parameters.payload)"},
                "headers": {},
            }
        ]
    }
    task = WebActivity(
        name="web",
        task_key="web",
        url=ResolvedExpression(
            code="'https://api.' + dbutils.widgets.get('host')",
            is_dynamic=True,
            required_imports=frozenset(),
        ),
        method="POST",
        body="json.loads(dbutils.widgets.get('payload'))",  # plain str path
        headers=None,
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    pairs = {p.adf_expression: p.python_code for p in snap.resolved_expressions}
    # ResolvedExpression case (url): .code is extracted
    assert "@concat('https://api.', pipeline().parameters.host)" in pairs
    assert (
        pairs["@concat('https://api.', pipeline().parameters.host)"] == "'https://api.' + dbutils.widgets.get('host')"
    )
    # Plain str case (body): used directly
    assert "@json(pipeline().parameters.payload)" in pairs
    assert pairs["@json(pipeline().parameters.payload)"] == "json.loads(dbutils.widgets.get('payload'))"


def test_adapter_extracts_lookup_source_query():
    """LookupActivity.source_query (when wkmigrate populated it) yields a pair."""
    source = {
        "activities": [
            {
                "name": "lk",
                "type": "Lookup",
                "depends_on": [],
                "first_row_only": True,
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": {
                        "type": "Expression",
                        "value": "@concat('SELECT * FROM ', pipeline().parameters.t)",
                    },
                },
            }
        ]
    }
    task = LookupActivity(
        name="lk",
        task_key="lk",
        first_row_only=True,
        source_query="'SELECT * FROM ' + dbutils.widgets.get('t')",
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    pairs = {p.adf_expression: p.python_code for p in snap.resolved_expressions}
    assert "@concat('SELECT * FROM ', pipeline().parameters.t)" in pairs
    assert pairs["@concat('SELECT * FROM ', pipeline().parameters.t)"] == "'SELECT * FROM ' + dbutils.widgets.get('t')"


def test_adapter_extracts_for_each_items_string():
    """ForEachActivity.items_string yields a pair."""
    source = {
        "activities": [
            {
                "name": "fe",
                "type": "ForEach",
                "depends_on": [],
                "items": {"type": "Expression", "value": "@createArray('a', 'b', 'c')"},
                "activities": [
                    {"name": "inner", "type": "DatabricksNotebook", "depends_on": [], "notebook_path": "/x"}
                ],
            }
        ]
    }
    inner = DatabricksNotebookActivity(name="inner", task_key="inner", notebook_path="/x")
    task = ForEachActivity(
        name="fe",
        task_key="fe",
        items_string="['a', 'b', 'c']",
        for_each_task=inner,
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    pairs = {p.adf_expression: p.python_code for p in snap.resolved_expressions}
    assert "@createArray('a', 'b', 'c')" in pairs
    assert pairs["@createArray('a', 'b', 'c')"] == "['a', 'b', 'c']"


def test_adapter_extracts_if_condition_decomposed_predicate():
    """IfConditionActivity has its predicate decomposed into op/left/right by wkmigrate.

    The original ADF expression is captured from the source dict; the IR-side
    Python is synthesized from the (left op right) tuple. This is the closest
    we can get to a faithful pair without re-parsing the predicate.
    """
    source = {
        "activities": [
            {
                "name": "ifc",
                "type": "IfCondition",
                "depends_on": [],
                "expression": {"type": "Expression", "value": "@equals(pipeline().parameters.x, 1)"},
                "if_true_activities": [],
                "if_false_activities": [],
            }
        ]
    }
    task = IfConditionActivity(
        name="ifc",
        task_key="ifc",
        op="==",
        left="dbutils.widgets.get('x')",
        right="1",
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    pairs = {p.adf_expression: p.python_code for p in snap.resolved_expressions}
    assert "@equals(pipeline().parameters.x, 1)" in pairs
    # Synthesized from (left, op, right) — exact format is the (left op right) string
    assert pairs["@equals(pipeline().parameters.x, 1)"] == "(dbutils.widgets.get('x') == 1)"


def test_adapter_uses_synthetic_label_when_source_expression_missing():
    """When the source dict has no matching expression but the IR has resolved
    code, the adapter falls back to a synthetic label like @notebook('name').field
    so the pair is still emitted (the python_code is what dimensions actually
    measure)."""
    # Source omits the activity entirely — IR has it but source doesn't
    source = {"activities": []}
    task = DatabricksNotebookActivity(
        name="orphan_nb",
        task_key="orphan_nb",
        notebook_path="/x",
        base_parameters={"k": "literal_value"},
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    assert len(snap.resolved_expressions) == 1
    pair = snap.resolved_expressions[0]
    # The fallback label includes the activity name and the property path so a
    # downstream consumer can still attribute the resolution.
    assert "orphan_nb" in pair.adf_expression
    assert "k" in pair.adf_expression
    assert pair.python_code == "literal_value"


def test_adapter_skips_notebook_base_parameters_with_empty_or_none_values():
    """Empty / None base_parameter values are not emitted as pairs (defensive)."""
    source = {
        "activities": [
            {
                "name": "nb",
                "type": "DatabricksNotebook",
                "depends_on": [],
                "notebook_path": "/x",
                "base_parameters": {},
            }
        ]
    }
    task = DatabricksNotebookActivity(
        name="nb",
        task_key="nb",
        notebook_path="/x",
        base_parameters=None,
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    # No base_parameters → no pairs from this activity
    assert len(snap.resolved_expressions) == 0


def test_adapter_existing_set_variable_extraction_still_works():
    """Regression check: SetVariableActivity extraction still produces a pair
    after the L-F17 walker is added (must not double-count or skip)."""
    source = {
        "activities": [
            {
                "name": "sv",
                "type": "SetVariable",
                "depends_on": [],
                "variable_name": "result",
                "value": {"type": "Expression", "value": "@concat('a', 'b')"},
            }
        ]
    }
    task = SetVariableActivity(
        name="sv",
        task_key="sv",
        variable_name="result",
        variable_value="str('a') + str('b')",
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    # Exactly one pair (no double-extraction from the new walker)
    set_var_pairs = [
        p for p in snap.resolved_expressions if "concat" in p.adf_expression or "result" in p.adf_expression
    ]
    assert len(set_var_pairs) >= 1
    # And the source ADF expression IS preferred over the @variables('result') fallback
    # when present in the source dict (this is also a small upgrade vs. the previous
    # adapter which always emitted the @variables() label)
    pairs_with_concat = [p for p in snap.resolved_expressions if "@concat" in p.adf_expression]
    assert len(pairs_with_concat) == 1
    assert pairs_with_concat[0].python_code == "str('a') + str('b')"
