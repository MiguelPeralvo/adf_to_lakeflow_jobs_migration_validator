#!/usr/bin/env python3
"""Generate 80 synthetic ADF pipelines inspired by real-world complex expression patterns.

All expressions are fully anonymized — no customer-identifiable content remains.
Produces 4 themes x 20 pipelines each, compatible with GroundTruthSuite.from_json().

Usage:
    python3 scripts/generate_customer_inspired_golden_set.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_DIR = os.path.join(REPO_ROOT, "golden_sets", "gen")

THEMES = [
    "customer_inspired_string",
    "customer_inspired_logical",
    "customer_inspired_collection_datetime",
    "customer_inspired_unsupported",
]

# Anonymization blocklist — generation fails if any of these appear in output
BLOCKLIST = [
    # Spanish terms from original pipelines
    "ejecuta", "comunes", "carga", "fecha", "resultado", "ejecucion",
    "intentos", "hora", "inicio", "busqueda", "cierre", "cerrado",
    "perimetro", "acumulado", "mensual", "totales", "balance",
    "cuentaresultados", "datos", "segunda", "formulas", "datatsources",
    "existe", "proceso", "activa", "control ejecucion",
    # Domain-specific identifiers
    "repsol", "crp0001", "crp0002", "datahub", "arquetipo", "bfcdt",
    "lakeh_a_pl", "lakeh_", "estrategdato", "dap-core",
    # Business-specific
    "bfc", "fcl", "cmd_", "cmd_notebook", "cmd_copy",
    # URLs
    "repsol.com", "datahub01",
    # Pipeline-specific names
    "romance standard time",
]


# ---------------------------------------------------------------------------
# Helper: ADF JSON building blocks
# ---------------------------------------------------------------------------
def expr(value: str) -> dict:
    """Create an ADF expression node."""
    return {"type": "Expression", "value": value}


def param_decl(ptype: str = "String", default: Any = "") -> dict:
    """Create a parameter declaration."""
    return {"type": ptype, "defaultValue": default}


def var_decl(vtype: str = "String", default: Any = "") -> dict:
    """Create a variable declaration."""
    return {"type": vtype, "defaultValue": default}


def depends_on(*activities: str) -> list[dict]:
    """Create dependsOn list."""
    return [
        {"activity": a, "dependencyConditions": ["Succeeded"]}
        for a in activities
    ]


def set_variable_activity(
    name: str, var_name: str, value_expr: str, deps: list[str] | None = None,
) -> dict:
    """Create a SetVariable activity."""
    return {
        "name": name,
        "type": "SetVariable",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "variableName": var_name,
            "value": expr(value_expr),
        },
    }


def append_variable_activity(
    name: str, var_name: str, value_expr: str, deps: list[str] | None = None,
) -> dict:
    """Create an AppendVariable activity."""
    return {
        "name": name,
        "type": "AppendVariable",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "variableName": var_name,
            "value": expr(value_expr),
        },
    }


def if_condition_activity(
    name: str,
    condition_expr: str,
    if_true: list[dict] | None = None,
    if_false: list[dict] | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Create an IfCondition activity."""
    result: dict = {
        "name": name,
        "type": "IfCondition",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "expression": expr(condition_expr),
            "ifTrueActivities": if_true or [
                set_variable_activity("SetTrueFlag", "status_flag", "@string('true')"),
            ],
            "ifFalseActivities": if_false or [
                set_variable_activity("SetFalseFlag", "status_flag", "@string('false')"),
            ],
        },
    }
    return result


def notebook_activity(
    name: str,
    notebook_path: str,
    base_params: dict[str, str] | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Create a DatabricksNotebook activity."""
    bp = {}
    for k, v in (base_params or {}).items():
        bp[k] = expr(v) if v.startswith("@") else {"type": "Expression", "value": v}
    return {
        "name": name,
        "type": "DatabricksNotebook",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "notebookPath": notebook_path,
            "baseParameters": bp,
        },
        "linkedServiceName": {
            "referenceName": "ls_databricks",
            "type": "LinkedServiceReference",
        },
    }


def web_activity(
    name: str,
    url_expr: str,
    method: str = "POST",
    body_expr: str | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Create a WebActivity activity."""
    tp: dict[str, Any] = {
        "url": expr(url_expr) if url_expr.startswith("@") else url_expr,
        "method": method,
        "headers": {"Content-Type": "application/json"},
    }
    if body_expr:
        tp["body"] = expr(body_expr)
    return {
        "name": name,
        "type": "WebActivity",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": tp,
    }


def foreach_activity(
    name: str,
    items_expr: str,
    inner_activities: list[dict],
    deps: list[str] | None = None,
    batch_count: int = 1,
) -> dict:
    """Create a ForEach activity."""
    return {
        "name": name,
        "type": "ForEach",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "isSequential": batch_count == 1,
            "items": expr(items_expr),
            "activities": inner_activities,
            "batchCount": batch_count,
        },
    }


def copy_activity(
    name: str,
    source_query_expr: str | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Create a Copy activity."""
    source: dict[str, Any] = {"type": "AzureSqlSource"}
    if source_query_expr:
        source["sqlReaderQuery"] = expr(source_query_expr)
    return {
        "name": name,
        "type": "Copy",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "source": source,
            "sink": {"type": "ParquetSink"},
        },
    }


def lookup_activity(
    name: str,
    query_expr: str | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Create a Lookup activity."""
    source: dict[str, Any] = {"type": "AzureSqlSource"}
    if query_expr:
        source["sqlReaderQuery"] = expr(query_expr)
    return {
        "name": name,
        "type": "Lookup",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "source": source,
            "firstRowOnly": True,
        },
    }


def fail_activity(
    name: str, message_expr: str, error_code_expr: str, deps: list[str] | None = None,
) -> dict:
    """Create a Fail activity."""
    return {
        "name": name,
        "type": "Fail",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "message": expr(message_expr),
            "errorCode": expr(error_code_expr),
        },
    }


def until_activity(
    name: str,
    condition_expr: str,
    inner_activities: list[dict],
    deps: list[str] | None = None,
    timeout: str = "0.01:00:00",
) -> dict:
    """Create an Until activity."""
    return {
        "name": name,
        "type": "Until",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "expression": expr(condition_expr),
            "activities": inner_activities,
            "timeout": timeout,
        },
    }


