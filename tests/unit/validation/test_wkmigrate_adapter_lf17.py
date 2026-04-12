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
        CopyActivity,
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
        op="EQUAL_TO",
        left="dbutils.widgets.get('x')",
        right="1",
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    pairs = {p.adf_expression: p.python_code for p in snap.resolved_expressions}
    assert "@equals(pipeline().parameters.x, 1)" in pairs
    # L-F17 walker maps IR enum EQUAL_TO → Python ==
    assert pairs["@equals(pipeline().parameters.x, 1)"] == "(dbutils.widgets.get('x') == 1)"


def test_adapter_maps_ir_op_enum_to_python_operators():
    """All IR condition ops (EQUAL_TO, GREATER_THAN, etc.) are mapped to Python operators."""
    from lakeflow_migration_validator.adapters.wkmigrate_adapter import _IR_OP_TO_PYTHON

    source = {"activities": []}
    for ir_op, py_op in _IR_OP_TO_PYTHON.items():
        task = IfConditionActivity(name="ifc", task_key="ifc", op=ir_op, left="a", right="b")
        prepared = _build_minimal_prepared_for_task(task)
        snap = from_wkmigrate(source, prepared)
        assert len(snap.resolved_expressions) == 1
        assert f"(a {py_op} b)" == snap.resolved_expressions[0].python_code, (
            f"IR op {ir_op!r} should map to Python {py_op!r}"
        )


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

    # Exactly one pair (no double-extraction from the new walker).
    set_var_pairs = [
        p for p in snap.resolved_expressions if "concat" in p.adf_expression or "result" in p.adf_expression
    ]
    assert len(set_var_pairs) == 1
    # And the source ADF expression IS preferred over the @variables('result') fallback
    # when present in the source dict (this is also a small upgrade vs. the previous
    # adapter which always emitted the @variables() label).
    pairs_with_concat = [p for p in snap.resolved_expressions if "@concat" in p.adf_expression]
    assert len(pairs_with_concat) == 1
    assert pairs_with_concat[0].python_code == "str('a') + str('b')"


# ---------------------------------------------------------------------------
# L-F19: dropped-expression-field detection (W-9 — Copy.source.sql_reader_query)
#
# These tests cover the second half of the lmv-side feedback loop. L-F17
# extracts pairs *when wkmigrate resolved the expression*. L-F19 emits a
# synthetic not_translatable warning *when wkmigrate silently dropped the
# expression at translate time* — the gap that makes
# expression_coverage drop in the lmv sweep where it would otherwise be a
# silent zero.
# ---------------------------------------------------------------------------


def test_adapter_emits_dropped_field_warning_for_copy_with_expression_sql_reader_query():
    """W-9: Copy.source.sql_reader_query is dropped by wkmigrate's
    _parse_sql_format_options. The adapter must emit a synthetic
    dropped_expression_field warning so the dimension can count it."""
    source = {
        "activities": [
            {
                "name": "copy",
                "type": "Copy",
                "depends_on": [],
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": {
                        "type": "Expression",
                        "value": "@concat('SELECT * FROM ', pipeline().parameters.t)",
                    },
                },
                "sink": {"type": "AzureDatabricksDeltaLakeSink"},
            }
        ]
    }
    # CopyActivity built with the same shape wkmigrate would produce: source_properties
    # is the dict from _parse_sql_format_options, which has no sql_reader_query key.
    task = CopyActivity(
        name="copy",
        task_key="copy",
        source_properties={"type": "sqlserver", "query_isolation_level": "READ_COMMITTED"},
        sink_properties={"type": "delta"},
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    drops = [nt for nt in snap.not_translatable if nt.get("kind") == "dropped_expression_field"]
    assert len(drops) == 1
    drop = drops[0]
    assert drop["original_activity_type"] == "Copy"
    assert drop["property"] == "source.sql_reader_query"
    assert drop["adf_expression"] == "@concat('SELECT * FROM ', pipeline().parameters.t)"
    # Message must contain "expression" so compute_expression_coverage counts it.
    assert "expression" in drop["message"].lower()
    assert "Copy" in drop["message"]


def test_adapter_skips_dropped_field_warning_when_copy_has_no_sql_reader_query():
    """No source.sql_reader_query in the source dict → no warning."""
    source = {
        "activities": [
            {
                "name": "copy",
                "type": "Copy",
                "depends_on": [],
                "source": {"type": "AzureSqlSource"},
                "sink": {"type": "AzureDatabricksDeltaLakeSink"},
            }
        ]
    }
    task = CopyActivity(name="copy", task_key="copy", source_properties={"type": "sqlserver"})
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    drops = [nt for nt in snap.not_translatable if nt.get("kind") == "dropped_expression_field"]
    assert len(drops) == 0


def test_adapter_skips_dropped_field_warning_when_copy_has_literal_sql_reader_query():
    """Literal (non-Expression) sql_reader_query in source dict → no warning.

    The L-F19 detector only fires on `{type: Expression, value: ...}` shapes
    because plain string literals could be picked up by a future wkmigrate
    enhancement without needing the same Expression-resolution path. This
    keeps the false-positive rate low while the wkmigrate gap is still open.
    """
    source = {
        "activities": [
            {
                "name": "copy",
                "type": "Copy",
                "depends_on": [],
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": "SELECT * FROM static_table",
                },
                "sink": {"type": "AzureDatabricksDeltaLakeSink"},
            }
        ]
    }
    task = CopyActivity(name="copy", task_key="copy", source_properties={"type": "sqlserver"})
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    drops = [nt for nt in snap.not_translatable if nt.get("kind") == "dropped_expression_field"]
    assert len(drops) == 0


