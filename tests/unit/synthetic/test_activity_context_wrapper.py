"""TDD tests for the activity-context wrapper sweep (L-F5).

Wraps a single ADF expression in different activity contexts (SetVariable,
IfCondition, ForEach, WebActivity body, Lookup source query, Copy source
query, DatabricksNotebook base_parameter) and verifies the resulting ADF
JSON has the expression injected at the correct expression-bearing
property.

These tests intentionally do NOT import wkmigrate so they run in the fast
tier (LR-1). The sweep_activity_contexts test uses a mock convert_fn so
it also stays in the fast tier.
"""

from __future__ import annotations

from lakeflow_migration_validator.synthetic.activity_context_wrapper import (
    ACTIVITY_CONTEXTS,
    sweep_activity_contexts,
    wrap_in_copy_query,
    wrap_in_for_each,
    wrap_in_if_condition,
    wrap_in_lookup_query,
    wrap_in_notebook_base_param,
    wrap_in_set_variable,
    wrap_in_web_body,
)


# ---------------------------------------------------------------------------
# Per-context wrapper tests — verify shape and expression injection
# ---------------------------------------------------------------------------


def _expression_node(value: str) -> dict:
    return {"type": "Expression", "value": value}


def test_wrap_in_set_variable_injects_expression_at_value():
    pipe = wrap_in_set_variable("@concat('a', 'b')", name="t")

    assert pipe["name"] == "t"
    assert len(pipe["activities"]) == 1
    activity = pipe["activities"][0]
    assert activity["type"] == "SetVariable"
    assert activity["value"] == _expression_node("@concat('a', 'b')")
    assert "result" in pipe["variables"]


def test_wrap_in_if_condition_injects_expression_at_expression_property():
    pipe = wrap_in_if_condition("@equals(1, 1)", name="t")

    activity = pipe["activities"][0]
    assert activity["type"] == "IfCondition"
    # IfCondition's expression-bearing property is `expression` per
    # pipeline_generator.py:163-164 (wkmigrate reads activity.get("expression"))
    assert activity["expression"] == _expression_node("@equals(1, 1)")
    # Both branches are populated with a trivial DatabricksNotebook so
    # wkmigrate has a non-empty body to wrap (otherwise it falls back to a
    # placeholder activity, obscuring the predicate signal).
    assert len(activity["if_true_activities"]) == 1
    assert activity["if_true_activities"][0]["type"] == "DatabricksNotebook"
    assert len(activity["if_false_activities"]) == 1
    assert activity["if_false_activities"][0]["type"] == "DatabricksNotebook"


def test_wrap_in_for_each_injects_expression_at_items():
    pipe = wrap_in_for_each("@createArray('a', 'b')", name="t")

    activity = pipe["activities"][0]
    assert activity["type"] == "ForEach"
    assert activity["items"] == _expression_node("@createArray('a', 'b')")
    # The inner activities array is populated with a trivial DatabricksNotebook
    # so wkmigrate has a body to iterate over (otherwise it falls back to a
    # placeholder, obscuring the items-translation signal).
    assert len(activity["activities"]) == 1
    assert activity["activities"][0]["type"] == "DatabricksNotebook"


def test_wrap_in_web_body_injects_expression_at_body():
    pipe = wrap_in_web_body("@concat('hello', 'world')", name="t")

    activity = pipe["activities"][0]
    assert activity["type"] == "WebActivity"
    assert activity["body"] == _expression_node("@concat('hello', 'world')")
    # url and method are present so wkmigrate can validate the activity shape
    assert "url" in activity
    assert "method" in activity


def test_wrap_in_lookup_query_injects_expression_at_sql_reader_query():
    """The deferred wkmigrate#28 Lookup translator adoption gap is exactly this property."""
    pipe = wrap_in_lookup_query("@concat('SELECT * FROM ', 'config_table')", name="t")

    activity = pipe["activities"][0]
    assert activity["type"] == "Lookup"
    # The expression is injected at source.sql_reader_query — the property
    # wkmigrate's deferred Lookup translator should adopt
    assert activity["source"]["sql_reader_query"] == _expression_node("@concat('SELECT * FROM ', 'config_table')")
    # Lookup needs an input dataset definition for wkmigrate to recognise it
    assert "input_dataset_definitions" in activity
    assert len(activity["input_dataset_definitions"]) >= 1


