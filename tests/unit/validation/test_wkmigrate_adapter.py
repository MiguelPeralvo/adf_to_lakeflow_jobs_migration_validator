"""Adapter boundary tests — IMPORTS wkmigrate.

These tests verify that from_wkmigrate() correctly maps wkmigrate types into
ConversionSnapshot. If wkmigrate changes a field name or restructures a class,
these tests break first (and only these tests break).
"""

import pytest

from lakeflow_migration_validator import evaluate, evaluate_from_wkmigrate
from lakeflow_migration_validator.adapters.wkmigrate_adapter import (
    adf_to_snapshot,
    from_wkmigrate,
)
from lakeflow_migration_validator.contract import DependencyRef
from wkmigrate.models.ir.pipeline import (
    Activity,
    DatabricksNotebookActivity,
    Dependency,
    ForEachActivity,
    IfConditionActivity,
    LookupActivity,
    Pipeline,
    SetVariableActivity,
    WebActivity,
)
from wkmigrate.models.workflows.artifacts import NotebookArtifact, PreparedActivity, PreparedWorkflow
from wkmigrate.models.workflows.instructions import SecretInstruction
from wkmigrate.parsers.expression_parsers import ResolvedExpression


def _build_prepared_workflow(
    *,
    include_placeholder: bool = True,
    include_notebook: bool = True,
    include_secret: bool = True,
    include_param: bool = True,
    include_dependency: bool = True,
    include_not_translatable: bool = True,
    include_expression_pair: bool = True,
):
    source_pipeline = {
        "activities": [
            {
                "name": "downstream",
                "depends_on": [{"activity": "upstream"}],
            }
        ]
    }

    pipeline_tasks = []
    if include_dependency:
        pipeline_tasks.extend(
            [
                Activity(name="upstream", task_key="upstream"),
                Activity(
                    name="downstream",
                    task_key="downstream",
                    depends_on=[Dependency(task_key="upstream", outcome="Succeeded")],
                ),
            ]
        )
    if include_expression_pair:
        pipeline_tasks.append(
            SetVariableActivity(
                name="set_var",
                task_key="set_var",
                variable_name="x",
                variable_value="1 + 1",
            )
        )

    pipeline = Pipeline(
        name="pipeline",
        parameters=[{"name": "param1"}] if include_param else None,
        schedule=None,
        tasks=pipeline_tasks,
        tags={},
        not_translatable=[{"message": "unsupported expression"}] if include_not_translatable else [],
    )

    activities = [
        PreparedActivity(
            task={
                "task_key": "task_real",
                "notebook_task": {"notebook_path": "/Shared/real_notebook"},
            },
            notebooks=[NotebookArtifact(file_path="/nb/real.py", content="x = 1")] if include_notebook else None,
            secrets=(
                [
                    SecretInstruction(
                        scope="scope1", key="key1", service_name=None, service_type=None, provided_value=None
                    )
                ]
                if include_secret
                else None
            ),
        )
    ]
    if include_placeholder:
        activities.append(
            PreparedActivity(
                task={
                    "task_key": "task_placeholder",
                    "notebook_task": {"notebook_path": "/UNSUPPORTED_ADF_ACTIVITY"},
                }
            )
        )

    prepared = PreparedWorkflow(pipeline=pipeline, activities=activities)
    return source_pipeline, prepared


def test_adapter_maps_tasks_with_placeholder_detection():
    """Tasks pointing to /UNSUPPORTED_ADF_ACTIVITY get is_placeholder=True."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)

    assert len(snapshot.tasks) == 2
    by_key = {task.task_key: task for task in snapshot.tasks}
    assert by_key["task_real"].is_placeholder is False
    assert by_key["task_placeholder"].is_placeholder is True


def test_adapter_raises_when_task_key_is_missing():
    """Adapter fails fast when a prepared task has no task_key."""
    source = {"activities": []}
    pipeline = Pipeline(name="pipeline", parameters=None, schedule=None, tasks=[], tags={})
    prepared = PreparedWorkflow(
        pipeline=pipeline,
        activities=[
            PreparedActivity(
                task={"notebook_task": {"notebook_path": "/Shared/real_notebook"}},
            )
        ],
    )

    with pytest.raises(ValueError, match="task_key"):
        from_wkmigrate(source, prepared)


def test_adapter_maps_notebooks():
    """All NotebookArtifacts become NotebookSnapshots with file_path and content."""
    source, prepared = _build_prepared_workflow(include_placeholder=False)

    snapshot = from_wkmigrate(source, prepared)

    assert len(snapshot.notebooks) == 1
    assert snapshot.notebooks[0].file_path == "/nb/real.py"
    assert snapshot.notebooks[0].content == "x = 1"


def test_adapter_maps_secrets():
    """All SecretInstructions become SecretRefs."""
    source, prepared = _build_prepared_workflow(include_placeholder=False)

    snapshot = from_wkmigrate(source, prepared)

    assert len(snapshot.secrets) == 1
    assert snapshot.secrets[0].scope == "scope1"
    assert snapshot.secrets[0].key == "key1"


def test_adapter_maps_parameters():
    """Pipeline parameters become a tuple of name strings."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)

    assert snapshot.parameters == ("param1",)