def test_adapter_skips_dropped_field_warning_for_copy_when_ir_already_has_sql_reader_query():
    """Future-proofing: if wkmigrate ever wires sql_reader_query into
    source_properties, do not double-warn — L-F17 should be extended to
    extract it as a regular ExpressionPair instead. This test pins that
    contract so the W-9 fix can land cleanly without churning L-F19."""
    source = {
        "activities": [
            {
                "name": "copy",
                "type": "Copy",
                "depends_on": [],
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": {"type": "Expression", "value": "@x"},
                },
                "sink": {"type": "AzureDatabricksDeltaLakeSink"},
            }
        ]
    }
    task = CopyActivity(
        name="copy",
        task_key="copy",
        # Hypothetical post-W-9 IR shape: source_properties carries the resolved query.
        source_properties={"type": "sqlserver", "sql_reader_query": "resolved_python"},
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    drops = [nt for nt in snap.not_translatable if nt.get("kind") == "dropped_expression_field"]
    assert len(drops) == 0


def test_adapter_skips_dropped_field_warning_for_lookup_when_ir_has_resolved_string():
    """The L-F17 walker already extracts LookupActivity.source_query as a
    pair when it's a non-empty string (post-W-7 / pr/27-3). L-F19 must NOT
    double-emit a warning for the same activity."""
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

    drops = [nt for nt in snap.not_translatable if nt.get("kind") == "dropped_expression_field"]
    assert len(drops) == 0
    # Walker emits a pair for this case, so resolved_expressions should be 1.
    assert len(snap.resolved_expressions) == 1


def test_adapter_emits_dropped_field_warning_for_lookup_with_empty_ir_source_query():
    """If a future regression slips a non-string sql_reader_query into the
    LookupActivity.source_query field (e.g. None because the resolver
    returned UnsupportedValue and the translator forgot to fail), L-F19
    must catch it. This complements the W-7 hard-crash signal which fires
    much earlier (in the preparer)."""
    source = {
        "activities": [
            {
                "name": "lk",
                "type": "Lookup",
                "depends_on": [],
                "first_row_only": True,
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": {"type": "Expression", "value": "@concat('a', 'b')"},
                },
            }
        ]
    }
    task = LookupActivity(name="lk", task_key="lk", first_row_only=True, source_query=None)
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    drops = [nt for nt in snap.not_translatable if nt.get("kind") == "dropped_expression_field"]
    assert len(drops) == 1
    assert drops[0]["original_activity_type"] == "Lookup"
    assert drops[0]["property"] == "source.sql_reader_query"


def test_adapter_dropped_field_warning_lifts_expression_coverage_denominator():
    """End-to-end: a Copy with a dropped sql_reader_query should make the
    expression_coverage dimension report a measurable failure (score < 1.0,
    measurable=True), not the silent vacuous-100% case."""
    from lakeflow_migration_validator.dimensions.expression_coverage import compute_expression_coverage

    source = {
        "activities": [
            {
                "name": "copy",
                "type": "Copy",
                "depends_on": [],
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": {"type": "Expression", "value": "@concat('a', 'b')"},
                },
                "sink": {"type": "AzureDatabricksDeltaLakeSink"},
            }
        ]
    }
    task = CopyActivity(name="copy", task_key="copy", source_properties={"type": "sqlserver"})
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    score, details = compute_expression_coverage(snap)
    assert details["measurable"] is True
    assert score == 0.0
    assert details["total"] == 1
    assert details["resolved"] == 0


def test_adapter_skips_if_condition_with_missing_operands():
    """If left or right is missing (None or empty), the IfCondition handler
    must NOT emit a pair — otherwise python_code becomes the literal text
    'None' or '() == ()' and silently inflates X-1/X-2 coverage. Cursor
    Bugbot caught this on PR #20."""
    source = {"activities": []}
    # Build an IfConditionActivity with left=None to simulate a malformed IR
    task = IfConditionActivity(
        name="bad_if",
        task_key="bad_if",
        op="EQUAL_TO",
        left="",  # ← invalid: empty operand
        right="1",
    )
    prepared = _build_minimal_prepared_for_task(task)

    snap = from_wkmigrate(source, prepared)

    # No pair emitted because left is empty
    if_pairs = [p for p in snap.resolved_expressions if "if_condition" in p.adf_expression or "==" in p.python_code]
    assert len(if_pairs) == 0
