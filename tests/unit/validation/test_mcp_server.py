"""TDD tests for the MCP tool surface."""

import pytest


def test_validate_pipeline_tool_returns_scorecard_dict():
    """MCP tool 'validate_pipeline' returns a serialized scorecard."""
    pytest.skip("TDD: implement MCP server first")


def test_validate_expression_tool_returns_score_and_reasoning():
    """MCP tool 'validate_expression' returns {score, reasoning}."""
    pytest.skip("TDD: implement MCP server first")


def test_suggest_fix_tool_returns_suggestion():
    """MCP tool 'suggest_fix' returns a code suggestion string."""
    pytest.skip("TDD: implement MCP server first")


def test_missing_adf_json_returns_error():
    """MCP tool with empty input returns an error message, not an exception."""
    pytest.skip("TDD: implement MCP server first")