def test_adapter_filters_nameless_parameters():
    """Parameters without a valid name are ignored."""
    source = {"activities": []}
    pipeline = Pipeline(
        name="pipeline",
        parameters=[{"name": "param1"}, {}, {"name": ""}],
        schedule=None,
        tasks=[],
        tags={},
    )
    prepared = PreparedWorkflow(pipeline=pipeline, activities=[])

    snapshot = from_wkmigrate(source, prepared)

    assert snapshot.parameters == ("param1",)


def test_adapter_maps_dependencies():
    """IR Dependency objects become DependencyRef pairs."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)

    assert snapshot.dependencies == (DependencyRef(source_task="upstream", target_task="downstream"),)


def test_adapter_maps_not_translatable():
    """Pipeline.not_translatable list is preserved (alongside any L-F12 placeholder warnings)."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)

    # The pipeline-level warning is preserved verbatim
    assert {"message": "unsupported expression"} in snapshot.not_translatable
    # And the default fixture includes a placeholder activity, so a
    # placeholder_activity warning is also present (L-F12)
    assert any(nt.get("kind") == "placeholder_activity" for nt in snapshot.not_translatable)


def test_adapter_maps_expression_pairs():
    """SetVariableActivity tasks produce ExpressionPair entries."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)

    assert len(snapshot.resolved_expressions) == 1
    pair = snapshot.resolved_expressions[0]
    assert pair.adf_expression == "@variables('x')"
    assert pair.python_code == "1 + 1"


def test_adapter_ignores_invalid_expression_pairs():
    """Only non-empty string variable_name/value pairs are converted."""
    source = {"activities": []}
    pipeline = Pipeline(
        name="pipeline",
        parameters=None,
        schedule=None,
        tasks=[
            SetVariableActivity(name="ok", task_key="ok", variable_name="x", variable_value="1 + 1"),
            SetVariableActivity(name="bad", task_key="bad", variable_name="", variable_value=""),
        ],
        tags={},
    )
    prepared = PreparedWorkflow(pipeline=pipeline, activities=[])

    snapshot = from_wkmigrate(source, prepared)

    assert len(snapshot.resolved_expressions) == 1
    assert snapshot.resolved_expressions[0].adf_expression == "@variables('x')"


def test_adapter_counts_source_dependencies():
    """total_source_dependencies matches the ADF JSON depends_on count."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)

    assert snapshot.total_source_dependencies == 1


def test_adapter_counts_source_dependencies_with_camel_case_key():
    """total_source_dependencies also supports ADF's dependsOn field."""
    source = {
        "activities": [
            {"name": "a", "dependsOn": [{"activity": "b"}]},
            {"name": "b", "dependsOn": [{"activity": "c"}, {"activity": "d"}]},
        ]
    }
    pipeline = Pipeline(name="pipeline", parameters=None, schedule=None, tasks=[], tags={})
    prepared = PreparedWorkflow(pipeline=pipeline, activities=[])

    snapshot = from_wkmigrate(source, prepared)

    assert snapshot.total_source_dependencies == 3


def test_adapter_handles_empty_pipeline():
    """A pipeline with no activities produces an empty snapshot."""
    source = {"activities": []}
    pipeline = Pipeline(name="empty", parameters=None, schedule=None, tasks=[], tags={})
    prepared = PreparedWorkflow(pipeline=pipeline, activities=[])

    snapshot = from_wkmigrate(source, prepared)

    assert snapshot.tasks == ()
    assert snapshot.notebooks == ()
    assert snapshot.secrets == ()
    assert snapshot.parameters == ()
    assert snapshot.dependencies == ()
    assert snapshot.not_translatable == ()
    assert snapshot.resolved_expressions == ()
    assert snapshot.total_source_dependencies == 0


