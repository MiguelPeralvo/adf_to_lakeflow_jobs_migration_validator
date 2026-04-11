# Databricks Lakeflow Jobs Patterns

> Last updated: 2026-04-11

## What Lakeflow Jobs Are

Databricks Lakeflow Jobs (formerly "Workflows") orchestrate tasks in a DAG. Each task runs a notebook, JAR, Python script, or SQL query. The migration target for ADF pipelines.

## Structural Mapping: ADF → Lakeflow Jobs

| ADF Concept | Lakeflow Jobs Equivalent |
|-------------|-------------------------|
| Pipeline | Job (with task DAG) |
| Activity | Task |
| Activity dependency (dependsOn) | Task dependency |
| Pipeline parameter | Job parameter (via widgets) |
| Variable | Notebook-scoped variable |
| ForEach | Task loop (or notebook-internal loop) |
| IfCondition | `dbutils.notebook.run()` conditional |
| Notebook activity | Notebook task (direct) |
| Copy activity | Notebook task (with Spark read/write) |
| Lookup activity | Notebook task (with Spark SQL) |
| SetVariable | Assignment in notebook |
| WebActivity | Notebook task (with `requests`) |

## Parameter Passing Patterns

### Pipeline Parameters → Widgets
```python
# In the generated notebook:
dbutils.widgets.text("env", "")
dbutils.widgets.text("batch_id", "")

# Usage:
env = dbutils.widgets.get("env")
batch_id = dbutils.widgets.get("batch_id")
```

### Activity Output → Task Values
```python
# In the upstream task (e.g., Lookup):
dbutils.jobs.taskValues.set(key="config_value", value=result)

# In the downstream task:
config_value = dbutils.jobs.taskValues.get(taskKey="lookup_task", key="config_value")
```

### Variables → Notebook Scope
```python
# ADF: SetVariable "result" = @concat('prefix_', pipeline().parameters.name)
result = str('prefix_') + str(dbutils.widgets.get('name'))
```

## Notebook Code Quality Criteria

What makes a "good" translated notebook:

1. **No SyntaxError** — the notebook must be valid Python
2. **Correct widget declarations** — every parameter reference has a matching `dbutils.widgets.text()` call
3. **Proper coercion** — `dbutils.widgets.get()` always returns str; math needs `int()`/`float()`
4. **Dependency order** — code cells follow the DAG order
5. **Idempotent** — safe to rerun (no append-only side effects without guards)
6. **Error handling** — `try/except` for external calls (WebActivity → requests)
7. **Secret management** — secrets via `dbutils.secrets.get(scope, key)`, never hardcoded

## Common Translation Pitfalls

| Pitfall | Description | Detection |
|---------|-------------|-----------|
| Missing widgets | Parameter used but not declared | `parameter_completeness` dimension |
| String math | `widgets.get + 1` instead of `int(widgets.get) + 1` | Semantic equivalence judge |
| Lost dependencies | `dependsOn` not reflected in task DAG | `dependency_preservation` dimension |
| Placeholder notebooks | Unsupported activity → empty notebook with TODO | `activity_coverage` dimension |
| Silent drops | Expression-bearing field ignored by translator | `expression_coverage` + L-F19 detector |

## Cluster Configuration

Generated notebooks should declare cluster requirements:
```python
# At the top of the notebook:
# Databricks notebook source
# MAGIC %md
# MAGIC ### Migrated from ADF Pipeline: {pipeline_name}
# MAGIC Activity: {activity_name} ({activity_type})
```

## Secrets Management

ADF linked services with credentials → Databricks secret scopes:
```python
# ADF: linkedService("MyStorage").connectionString
# Lakeflow:
connection_string = dbutils.secrets.get(scope="migration", key="MyStorage_connectionString")
```

The `secret_completeness` dimension checks that every ADF credential reference has a corresponding secret instruction.