def test_wrap_in_copy_query_injects_expression_at_source_sql_reader_query():
    """The other deferred wkmigrate#28 Copy translator adoption gap."""
    pipe = wrap_in_copy_query("@concat('SELECT * FROM ', 'src')", name="t")

    activity = pipe["activities"][0]
    assert activity["type"] == "Copy"
    assert activity["source"]["sql_reader_query"] == _expression_node("@concat('SELECT * FROM ', 'src')")
    # Copy needs both input and output dataset definitions
    assert "input_dataset_definitions" in activity
    assert "output_dataset_definitions" in activity
    # Copy needs a translator with at least one column mapping; wkmigrate's
    # Copy preparer raises ValueError("No column mapping provided for copy
    # data task") when absent.
    assert "translator" in activity
    assert activity["translator"]["type"] == "TabularTranslator"
    assert len(activity["translator"]["mappings"]) >= 1


def test_wrap_in_notebook_base_param_injects_expression_at_base_parameters():
    pipe = wrap_in_notebook_base_param("@pipeline().RunId", name="t")

    activity = pipe["activities"][0]
    assert activity["type"] == "DatabricksNotebook"
    assert "base_parameters" in activity
    # The expression is the value of (any) one base_parameter key
    base_params = activity["base_parameters"]
    assert len(base_params) >= 1
    # Find the parameter that holds our expression
    matched = [v for v in base_params.values() if v == _expression_node("@pipeline().RunId")]
    assert len(matched) == 1


def test_activity_contexts_dict_lists_all_seven_wrappers():
    """The ACTIVITY_CONTEXTS dict is the registry that drives the sweep."""
    expected = {
        "set_variable",
        "if_condition",
        "for_each",
        "web_body",
        "lookup_query",
        "copy_query",
        "notebook_base_param",
    }
    assert set(ACTIVITY_CONTEXTS.keys()) == expected
    # Each value is a callable that takes (expression, name) and returns a dict
    for name, fn in ACTIVITY_CONTEXTS.items():
        result = fn("@test()", name=f"probe_{name}")
        assert isinstance(result, dict)
        assert "name" in result
        assert "activities" in result


# ---------------------------------------------------------------------------
# Sweep helper tests — uses a mock convert_fn so we don't need wkmigrate
# ---------------------------------------------------------------------------


def _make_mock_snapshot(resolved_count: int = 0, placeholder_count: int = 0):
    """Build a tiny mock snapshot for sweep tests without depending on the real adapter."""
    from lakeflow_migration_validator.contract import ConversionSnapshot, ExpressionPair

    placeholder_warnings = [
        {
            "kind": "placeholder_activity",
            "task_key": f"ph_{i}",
            "property": f"ph_{i}",
            "message": "Activity 'mystery' was substituted with a placeholder DatabricksNotebookActivity",
        }
        for i in range(placeholder_count)
    ]
    expressions = tuple(ExpressionPair(adf_expression=f"@x{i}", python_code=f"x{i}") for i in range(resolved_count))
    return ConversionSnapshot(
        tasks=(),
        notebooks=(),
        secrets=(),
        parameters=(),
        dependencies=(),
        not_translatable=tuple(placeholder_warnings),
        resolved_expressions=expressions,
        source_pipeline={},
        total_source_dependencies=0,
    )


def test_sweep_aggregates_per_cell_resolved_and_placeholder_counts():
    """Sweep aggregates resolved + placeholder counts per (category, context) cell."""
    corpus = [
        {"adf_expression": "@a", "category": "string", "expected_python": "a"},
        {"adf_expression": "@b", "category": "string", "expected_python": "b"},
        {"adf_expression": "@c", "category": "math", "expected_python": "c"},
    ]

    # Mock convert_fn always returns a snapshot with 1 resolved expression
    # except for if_condition where it returns a placeholder (simulating
    # wkmigrate failing to translate the activity)
    def mock_convert(payload: dict):
        activity_type = payload["activities"][0]["type"]
        if activity_type == "IfCondition":
            return _make_mock_snapshot(resolved_count=0, placeholder_count=1)
        return _make_mock_snapshot(resolved_count=1, placeholder_count=0)

    result = sweep_activity_contexts(corpus, mock_convert)

    # Each (category, context) cell got run once (or twice for string)
    assert "string,set_variable" in result["by_cell"]
    assert result["by_cell"]["string,set_variable"]["total"] == 2
    assert result["by_cell"]["string,set_variable"]["resolved"] == 2

    # IfCondition cells should show 0 resolved + 1 placeholder for each entry
    assert result["by_cell"]["string,if_condition"]["total"] == 2
    assert result["by_cell"]["string,if_condition"]["resolved"] == 0
    assert result["by_cell"]["string,if_condition"]["placeholder_count"] == 2

    # Per-context totals roll up across categories
    assert result["by_context"]["set_variable"]["total"] == 3
    assert result["by_context"]["set_variable"]["resolved"] == 3
    assert result["by_context"]["if_condition"]["total"] == 3
    assert result["by_context"]["if_condition"]["resolved"] == 0
    assert result["by_context"]["if_condition"]["placeholder_count"] == 3


