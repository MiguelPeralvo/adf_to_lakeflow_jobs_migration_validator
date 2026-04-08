"""Adapter boundary tests — IMPORTS wkmigrate.

These tests verify that from_wkmigrate() correctly maps wkmigrate types into
ConversionSnapshot. If wkmigrate changes a field name or restructures a class,
these tests break first (and only these tests break).
"""

import pytest

from lakeflow_migration_validator import evaluate, evaluate_from_wkmigrate
from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate
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
    """Pipeline.not_translatable list is preserved."""
    source, prepared = _build_prepared_workflow()

    snapshot = from_wkmigrate(source, prepared)

    assert snapshot.not_translatable == ({"message": "unsupported expression"},)


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