def switch_activity(
    name: str,
    on_expr: str,
    cases: dict[str, list[dict]],
    default_activities: list[dict] | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Create a Switch activity."""
    return {
        "name": name,
        "type": "Switch",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "on": expr(on_expr),
            "cases": [
                {"value": k, "activities": v} for k, v in cases.items()
            ],
            "defaultActivities": default_activities or [],
        },
    }


def execute_pipeline_activity(
    name: str,
    pipeline_ref: str,
    parameters: dict[str, str] | None = None,
    deps: list[str] | None = None,
) -> dict:
    """Create an ExecutePipeline activity."""
    params = {}
    for k, v in (parameters or {}).items():
        params[k] = expr(v) if v.startswith("@") else v
    return {
        "name": name,
        "type": "ExecutePipeline",
        "dependsOn": depends_on(*deps) if deps else [],
        "userProperties": [],
        "typeProperties": {
            "pipeline": {"referenceName": pipeline_ref, "type": "PipelineReference"},
            "parameters": params,
            "waitOnCompletion": True,
        },
    }


def build_pipeline(
    name: str,
    parameters: dict[str, dict],
    variables: dict[str, dict],
    activities: list[dict],
) -> dict:
    """Build a complete ADF pipeline JSON."""
    return {
        "name": name,
        "properties": {
            "parameters": parameters,
            "variables": variables,
            "activities": activities,
        },
    }


# ---------------------------------------------------------------------------
# Suite JSON helpers (compatible with GroundTruthSuite.from_json)
# ---------------------------------------------------------------------------
def empty_snapshot(pipeline_json: dict) -> dict:
    """Build a minimal expected_snapshot dict for a pipeline."""
    activities = pipeline_json.get("properties", {}).get("activities", [])
    params = list(pipeline_json.get("properties", {}).get("parameters", {}).keys())

    tasks = []
    deps = []
    for act in activities:
        task_key = act["name"]
        is_placeholder = act.get("type") in ("WebActivity", "ExecutePipeline", "Fail")
        tasks.append({"task_key": task_key, "is_placeholder": is_placeholder})
        for dep in act.get("dependsOn", []):
            deps.append({"source_task": dep["activity"], "target_task": task_key})

    return {
        "tasks": tasks,
        "notebooks": [],
        "secrets": [],
        "parameters": params,
        "dependencies": deps,
        "resolved_expressions": [],
        "source_pipeline": pipeline_json,
        "total_source_dependencies": len(deps),
        "expected_outputs": {},
        "adf_run_outputs": {},
        "not_translatable": [],
    }


def pipeline_to_suite_entry(
    pipeline_json: dict, description: str, difficulty: str = "complex",
) -> dict:
    """Wrap a pipeline JSON as a suite.json entry."""
    return {
        "adf_json": pipeline_json,
        "description": description,
        "difficulty": difficulty,
        "expected_snapshot": empty_snapshot(pipeline_json),
    }


# ===========================================================================
# THEME 1: customer_inspired_string (20 pipelines)
# ===========================================================================
def gen_string_pipelines() -> list[tuple[str, dict, str]]:
    """Generate 20 string-focused pipelines. Returns [(name, json, description)]."""
    pipelines = []

    # 000 — multi_arg_concat_path_builder
    p = build_pipeline(
        "multi_arg_concat_path_builder",
        {"env": param_decl("String", "prod"), "region": param_decl("String", "us-east"),
         "dataset_name": param_decl("String", "customers"), "version": param_decl("String", "v2")},
        {"full_path": var_decl(), "archive_path": var_decl(), "log_path": var_decl()},
        [
            set_variable_activity("SetFullPath", "full_path",
                "@concat('/volumes/', pipeline().parameters.env, '/', pipeline().parameters.region, '/gold/', pipeline().parameters.dataset_name, '/', formatDateTime(utcnow(), 'yyyy/MM/dd'))"),
            set_variable_activity("SetArchivePath", "archive_path",
                "@concat('/volumes/', pipeline().parameters.env, '/archive/', pipeline().parameters.dataset_name, '_', pipeline().parameters.version, '_', formatDateTime(utcnow(), 'yyyyMMdd'))"),
            set_variable_activity("SetLogPath", "log_path",
                "@concat('/volumes/', pipeline().parameters.env, '/', pipeline().parameters.region, '/logs/', pipeline().Pipeline, '/', pipeline().RunId)",
                deps=["SetFullPath"]),
            notebook_activity("ProcessData", "/pipelines/data_loader/process",
                {"input_path": "@variables('full_path')", "output_path": "@variables('archive_path')",
                 "log_path": "@variables('log_path')", "run_date": "@formatDateTime(utcnow(), 'yyyy-MM-dd')"},
                deps=["SetLogPath"]),
        ],
    )
    pipelines.append(("000_multi_arg_concat_path_builder", p, "Multi-argument concat for path construction with 6+ parameters and formatDateTime."))

    # 001 — string_interpolation_table_names
    p = build_pipeline(
        "string_interpolation_table_names",
        {"env": param_decl("String", "prod"), "table_name": param_decl("String", "orders"),
         "schema_name": param_decl("String", "analytics")},
        {"qualified_name": var_decl(), "staging_name": var_decl()},
        [
            set_variable_activity("SetQualifiedName", "qualified_name",
                "@{concat(pipeline().parameters.env, '_', pipeline().parameters.schema_name, '.', pipeline().parameters.table_name)}"),
            set_variable_activity("SetStagingName", "staging_name",
                "@{concat('stg_', pipeline().parameters.table_name, '_', formatDateTime(utcnow(), 'yyyyMMdd'))}",
                deps=["SetQualifiedName"]),
            copy_activity("CopyToStaging",
                "@concat('SELECT * FROM ', variables('qualified_name'), ' WHERE load_date >= ''', formatDateTime(utcnow(), 'yyyy-MM-dd'), '''')",
                deps=["SetStagingName"]),
        ],
    )
    pipelines.append(("001_string_interpolation_table_names", p, "String interpolation @{...} for qualified table names with date partitioning."))

    # 002 — nested_split_connection_parser
    p = build_pipeline(
        "nested_split_connection_parser",
        {"connection_string": param_decl("String", "Server=myserver;Database=mydb;User=admin"),
         "fallback_db": param_decl("String", "default_db")},
        {"server_name": var_decl(), "database_name": var_decl(), "is_valid": var_decl("String", "false")},
        [
            set_variable_activity("ExtractServer", "server_name",
                "@split(split(pipeline().parameters.connection_string, ';')[0], '=')[1]"),
            set_variable_activity("ExtractDatabase", "database_name",
                "@split(split(pipeline().parameters.connection_string, ';')[1], '=')[1]",
                deps=["ExtractServer"]),
            if_condition_activity("ValidateConnection",
                "@not(empty(variables('server_name')))",
                if_true=[
                    set_variable_activity("MarkValid", "is_valid", "@string('true')"),
                ],
                if_false=[
                    set_variable_activity("UseFallback", "database_name",
                        "@pipeline().parameters.fallback_db"),
                ],
                deps=["ExtractDatabase"]),
            lookup_activity("LookupSchema",
                "@concat('SELECT TOP 1 * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_CATALOG = ''', variables('database_name'), '''')",
                deps=["ValidateConnection"]),
        ],
    )
    pipelines.append(("002_nested_split_connection_parser", p, "Nested split(split(...)[N], delim)[M] for connection string parsing with validation."))

    # 003 — item_to_string_foreach_processor
    p = build_pipeline(
        "item_to_string_foreach_processor",
        {"config_file": param_decl("String", "etl_config.json")},
        {"processed_items": var_decl("Array", [])},
        [
            lookup_activity("ReadConfig"),
            foreach_activity("ProcessItems", "@activity('ReadConfig').output.value",
                [
                    set_variable_activity("SerializeItem", "current_item",
                        "@string(item())"),
                    if_condition_activity("CheckItemFiles",
                        "@contains(string(item().files), pipeline().parameters.config_file)",
                        if_true=[
                            set_variable_activity("ExtractFiles", "current_files",
                                "@if(startswith(string(item().files), '['), string(item().files), concat('[', string(item().files), ']'))"),
                        ],
                        if_false=[
                            set_variable_activity("SetEmptyFiles", "current_files",
                                "@string('[]')"),
                        ]),
                ],
                deps=["ReadConfig"]),
        ],
    )
    # Fix: add missing variables
    p["properties"]["variables"]["current_item"] = var_decl()
    p["properties"]["variables"]["current_files"] = var_decl()
    pipelines.append(("003_item_to_string_foreach_processor", p, "ForEach with string(item()), string(item().files), contains, startswith — item serialization patterns."))

    # 004 — join_collected_ids_notifier
    p = build_pipeline(
        "join_collected_ids_notifier",
        {"batch_size": param_decl("Int", 10)},
        {"collected_ids": var_decl("Array", []), "id_csv": var_decl(), "status": var_decl()},
        [
            append_variable_activity("CollectId1", "collected_ids", "@string('id_001')"),
            append_variable_activity("CollectId2", "collected_ids", "@string('id_002')", deps=["CollectId1"]),
            append_variable_activity("CollectId3", "collected_ids", "@string('id_003')", deps=["CollectId2"]),
            set_variable_activity("BuildCsv", "id_csv",
                "@join(variables('collected_ids'), ',')",
                deps=["CollectId3"]),
            web_activity("NotifyWebhook",
                "https://api.example-corp.com/v1/notifications",
                body_expr="@concat('{\"batch_ids\": \"', variables('id_csv'), '\", \"count\": ', string(length(variables('collected_ids'))), '}')",
                deps=["BuildCsv"]),
        ],
    )
    pipelines.append(("004_join_collected_ids_notifier", p, "AppendVariable + join(variables('array'), ',') for CSV construction + WebActivity notification."))

    # 005 — json_payload_concat_webhook
    p = build_pipeline(
        "json_payload_concat_webhook",
        {"job_id": param_decl("String", "j-001"), "env": param_decl("String", "prod"),
         "owner": param_decl("String", "data-team"), "priority": param_decl("String", "high"),
         "source_system": param_decl("String", "erp")},
        {"payload": var_decl(), "execution_result": var_decl(), "timestamp": var_decl()},
        [
            set_variable_activity("SetTimestamp", "timestamp",
                "@utcnow('yyyy-MM-dd HH:mm:ss.fff')"),
            set_variable_activity("BuildPayload", "payload",
                "@concat('{\"job_id\":\"', pipeline().parameters.job_id, '\",\"env\":\"', pipeline().parameters.env, '\",\"owner\":\"', pipeline().parameters.owner, '\",\"priority\":\"', pipeline().parameters.priority, '\",\"source\":\"', pipeline().parameters.source_system, '\",\"pipeline\":\"', pipeline().Pipeline, '\",\"run_id\":\"', pipeline().RunId, '\",\"status\":\"', variables('execution_result'), '\",\"timestamp\":\"', variables('timestamp'), '\"}')",
                deps=["SetTimestamp"]),
            web_activity("SendPayload",
                "https://api.example-corp.com/v2/events",
                body_expr="@variables('payload')",
                deps=["BuildPayload"]),
        ],
    )
    pipelines.append(("005_json_payload_concat_webhook", p, "15-argument concat building JSON payload for webhook with pipeline system variables."))

    # 006 — env_branching_url_builder
    p = build_pipeline(
        "env_branching_url_builder",
        {"env": param_decl("String", "prod"), "endpoint": param_decl("String", "status")},
        {"api_url": var_decl(), "response": var_decl()},
        [
            set_variable_activity("BuildUrl", "api_url",
                "@if(equals(pipeline().parameters.env, 'prod'), concat('https://api.example-corp.com/v2/', pipeline().parameters.endpoint), concat('https://api-', pipeline().parameters.env, '.example-corp.com/v2/', pipeline().parameters.endpoint))"),
            if_condition_activity("CheckEnv",
                "@or(equals(pipeline().parameters.env, 'prod'), equals(pipeline().parameters.env, 'staging'))",
                if_true=[
                    set_variable_activity("SetProdFlag", "response", "@string('production_mode')"),
                ],
                deps=["BuildUrl"]),
            web_activity("CallApi", "@variables('api_url')",
                body_expr="@concat('{\"pipeline\": \"', pipeline().Pipeline, '\"}')",
                deps=["CheckEnv"]),
        ],
    )
    pipelines.append(("006_env_branching_url_builder", p, "Environment-aware URL construction with if/equals branching and concat."))

    # 007 — message_sanitization_pipeline
    p = build_pipeline(
        "message_sanitization_pipeline",
        {"raw_message": param_decl("String", "Line1\nLine2\tTab")},
        {"sanitized": var_decl(), "encoded": var_decl(), "final_message": var_decl()},
        [
            set_variable_activity("EncodeMessage", "encoded",
                "@uriComponent(pipeline().parameters.raw_message)"),
            set_variable_activity("SanitizeMessage", "sanitized",
                "@replace(replace(replace(uriComponentToString(replace(replace(replace(uriComponent(pipeline().parameters.raw_message), '%0a', ''), '%0A', ''), '%09', '')), '\"', ''), '\\\\', '/'), 'nvarchar', 'nvar_char')",
                deps=["EncodeMessage"]),
            set_variable_activity("BuildFinalMessage", "final_message",
                "@if(empty(pipeline().parameters.raw_message), '', variables('sanitized'))",
                deps=["SanitizeMessage"]),
            web_activity("LogSanitized", "https://api.example-corp.com/v1/logs",
                body_expr="@concat('{\"message\": \"', variables('final_message'), '\"}')",
                deps=["BuildFinalMessage"]),
        ],
    )
    pipelines.append(("007_message_sanitization_pipeline", p, "Deep replace(replace(uriComponentToString(replace(uriComponent(...))))) chain for message sanitization."))

    # 008 — dynamic_sql_query_builder
    p = build_pipeline(
        "dynamic_sql_query_builder",
        {"table_name": param_decl("String", "orders"), "date_filter": param_decl("String", "2024-01-01"),
         "limit": param_decl("Int", 1000)},
        {"query": var_decl()},
        [
            set_variable_activity("BuildQuery", "query",
                "@concat('SELECT TOP ', string(pipeline().parameters.limit), ' * FROM dbo.', pipeline().parameters.table_name, ' WHERE created_at >= ''', pipeline().parameters.date_filter, ''' ORDER BY created_at DESC')"),
            lookup_activity("ExecuteQuery", "@variables('query')", deps=["BuildQuery"]),
            copy_activity("ExportResults",
                "@concat('SELECT * FROM dbo.', pipeline().parameters.table_name, ' WHERE id IN (SELECT id FROM dbo.', pipeline().parameters.table_name, ' WHERE created_at >= ''', pipeline().parameters.date_filter, ''')')",
                deps=["ExecuteQuery"]),
        ],
    )
    pipelines.append(("008_dynamic_sql_query_builder", p, "Dynamic SQL construction via concat with table name, date, and limit parameters."))

    # 009 — path_construction_with_date
    p = build_pipeline(
        "path_construction_with_date",
        {"zone": param_decl("String", "gold"), "dataset": param_decl("String", "transactions")},
        {"data_path": var_decl(), "checkpoint_path": var_decl()},
        [
            set_variable_activity("SetDataPath", "data_path",
                "@concat('/volumes/catalog/', pipeline().parameters.zone, '/', pipeline().parameters.dataset, '/year=', formatDateTime(utcnow(), 'yyyy'), '/month=', formatDateTime(utcnow(), 'MM'), '/day=', formatDateTime(utcnow(), 'dd'))"),
            set_variable_activity("SetCheckpointPath", "checkpoint_path",
                "@concat('/volumes/catalog/checkpoints/', pipeline().parameters.dataset, '_', formatDateTime(utcnow(), 'yyyyMMddHHmmss'))",
                deps=["SetDataPath"]),
            copy_activity("LoadData", deps=["SetCheckpointPath"]),
        ],
    )
    pipelines.append(("009_path_construction_with_date", p, "Path construction with concat + formatDateTime(utcnow(), ...) for date-partitioned storage."))

    # 010 — tolower_toupper_normalizer
    p = build_pipeline(
        "tolower_toupper_normalizer",
        {"input_code": param_decl("String", " ABC-123 "), "category": param_decl("String", "Premium")},
        {"normalized_code": var_decl(), "upper_category": var_decl(),
         "trimmed_code": var_decl(), "final_key": var_decl()},
        [
            set_variable_activity("TrimCode", "trimmed_code",
                "@trim(pipeline().parameters.input_code)"),
            set_variable_activity("NormalizeCode", "normalized_code",
                "@toLower(trim(pipeline().parameters.input_code))",
                deps=["TrimCode"]),
            set_variable_activity("UpperCategory", "upper_category",
                "@toUpper(pipeline().parameters.category)",
                deps=["TrimCode"]),
            set_variable_activity("BuildKey", "final_key",
                "@concat(variables('normalized_code'), ':', variables('upper_category'))",
                deps=["NormalizeCode", "UpperCategory"]),
        ],
    )
    pipelines.append(("010_tolower_toupper_normalizer", p, "String normalization with toLower, toUpper, trim combinations."))

    # 011 — substring_extraction_parser
    p = build_pipeline(
        "substring_extraction_parser",
        {"log_entry": param_decl("String", "2024-01-15T10:30:00Z|ERROR|Module:Auth|Failed login")},
        {"timestamp_part": var_decl(), "level_part": var_decl(), "module_part": var_decl()},
        [
            set_variable_activity("ExtractTimestamp", "timestamp_part",
                "@substring(pipeline().parameters.log_entry, 0, indexOf(pipeline().parameters.log_entry, '|'))"),
            set_variable_activity("ExtractLevel", "level_part",
                "@substring(pipeline().parameters.log_entry, add(indexOf(pipeline().parameters.log_entry, '|'), 1), sub(indexOf(substring(pipeline().parameters.log_entry, add(indexOf(pipeline().parameters.log_entry, '|'), 1), sub(length(pipeline().parameters.log_entry), add(indexOf(pipeline().parameters.log_entry, '|'), 1))), '|'), 0))",
                deps=["ExtractTimestamp"]),
            set_variable_activity("ExtractModule", "module_part",
                "@substring(pipeline().parameters.log_entry, add(indexOf(pipeline().parameters.log_entry, 'Module:'), 7), sub(indexOf(substring(pipeline().parameters.log_entry, add(indexOf(pipeline().parameters.log_entry, 'Module:'), 7), 50), '|'), 0))",
                deps=["ExtractLevel"]),
            if_condition_activity("CheckError",
                "@equals(variables('level_part'), 'ERROR')",
                deps=["ExtractModule"]),
        ],
    )
    pipelines.append(("011_substring_extraction_parser", p, "Complex substring with indexOf for structured log entry parsing."))

    # 012 — multi_replace_data_cleaner
    p = build_pipeline(
        "multi_replace_data_cleaner",
        {"raw_data": param_decl("String", "value with <tags> & \"quotes\"")},
        {"clean_step1": var_decl(), "clean_step2": var_decl(), "clean_final": var_decl()},
        [
            set_variable_activity("StripTags", "clean_step1",
                "@replace(replace(pipeline().parameters.raw_data, '<', '&lt;'), '>', '&gt;')"),
            set_variable_activity("EscapeQuotes", "clean_step2",
                "@replace(replace(variables('clean_step1'), '\"', '\\\\\"'), '\\\\', '\\\\\\\\')",
                deps=["StripTags"]),
            set_variable_activity("FinalClean", "clean_final",
                "@replace(replace(replace(replace(variables('clean_step2'), '&', '&amp;'), char(10), ' '), char(13), ' '), char(9), ' ')",
                deps=["EscapeQuotes"]),
            notebook_activity("ProcessCleanData", "/pipelines/cleaner/process",
                {"cleaned_data": "@variables('clean_final')"},
                deps=["FinalClean"]),
        ],
    )
    pipelines.append(("012_multi_replace_data_cleaner", p, "Chained replace() calls (4+ levels) for data sanitization with HTML escaping."))

    # 013 — base64_config_decoder
    p = build_pipeline(
        "base64_config_decoder",
        {"encoded_config": param_decl("String", "eyJrZXkiOiAidmFsdWUifQ==")},
        {"decoded_config": var_decl(), "parsed_key": var_decl()},
        [
            lookup_activity("FetchEncodedConfig"),
            set_variable_activity("DecodeConfig", "decoded_config",
                "@base64ToString(pipeline().parameters.encoded_config)",
                deps=["FetchEncodedConfig"]),
            set_variable_activity("ExtractKey", "parsed_key",
                "@split(split(variables('decoded_config'), '\"key\":')[1], '\"')[1]",
                deps=["DecodeConfig"]),
        ],
    )
    pipelines.append(("013_base64_config_decoder", p, "base64ToString for config decoding with nested split for JSON field extraction."))

    # 014 — connection_string_resolver
    p = build_pipeline(
        "connection_string_resolver",
        {"host": param_decl("String", "db.example-corp.com"), "port": param_decl("Int", 5432),
         "database": param_decl("String", "analytics"), "ssl_mode": param_decl("String", "require")},
        {"conn_string": var_decl(), "jdbc_url": var_decl()},
        [
            set_variable_activity("BuildConnString", "conn_string",
                "@concat('Host=', pipeline().parameters.host, ';Port=', string(pipeline().parameters.port), ';Database=', pipeline().parameters.database, ';SslMode=', pipeline().parameters.ssl_mode)"),
            set_variable_activity("BuildJdbc", "jdbc_url",
                "@concat('jdbc:postgresql://', pipeline().parameters.host, ':', string(pipeline().parameters.port), '/', pipeline().parameters.database, '?sslmode=', pipeline().parameters.ssl_mode)",
                deps=["BuildConnString"]),
            copy_activity("CopyData", deps=["BuildJdbc"]),
        ],
    )
    pipelines.append(("014_connection_string_resolver", p, "Connection string construction with concat and string() type conversion for port."))

    # 015 — csv_header_builder
    p = build_pipeline(
        "csv_header_builder",
        {"column_list": param_decl("String", "id,name,email,created_at")},
        {"columns": var_decl("Array", []), "header_line": var_decl(), "column_count": var_decl()},
        [
            set_variable_activity("SplitColumns", "header_line",
                "@join(createArray('id', 'name', 'email', 'created_at', 'updated_at'), '|')"),
            set_variable_activity("CountColumns", "column_count",
                "@string(length(split(pipeline().parameters.column_list, ',')))",
                deps=["SplitColumns"]),
            set_variable_activity("BuildHeader", "header_line",
                "@concat('HEADER|', variables('column_count'), '|', replace(pipeline().parameters.column_list, ',', '|'))",
                deps=["CountColumns"]),
            foreach_activity("ProcessColumns",
                "@split(pipeline().parameters.column_list, ',')",
                [set_variable_activity("ProcessCol", "current_col", "@concat('col_', item())")],
                deps=["BuildHeader"]),
        ],
    )
    p["properties"]["variables"]["current_col"] = var_decl()
    pipelines.append(("015_csv_header_builder", p, "split + join + createArray + length for CSV header construction."))

    # 016 — guid_correlation_tracker
    p = build_pipeline(
        "guid_correlation_tracker",
        {"app_name": param_decl("String", "data-pipeline")},
        {"correlation_id": var_decl(), "trace_id": var_decl()},
        [
            set_variable_activity("GenerateCorrelationId", "correlation_id",
                "@concat(guid(), '_', utcnow('yyyyMMddHHmmssfff'))"),
            set_variable_activity("GenerateTraceId", "trace_id",
                "@concat(pipeline().parameters.app_name, '#', pipeline().Pipeline, '#', utcnow('yyyy/MM/dd'), '#', pipeline().RunId)",
                deps=["GenerateCorrelationId"]),
            web_activity("RegisterTrace", "https://api.example-corp.com/v1/traces",
                body_expr="@concat('{\"correlation_id\": \"', variables('correlation_id'), '\", \"trace_id\": \"', variables('trace_id'), '\"}')",
                deps=["GenerateTraceId"]),
        ],
    )
    pipelines.append(("016_guid_correlation_tracker", p, "guid() + utcnow() + concat for correlation/trace ID generation with pipeline system vars."))

    # 017 — multiline_sql_param_builder
    p = build_pipeline(
        "multiline_sql_param_builder",
        {"schema": param_decl("String", "dbo"), "table": param_decl("String", "orders"),
         "start_date": param_decl("String", "2024-01-01"), "end_date": param_decl("String", "2024-12-31"),
         "status_filter": param_decl("String", "active")},
        {"dynamic_query": var_decl()},
        [
            set_variable_activity("BuildComplexQuery", "dynamic_query",
                "@concat('SELECT o.id, o.customer_id, o.amount, c.name ', 'FROM ', pipeline().parameters.schema, '.', pipeline().parameters.table, ' o ', 'INNER JOIN ', pipeline().parameters.schema, '.customers c ON o.customer_id = c.id ', 'WHERE o.created_at BETWEEN ''', pipeline().parameters.start_date, ''' AND ''', pipeline().parameters.end_date, ''' ', 'AND o.status = ''', pipeline().parameters.status_filter, ''' ', 'ORDER BY o.created_at DESC')"),
            lookup_activity("RunQuery", "@variables('dynamic_query')", deps=["BuildComplexQuery"]),
            copy_activity("ExportResults", "@variables('dynamic_query')", deps=["RunQuery"]),
        ],
    )
    pipelines.append(("017_multiline_sql_param_builder", p, "Complex multi-part SQL query construction via concat with 5 parameters."))

    # 018 — email_template_renderer
    p = build_pipeline(
        "email_template_renderer",
        {"recipient": param_decl("String", "team@example-corp.com"),
         "subject": param_decl("String", "Pipeline Complete"),
         "pipeline_name": param_decl("String", "daily_etl")},
        {"email_body": var_decl(), "subject_line": var_decl(),
         "timestamp": var_decl(), "status_text": var_decl()},
        [
            set_variable_activity("SetTimestamp", "timestamp",
                "@convertFromUtc(utcnow(), 'Eastern Standard Time', 'dd/MM/yyyy HH:mm')"),
            set_variable_activity("BuildSubject", "subject_line",
                "@concat('[', toUpper(pipeline().parameters.pipeline_name), '] ', pipeline().parameters.subject, ' - ', formatDateTime(utcnow(), 'yyyy-MM-dd'))",
                deps=["SetTimestamp"]),
            set_variable_activity("SetStatus", "status_text",
                "@concat('Pipeline ', pipeline().parameters.pipeline_name, ' completed at ', variables('timestamp'))",
                deps=["SetTimestamp"]),
            set_variable_activity("BuildBody", "email_body",
                "@concat('<html><body><h2>', variables('subject_line'), '</h2><p>', variables('status_text'), '</p><p>Run ID: ', pipeline().RunId, '</p></body></html>')",
                deps=["BuildSubject", "SetStatus"]),
            web_activity("SendEmail", "https://api.example-corp.com/v1/email",
                body_expr="@concat('{\"to\": \"', pipeline().parameters.recipient, '\", \"subject\": \"', variables('subject_line'), '\", \"body\": \"', replace(variables('email_body'), '\"', '\\\\\"'), '\"}')",
                deps=["BuildBody"]),
        ],
    )
    pipelines.append(("018_email_template_renderer", p, "Email template with convertFromUtc, toUpper, concat, replace for HTML body construction."))

    # 019 — config_driven_path_assembler
    p = build_pipeline(
        "config_driven_path_assembler",
        {"env": param_decl("String", "prod"), "region": param_decl("String", "us-east"),
         "app_name": param_decl("String", "analytics"), "module": param_decl("String", "ingestion"),
         "version": param_decl("String", "v3"), "tenant_id": param_decl("String", "t-001"),
         "format": param_decl("String", "delta"), "compression": param_decl("String", "snappy")},
        {"base_path": var_decl(), "data_path": var_decl(), "metadata_path": var_decl()},
        [
            set_variable_activity("SetBasePath", "base_path",
                "@concat('/volumes/', pipeline().parameters.env, '/', pipeline().parameters.region, '/', pipeline().parameters.tenant_id, '/', pipeline().parameters.app_name, '/', pipeline().parameters.version)"),
            set_variable_activity("SetDataPath", "data_path",
                "@concat(variables('base_path'), '/', pipeline().parameters.module, '/data/', pipeline().parameters.format, '/', formatDateTime(utcnow(), 'yyyy/MM/dd'))",
                deps=["SetBasePath"]),
            set_variable_activity("SetMetadataPath", "metadata_path",
                "@concat(variables('base_path'), '/metadata/', pipeline().parameters.module, '_', formatDateTime(utcnow(), 'yyyyMMdd'), '.json')",
                deps=["SetBasePath"]),
            notebook_activity("RunIngestion", "/pipelines/ingestion/main",
                {"data_path": "@variables('data_path')", "metadata_path": "@variables('metadata_path')",
                 "compression": "@pipeline().parameters.compression"},
                deps=["SetDataPath", "SetMetadataPath"]),
        ],
    )
    pipelines.append(("019_config_driven_path_assembler", p, "8-parameter path assembly with concat, variables, formatDateTime across 3 path components."))

    return pipelines


# ===========================================================================
# THEME 2: customer_inspired_logical (20 pipelines)
# ===========================================================================
def gen_logical_pipelines() -> list[tuple[str, dict, str]]:
    """Generate 20 logical-expression-focused pipelines."""
    pipelines = []

    # 000 — dual_variable_gate
    p = build_pipeline(
        "dual_variable_gate",
        {"enable_processing": param_decl("Bool", True)},
        {"should_continue": var_decl("Boolean", True), "not_skipped": var_decl("Boolean", True), "status_flag": var_decl()},
        [
            set_variable_activity("InitContinue", "should_continue", "@bool(pipeline().parameters.enable_processing)"),
            if_condition_activity("ContinuationGate",
                "@and(variables('should_continue'), variables('not_skipped'))",
                deps=["InitContinue"]),
        ],
    )
    pipelines.append(("000_dual_variable_gate", p, "and(variables('a'), variables('b')) — dual boolean variable gate for continuation logic."))

    # 001 — intersection_module_filter
    p = build_pipeline(
        "intersection_module_filter",
        {"allowed_modules": param_decl("Array", ["all", "core", "reporting"]),
         "run_mode": param_decl("String", "full")},
        {"status_flag": var_decl()},
        [
            if_condition_activity("ModuleFilterGate",
                "@and(not(empty(intersection(pipeline().parameters.allowed_modules, createArray('all', 'core', 'reporting', 'analytics')))), equals(pipeline().parameters.run_mode, 'full'))"),
        ],
    )
    pipelines.append(("001_intersection_module_filter", p, "and(not(empty(intersection(param, createArray(...)))), equals(param, value)) — module filtering with intersection."))

    # 002 — triple_nested_validation
    p = build_pipeline(
        "triple_nested_validation",
        {"env": param_decl("String", "prod"), "load_type": param_decl("String", "full"),
         "factory_name": param_decl("String", "data_factory_prod")},
        {"validation_passed": var_decl(), "status_flag": var_decl()},
        [
            lookup_activity("RunDataValidation"),
            if_condition_activity("TripleGate",
                "@and(and(equals(activity('RunDataValidation').output.firstRow.is_valid, '1'), not(or(equals(pipeline().parameters.env, 'dev'), equals(pipeline().parameters.env, 'test')))), equals(pipeline().parameters.factory_name, 'data_factory_prod'))",
                if_true=[
                    set_variable_activity("SetValidated", "validation_passed", "@string('true')"),
                ],
                if_false=[
                    set_variable_activity("SetNotValidated", "validation_passed", "@string('false')"),
                ],
                deps=["RunDataValidation"]),
        ],
    )
    pipelines.append(("002_triple_nested_validation", p, "and(and(equals(lookup_output, val), not(or(equals, equals))), equals(param, val)) — triple-nested boolean validation."))

    # 003 — load_type_router
    p = build_pipeline(
        "load_type_router",
        {"load_type": param_decl("String", "full")},
        {"status_flag": var_decl()},
        [
            if_condition_activity("LoadTypeCheck",
                "@or(equals(pipeline().parameters.load_type, 'full'), equals(pipeline().parameters.load_type, 'incremental'))",
                if_true=[copy_activity("RunCopy")],
                if_false=[fail_activity("FailInvalidType",
                    "@concat('Invalid load_type: ', pipeline().parameters.load_type)",
                    "@string('INVALID_LOAD_TYPE')")]),
        ],
    )
    pipelines.append(("003_load_type_router", p, "or(equals(param, 'val1'), equals(param, 'val2')) — load type routing with fail on invalid."))

    # 004 — retry_loop_exit
    p = build_pipeline(
        "retry_loop_exit",
        {"max_retries": param_decl("Int", 5)},
        {"is_complete": var_decl("Boolean", False), "retry_attempts": var_decl("Array", []),
         "current_result": var_decl(), "status_flag": var_decl()},
        [
            until_activity("RetryLoop",
                "@or(variables('is_complete'), equals(length(variables('retry_attempts')), pipeline().parameters.max_retries))",
                [
                    web_activity("AttemptCall", "https://api.example-corp.com/v1/check", method="GET"),
                    append_variable_activity("TrackAttempt", "retry_attempts", "@string(utcnow())"),
                ]),
        ],
    )
    pipelines.append(("004_retry_loop_exit", p, "or(variables('done'), equals(length(variables('attempts')), param)) — Until loop exit with retry tracking."))

    # 005-012 — contains_filter_variants (8 pipelines)
    filter_targets = [
        ("customers", "customer data"), ("orders", "order records"),
        ("products", "product catalog"), ("inventory", "stock levels"),
        ("shipments", "logistics data"), ("payments", "payment records"),
        ("audit_log", "audit entries"), ("analytics", "analytics tables"),
    ]
    for i, (target, desc) in enumerate(filter_targets):
        idx = 5 + i
        p = build_pipeline(
            f"contains_filter_variant_{idx:03d}",
            {"target_tables": param_decl("String", f"{target},accounts,reports"),
             "enable_filter": param_decl("Bool", True)},
            {"should_process": var_decl(), "status_flag": var_decl()},
            [
                if_condition_activity(f"Filter{target.title().replace('_', '')}",
                    f"@contains(pipeline().parameters.target_tables, '{target}')",
                    if_true=[
                        notebook_activity(f"Process{target.title().replace('_', '')}",
                            f"/pipelines/etl/{target}/load"),
                    ],
                    if_false=[
                        set_variable_activity("SkipProcessing", "should_process",
                            "@string('skipped')"),
                    ]),
            ],
        )
        pipelines.append((f"{idx:03d}_contains_filter_{target}", p,
            f"contains(param, '{target}') — filter variant for {desc} processing."))

    # 013 — time_window_guard
    p = build_pipeline(
        "time_window_guard",
        {"earliest_start": param_decl("String", "08:15"), "latest_start": param_decl("String", "22:00")},
        {"current_hour": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("SetCurrentHour", "current_hour",
                "@convertFromUtc(utcnow(), 'Eastern Standard Time', 'HH:mm')"),
            if_condition_activity("TimeWindowCheck",
                "@greaterOrEquals(variables('current_hour'), pipeline().parameters.earliest_start)",
                if_true=[
                    notebook_activity("RunScheduledJob", "/pipelines/scheduler/main"),
                ],
                if_false=[
                    fail_activity("TooEarly",
                        "@concat('Current time ', variables('current_hour'), ' is before allowed window ', pipeline().parameters.earliest_start)",
                        "@string('TIME_WINDOW_VIOLATION')"),
                ],
                deps=["SetCurrentHour"]),
        ],
    )
    pipelines.append(("013_time_window_guard", p, "greaterOrEquals(variables('hour'), param) — time window guard with convertFromUtc."))

    # 014 — complex_boolean_orchestrator
    p = build_pipeline(
        "complex_boolean_orchestrator",
        {"env": param_decl("String", "prod"), "load_type": param_decl("String", "full"),
         "modules": param_decl("Array", ["all"]), "enable_validation": param_decl("Bool", True),
         "run_mode": param_decl("String", "full")},
        {"should_continue": var_decl("Boolean", True), "not_skipped": var_decl("Boolean", True),
         "validation_result": var_decl(), "status_flag": var_decl()},
        [
            if_condition_activity("EnvironmentGate",
                "@and(not(or(equals(pipeline().parameters.env, 'dev'), equals(pipeline().parameters.env, 'sandbox'))), or(equals(pipeline().parameters.load_type, 'full'), equals(pipeline().parameters.load_type, 'incremental')))"),
            if_condition_activity("ModuleGate",
                "@and(not(empty(intersection(pipeline().parameters.modules, createArray('all', 'core', 'reporting')))), equals(pipeline().parameters.run_mode, 'full'))",
                deps=["EnvironmentGate"]),
            if_condition_activity("CombinedGate",
                "@and(and(variables('should_continue'), variables('not_skipped')), bool(pipeline().parameters.enable_validation))",
                deps=["ModuleGate"]),
        ],
    )
    pipelines.append(("014_complex_boolean_orchestrator", p, "5+ boolean operators: and, or, not, empty, intersection, equals, bool combined in 3 cascading gates."))

    # 015 — switch_like_if_cascade
    p = build_pipeline(
        "switch_like_if_cascade",
        {"action": param_decl("String", "transform")},
        {"result": var_decl(), "status_flag": var_decl()},
        [
            if_condition_activity("Route",
                "@equals(pipeline().parameters.action, 'extract')",
                if_true=[
                    set_variable_activity("SetExtract", "result", "@string('extracting')"),
                ],
                if_false=[
                    if_condition_activity("Route2",
                        "@equals(pipeline().parameters.action, 'transform')",
                        if_true=[
                            set_variable_activity("SetTransform", "result", "@string('transforming')"),
                        ],
                        if_false=[
                            if_condition_activity("Route3",
                                "@equals(pipeline().parameters.action, 'load')",
                                if_true=[
                                    set_variable_activity("SetLoad", "result", "@string('loading')"),
                                ],
                                if_false=[
                                    set_variable_activity("SetUnknown", "result",
                                        "@concat('unknown_action:', pipeline().parameters.action)"),
                                ]),
                        ]),
                ]),
        ],
    )
    pipelines.append(("015_switch_like_if_cascade", p, "Chained if(equals(...), ..., if(equals(...), ...)) — cascading dispatch without Switch activity."))

    # 016 — negated_or_compound
    p = build_pipeline(
        "negated_or_compound",
        {"load_type": param_decl("String", "full"), "env": param_decl("String", "prod")},
        {"status_flag": var_decl()},
        [
            if_condition_activity("ExcludeDevTypes",
                "@not(or(equals(pipeline().parameters.load_type, 'test'), equals(pipeline().parameters.load_type, 'debug')))",
                if_true=[
                    notebook_activity("RunProduction", "/pipelines/etl/main"),
                ]),
        ],
    )
    pipelines.append(("016_negated_or_compound", p, "not(or(equals(...), equals(...))) — negated compound condition for excluding dev types."))

    # 017 — multi_equals_dispatch
    p = build_pipeline(
        "multi_equals_dispatch",
        {"source_type": param_decl("String", "database")},
        {"connector": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("DispatchConnector", "connector",
                "@if(equals(pipeline().parameters.source_type, 'database'), 'jdbc', if(equals(pipeline().parameters.source_type, 'api'), 'rest', if(equals(pipeline().parameters.source_type, 'file'), 'blob', if(equals(pipeline().parameters.source_type, 'stream'), 'kafka', 'unknown'))))"),
            if_condition_activity("ValidateConnector",
                "@not(equals(variables('connector'), 'unknown'))",
                deps=["DispatchConnector"]),
        ],
    )
    pipelines.append(("017_multi_equals_dispatch", p, "Nested if(equals(...), val, if(equals(...), val, ...)) — 4-level dispatch without Switch."))

    # 018 — coalesce_based_null_guard
    p = build_pipeline(
        "coalesce_based_null_guard",
        {"input_id": param_decl("String", ""), "fallback_id": param_decl("String", "default-001")},
        {"effective_id": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("ResolveId", "effective_id",
                "@if(or(equals(coalesce(pipeline().parameters.input_id, ''), ''), equals(pipeline().parameters.input_id, 'null')), pipeline().parameters.fallback_id, pipeline().parameters.input_id)"),
            if_condition_activity("ValidateId",
                "@not(equals(variables('effective_id'), ''))",
                deps=["ResolveId"]),
        ],
    )
    pipelines.append(("018_coalesce_based_null_guard", p, "or(equals(coalesce(param, ''), ''), equals(param, 'null')) — null/empty guard with coalesce."))

    # 019 — boolean_with_length_check
    p = build_pipeline(
        "boolean_with_length_check",
        {"required_modules": param_decl("Array", ["core"]), "min_modules": param_decl("Int", 1)},
        {"status_flag": var_decl()},
        [
            if_condition_activity("LengthGate",
                "@and(not(empty(pipeline().parameters.required_modules)), greaterOrEquals(length(pipeline().parameters.required_modules), pipeline().parameters.min_modules))"),
        ],
    )
    pipelines.append(("019_boolean_with_length_check", p, "and(not(empty(...)), greaterOrEquals(length(...), param)) — non-empty + minimum length gate."))

    return pipelines


# ===========================================================================
# THEME 3: customer_inspired_collection_datetime (20 pipelines)
# ===========================================================================
def gen_collection_datetime_pipelines() -> list[tuple[str, dict, str]]:
    """Generate 20 collection/datetime/math pipelines."""
    pipelines = []

    # 000-007 — intersection variants
    module_sets = [
        ("core_analytics", ["all", "core", "analytics", "core_analytics"]),
        ("core_reporting", ["all", "core", "reporting", "core_reporting"]),
        ("data_ingestion", ["all", "data", "ingestion", "data_ingestion"]),
        ("data_transform", ["all", "data", "transform", "data_transform"]),
        ("ml_training", ["all", "ml", "training", "ml_training"]),
        ("ml_inference", ["all", "ml", "inference", "ml_inference"]),
        ("export_batch", ["all", "export", "batch", "export_batch"]),
        ("export_stream", ["all", "export", "stream", "export_stream"]),
    ]
    for i, (suffix, values) in enumerate(module_sets):
        values_str = ", ".join(f"'{v}'" for v in values)
        p = build_pipeline(
            f"intersection_variant_{i:03d}",
            {"requested_modules": param_decl("Array", ["all"]),
             "run_flag": param_decl("String", "enabled")},
            {"status_flag": var_decl()},
            [
                if_condition_activity(f"Check{suffix.title().replace('_', '')}",
                    f"@not(empty(intersection(pipeline().parameters.requested_modules, createArray({values_str}))))"),
            ],
        )
        pipelines.append((f"{i:03d}_intersection_variant_{suffix}", p,
            f"not(empty(intersection(param, createArray({values_str})))) — module check variant {i}."))

    # 008 — empty_intersection_guard
    p = build_pipeline(
        "empty_intersection_guard",
        {"user_roles": param_decl("Array", []), "required_roles": param_decl("Array", ["admin", "editor"])},
        {"has_access": var_decl(), "status_flag": var_decl()},
        [
            if_condition_activity("AccessCheck",
                "@empty(intersection(pipeline().parameters.user_roles, pipeline().parameters.required_roles))",
                if_true=[
                    fail_activity("DenyAccess",
                        "@concat('No matching roles. Required: ', string(pipeline().parameters.required_roles))",
                        "@string('ACCESS_DENIED')"),
                ],
                if_false=[
                    set_variable_activity("GrantAccess", "has_access", "@string('true')"),
                ]),
        ],
    )
    pipelines.append(("008_empty_intersection_guard", p, "empty(intersection(param, param)) — role-based access control with intersection."))

    # 009 — union_config_merger
    p = build_pipeline(
        "union_config_merger",
        {"override_config": param_decl("String", "{}")},
        {"base_config": var_decl(), "merged_config": var_decl(), "status_flag": var_decl()},
        [
            lookup_activity("FetchBaseConfig"),
            set_variable_activity("StoreBase", "base_config",
                "@string(activity('FetchBaseConfig').output.firstRow)",
                deps=["FetchBaseConfig"]),
            set_variable_activity("MergeConfigs", "merged_config",
                "@string(union(json(pipeline().parameters.override_config), json(variables('base_config'))))",
                deps=["StoreBase"]),
        ],
    )
    pipelines.append(("009_union_config_merger", p, "string(union(json(param), json(variables(...)))) — config merging with union + json."))

    # 010 — json_variable_parser
    p = build_pipeline(
        "json_variable_parser",
        {"serialized_payload": param_decl("String", '{"key": "value", "count": 42}')},
        {"parsed_data": var_decl(), "extracted_key": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("ParsePayload", "parsed_data",
                "@string(json(pipeline().parameters.serialized_payload))"),
            set_variable_activity("ExtractKey", "extracted_key",
                "@json(pipeline().parameters.serialized_payload).key",
                deps=["ParsePayload"]),
            foreach_activity("ProcessEntries",
                "@json(pipeline().parameters.serialized_payload)",
                [set_variable_activity("ProcessEntry", "current_entry", "@string(item())")],
                deps=["ExtractKey"]),
        ],
    )
    p["properties"]["variables"]["current_entry"] = var_decl()
    pipelines.append(("010_json_variable_parser", p, "json(param) for deserialization + property access and ForEach iteration."))

    # 011 — timezone_conversion_reporter
    p = build_pipeline(
        "timezone_conversion_reporter",
        {"target_timezone": param_decl("String", "Eastern Standard Time")},
        {"local_datetime": var_decl(), "local_time_only": var_decl(), "utc_timestamp": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("ConvertFull", "local_datetime",
                "@convertFromUtc(utcnow(), pipeline().parameters.target_timezone, 'dd/MM/yyyy HH:mm')"),
            set_variable_activity("ConvertTimeOnly", "local_time_only",
                "@convertFromUtc(utcnow(), pipeline().parameters.target_timezone, 'HH:mm')",
                deps=["ConvertFull"]),
            set_variable_activity("SetUtc", "utc_timestamp",
                "@utcnow('yyyy-MM-dd HH:mm:ss.fff')",
                deps=["ConvertFull"]),
            web_activity("ReportTimes", "https://api.example-corp.com/v1/metrics",
                body_expr="@concat('{\"local\": \"', variables('local_datetime'), '\", \"utc\": \"', variables('utc_timestamp'), '\"}')",
                deps=["ConvertTimeOnly", "SetUtc"]),
        ],
    )
    pipelines.append(("011_timezone_conversion_reporter", p, "convertFromUtc(utcnow(), timezone, format) — timezone conversion with multiple formats."))

    # 012 — date_coalesce_default
    p = build_pipeline(
        "date_coalesce_default",
        {"override_date": param_decl("String", "")},
        {"effective_date": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("ResolveDate", "effective_date",
                "@coalesce(pipeline().parameters.override_date, formatDateTime(utcnow(), 'yyyy/MM/dd'))"),
            notebook_activity("RunWithDate", "/pipelines/etl/dated_load",
                {"load_date": "@variables('effective_date')"},
                deps=["ResolveDate"]),
        ],
    )
    pipelines.append(("012_date_coalesce_default", p, "coalesce(param, formatDateTime(utcnow(), format)) — date parameter with utcnow fallback."))

    # 013 — utcnow_formatted_partition
    p = build_pipeline(
        "utcnow_formatted_partition",
        {"table_name": param_decl("String", "events")},
        {"partition_key": var_decl(), "record_timestamp": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("SetPartitionKey", "partition_key",
                "@formatDateTime(utcnow(), 'yyyy/MM/dd')"),
            set_variable_activity("SetRecordTimestamp", "record_timestamp",
                "@utcnow('yyyy-MM-dd HH:mm:ss.fff')",
                deps=["SetPartitionKey"]),
            copy_activity("CopyPartitioned",
                "@concat('SELECT *, ''', variables('record_timestamp'), ''' AS load_timestamp FROM ', pipeline().parameters.table_name)",
                deps=["SetRecordTimestamp"]),
        ],
    )
    pipelines.append(("013_utcnow_formatted_partition", p, "utcnow('yyyy-MM-dd HH:mm:ss.fff') and formatDateTime(utcnow(), ...) for timestamp partitioning."))

    # 014 — numeric_param_subtraction
    p = build_pipeline(
        "numeric_param_subtraction",
        {"total_workers": param_decl("Int", 8), "reserved_workers": param_decl("Int", 2)},
        {"available_workers": var_decl(), "adjusted_count": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("CalcAvailable", "available_workers",
                "@string(sub(pipeline().parameters.total_workers, pipeline().parameters.reserved_workers))"),
            set_variable_activity("AdjustCount", "adjusted_count",
                "@string(sub(pipeline().parameters.total_workers, 4))",
                deps=["CalcAvailable"]),
            if_condition_activity("CheckMinWorkers",
                "@greater(sub(pipeline().parameters.total_workers, pipeline().parameters.reserved_workers), 0)",
                deps=["AdjustCount"]),
        ],
    )
    pipelines.append(("014_numeric_param_subtraction", p, "sub(param, N) — numeric parameter subtraction with type coercion."))

    # 015 — retry_count_length
    p = build_pipeline(
        "retry_count_length",
        {"max_retries": param_decl("Int", 3)},
        {"retry_attempts": var_decl("Array", []), "current_count": var_decl(), "status_flag": var_decl()},
        [
            append_variable_activity("TrackAttempt1", "retry_attempts", "@utcnow()"),
            set_variable_activity("CountRetries", "current_count",
                "@string(length(variables('retry_attempts')))",
                deps=["TrackAttempt1"]),
            until_activity("RetryUntilDone",
                "@equals(length(variables('retry_attempts')), pipeline().parameters.max_retries)",
                [
                    append_variable_activity("TrackAttemptN", "retry_attempts", "@utcnow()"),
                ],
                deps=["CountRetries"]),
        ],
    )
    pipelines.append(("015_retry_count_length", p, "length(variables('array')) + equals for retry count tracking in Until loop."))

    # 016 — date_range_partitioned_copy
    p = build_pipeline(
        "date_range_partitioned_copy",
        {"start_date": param_decl("String", "2024-01-01"), "days_back": param_decl("Int", 7)},
        {"computed_end_date": var_decl(), "date_filter": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("ComputeEndDate", "computed_end_date",
                "@formatDateTime(addDays(utcnow(), mul(pipeline().parameters.days_back, -1)), 'yyyy-MM-dd')"),
            set_variable_activity("BuildDateFilter", "date_filter",
                "@concat('created_at BETWEEN ''', variables('computed_end_date'), ''' AND ''', formatDateTime(utcnow(), 'yyyy-MM-dd'), '''')",
                deps=["ComputeEndDate"]),
            copy_activity("CopyDateRange",
                "@concat('SELECT * FROM orders WHERE ', variables('date_filter'))",
                deps=["BuildDateFilter"]),
        ],
    )
    pipelines.append(("016_date_range_partitioned_copy", p, "addDays + formatDateTime + mul for computed date range filtering."))

    # 017 — collection_operations_full
    p = build_pipeline(
        "collection_operations_full",
        {"config_a": param_decl("String", '{"key1": "val1"}'),
         "config_b": param_decl("String", '{"key2": "val2"}'),
         "required_keys": param_decl("Array", ["key1", "key2"]),
         "available_keys": param_decl("Array", ["key1", "key3"])},
        {"merged": var_decl(), "common_keys": var_decl(), "has_all_keys": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("MergeConfigs", "merged",
                "@string(union(json(pipeline().parameters.config_a), json(pipeline().parameters.config_b)))"),
            set_variable_activity("FindCommonKeys", "common_keys",
                "@string(intersection(pipeline().parameters.required_keys, pipeline().parameters.available_keys))",
                deps=["MergeConfigs"]),
            set_variable_activity("CheckAllPresent", "has_all_keys",
                "@string(empty(intersection(pipeline().parameters.required_keys, pipeline().parameters.available_keys)))",
                deps=["FindCommonKeys"]),
            if_condition_activity("ValidateKeys",
                "@not(empty(intersection(pipeline().parameters.required_keys, pipeline().parameters.available_keys)))",
                deps=["CheckAllPresent"]),
        ],
    )
    pipelines.append(("017_collection_operations_full", p, "union + intersection + empty + json + createArray combined in one pipeline."))

    # 018 — datetime_watermark_manager
    p = build_pipeline(
        "datetime_watermark_manager",
        {"watermark_override": param_decl("String", ""),
         "timezone": param_decl("String", "Eastern Standard Time")},
        {"effective_watermark": var_decl(), "local_watermark": var_decl(),
         "formatted_watermark": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("ResolveWatermark", "effective_watermark",
                "@coalesce(pipeline().parameters.watermark_override, formatDateTime(utcnow(), 'yyyy-MM-ddTHH:mm:ss'))"),
            set_variable_activity("ConvertToLocal", "local_watermark",
                "@convertFromUtc(utcnow(), pipeline().parameters.timezone, 'yyyy-MM-dd HH:mm:ss')",
                deps=["ResolveWatermark"]),
            set_variable_activity("FormatWatermark", "formatted_watermark",
                "@formatDateTime(utcnow(), 'yyyy/MM/dd')",
                deps=["ConvertToLocal"]),
            copy_activity("IncrementalCopy",
                "@concat('SELECT * FROM events WHERE updated_at > ''', variables('effective_watermark'), '''')",
                deps=["FormatWatermark"]),
        ],
    )
    pipelines.append(("018_datetime_watermark_manager", p, "coalesce + convertFromUtc + formatDateTime combined for watermark management."))

    # 019 — math_expression_batch_sizer
    p = build_pipeline(
        "math_expression_batch_sizer",
        {"total_records": param_decl("Int", 10000), "num_partitions": param_decl("Int", 4),
         "overhead_factor": param_decl("Int", 2), "min_batch": param_decl("Int", 100)},
        {"batch_size": var_decl(), "adjusted_size": var_decl(),
         "partition_size": var_decl(), "remainder": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("CalcBatchSize", "batch_size",
                "@string(div(pipeline().parameters.total_records, pipeline().parameters.num_partitions))"),
            set_variable_activity("CalcAdjusted", "adjusted_size",
                "@string(add(div(pipeline().parameters.total_records, pipeline().parameters.num_partitions), mul(pipeline().parameters.overhead_factor, pipeline().parameters.num_partitions)))",
                deps=["CalcBatchSize"]),
            set_variable_activity("CalcRemainder", "remainder",
                "@string(mod(pipeline().parameters.total_records, pipeline().parameters.num_partitions))",
                deps=["CalcBatchSize"]),
            set_variable_activity("CalcPartition", "partition_size",
                "@string(sub(div(pipeline().parameters.total_records, pipeline().parameters.num_partitions), pipeline().parameters.overhead_factor))",
                deps=["CalcAdjusted"]),
            if_condition_activity("CheckMinBatch",
                "@greater(div(pipeline().parameters.total_records, pipeline().parameters.num_partitions), pipeline().parameters.min_batch)",
                deps=["CalcPartition"]),
        ],
    )
    pipelines.append(("019_math_expression_batch_sizer", p, "add + sub + mul + div + mod on parameters for batch size calculation."))

    return pipelines


# ===========================================================================
# THEME 4: customer_inspired_unsupported (20 pipelines)
# ===========================================================================
def gen_unsupported_pipelines() -> list[tuple[str, dict, str]]:
    """Generate 20 pipelines featuring unsupported expression patterns."""
    pipelines = []

    # 000 — global_param_env_reader
    p = build_pipeline(
        "global_param_env_reader",
        {"app_name": param_decl("String", "etl")},
        {"lib_path": var_decl(), "config_path": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("SetLibPath", "lib_path",
                "@concat('/volumes/catalog/', pipeline().globalParameters.env_variable, '/gold/config/common_libraries/', pipeline().globalParameters.lib_file_name)"),
            set_variable_activity("SetConfigPath", "config_path",
                "@concat('/volumes/catalog/', pipeline().globalParameters.env_variable, '/gold/config/', pipeline().parameters.app_name, '/settings.json')",
                deps=["SetLibPath"]),
            notebook_activity("RunWithLibs", "/pipelines/etl/main",
                {"library_path": "@variables('lib_path')", "config_path": "@variables('config_path')"},
                deps=["SetConfigPath"]),
        ],
    )
    pipelines.append(("000_global_param_env_reader", p, "pipeline().globalParameters.X — unsupported global parameter for library paths."))

    # 001 — global_param_url_builder
    p = build_pipeline(
        "global_param_url_builder",
        {"job_id": param_decl("String", "j-001")},
        {"api_url": var_decl(), "permissions_url": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("BuildApiUrl", "api_url",
                "@concat(pipeline().globalParameters.databricks_api_url, '/api/2.1/jobs/runs/get?run_id=', pipeline().parameters.job_id)"),
            set_variable_activity("BuildPermissionsUrl", "permissions_url",
                "@concat(pipeline().globalParameters.databricks_api_url, '/api/2.0/permissions/jobs/', pipeline().parameters.job_id)",
                deps=["BuildApiUrl"]),
            web_activity("CheckJobStatus", "@variables('api_url')", method="GET",
                deps=["BuildPermissionsUrl"]),
        ],
    )
    pipelines.append(("001_global_param_url_builder", p, "pipeline().globalParameters in URL concat — unsupported global parameter for API URLs."))

    # 002-005 — run_output variants
    run_output_activities = [
        ("data_validation", "RunDataValidation", "is_valid"),
        ("row_count_check", "CheckRowCount", "row_count"),
        ("schema_check", "ValidateSchema", "schema_valid"),
        ("notebook_result", "RunNotebook", "result_code"),
    ]
    for i, (suffix, act_name, _field) in enumerate(run_output_activities):
        idx = 2 + i
        p = build_pipeline(
            f"run_output_variant_{suffix}",
            {"threshold": param_decl("Int", 1)},
            {"check_result": var_decl(), "status_flag": var_decl()},
            [
                notebook_activity(act_name, f"/pipelines/checks/{suffix}"),
                if_condition_activity(f"Check{act_name}Result",
                    f"@equals(activity('{act_name}').output.runOutput, pipeline().parameters.threshold)",
                    deps=[act_name]),
                set_variable_activity("StoreResult", "check_result",
                    f"@string(activity('{act_name}').output.runOutput)",
                    deps=[f"Check{act_name}Result"]),
            ],
        )
        pipelines.append((f"{idx:03d}_run_output_{suffix}", p,
            f"activity('{act_name}').output.runOutput — unsupported notebook output reference."))

    # 006-007 — pipeline_return_value
    prv_variants = [
        ("result_code", "RunChildPipeline", "pipelineReturnValue.result_code", "child_etl"),
        ("array_data", "RunDataExtract", "pipelineReturnValue.str_array", "data_extract"),
    ]
    for i, (suffix, act_name, prop, pipeline_ref) in enumerate(prv_variants):
        idx = 6 + i
        p = build_pipeline(
            f"pipeline_return_value_{suffix}",
            {"input_param": param_decl("String", "default")},
            {"return_value": var_decl(), "status_flag": var_decl()},
            [
                execute_pipeline_activity(act_name, pipeline_ref,
                    {"input": "@pipeline().parameters.input_param"}),
                set_variable_activity("CaptureReturn", "return_value",
                    f"@activity('{act_name}').output.{prop}",
                    deps=[act_name]),
                if_condition_activity("CheckReturn",
                    f"@not(empty(activity('{act_name}').output.{prop}))",
                    deps=["CaptureReturn"]),
            ],
        )
        pipelines.append((f"{idx:03d}_pipeline_return_value_{suffix}", p,
            f"activity('{act_name}').output.{prop} — unsupported pipelineReturnValue reference."))

    # 008-009 — error handlers
    error_variants = [
        ("message", "RunCriticalJob", "error.message"),
        ("error_code", "RunBatchProcess", "error.errorCode"),
    ]
    for i, (suffix, act_name, prop) in enumerate(error_variants):
        idx = 8 + i
        p = build_pipeline(
            f"error_handler_{suffix}",
            {},
            {"error_detail": var_decl(), "error_code": var_decl(), "status_flag": var_decl()},
            [
                notebook_activity(act_name, f"/pipelines/jobs/{suffix}_job"),
                set_variable_activity("CaptureError", "error_detail",
                    f"@activity('{act_name}').{prop}",
                    deps=[act_name]),
                set_variable_activity("BuildErrorMessage", "error_code",
                    f"@concat('Error: ', activity('{act_name}').{prop})",
                    deps=["CaptureError"]),
                fail_activity("ReportError",
                    f"@concat('Pipeline failed: ', activity('{act_name}').{prop})",
                    f"@concat('ERR_', activity('{act_name}').error.errorCode)",
                    deps=["BuildErrorMessage"]),
            ],
        )
        pipelines.append((f"{idx:03d}_error_handler_{suffix}", p,
            f"activity('{act_name}').{prop} — unsupported error property reference."))

    # 010-013 — optional_chaining (item()?.X)
    chaining_variants = [
        ("condition", "@coalesce(item()?.condition, 'notFound')"),
        ("condition_name", "@coalesce(item()?.condition?.name, 'name_notFound')"),
        ("item_type", "@toUpper(coalesce(item()?.type, 'default'))"),
        ("aux_params", "@coalesce(item()?.aux_params, '{}')"),
    ]
    for i, (suffix, chain_expr) in enumerate(chaining_variants):
        idx = 10 + i
        p = build_pipeline(
            f"optional_chaining_{suffix}",
            {"items_config": param_decl("String", '[{"name": "task1"}]')},
            {"resolved_value": var_decl(), "status_flag": var_decl()},
            [
                foreach_activity(f"Process{suffix.title().replace('_', '')}",
                    "@json(pipeline().parameters.items_config)",
                    [
                        set_variable_activity("ResolveChain", "resolved_value", chain_expr),
                    ]),
            ],
        )
        pipelines.append((f"{idx:03d}_optional_chaining_{suffix}", p,
            f"{chain_expr} — unsupported optional chaining (item()?.X) in ForEach."))

    # 014 — data_factory_env_check
    p = build_pipeline(
        "data_factory_env_check",
        {"expected_factory": param_decl("String", "data_factory_prod")},
        {"is_prod": var_decl(), "status_flag": var_decl()},
        [
            if_condition_activity("CheckFactory",
                "@equals(pipeline().DataFactory, pipeline().parameters.expected_factory)",
                if_true=[
                    set_variable_activity("SetProd", "is_prod", "@string('true')"),
                ],
                if_false=[
                    set_variable_activity("SetNonProd", "is_prod", "@string('false')"),
                ]),
        ],
    )
    pipelines.append(("014_data_factory_env_check", p, "pipeline().DataFactory — unsupported system variable for environment detection."))

    # 015 — triggered_by_pipeline_id
    p = build_pipeline(
        "triggered_by_pipeline_id",
        {"app_name": param_decl("String", "orchestrator"), "pipeline_name": param_decl("String", "main")},
        {"unique_id": var_decl(), "status_flag": var_decl()},
        [
            set_variable_activity("GenerateUniqueId", "unique_id",
                "@concat(pipeline().parameters.app_name, '#$', pipeline().parameters.pipeline_name, '#', utcnow('yyyy/MM/dd'), '#', pipeline().TriggeredByPipelineRunId)"),
            if_condition_activity("HasParent",
                "@not(equals(pipeline().TriggeredByPipelineRunId, ''))",
                deps=["GenerateUniqueId"]),
        ],
    )
    pipelines.append(("015_triggered_by_pipeline_id", p, "pipeline().TriggeredByPipelineRunId — unsupported system variable in UID generation."))

    # 016 — deep_output_chain
    p = build_pipeline(
        "deep_output_chain",
        {},
        {"cluster_id": var_decl(), "status_flag": var_decl()},
        [
            web_activity("GetClusterId", "https://api.example-corp.com/api/2.1/jobs/runs/get", method="GET"),
            set_variable_activity("ExtractClusterId", "cluster_id",
                "@activity('GetClusterId').output.tasks[0].cluster_instance.cluster_id",
                deps=["GetClusterId"]),
        ],
    )
    pipelines.append(("016_deep_output_chain", p, "activity().output.tasks[0].cluster_instance.cluster_id — unsupported deep output chain with index."))

    # 017 — activity_output_bare
    p = build_pipeline(
        "activity_output_bare",
        {},
        {"has_error": var_decl(), "output_data": var_decl(), "status_flag": var_decl()},
        [
            notebook_activity("RunProcess", "/pipelines/process/main"),
            set_variable_activity("CheckForError", "has_error",
                "@string(contains(activity('RunProcess').output, 'runError'))",
                deps=["RunProcess"]),
            set_variable_activity("CaptureOutput", "output_data",
                "@concat('result##', if(contains(activity('RunProcess').output, 'runError'), '', activity('RunProcess').output.runOutput))",
                deps=["CheckForError"]),
        ],
    )
    pipelines.append(("017_activity_output_bare", p, "activity('name').output without sub-property — unsupported bare output reference in contains()."))

    # 018 — nested_unsupported_5level
    p = build_pipeline(
        "nested_unsupported_5level",
        {"previous_outputs": param_decl("String", "{}"), "execution_outputs": param_decl("String", "{}")},
        {"skip_condition": var_decl(), "debug_trace": var_decl(), "status_flag": var_decl()},
        [
            foreach_activity("EvaluateConditions",
                "@json(pipeline().parameters.previous_outputs)",
                [
                    set_variable_activity("NonSkipCondition", "skip_condition",
                        "@if(equals(string(coalesce(item()?.condition, 'notFound')), 'notFound'), true, if(contains(variables('execution_outputs'), concat('\"', coalesce(item()?.condition?.name, 'name_notFound'), '\"')), if(contains(string(json(variables('execution_outputs'))[item().condition.name]), concat('\"', coalesce(item()?.condition?.internal_name, item().condition.name), '\"')), true, false), false))"),
                    set_variable_activity("DebugTrace", "debug_trace",
                        "@if(equals(string(coalesce(item()?.condition, 'notFound')), 'notFound'), concat('No condition for task: ', coalesce(item()?.name, 'unnamed')), concat('Outputs: ', variables('execution_outputs')))",
                        deps=["NonSkipCondition"]),
                ]),
        ],
    )
    p["properties"]["variables"]["execution_outputs"] = var_decl("String", "{}")
    pipelines.append(("018_nested_unsupported_5level", p, "5-level deep if/equals/coalesce/contains with item()?.X — the most complex unsupported pattern."))

    # 019 — union_with_return_value
    p = build_pipeline(
        "union_with_return_value",
        {},
        {"merged_outputs": var_decl(), "execution_outputs": var_decl("String", "{}"), "status_flag": var_decl()},
        [
            execute_pipeline_activity("RunInternalSwitch", "internal_switch_pipeline",
                {"config": "@pipeline().parameters.config"} if False else {}),
            foreach_activity("AggregateOutputs",
                "@createArray('step1', 'step2', 'step3')",
                [
                    set_variable_activity("MergeOutput", "merged_outputs",
                        "@string(union(json(if(startswith(activity('RunInternalSwitch').output.pipelineReturnValue.result, '{'), concat('{\"', coalesce(item()?.name, 'unnamed'), '\": ', activity('RunInternalSwitch').output.pipelineReturnValue.result, '}'), '{}')), json(variables('execution_outputs'))))"),
                ],
                deps=["RunInternalSwitch"]),
        ],
    )
    pipelines.append(("019_union_with_return_value", p, "string(union(json(if(startswith(activity().output.pipelineReturnValue...)))))  — deeply nested unsupported with union + json + pipelineReturnValue + item()?.X."))

    return pipelines


# ===========================================================================
# Main: generate all pipelines, write to disk, verify anonymization
# ===========================================================================
def verify_anonymization(output_dir: str) -> list[str]:
    """Scan all generated JSON for blocklist violations. Returns violation list."""
    violations = []
    for root, _dirs, files in os.walk(output_dir):
        for fname in files:
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, encoding="utf-8") as f:
                content = f.read().lower()
            for term in BLOCKLIST:
                if term.lower() in content:
                    violations.append(f"{fpath}: contains blocklisted term '{term}'")
    return violations


def main() -> None:
    """Generate all 80 pipelines across 4 themes."""
    theme_generators = {
        "customer_inspired_string": gen_string_pipelines,
        "customer_inspired_logical": gen_logical_pipelines,
        "customer_inspired_collection_datetime": gen_collection_datetime_pipelines,
        "customer_inspired_unsupported": gen_unsupported_pipelines,
    }

    total_pipelines = 0
    for theme, generator in theme_generators.items():
        theme_dir = os.path.join(GEN_DIR, theme)
        os.makedirs(theme_dir, exist_ok=True)

        entries = generator()
        suite_pipelines = []

        for dir_name, pipeline_json, description in entries:
            # Write individual adf_pipeline.json
            pipeline_dir = os.path.join(theme_dir, dir_name)
            os.makedirs(pipeline_dir, exist_ok=True)
            pipeline_path = os.path.join(pipeline_dir, "adf_pipeline.json")
            with open(pipeline_path, "w", encoding="utf-8") as f:
                json.dump(pipeline_json, f, indent=2, sort_keys=False)

            # Build suite entry
            suite_pipelines.append(
                pipeline_to_suite_entry(pipeline_json, description)
            )
            total_pipelines += 1

        # Write suite.json
        suite_path = os.path.join(theme_dir, "suite.json")
        with open(suite_path, "w", encoding="utf-8") as f:
            json.dump({"pipelines": suite_pipelines}, f, indent=2, sort_keys=False)

        print(f"  {theme}: {len(entries)} pipelines written")

    print(f"\nTotal: {total_pipelines} pipelines across {len(theme_generators)} themes")

    # Verify anonymization
    print("\nVerifying anonymization...")
    violations = verify_anonymization(GEN_DIR)
    # Only check NEW theme directories
    new_violations = [v for v in violations if "customer_inspired_" in v]
    if new_violations:
        print(f"\nANONYMIZATION VIOLATIONS ({len(new_violations)}):")
        for v in new_violations:
            print(f"  {v}")
        sys.exit(1)
    else:
        print("Anonymization check PASSED — no blocklisted terms found in new pipelines.")

    print(f"\nDone. Files written to {GEN_DIR}/customer_inspired_*/")


if __name__ == "__main__":
    main()
