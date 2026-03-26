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
    ):
        self._convert_fn = convert_fn or snapshot_from_adf_payload
        self._judge_provider = judge_provider

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
