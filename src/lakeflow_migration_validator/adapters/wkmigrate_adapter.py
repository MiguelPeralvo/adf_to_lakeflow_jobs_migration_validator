"""wkmigrate adapter — the ONLY file that imports wkmigrate types.

If wkmigrate renames a field or restructures a class, only this file breaks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    DependencyRef,
    ExpressionPair,
    NotebookSnapshot,
    SecretRef,
    TaskSnapshot,
)

if TYPE_CHECKING:
    # Type-checker-only import: keeps the adapter module importable in
    # environments where wkmigrate isn't installed (LA-3 graceful
    # degradation). Runtime callers of from_wkmigrate / adf_to_snapshot
    # still need wkmigrate, but `import lakeflow_migration_validator.adapters.wkmigrate_adapter`
    # itself does not.
    from wkmigrate.models.workflows.artifacts import PreparedWorkflow

_PLACEHOLDER_PATH = "/UNSUPPORTED_ADF_ACTIVITY"

_IR_OP_TO_PYTHON: dict[str, str] = {
    "EQUAL_TO": "==",
    "NOT_EQUAL_TO": "!=",
    "GREATER_THAN": ">",
    "GREATER_THAN_OR_EQUAL": ">=",
    "LESS_THAN": "<",
    "LESS_THAN_OR_EQUAL": "<=",
}


def _coerce_resolved_value(value: Any) -> str | None:
    """Coerce a wkmigrate IR value into a plain Python source string.

    wkmigrate IR fields hold either:
    - plain ``str`` (most resolved Python output, e.g. ``DatabricksNotebookActivity.base_parameters[k]``)
    - ``ResolvedExpression`` instances (used by ``WebActivity`` for url/body/headers
      since pr/27-3) — these have a ``.code: str`` attribute carrying the actual code
    - ``None`` (the field was not populated)
    - other types (defensive — return None)

    Returns the underlying code string, or None if the value isn't usable.
    """
    if value is None:
        return None
    # Lazy import to keep the LA-3 graceful-degradation invariant: importing
    # this adapter module must not fail when wkmigrate isn't installed.
    from wkmigrate.parsers.expression_parsers import ResolvedExpression

    if isinstance(value, ResolvedExpression):
        return value.code or None
    if isinstance(value, str):
        return value or None
    return None


def _build_source_activity_index(source_pipeline: dict) -> dict[str, dict]:
    """Walk the source ADF JSON once and return ``{activity_name → activity_dict}``.

    Tolerates both the flattened ``{activities: [...]}`` shape and the
    Azure-native wrapped ``{properties: {activities: [...]}}`` shape, in
    case the caller hasn't already passed it through ``unwrap_adf_pipeline``.
    """
    activities = source_pipeline.get("activities")
    if activities is None:
        activities = source_pipeline.get("properties", {}).get("activities", [])
    if not isinstance(activities, list):
        return {}
    index: dict[str, dict] = {}
    for activity in activities:
        if isinstance(activity, dict):
            name = activity.get("name")
            if isinstance(name, str) and name:
                index[name] = activity
    return index


def _source_expression_at(source_activity: dict | None, *property_path: str) -> str | None:
    """Look up the original ADF expression text at *source_activity[path...]*.

    Walks the source dict following ``property_path``. Returns the inner
    ``value`` if the leaf is the canonical ``{type: "Expression", value: "@..."}``
    shape, otherwise None.
    """
    if not isinstance(source_activity, dict):
        return None
    cursor: Any = source_activity
    for key in property_path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if isinstance(cursor, dict) and cursor.get("type") == "Expression":
        value = cursor.get("value")
        if isinstance(value, str) and value:
            return value
    return None


def _detect_dropped_expression_fields(
    prepared_pipeline: Any,
    source_index: dict[str, dict],
) -> list[dict]:
    """L-F19: detect expression-bearing fields that wkmigrate silently dropped.

    L-F17 closes the gap where wkmigrate *does* resolve an expression but the
    adapter forgot to walk it. This function closes the complementary gap:
    wkmigrate's translator silently *drops* the expression at translate time,
    so even a perfect walker has nothing to extract.

    The first concrete instance is ``Copy.source.sql_reader_query`` (W-9):
    wkmigrate's ``_parse_sql_format_options`` (parsers/dataset_parsers.py)
    builds the ``CopyActivity.source_properties`` dict from a fixed key list
    that does **not** include ``sql_reader_query``. The query — literal or
    Expression — is therefore lost the moment ``translate_copy_activity``
    runs. Both alpha_1 and pr/27-3-translator-adoption have this gap; it is
    distinct from W-7 (Lookup translator crashes on Expression sql_reader_query)
    and W-8 (initially mis-diagnosed Copy fixture).

    A second instance is the post-W-7 Lookup case where ``LookupActivity``
    is constructed but ``source_query`` ends up empty/non-string (e.g. when
    a future regression slips through and the dict-typed value reappears).
    The check is intentionally narrow — it only fires when the source dict
    actually has an Expression and the IR has nothing usable — so it does
    not double-count W-7 (which manifests as a hard crash before the adapter
    is even reached).

    Each detected drop is emitted as a synthetic ``not_translatable`` warning
    with ``kind == "dropped_expression_field"``. The warning message contains
    the substring ``"expression"`` so ``compute_expression_coverage`` counts it
    in its ``unsupported`` denominator (matching the existing dimension's
    keyword filter at dimensions/expression_coverage.py:46). The structured
    fields (``original_activity_type``, ``property``) let failure-signature
    regexes in ``dev/wkmigrate-issue-map.json`` (e.g. W-9) match cleanly
    without depending on a brittle task_key substring.

    Args:
        prepared_pipeline: wkmigrate's ``Pipeline`` IR.
        source_index: pre-built ``{name → source_activity_dict}`` map (built
            once in ``from_wkmigrate`` and reused for L-F12 / L-F17 / L-F19).
    """
    from wkmigrate.models.ir.pipeline import CopyActivity, LookupActivity

    warnings_out: list[dict] = []

    for task in prepared_pipeline.tasks:
        task_name = getattr(task, "name", None)
        if not isinstance(task_name, str):
            continue
        source_activity = source_index.get(task_name)
        if not isinstance(source_activity, dict):
            continue

        if isinstance(task, CopyActivity):
            source_expr = _source_expression_at(source_activity, "source", "sql_reader_query")
            if source_expr is None:
                continue
            # The IR's CopyActivity.source_properties never carries
            # sql_reader_query — _parse_sql_format_options drops it. So as
            # long as the source dict has an Expression there, the field is
            # dropped, period.
            ir_props = task.source_properties or {}
            if "sql_reader_query" in ir_props and ir_props.get("sql_reader_query"):
                # Future-proofing: if wkmigrate ever wires sql_reader_query
                # into source_properties, do not double-warn — L-F17 should
                # be extended to extract it as a regular ExpressionPair.
                continue
            warnings_out.append(
                {
                    "kind": "dropped_expression_field",
                    "task_key": task_name,
                    "property": "source.sql_reader_query",
                    "original_activity_type": "Copy",
                    "adf_expression": source_expr,
                    "message": (
                        f"Activity '{task_name}' (type: Copy) has source.sql_reader_query "
                        f"as an ADF expression ('{source_expr}'), but wkmigrate's "
                        f"_parse_sql_format_options dropped it during translation "
                        f"(CopyActivity.source_properties has no 'sql_reader_query' key). "
                        f"The query is lost in the generated notebook."
                    ),
                }
            )
            continue

        if isinstance(task, LookupActivity):
            source_expr = _source_expression_at(source_activity, "source", "sql_reader_query") or _source_expression_at(
                source_activity, "source", "query"
            )
            if source_expr is None:
                continue
            ir_query = task.source_query
            if isinstance(ir_query, str) and ir_query:
                # Walker handles this case via the existing Lookup branch in
                # _extract_resolved_expression_pairs — do not double-emit.
                continue
            warnings_out.append(
                {
                    "kind": "dropped_expression_field",
                    "task_key": task_name,
                    "property": "source.sql_reader_query",
                    "original_activity_type": "Lookup",
                    "adf_expression": source_expr,
                    "message": (
                        f"Activity '{task_name}' (type: Lookup) has source.sql_reader_query "
                        f"as an ADF expression ('{source_expr}'), but the IR's "
                        f"LookupActivity.source_query was not populated with a usable string. "
                        f"The query expression was dropped before reaching the adapter."
                    ),
                }
            )
            continue

    return warnings_out


def _extract_resolved_expression_pairs(
    prepared_pipeline: Any,
    source_pipeline: dict,
    source_index: dict[str, dict] | None = None,
) -> list[ExpressionPair]:
    """L-F17: walk every IR activity type that exposes expression-bearing properties.

    Before this function was introduced, the adapter only extracted
    ``ExpressionPair`` entries from ``SetVariableActivity`` (variable_name +
    variable_value), so all other activity types adopted by wkmigrate
    (Notebook.base_parameters, WebActivity.url/body/headers,
    IfCondition.expression, ForEach.items, Lookup.source.sql_reader_query)
    silently produced 0 resolved expressions even when wkmigrate had already
    done the resolution. The L-F5 sweep (PR #19) made this gap measurable;
    this function closes it.

    For each task we look up the matching source ADF activity by name and
    pair the IR-side resolved Python with the original ``@`` expression.
    When the source dict has no matching expression (e.g. the activity was
    synthesised by wkmigrate's preparer or the source uses a literal that
    wkmigrate later wrapped), a synthetic label like
    ``@<activity_type>('<task>').<field>`` is used instead — the
    ``python_code`` field is what dimensions actually measure, so emitting
    the pair is still valuable for X-1 / X-2 ratios.

    Args:
        prepared_pipeline: wkmigrate's ``Pipeline`` IR (``prepared.pipeline``).
        source_pipeline: raw ADF JSON dict (preserved on the snapshot).
        source_index: optional pre-built ``{name → source_activity_dict}`` map.
            ``from_wkmigrate`` builds this once for placeholder type lookup
            (L-F18) and passes it through to avoid rebuilding it here. When
            None (e.g. external callers), it's built lazily from
            ``source_pipeline`` so the public signature stays callable on
            its own.
    """
    # Lazy import of wkmigrate IR types: keeps `import lakeflow_migration_validator
    # .adapters.wkmigrate_adapter` working in environments without wkmigrate
    # installed (LA-3 graceful degradation invariant; see PR #18).
    from wkmigrate.models.ir.pipeline import (
        CopyActivity,
        DatabricksNotebookActivity,
        ForEachActivity,
        IfConditionActivity,
        LookupActivity,
        SetVariableActivity,
        WebActivity,
    )

    if source_index is None:
        source_index = _build_source_activity_index(source_pipeline)
    pairs: list[ExpressionPair] = []

    for task in prepared_pipeline.tasks:
        task_name = getattr(task, "name", None)
        if not isinstance(task_name, str):
            continue
        source_activity = source_index.get(task_name)

        if isinstance(task, SetVariableActivity):
            variable_name = task.variable_name
            variable_value = task.variable_value
            if isinstance(variable_name, str) and variable_name and isinstance(variable_value, str) and variable_value:
                pairs.append(
                    ExpressionPair(
                        adf_expression=(
                            _source_expression_at(source_activity, "value") or f"@variables('{variable_name}')"
                        ),
                        python_code=variable_value,
                        context="set_variable",
                    )
                )
            continue

        if isinstance(task, DatabricksNotebookActivity):
            if task.base_parameters:
                for param_name, param_value in task.base_parameters.items():
                    code = _coerce_resolved_value(param_value)
                    if code is None:
                        continue
                    adf = (
                        _source_expression_at(source_activity, "base_parameters", param_name)
                        or f"@notebook('{task_name}').base_parameters.{param_name}"
                    )
                    pairs.append(ExpressionPair(adf_expression=adf, python_code=code, context="notebook_base_param"))
            continue

        if isinstance(task, WebActivity):
            for prop_name, prop_value in (("url", task.url), ("body", task.body)):
                code = _coerce_resolved_value(prop_value)
                if code is None:
                    continue
                adf = _source_expression_at(source_activity, prop_name)
                if adf is None:
                    continue
                pairs.append(ExpressionPair(adf_expression=adf, python_code=code, context="web_body"))
            # headers can be: dict[str, Any | ResolvedExpression], a single
            # ResolvedExpression covering the whole dict, or None.
            headers_code = _coerce_resolved_value(task.headers)
            if headers_code is not None:
                headers_adf = _source_expression_at(source_activity, "headers")
                if headers_adf is not None:
                    pairs.append(ExpressionPair(adf_expression=headers_adf, python_code=headers_code, context="web_headers"))
            elif isinstance(task.headers, dict):
                for header_name, header_value in task.headers.items():
                    code = _coerce_resolved_value(header_value)
                    if code is None:
                        continue
                    adf = (
                        _source_expression_at(source_activity, "headers", header_name)
                        or f"@web('{task_name}').headers.{header_name}"
                    )
                    pairs.append(ExpressionPair(adf_expression=adf, python_code=code, context="web_headers"))
            continue

        if isinstance(task, LookupActivity):
            source_query_code = _coerce_resolved_value(task.source_query)
            if source_query_code is not None:
                adf = (
                    _source_expression_at(source_activity, "source", "sql_reader_query")
                    or f"@lookup('{task_name}').source.sql_reader_query"
                )
                pairs.append(ExpressionPair(adf_expression=adf, python_code=source_query_code, context="lookup_query"))
            continue

        if isinstance(task, CopyActivity):
            source_props = getattr(task, "source_properties", None)
            if isinstance(source_props, dict):
                query_val = source_props.get("sql_reader_query")
                code = _coerce_resolved_value(query_val)
                if code is not None:
                    adf = (
                        _source_expression_at(source_activity, "source", "sql_reader_query")
                        or f"@copy('{task_name}').source.sql_reader_query"
                    )
                    pairs.append(ExpressionPair(adf_expression=adf, python_code=code, context="copy_query"))
            continue

        if isinstance(task, ForEachActivity):
            items_code = _coerce_resolved_value(task.items_string)
            if items_code is not None:
                adf = _source_expression_at(source_activity, "items") or f"@for_each('{task_name}').items"
                pairs.append(ExpressionPair(adf_expression=adf, python_code=items_code, context="for_each"))
            continue

        if isinstance(task, IfConditionActivity):
            # The original ADF predicate (`@equals(...)` etc.) has been
            # decomposed into op/left/right at IR construction time and the
            # canonical text is lost. We synthesise a (left op right)
            # expression on the IR side and pair it with the original ADF
            # expression captured from the source dict (when available).
            #
            # All three operands must be non-empty strings — otherwise the
            # f-string would silently embed the literal "None" (or "") into
            # python_code, and that bogus pair would inflate X-1/X-2
            # coverage metrics. Defensive validation matches every other
            # handler in this walker (each of which goes through
            # _coerce_resolved_value or an isinstance check before emitting).
            op = getattr(task, "op", None)
            left = getattr(task, "left", None)
            right = getattr(task, "right", None)
            if isinstance(op, str) and op and isinstance(left, str) and left and isinstance(right, str) and right:
                python_op = _IR_OP_TO_PYTHON.get(op, op)
                python_code = f"({left} {python_op} {right})"
                adf = _source_expression_at(source_activity, "expression") or f"@if_condition('{task_name}').expression"
                pairs.append(ExpressionPair(adf_expression=adf, python_code=python_code, context="if_condition"))
            continue

    return pairs


def unwrap_adf_pipeline(payload: Any) -> Any:
    """Flatten Azure-native ADF JSON ``{name, properties: {...}}`` shape.

    wkmigrate's ``translate_pipeline`` expects the *flattened* shape
    ``{name, activities, parameters, ...}``. Azure ADF's REST API and the
    ``Get Pipeline`` factory client return the *wrapped* shape
    ``{name, properties: {activities, parameters, ...}}``. When the wrapped
    shape is fed straight into ``translate_pipeline``, the resulting
    ``Pipeline`` IR has zero tasks (silently — no warning is emitted).

    This helper unwraps the ``properties`` envelope so callers can pass
    either shape to ``adf_to_snapshot`` or to wkmigrate directly.

    The function is intentionally pure (no wkmigrate imports) so it lives
    in the fast unit-test tier. Non-dict inputs are returned unchanged for
    defensive symmetry with the rest of the adapter.
    """
    if not isinstance(payload, dict):
        return payload
    properties = payload.get("properties")
    if not isinstance(properties, dict):
        return payload
    flat = {k: v for k, v in payload.items() if k != "properties"}
    flat.update(properties)
    return flat


def adf_to_snapshot(payload: dict) -> ConversionSnapshot:
    """One-shot: take raw ADF pipeline JSON, return a ``ConversionSnapshot``.

    Centralises the four-step chain (unwrap → translate → prepare → adapt)
    so individual call sites in ``cli.py`` / ``api.py`` / ``mcp_server.py``
    don't have to duplicate it. Honours the LA-1 invariant by keeping all
    wkmigrate imports inside this module.

    Accepts either the flat ``{name, activities, ...}`` shape or the
    Azure-native wrapped ``{name, properties: {...}}`` shape; the unwrap
    happens transparently. The original ``payload`` is preserved as the
    snapshot's ``source_pipeline`` so downstream dimensions can still
    inspect the original ADF JSON.
    """
    # Imports are local because they fail when wkmigrate isn't installed
    # (graceful degradation, LA-3). The adapter is the only allowed file
    # for these imports per LA-1.
    from wkmigrate.preparers.preparer import prepare_workflow
    from wkmigrate.translators.pipeline_translators.pipeline_translator import (
        translate_pipeline,
    )

    flat_payload = unwrap_adf_pipeline(payload)
    pipeline_ir = translate_pipeline(flat_payload)
    prepared = prepare_workflow(pipeline_ir)
    return from_wkmigrate(payload, prepared)


def from_wkmigrate(source_pipeline: dict, prepared_workflow) -> ConversionSnapshot:
    """Convert wkmigrate PreparedWorkflow into the validator's generic contract.

    Args:
        source_pipeline: Raw ADF pipeline JSON.
        prepared_workflow: wkmigrate ``PreparedWorkflow`` instance.

    Returns:
        A ``ConversionSnapshot`` suitable for passing to ``evaluate()``.
    """
    prepared: PreparedWorkflow = prepared_workflow

    # Build the source-by-name index once and reuse it for both placeholder
    # type lookup (L-F18) and the resolved-expression walker (L-F17).
    source_index = _build_source_activity_index(source_pipeline)

    tasks = []
    placeholder_warnings: list[dict] = []
    for activity in prepared.activities:
        notebook_path = activity.task.get("notebook_task", {}).get("notebook_path", "")
        task_key = activity.task.get("task_key")
        if not isinstance(task_key, str) or not task_key:
            raise ValueError("Missing or invalid task_key in prepared activity task.")
        is_placeholder = notebook_path == _PLACEHOLDER_PATH
        tasks.append(
            TaskSnapshot(
                task_key=task_key,
                is_placeholder=is_placeholder,
            )
        )
        if is_placeholder:
            # L-F12: surface placeholder activities into not_translatable so
            # dimensions (expression_coverage, not_translatable_ratio) can
            # see them and downstream consumers can attribute the gap to
            # an unrecognised wkmigrate translator instead of "no
            # expressions in source" (the silent-empty case from L-F2).
            #
            # L-F18: also enrich the warning with the original ADF activity
            # type from the source dict (e.g. "Copy", "ForEach", "WebActivity")
            # so failure-signature regexes in dev/wkmigrate-issue-map.json
            # can match by activity type rather than relying on a task_key
            # substring (which depends on the user's pipeline naming
            # convention and is brittle). Stored as a structured field
            # `original_activity_type` AND embedded in the message text as
            # `(type: <Type>)` for the regex matchers.
            source_activity = source_index.get(task_key)
            original_activity_type: str | None = None
            if isinstance(source_activity, dict):
                source_type = source_activity.get("type")
                if isinstance(source_type, str) and source_type:
                    original_activity_type = source_type
            type_label = original_activity_type or "<unknown>"
            placeholder_warnings.append(
                {
                    "kind": "placeholder_activity",
                    "task_key": task_key,
                    "property": task_key,
                    "original_activity_type": original_activity_type,
                    "message": (
                        f"Activity '{task_key}' (type: {type_label}) was substituted with a "
                        f"placeholder DatabricksNotebookActivity (wkmigrate did not recognise "
                        f"the source ADF activity type)."
                    ),
                }
            )

    notebooks = tuple(
        NotebookSnapshot(file_path=notebook.file_path, content=notebook.content) for notebook in prepared.all_notebooks
    )

    secrets = tuple(SecretRef(scope=secret.scope, key=secret.key) for secret in prepared.all_secrets)

    params = []
    if prepared.pipeline.parameters:
        for parameter in prepared.pipeline.parameters:
            name = parameter.get("name")
            if name:
                params.append(name)

    dependencies = []
    for task in prepared.pipeline.tasks:
        if task.depends_on:
            for dependency in task.depends_on:
                dependencies.append(
                    DependencyRef(
                        source_task=dependency.task_key,
                        target_task=task.task_key,
                    )
                )

    activities_top = source_pipeline.get("activities")
    adf_activities = (
        activities_top if activities_top is not None else source_pipeline.get("properties", {}).get("activities", [])
    )
    total_source_dependencies = sum(
        len(activity.get("depends_on") or activity.get("dependsOn") or []) for activity in adf_activities
    )

    expressions = _extract_resolved_expression_pairs(
        prepared.pipeline,
        source_pipeline,
        source_index=source_index,
    )

    # L-F19: detect expression-bearing fields that wkmigrate silently dropped
    # at translate time (Copy.source.sql_reader_query is the first concrete
    # case — see W-9 in dev/wkmigrate-issue-map.json). These dropped-field
    # warnings are merged into not_translatable so compute_expression_coverage
    # counts them in its denominator and the gap shows up in the X-1 sweep.
    dropped_field_warnings = _detect_dropped_expression_fields(prepared.pipeline, source_index)

    # Merge wkmigrate's pipeline-level warnings with the L-F12 placeholder
    # warnings and L-F19 dropped-field warnings we synthesised above. Order:
    # wkmigrate-emitted first (preserves source order), then placeholders,
    # then dropped-field — both groups appear after any wkmigrate warnings.
    all_not_translatable = (
        tuple(prepared.pipeline.not_translatable) + tuple(placeholder_warnings) + tuple(dropped_field_warnings)
    )

    return ConversionSnapshot(
        tasks=tuple(tasks),
        notebooks=notebooks,
        secrets=secrets,
        parameters=tuple(params),
        dependencies=tuple(dependencies),
        not_translatable=all_not_translatable,
        resolved_expressions=tuple(expressions),
        source_pipeline=source_pipeline,
        total_source_dependencies=total_source_dependencies,
    )