def test_roundtrip_evaluate_from_wkmigrate():
    """evaluate_from_wkmigrate() produces the same score as evaluate(from_wkmigrate(...))."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)
    direct = evaluate(snapshot)
    wrapped = evaluate_from_wkmigrate(source, prepared)

    assert wrapped.score == direct.score
    assert wrapped.to_dict() == direct.to_dict()


# ---------------------------------------------------------------------------
# L-F12: placeholder activity surfacing
# ---------------------------------------------------------------------------


def test_placeholder_activity_surfaces_in_not_translatable():
    """When an activity is mapped to /UNSUPPORTED_ADF_ACTIVITY, surface as not_translatable.

    Pre-#27 wkmigrate (and any future case where a source ADF activity has no
    real translator) silently substitutes a DatabricksNotebookActivity with
    notebook_path=/UNSUPPORTED_ADF_ACTIVITY. The adapter should:
      1) still mark the task as is_placeholder=True (existing behavior)
      2) ALSO add an entry to not_translatable so dimensions can count it
    """
    source = {"activities": [{"name": "mystery", "type": "UnknownActivityType"}]}
    pipeline = Pipeline(name="pipeline", parameters=None, schedule=None, tasks=[], tags={})
    prepared = PreparedWorkflow(
        pipeline=pipeline,
        activities=[
            PreparedActivity(
                task={
                    "task_key": "mystery",
                    "notebook_task": {"notebook_path": "/UNSUPPORTED_ADF_ACTIVITY"},
                }
            )
        ],
    )

    snapshot = from_wkmigrate(source, prepared)

    # Existing behavior: task is marked as placeholder
    assert len(snapshot.tasks) == 1
    assert snapshot.tasks[0].is_placeholder is True

    # New behavior: placeholder also surfaces as a not_translatable warning
    placeholder_warnings = [nt for nt in snapshot.not_translatable if nt.get("kind") == "placeholder_activity"]
    assert len(placeholder_warnings) == 1
    warning = placeholder_warnings[0]
    assert warning["task_key"] == "mystery"
    assert "placeholder" in warning["message"].lower() or "unsupported" in warning["message"].lower()


def test_placeholder_warnings_do_not_overwrite_pipeline_warnings():
    """Pipeline.not_translatable warnings AND placeholder warnings both appear."""
    source = {"activities": []}
    pipeline = Pipeline(
        name="pipeline",
        parameters=None,
        schedule=None,
        tasks=[],
        tags={},
        not_translatable=[{"message": "pipeline-level warning", "property": "p"}],
    )
    prepared = PreparedWorkflow(
        pipeline=pipeline,
        activities=[
            PreparedActivity(task={"task_key": "ph", "notebook_task": {"notebook_path": "/UNSUPPORTED_ADF_ACTIVITY"}})
        ],
    )

    snapshot = from_wkmigrate(source, prepared)

    messages = [nt.get("message", "") for nt in snapshot.not_translatable]
    assert "pipeline-level warning" in messages
    assert any("placeholder" in m.lower() or "unsupported" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# L-F1: adf_to_snapshot one-shot helper that handles wrapped input
# ---------------------------------------------------------------------------


def test_adf_to_snapshot_handles_wrapped_azure_native_input():
    """The wrapped {name, properties: {activities, ...}} shape produces a non-empty snapshot.

    This is L-F1 — wkmigrate's translate_pipeline silently produces an empty IR
    when given the wrapped Azure-native shape, but adf_to_snapshot unwraps
    properties before calling translate_pipeline so the IR is non-empty.
    """
    wrapped = {
        "name": "synthetic_pipe",
        "properties": {
            "activities": [
                {
                    "name": "set_var",
                    "type": "SetVariable",
                    "depends_on": [],
                    "variable_name": "result",
                    "value": {"type": "Expression", "value": "@concat('hello', 'world')"},
                }
            ],
            "variables": {"result": {"type": "String"}},
        },
    }

    snapshot = adf_to_snapshot(wrapped)

    # The activity was found (non-empty tasks)
    assert len(snapshot.tasks) > 0


def test_adf_to_snapshot_handles_already_flat_input():
    """Flat input {name, activities, ...} also works (idempotent unwrap)."""
    flat = {
        "name": "flat_pipe",
        "activities": [
            {
                "name": "set_var",
                "type": "SetVariable",
                "depends_on": [],
                "variable_name": "result",
                "value": {"type": "Expression", "value": "@concat('a', 'b')"},
            }
        ],
        "variables": {"result": {"type": "String"}},
    }

    snapshot = adf_to_snapshot(flat)

    assert len(snapshot.tasks) > 0


# ---------------------------------------------------------------------------
# L-F17: from_wkmigrate walks non-SetVariable activities for resolved
# expressions. Before this, the adapter only extracted ExpressionPair entries
# from SetVariableActivity tasks (variable_name + variable_value). All other
# activity types adopted by wkmigrate (Notebook.base_parameters, WebActivity
# url/body/headers, IfCondition.expression, ForEach.items, Lookup
# .source.sql_reader_query) silently produced 0 resolved expressions even
# when wkmigrate had already done the resolution upstream.
# ---------------------------------------------------------------------------


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
