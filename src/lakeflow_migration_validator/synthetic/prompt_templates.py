"""Preset prompt templates for synthetic pipeline generation.

Each template focuses on a specific testing scenario. Templates use
``{count}`` and ``{max_activities}`` placeholders that are filled at
generation time. The user can edit the resolved prompt before submitting.
"""

from __future__ import annotations

PROMPT_TEMPLATES: dict[str, dict[str, str]] = {
    "complex_expressions": {
        "label": "Complex Expressions",
        "icon": "function",
        "description": "Nested expressions 3+ levels deep combining concat, formatDateTime, pipeline().parameters, and activity().output",
        "prompt": """Generate {count} realistic ADF pipelines that stress-test complex
nested ADF expressions. Each pipeline should:
- Use expressions nested 3+ levels deep combining concat, formatDateTime,
  utcNow, pipeline().parameters, and activity().output references
- Include SetVariable activities that consume upstream Lookup outputs
  via @activity('LookupName').output.firstRow.columnName
- Include pipeline parameters: env, prefix, threshold, date_override
- Have {max_activities} activities with dependency chains
- Use realistic naming conventions (e.g., etl_daily_load, extract_customer_data)

Output ONLY valid ADF pipeline JSON per pipeline. Each pipeline must have
"name" and "properties.activities" fields.""",
    },

    "deep_nesting": {
        "label": "Deep Nesting",
        "icon": "account_tree",
        "description": "ForEach containing IfCondition containing ForEach — 3+ levels of control flow",
        "prompt": """Generate {count} ADF pipelines with deeply nested control flow:
- ForEach containing IfCondition containing another ForEach or nested IfCondition
- Inner activities should be DatabricksNotebook with expression-valued base_parameters
- ForEach items should use expression-generated arrays like
  @createArray(concat('table_', pipeline().parameters.suffix), 'config_data')
- IfCondition predicates should use logical operators:
  @and(greater(pipeline().parameters.threshold, 50), not(equals(pipeline().parameters.env, 'prod')))
- Have {max_activities} activities total across all nesting levels
- Include pipeline parameters: env, threshold, suffix, batch_size

Output ONLY valid ADF pipeline JSON.""",
    },

    "activity_mix": {
        "label": "Activity Mix",
        "icon": "dashboard",
        "description": "All supported activity types with realistic dependency chains",
        "prompt": """Generate {count} ADF pipelines using ALL supported activity types:
DatabricksNotebook, Copy, Lookup, WebActivity, SetVariable, ForEach, IfCondition.
Each pipeline should:
- Use at least 4 different activity types
- Have realistic dependency chains (Lookup -> SetVariable -> Copy -> Notebook)
- Include linked service references for Copy and Lookup activities
- Use expressions in at least 3 activity properties
- Have {max_activities} activities total
- Include pipeline parameters: env, source_container, target_schema

Output ONLY valid ADF pipeline JSON.""",
    },

    "math_on_params": {
        "label": "Math on Parameters",
        "icon": "calculate",
        "description": "Math functions on pipeline parameters — tests numeric coercion",
        "prompt": """Generate {count} ADF pipelines that extensively use math functions
on pipeline parameters. These stress-test the numeric coercion logic since
dbutils.widgets.get() returns strings. Each pipeline should include expressions like:
- @add(mul(pipeline().parameters.count, 2), 1)
- @div(pipeline().parameters.total, pipeline().parameters.batch_size)
- @mod(pipeline().parameters.row_count, 1000)
- @sub(pipeline().parameters.limit, activity('GetCount').output.firstRow.current)
- Include pipeline parameters with numeric defaults: count (Int, default 10),
  batch_size (Int, default 100), total (Int, default 1000), limit (Int, default 500)
- Have {max_activities} activities

Output ONLY valid ADF pipeline JSON.""",
    },

    "unsupported_types": {
        "label": "Unsupported Types",
        "icon": "warning",
        "description": "Mix of supported and unsupported activity types — tests placeholder generation",
        "prompt": """Generate {count} ADF pipelines that include a mix of supported and
unsupported activity types. This tests placeholder generation and activity_coverage scoring.
- Supported: DatabricksNotebook, Copy, Lookup, WebActivity, SetVariable, ForEach, IfCondition
- Unsupported: AzureFunctionActivity, ExecuteSSISPackage, Wait, ExecutePipeline, Switch, Until
- Each pipeline should have roughly 50% supported and 50% unsupported activities
- Include dependencies between supported and unsupported activities
- Have {max_activities} activities total
- Include pipeline parameters: env, function_url, ssis_package_path

Output ONLY valid ADF pipeline JSON.""",
    },

    "full_coverage": {
        "label": "Full Coverage",
        "icon": "verified",
        "description": "Exercise ALL validator dimensions — each pipeline has deliberate weaknesses",
        "prompt": """Generate {count} ADF pipelines that exercise ALL dimensions of the
Lakeflow Migration Validator. Each pipeline should have deliberate weaknesses in
1-2 dimensions for targeted testing:
- activity_coverage: include 1-2 unsupported activity types
- expression_coverage: include 1-2 expressions that use unsupported functions
- dependency_preservation: include complex dependency conditions (not just Succeeded)
- notebook_validity: include activities that would generate syntactically complex notebooks
- parameter_completeness: reference parameters that are not defined in the pipeline
- secret_completeness: reference secrets in generated code
- not_translatable_ratio: include properties that cannot be translated (e.g., secure_input)
- Have {max_activities} activities total
- Include pipeline parameters: env, secret_key, storage_account

Output ONLY valid ADF pipeline JSON.""",
    },
}


def resolve_template(
    template_key: str,
    count: int = 10,
    max_activities: int = 10,
) -> str:
    """Resolve a preset template with the given parameters."""
    template = PROMPT_TEMPLATES.get(template_key)
    if template is None:
        raise ValueError(f"Unknown template: {template_key}. Available: {list(PROMPT_TEMPLATES.keys())}")
    return template["prompt"].format(count=count, max_activities=max_activities)


def list_templates() -> list[dict[str, str]]:
    """Return metadata for all available preset templates."""
    return [
        {"key": key, "label": t["label"], "icon": t["icon"], "description": t["description"]}
        for key, t in PROMPT_TEMPLATES.items()
    ]
