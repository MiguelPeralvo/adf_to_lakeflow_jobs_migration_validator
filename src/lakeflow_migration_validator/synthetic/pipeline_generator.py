"""Template-driven synthetic ADF pipeline generation.

Generated activities intentionally follow the Azure SDK-normalized shape used by
wkmigrate translators (snake_case keys such as ``depends_on`` and top-level
activity fields like ``IfCondition.expression``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    DependencyRef,
    ExpressionPair,
    NotebookSnapshot,
    SecretRef,
    TaskSnapshot,
)
from lakeflow_migration_validator.synthetic.expression_generator import ExpressionGenerator

_SUPPORTED_MODES = {"template", "llm", "adversarial"}
_SUPPORTED_COMPLEXITIES = {"simple", "nested", "mixed"}
_DEFAULT_ACTIVITY_TYPES = ("SetVariable", "IfCondition", "DatabricksNotebook", "Copy", "Lookup", "WebActivity", "ForEach")


@dataclass(frozen=True, slots=True)
class SyntheticPipeline:
    """A generated ADF pipeline and expected conversion outcome."""

    adf_json: dict[str, Any]
    expected_snapshot: ConversionSnapshot
    description: str
    difficulty: str


class PipelineGenerator:
    """Generates synthetic ADF pipelines using deterministic templates."""

    def __init__(
        self,
        mode: str = "template",
        judge_provider=None,
        preset: str | None = None,
        custom_prompt: str | None = None,
    ):
        if mode not in _SUPPORTED_MODES:
            raise ValueError(f"Unsupported generator mode: {mode}")
        if mode in {"llm", "adversarial"} and judge_provider is None:
            raise NotImplementedError("LLM mode requires a judge_provider")
        self.mode = mode
        self.judge_provider = judge_provider
        self.preset = preset
        self.custom_prompt = custom_prompt
        self.expression_generator = ExpressionGenerator()

    def generate(
        self,
        count: int = 10,
        difficulty: str = "medium",
        activity_types: list[str] | None = None,
        expression_complexity: str = "mixed",
        max_activities: int = 20,
    ) -> list[SyntheticPipeline]:
        """Generate a deterministic list of synthetic pipelines."""
        if count <= 0:
            return []
        if expression_complexity not in _SUPPORTED_COMPLEXITIES:
            raise ValueError(f"Unsupported expression complexity: {expression_complexity}")
        if max_activities < 1:
            raise ValueError("max_activities must be >= 1")

        selected_activity_types = tuple(activity_types or _DEFAULT_ACTIVITY_TYPES)
        categories = self._expression_categories(expression_complexity)
        difficulty_label = "adversarial" if self.mode == "adversarial" else difficulty

        synthetic_pipelines: list[SyntheticPipeline] = []
        for idx in range(count):
            activity_count = 1 + (idx % max_activities)
            expressions = self.expression_generator.generate(count=activity_count, categories=categories)
            activities = self._build_activities(
                index=idx,
                activity_count=activity_count,
                activity_types=selected_activity_types,
                expressions=expressions,
            )
            pipeline_name = f"synthetic_pipeline_{idx:03d}"
            params = [{"name": "param1"}, {"name": "param2"}]
            adf_json = {
                "name": pipeline_name,
                "properties": {
                    "parameters": {
                        "param1": {"type": "String"},
                        "param2": {"type": "String"},
                    },
                    "activities": activities,
                },
            }
            expected_snapshot = self._build_expected_snapshot(
                source_pipeline=adf_json,
                expressions=expressions,
                params=params,
                activity_count=activity_count,
                pipeline_index=idx,
                pipeline_name=pipeline_name,
            )
            synthetic_pipelines.append(
                SyntheticPipeline(
                    adf_json=adf_json,
                    expected_snapshot=expected_snapshot,
                    description=f"Pipeline {idx} with {activity_count} activities ({expression_complexity}).",
                    difficulty=difficulty_label,
                )
            )
        return synthetic_pipelines

    @staticmethod
    def _expression_categories(expression_complexity: str) -> list[str]:
        if expression_complexity == "simple":
            return ["string", "math", "logical"]
        if expression_complexity == "nested":
            return ["nested"]
        return ["string", "math", "datetime", "logical", "collection", "nested"]

    def _build_activities(
        self,
        index: int,
        activity_count: int,
        activity_types: tuple[str, ...],
        expressions,
    ) -> list[dict[str, Any]]:
        activities: list[dict[str, Any]] = []
        for activity_idx in range(activity_count):
            activity_name = f"task_{index}_{activity_idx}"
            activity_type = activity_types[activity_idx % len(activity_types)]
            expression_case = expressions[activity_idx]
            depends_on = (
                []
                if activity_idx == 0
                else [{"activity": f"task_{index}_{activity_idx - 1}", "dependency_conditions": ["Succeeded"]}]
            )
            activity: dict[str, Any] = {
                "name": activity_name,
                "type": activity_type,
                "depends_on": depends_on,
            }
            # Keep normalized keys at the activity top level; wkmigrate activity
            # translators read from these fields directly.
            activity.update(self._type_properties(activity_name, activity_type, expression_case.adf_expression))
            activities.append(activity)
        return activities

    @staticmethod
    def _type_properties(activity_name: str, activity_type: str, adf_expression: str) -> dict[str, Any]:
        if activity_type == "SetVariable":
            return {"variable_name": f"{activity_name}_result", "value": {"type": "Expression", "value": adf_expression}}
        if activity_type == "IfCondition":
            return {
                # wkmigrate reads activity.get("expression") at top level.
                "expression": {"type": "Expression", "value": "@equals(1,1)"},
                "if_true_activities": [
                    {
                        "name": f"{activity_name}_if_true",
                        "type": "DatabricksNotebook",
                        "depends_on": [],
                        "notebook_path": "/Workspace/notebooks/if_true",
                    }
                ],
                "if_false_activities": [
                    {
                        "name": f"{activity_name}_if_false",
                        "type": "DatabricksNotebook",
                        "depends_on": [],
                        "notebook_path": "/Workspace/notebooks/if_false",
                    }
                ],
            }
        if activity_type == "DatabricksNotebook":
            return {
                "notebook_path": f"/Workspace/notebooks/{activity_name}",
                "base_parameters": {
                    "run_id": {"type": "Expression", "value": "@pipeline().RunId"},
                },
            }
        if activity_type == "Copy":
            return {
                "source": {
                    "type": "DelimitedTextSource",
                    "store_settings": {"type": "AzureBlobFSReadSettings"},
                    "format_settings": {"type": "DelimitedTextReadSettings"},
                },
                "sink": {"type": "AzureDatabricksDeltaLakeSink"},
                "input_dataset_definitions": [
                    {
                        "name": "source_csv_dataset",
                        "properties": {
                            "type": "DelimitedText",
                            "location": {
                                "type": "AzureBlobFSLocation",
                                "file_name": "input.csv",
                                "folder_path": "incoming",
                                "file_system": "raw",
                            },
                        },
                        "linked_service_definition": {
                            "name": "adls_source",
                            "properties": {"type": "AzureBlobFS"},
                        },
                    }
                ],
                "output_dataset_definitions": [
                    {
                        "name": "sink_delta_dataset",
                        "properties": {
                            "type": "AzureDatabricksDeltaLakeDataset",
                            "location": {
                                "type": "AzureBlobFSLocation",
                                "folder_path": "processed",
                                "file_system": "silver",
                            },
                            "table": "target_table",
                        },
                        "linked_service_definition": {
                            "name": "adls_sink",
                            "properties": {"type": "AzureBlobFS"},
                        },
                    }
                ],
            }
        if activity_type == "Lookup":
            return {
                "first_row_only": True,
                "source": {
                    "type": "AzureSqlSource",
                    "sql_reader_query": "SELECT TOP 1 * FROM config_table",
                },
                "input_dataset_definitions": [
                    {
                        "name": "lookup_source_dataset",
                        "properties": {
                            "type": "AzureSqlTable",
                            "schema_type_properties_schema": "dbo",
                            "table": "config_table",
                        },
                        "linked_service_definition": {
                            "name": "sql_linked_service",
                            "properties": {
                                "type": "SqlServer",
                                "server": "demo.database.windows.net",
                                "database": "demo",
                            },
                        },
                    }
                ],
            }
        if activity_type == "WebActivity":
            return {
                "url": "https://api.example.com/webhook",
                "method": "POST",
                "body": {"event": "synthetic", "value": adf_expression},
                "headers": {"Content-Type": "application/json"},
            }
        if activity_type == "ForEach":
            return {
                "batch_count": 2,
                "items": {"type": "Expression", "value": "@createArray('a', 'b')"},
                "activities": [
                    {
                        "name": f"{activity_name}_inner_notebook",
                        "type": "DatabricksNotebook",
                        "depends_on": [],
                        "notebook_path": "/Workspace/notebooks/for_each_inner",
                        "base_parameters": {"item_value": {"type": "Expression", "value": "@item()"}},
                    }
                ],
            }
        return {}

    def _build_expected_snapshot(
        self,
        source_pipeline: dict[str, Any],
        expressions,
        params: list[dict[str, str]],
        activity_count: int,
        pipeline_index: int,
        pipeline_name: str,
    ) -> ConversionSnapshot:
        tasks = tuple(TaskSnapshot(task_key=f"task_{pipeline_index}_{i}", is_placeholder=False) for i in range(activity_count))
        notebooks = tuple(
            NotebookSnapshot(
                file_path=f"/notebooks/{pipeline_name}_{i}.py",
                content="\n".join(
                    [
                        f"# notebook for {pipeline_name} activity {i}",
                        "dbutils.widgets.get('param1')",
                        "dbutils.widgets.get('param2')",
                        "dbutils.secrets.get(scope='scope1', key='key1')",
                        f"value = {expressions[i].expected_python}",
                    ]
                ),
            )
            for i in range(activity_count)
        )
        secrets = (SecretRef(scope="scope1", key="key1"),)
        dependencies = tuple(
            DependencyRef(
                source_task=f"task_{pipeline_index}_{i - 1}",
                target_task=f"task_{pipeline_index}_{i}",
            )
            for i in range(1, activity_count)
        )
        resolved_expressions = tuple(
            ExpressionPair(adf_expression=case.adf_expression, python_code=case.expected_python) for case in expressions
        )
        expected_outputs = {
            f"task_{pipeline_index}_{i}": expressions[i].expected_python for i in range(activity_count)
        }
        return ConversionSnapshot(
            tasks=tasks,
            notebooks=notebooks,
            secrets=secrets,
            parameters=tuple(param["name"] for param in params),
            dependencies=dependencies,
            resolved_expressions=resolved_expressions,
            source_pipeline=source_pipeline,
            total_source_dependencies=max(activity_count - 1, 0),
            expected_outputs=expected_outputs,
        )