def test_sweep_records_sample_failures_for_zero_resolved_cells():
    """When a cell has 0 resolved expressions, sample failures get recorded for diagnosis."""
    corpus = [{"adf_expression": "@fail", "category": "string", "expected_python": "fail"}]

    def mock_convert(payload):
        return _make_mock_snapshot(resolved_count=0, placeholder_count=1)

    result = sweep_activity_contexts(corpus, mock_convert, contexts=["set_variable"])

    cell = result["by_cell"]["string,set_variable"]
    assert cell["total"] == 1
    assert cell["resolved"] == 0
    assert len(cell["sample_failures"]) == 1
    assert cell["sample_failures"][0]["adf_expression"] == "@fail"
    assert "expected_python" in cell["sample_failures"][0]


def test_sweep_handles_convert_fn_exceptions_as_errors():
    """If convert_fn raises, the cell records an error_count + a sample failure."""
    corpus = [{"adf_expression": "@boom", "category": "string", "expected_python": "boom"}]

    def mock_convert(payload):
        raise ValueError("simulated wkmigrate crash")

    result = sweep_activity_contexts(corpus, mock_convert, contexts=["set_variable"])

    cell = result["by_cell"]["string,set_variable"]
    assert cell["error_count"] == 1
    assert cell["resolved"] == 0
    # Sample failure includes the error message
    assert len(cell["sample_failures"]) == 1
    assert "error" in cell["sample_failures"][0]
    assert "ValueError" in cell["sample_failures"][0]["error"]


def test_sweep_respects_explicit_contexts_subset():
    """contexts= argument restricts which wrappers are exercised."""
    corpus = [{"adf_expression": "@x", "category": "string", "expected_python": "x"}]

    def mock_convert(payload):
        return _make_mock_snapshot(resolved_count=1)

    result = sweep_activity_contexts(corpus, mock_convert, contexts=["lookup_query", "copy_query"])

    assert set(result["contexts_run"]) == {"lookup_query", "copy_query"}
    assert "string,lookup_query" in result["by_cell"]
    assert "string,copy_query" in result["by_cell"]
    assert "string,set_variable" not in result["by_cell"]


def test_sweep_skips_unknown_context_names():
    """Unknown context names in the explicit list are silently dropped (not an error)."""
    corpus = [{"adf_expression": "@x", "category": "string", "expected_python": "x"}]

    def mock_convert(payload):
        return _make_mock_snapshot(resolved_count=1)

    result = sweep_activity_contexts(corpus, mock_convert, contexts=["set_variable", "imaginary_context"])

    # Only set_variable was actually exercised
    assert "string,set_variable" in result["by_cell"]
    assert not any("imaginary_context" in k for k in result["by_cell"])


# ---------------------------------------------------------------------------
# Parameter-injection tests (corpus growth follow-up to L-F19)
#
# Pairs that reference @pipeline().parameters.X carry an optional
# `referenced_params: [{name, type}]` array. Wrappers must inject these into
# the synthetic pipeline's `parameters` block so wkmigrate's parameter
# resolver can find them. Pairs without the field — including the entire
# legacy expressions.json corpus — must continue to work unchanged.
# ---------------------------------------------------------------------------


def test_wrap_in_set_variable_omits_parameters_when_referenced_params_is_none():
    """Backward compatibility: pairs with no referenced_params produce a
    pipeline with NO `parameters` key, matching the legacy shape."""
    pipe = wrap_in_set_variable("@concat('a', 'b')", referenced_params=None)
    assert "parameters" not in pipe


