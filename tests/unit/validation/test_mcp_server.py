"""Unit tests for the MCP tool surface."""

from __future__ import annotations

from lakeflow_migration_validator.mcp_server import LMVMCPServer
from tests.unit.validation.conftest import make_notebook, make_snapshot, make_task


class _Provider:
    def judge(self, prompt: str, model: str | None = None):
        if "suggest" in prompt.lower():
            return {"score": 0.0, "reasoning": "Replace placeholder notebook with template"}
        return {"score": 0.91, "reasoning": "Equivalent"}


def test_validate_pipeline_tool_returns_scorecard_dict():
    """MCP tool 'validate_pipeline' returns a serialized scorecard."""
    server = LMVMCPServer(
        convert_fn=lambda _adf: make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()]),
        judge_provider=_Provider(),
    )

    payload = server.validate_pipeline({"adf_json": {"name": "pipe_a"}})

    assert "score" in payload
    assert "dimensions" in payload


def test_validate_expression_tool_returns_score_and_reasoning():
    """MCP tool 'validate_expression' returns {score, reasoning}."""
    server = LMVMCPServer(convert_fn=lambda _adf: make_snapshot(), judge_provider=_Provider())

    payload = server.validate_expression({"adf_expression": "@add(1,2)", "python_code": "(1 + 2)"})

    assert payload["score"] == 0.91
    assert payload["reasoning"] == "Equivalent"


def test_suggest_fix_tool_returns_suggestion():
    """MCP tool 'suggest_fix' returns a code suggestion string."""
    server = LMVMCPServer(convert_fn=lambda _adf: make_snapshot(), judge_provider=_Provider())

    payload = server.suggest_fix({"context": "activity_coverage is low"})

    assert payload == {"suggestion": "Replace placeholder notebook with template"}


def test_missing_adf_json_returns_error():
    """MCP tool with empty input returns an error message, not an exception."""
    server = LMVMCPServer(convert_fn=lambda _adf: make_snapshot(), judge_provider=_Provider())

    payload = server.validate_pipeline({})

    assert payload == {"error": "adf_json is required"}
