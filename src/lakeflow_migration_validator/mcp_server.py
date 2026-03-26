"""MCP-friendly tool wrappers for validation workflows."""

from __future__ import annotations

from typing import Any, Callable

from lakeflow_migration_validator import evaluate
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.serialization import snapshot_from_adf_payload


class LMVMCPServer:
    """Thin MCP tool facade over the validator service functions."""

    def __init__(
        self,
        *,
        convert_fn: Callable[[dict], ConversionSnapshot] | None = None,
        judge_provider: JudgeProvider | None = None,
        parallel_runner=None,
    ):
        self._convert_fn = convert_fn or snapshot_from_adf_payload
        self._judge_provider = judge_provider
        self._parallel_runner = parallel_runner

    def validate_pipeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate a pipeline payload and return serialized scorecard."""
        adf_json = payload.get("adf_json")
        if not isinstance(adf_json, dict):
            return {"error": "adf_json is required"}
        try:
            snapshot = self._convert_fn(adf_json)
            scorecard = evaluate(snapshot)
            return scorecard.to_dict()
        except Exception as exc:
            return {"error": str(exc)}

    def validate_expression(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate one expression pair and return score + reasoning."""
        if self._judge_provider is None:
            return {"error": "judge_provider is not configured"}

        adf_expression = payload.get("adf_expression")
        python_code = payload.get("python_code")
        if not isinstance(adf_expression, str) or not adf_expression:
            return {"error": "adf_expression is required"}
        if not isinstance(python_code, str) or not python_code:
            return {"error": "python_code is required"}

        prompt = (
            "Evaluate semantic equivalence between ADF and Python code. "
            f"ADF: {adf_expression}\nPython: {python_code}"
        )
        try:
            response = self._judge_provider.judge(prompt)
            score = float(response.get("score", 0.0))
            return {
                "score": max(0.0, min(1.0, score)),
                "reasoning": str(response.get("reasoning", "")),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def suggest_fix(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Suggest a conversion fix for a failed dimension context."""
        if self._judge_provider is None:
            return {"error": "judge_provider is not configured"}

        context = payload.get("context", "")
        if not isinstance(context, str) or not context:
            return {"error": "context is required"}

        prompt = f"Suggest a concrete fix for this migration issue: {context}"
        try:
            response = self._judge_provider.judge(prompt)
            return {"suggestion": str(response.get("reasoning", ""))}
        except Exception as exc:
            return {"error": str(exc)}

    def run_parallel_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run ADF-vs-Databricks output comparison and return full result."""
        if self._parallel_runner is None:
            return {"error": "parallel_runner is not configured"}

        pipeline_name = payload.get("pipeline_name")
        if not isinstance(pipeline_name, str) or not pipeline_name:
            return {"error": "pipeline_name is required"}

        parameters = payload.get("parameters", {})
        if not isinstance(parameters, dict):
            return {"error": "parameters must be a dict"}

        snapshot_payload = payload.get("snapshot")
        if snapshot_payload is not None and not isinstance(snapshot_payload, dict):
            return {"error": "snapshot must be a dict when provided"}

        try:
            snapshot = self._convert_fn(snapshot_payload) if snapshot_payload is not None else None
            result = self._parallel_runner.run(
                pipeline_name,
                parameters=parameters,
                snapshot=snapshot,
            )
            return result.to_dict()
        except Exception as exc:
            return {"error": str(exc)}


def create_mcp_server(
    *,
    convert_fn: Callable[[dict], ConversionSnapshot] | None = None,
    judge_provider: JudgeProvider | None = None,
    parallel_runner=None,
):
    """Create and register an MCP server with the validator tool surface."""
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("mcp extra is not installed. Install with: pip install lmv[mcp]") from exc

    service = LMVMCPServer(
        convert_fn=convert_fn,
        judge_provider=judge_provider,
        parallel_runner=parallel_runner,
    )
    server = FastMCP("lakeflow-migration-validator")

    @server.tool()
    def validate_pipeline(adf_json: dict[str, Any]) -> dict[str, Any]:
        """Validate one pipeline and return serialized scorecard."""
        return service.validate_pipeline({"adf_json": adf_json})

    @server.tool()
    def validate_expression(adf_expression: str, python_code: str) -> dict[str, Any]:
        """Validate one expression pair and return score + reasoning."""
        return service.validate_expression(
            {"adf_expression": adf_expression, "python_code": python_code}
        )

    @server.tool()
    def suggest_fix(context: str) -> dict[str, Any]:
        """Suggest a conversion fix for failed-dimension context."""
        return service.suggest_fix({"context": context})

    @server.tool()
    def run_parallel_test(
        pipeline_name: str,
        parameters: dict[str, str] | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run parallel ADF-vs-Databricks output validation."""
        return service.run_parallel_test(
            {
                "pipeline_name": pipeline_name,
                "parameters": parameters or {},
                "snapshot": snapshot,
            }
        )

    return server
