"""Generate synthetic test data for parallel testing.

When a generated pipeline includes data-reading activities (Copy, Lookup),
this module produces matching source data files, SQL seed scripts, and
expected output values so that both ADF and Databricks can be run with
identical inputs.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any

from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider


@dataclass(frozen=True, slots=True)
class SyntheticTestData:
    """Test data generated alongside a synthetic pipeline."""

    pipeline_name: str
    source_files: dict[str, str]  # file_path → CSV/JSON content
    seed_sql: tuple[str, ...]  # SQL statements to seed lookup sources
    expected_outputs: dict[str, str]  # activity_name → expected output value
    setup_instructions: str  # human-readable setup guide

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_name": self.pipeline_name,
            "source_files": self.source_files,
            "seed_sql": list(self.seed_sql),
            "expected_outputs": self.expected_outputs,
            "setup_instructions": self.setup_instructions,
        }


class TestDataGenerator:
    """Generate test data that matches a pipeline's data requirements.

    Analyzes the pipeline JSON to find Copy and Lookup activities, then
    generates source data files, SQL seed scripts, and expected outputs.

    Uses deterministic generation by default. When a ``judge_provider``
    is supplied, uses LLM for more realistic data generation.
    """

    def __init__(self, judge_provider: JudgeProvider | None = None):
        self._provider = judge_provider

    def generate_for_pipeline(self, adf_json: dict) -> SyntheticTestData:
        """Analyze one pipeline and generate matching test data."""
        pipeline_name = adf_json.get("name", "unknown")
        activities = _get_activities(adf_json)

        source_files: dict[str, str] = {}
        seed_sql: list[str] = []
        expected_outputs: dict[str, str] = {}
        instructions: list[str] = []

        for activity in activities:
            act_type = activity.get("type", "")
            act_name = activity.get("name", "unknown")

            if act_type == "Copy":
                file_data = _generate_copy_source_data(activity)
                if file_data:
                    path, content = file_data
                    source_files[path] = content
                    expected_outputs[act_name] = f"copied_{len(content)} bytes"
                    instructions.append(f"Upload {path} to the source container for activity '{act_name}'")

            elif act_type == "Lookup":
                sql, rows = _generate_lookup_data(activity)
                if sql:
                    seed_sql.extend(sql)
                    expected_outputs[act_name] = json.dumps(rows[0] if rows else {})
                    instructions.append(f"Run seed SQL for activity '{act_name}' against the source database")

        if not instructions:
            instructions.append("No data-reading activities found — no test data needed")

        return SyntheticTestData(
            pipeline_name=pipeline_name,
            source_files=source_files,
            seed_sql=tuple(seed_sql),
            expected_outputs=expected_outputs,
            setup_instructions="\n".join(f"{i+1}. {instr}" for i, instr in enumerate(instructions)),
        )

    def generate_for_suite(
        self,
        pipelines: list[dict],
    ) -> list[SyntheticTestData]:
        """Generate test data for all pipelines in a suite."""
        return [self.generate_for_pipeline(p) for p in pipelines]


def _get_activities(adf_json: dict) -> list[dict]:
    """Extract activities from pipeline JSON."""
    props = adf_json.get("properties", adf_json)
    return props.get("activities", [])


def _generate_copy_source_data(activity: dict) -> tuple[str, str] | None:
    """Generate a CSV source file for a Copy activity."""
    # Extract dataset info to determine schema
    datasets = activity.get("input_dataset_definitions", [])
    if not datasets:
        datasets = activity.get("inputs", [])

    # Generate a simple CSV with 10 rows
    act_name = activity.get("name", "source")
    columns = ["id", "name", "value", "created_date", "category"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for i in range(10):
        writer.writerow(
            [
                i + 1,
                f"record_{i+1}",
                round(100.0 + i * 10.5, 2),
                f"2026-01-{(i % 28) + 1:02d}",
                ["A", "B", "C"][i % 3],
            ]
        )

    file_path = f"test_data/{act_name}_source.csv"
    return file_path, output.getvalue()


def _generate_lookup_data(activity: dict) -> tuple[list[str], list[dict]] | None:
    """Generate SQL seed statements for a Lookup activity."""
    act_name = activity.get("name", "lookup")

    # Extract table info from the activity
    source = activity.get("source", {})
    query = source.get("sql_reader_query", "")

    # Determine table name from query or dataset
    table_name = "config_table"
    if "FROM" in query.upper():
        parts = query.upper().split("FROM")
        if len(parts) > 1:
            table_name = parts[1].strip().split()[0].lower()

    # Generate seed data
    rows = [
        {"id": 1, "config_key": "batch_size", "config_value": "1000", "active": True},
        {"id": 2, "config_key": "output_path", "config_value": "/data/output", "active": True},
        {"id": 3, "config_key": "max_retries", "config_value": "3", "active": True},
    ]

    sql = [
        f"-- Seed data for Lookup activity '{act_name}'",
        f"CREATE TABLE IF NOT EXISTS {table_name} (id INT, config_key VARCHAR(255), config_value VARCHAR(255), active BIT);",
        f"DELETE FROM {table_name};",
    ]
    for row in rows:
        sql.append(
            f"INSERT INTO {table_name} (id, config_key, config_value, active) "
            f"VALUES ({row['id']}, '{row['config_key']}', '{row['config_value']}', {1 if row['active'] else 0});"
        )

    return sql, rows
