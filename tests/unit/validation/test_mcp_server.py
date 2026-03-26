"""Unit tests for the MCP tool surface."""

from __future__ import annotations

import sys
import types

from lakeflow_migration_validator import evaluate
from lakeflow_migration_validator.mcp_server import LMVMCPServer, create_mcp_server
from lakeflow_migration_validator.parallel.comparator import ComparisonResult
from lakeflow_migration_validator.parallel.parallel_test_runner import ParallelTestResult
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


def test_run_parallel_test_returns_payload():
    class _ParallelRunner:
        def run(self, pipeline_name: str, parameters: dict[str, str] | None = None, *, snapshot=None):
            scorecard = evaluate(make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()]))
            return ParallelTestResult(
                pipeline_name=pipeline_name,
                adf_outputs={"a": "1"},
                databricks_outputs={"a": "1"},
                comparisons=(
                    ComparisonResult(
                        activity_name="a",
                        adf_output="1",
                        databricks_output="1",
                        match=True,
                        diff=None,
                    ),
                ),
                equivalence_score=1.0,
                scorecard=scorecard,
            )

    server = LMVMCPServer(
        convert_fn=lambda _adf: make_snapshot(),
        judge_provider=_Provider(),
        parallel_runner=_ParallelRunner(),
    )

    payload = server.run_parallel_test({"pipeline_name": "pipe_a", "parameters": {"p": "1"}})

    assert payload["pipeline_name"] == "pipe_a"
    assert payload["equivalence_score"] == 1.0
    assert payload["comparisons"][0]["match"] is True
    assert "scorecard" in payload


def test_run_parallel_test_returns_error_when_runner_not_configured():
    server = LMVMCPServer(convert_fn=lambda _adf: make_snapshot(), judge_provider=_Provider())

    payload = server.run_parallel_test({"pipeline_name": "pipe_a"})

    assert payload == {"error": "parallel_runner is not configured"}


def test_run_parallel_test_with_snapshot_passes_through(monkeypatch):
    class _FakeFastMCP:
        def __init__(self, _name: str):
            self._tools: dict[str, object] = {}

        def tool(self):
            def decorator(fn):
                self._tools[fn.__name__] = fn
                return fn

            return decorator

    fake_fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
    fake_fastmcp_mod.FastMCP = _FakeFastMCP
    fake_server_mod = types.ModuleType("mcp.server")
    fake_server_mod.fastmcp = fake_fastmcp_mod
    fake_mcp_mod = types.ModuleType("mcp")
    fake_mcp_mod.server = fake_server_mod

    monkeypatch.setitem(sys.modules, "mcp", fake_mcp_mod)
    monkeypatch.setitem(sys.modules, "mcp.server", fake_server_mod)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fake_fastmcp_mod)

    class _ParallelRunner:
        def __init__(self):
            self.last_snapshot = None

        def run(self, pipeline_name: str, parameters: dict[str, str] | None = None, *, snapshot=None):
            self.last_snapshot = snapshot
            scorecard = evaluate(make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()]))
            return ParallelTestResult(
                pipeline_name=pipeline_name,
                adf_outputs={"a": "1"},
                databricks_outputs={"a": "1"},
                comparisons=(
                    ComparisonResult(
                        activity_name="a",
                        adf_output="1",
                        databricks_output="1",
                        match=True,
                        diff=None,
                    ),
                ),
                equivalence_score=1.0,
                scorecard=scorecard,
            )

    runner = _ParallelRunner()
    expected_snapshot = make_snapshot(tasks=[make_task("from_snapshot")], notebooks=[make_notebook()])

    server = create_mcp_server(
        convert_fn=lambda payload: expected_snapshot if payload == {"name": "snap"} else make_snapshot(),
        judge_provider=_Provider(),
        parallel_runner=runner,
    )

    tool = server._tools["run_parallel_test"]  # type: ignore[attr-defined]
    payload = tool("pipe_a", {"p": "1"}, {"name": "snap"})

    assert payload["pipeline_name"] == "pipe_a"
    assert runner.last_snapshot is expected_snapshot
