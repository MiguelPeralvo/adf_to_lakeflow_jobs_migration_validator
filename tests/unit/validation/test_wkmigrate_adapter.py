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
from wkmigrate.models.ir.pipeline import Activity, Dependency, Pipeline, SetVariableActivity
from wkmigrate.models.workflows.artifacts import NotebookArtifact, PreparedActivity, PreparedWorkflow
from wkmigrate.models.workflows.instructions import SecretInstruction


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
      3) (L-F18) carry the original ADF activity type so failure-signature
         regexes can match by type rather than task_key substring
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

    # L-F12 behavior: placeholder also surfaces as a not_translatable warning
    placeholder_warnings = [nt for nt in snapshot.not_translatable if nt.get("kind") == "placeholder_activity"]
    assert len(placeholder_warnings) == 1
    warning = placeholder_warnings[0]
    assert warning["task_key"] == "mystery"
    assert "placeholder" in warning["message"].lower() or "unsupported" in warning["message"].lower()

    # L-F18 behavior: the original ADF activity type is captured both as a
    # structured field AND embedded in the message text as `(type: <Type>)`
    # so failure-signature regexes in dev/wkmigrate-issue-map.json can
    # match by activity type rather than by task_key substring.
    assert warning["original_activity_type"] == "UnknownActivityType"
    assert "(type: UnknownActivityType)" in warning["message"]


def test_placeholder_warning_falls_back_when_source_activity_type_missing():
    """If the source dict has no matching activity (or the type is missing),
    the placeholder warning still emits with original_activity_type=None and
    a `(type: <unknown>)` label so the regex matchers don't crash."""
    source = {"activities": []}  # No matching activity in source
    pipeline = Pipeline(name="pipeline", parameters=None, schedule=None, tasks=[], tags={})
    prepared = PreparedWorkflow(
        pipeline=pipeline,
        activities=[
            PreparedActivity(
                task={
                    "task_key": "orphan",
                    "notebook_task": {"notebook_path": "/UNSUPPORTED_ADF_ACTIVITY"},
                }
            )
        ],
    )

    snapshot = from_wkmigrate(source, prepared)

    placeholder_warnings = [nt for nt in snapshot.not_translatable if nt.get("kind") == "placeholder_activity"]
    assert len(placeholder_warnings) == 1
    warning = placeholder_warnings[0]
    assert warning["task_key"] == "orphan"
    assert warning["original_activity_type"] is None
    assert "(type: <unknown>)" in warning["message"]


def test_placeholder_warning_captures_real_activity_types_for_w8_w10_signatures():
    """L-F18 enables W-8/W-10 regex matching by activity type. This test
    verifies a Copy activity → 'Copy' label and a ForEach activity →
    'ForEach' label, AND that the W-8/W-10 regex patterns from
    dev/wkmigrate-issue-map.json successfully match the new message format."""
    import re

    source = {
        "activities": [
            {"name": "copy_task", "type": "Copy"},
            {"name": "foreach_task", "type": "ForEach"},
        ]
    }
    pipeline = Pipeline(name="pipeline", parameters=None, schedule=None, tasks=[], tags={})
    prepared = PreparedWorkflow(
        pipeline=pipeline,
        activities=[
            PreparedActivity(
                task={"task_key": "copy_task", "notebook_task": {"notebook_path": "/UNSUPPORTED_ADF_ACTIVITY"}}
            ),
            PreparedActivity(
                task={"task_key": "foreach_task", "notebook_task": {"notebook_path": "/UNSUPPORTED_ADF_ACTIVITY"}}
            ),
        ],
    )

    snapshot = from_wkmigrate(source, prepared)

    by_type = {
        nt.get("original_activity_type"): nt
        for nt in snapshot.not_translatable
        if nt.get("kind") == "placeholder_activity"
    }
    assert "Copy" in by_type
    assert "ForEach" in by_type

    # Regex compatibility check: the W-8 / W-10 patterns from
    # dev/wkmigrate-issue-map.json must match the new message format.
    w8_pattern = re.compile(r"(?i)\(type:\s*Copy\)")
    w10_pattern = re.compile(r"(?i)\(type:\s*ForEach\)")
    assert w8_pattern.search(by_type["Copy"]["message"])
    assert w10_pattern.search(by_type["ForEach"]["message"])


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