def test_wrap_in_set_variable_omits_parameters_when_referenced_params_is_empty_list():
    """Empty list = same as None: no parameters block."""
    pipe = wrap_in_set_variable("@concat('a', 'b')", referenced_params=[])
    assert "parameters" not in pipe


def test_wrap_in_set_variable_injects_parameters_block_when_referenced_params_present():
    """When referenced_params is non-empty, the wrapper injects a
    `parameters` block in wkmigrate's expected dict shape:
    {paramName: {type: <ADFType>}}."""
    pipe = wrap_in_set_variable(
        "@pipeline().parameters.tableName",
        referenced_params=[{"name": "tableName", "type": "String"}],
    )
    assert "parameters" in pipe
    assert pipe["parameters"] == {"tableName": {"type": "String"}}


def test_wrap_in_set_variable_injects_multiple_typed_parameters():
    """Multiple referenced params build a multi-key parameters dict, each
    carrying its own declared ADF type (String, Int, Float, Bool)."""
    pipe = wrap_in_set_variable(
        "@add(pipeline().parameters.qty, pipeline().parameters.price)",
        referenced_params=[
            {"name": "qty", "type": "Int"},
            {"name": "price", "type": "Float"},
        ],
    )
    assert pipe["parameters"] == {
        "qty": {"type": "Int"},
        "price": {"type": "Float"},
    }


def test_all_wrappers_accept_referenced_params_keyword():
    """Every wrapper in ACTIVITY_CONTEXTS must accept the `referenced_params`
    keyword so the sweep loop can call them uniformly. This test pins the
    contract — adding a new wrapper without the keyword will break here."""
    for context_name, wrap_fn in ACTIVITY_CONTEXTS.items():
        # Smoke: every wrapper should accept the keyword and produce a valid pipeline shape.
        pipe = wrap_fn(
            "@pipeline().parameters.x",
            name=f"smoke_{context_name}",
            referenced_params=[{"name": "x", "type": "String"}],
        )
        assert isinstance(pipe, dict), f"{context_name} returned non-dict"
        assert pipe.get("parameters") == {
            "x": {"type": "String"}
        }, f"{context_name} did not inject the parameters block"


def test_wrapper_normalises_missing_param_type_to_string():
    """Defensive: a referenced_params entry missing `type` defaults to
    String. The corpus schema test rejects this case at load time so it
    should never happen in practice, but the wrapper stays robust."""
    pipe = wrap_in_set_variable(
        "@pipeline().parameters.foo",
        referenced_params=[{"name": "foo"}],
    )
    assert pipe["parameters"] == {"foo": {"type": "String"}}


def test_wrapper_skips_malformed_referenced_params_entries():
    """Defensive: malformed entries (non-dict, missing name) are silently
    skipped so a single bad pair can't crash the entire sweep run."""
    pipe = wrap_in_set_variable(
        "@pipeline().parameters.real",
        referenced_params=[
            "not a dict",
            {},  # missing name
            {"name": ""},  # empty name
            {"name": "real", "type": "String"},  # only this one is kept
        ],
    )
    assert pipe["parameters"] == {"real": {"type": "String"}}


def test_sweep_threads_referenced_params_to_wrappers():
    """End-to-end: a corpus entry with referenced_params should produce a
    wrapped pipeline that carries the parameters block when it reaches
    convert_fn. Verified by recording every payload the mock receives."""
    corpus = [
        {
            "adf_expression": "@pipeline().parameters.tableName",
            "category": "string",
            "expected_python": "dbutils.widgets.get('tableName')",
            "referenced_params": [{"name": "tableName", "type": "String"}],
        },
        {
            "adf_expression": "@concat('a', 'b')",  # no params — control row
            "category": "string",
            "expected_python": "str('a') + str('b')",
        },
    ]
    payloads_seen: list[dict] = []

    def mock_convert(payload):
        payloads_seen.append(payload)
        return _make_mock_snapshot(resolved_count=1)

    sweep_activity_contexts(corpus, mock_convert, contexts=["set_variable"])

    assert len(payloads_seen) == 2
    # First payload (referenced_params present) carries the parameters block.
    assert payloads_seen[0]["parameters"] == {"tableName": {"type": "String"}}
    # Second payload (no referenced_params) has no parameters key.
    assert "parameters" not in payloads_seen[1]
