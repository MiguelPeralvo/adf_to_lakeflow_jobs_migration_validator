"""Semantic equivalence dimension factory based on LLMJudge."""

from __future__ import annotations

import json
from pathlib import Path

from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider, LLMJudge

_DEFAULT_CRITERIA = (
    "You are an expert judge for ADF-to-Python migration quality. "
    "Evaluate whether the Python output preserves the EXACT semantics of the "
    "original ADF expression. Pay careful attention to:\n"
    "  1. Type coercion — ADF functions like concat() auto-coerce to string; "
    "Python may need explicit str() calls.\n"
    "  2. Edge cases — null handling, empty strings, division-by-zero guards.\n"
    "  3. Function mapping — each ADF function must map to the correct Python "
    "equivalent (e.g., @toUpper → .upper(), @indexOf → .find()).\n"
    "  4. Nesting correctness — deeply nested expressions must preserve "
    "evaluation order and parenthesisation.\n"
    "  5. Parameter references — pipeline().parameters.X must map to the "
    "corresponding dbutils.widgets.get('X') call with proper coercion.\n"
    "  6. Activity output references — @activity('X').output.firstRow.col "
    "maps to dbutils.jobs.taskValues.get(taskKey='X', key='result')['firstRow']['col']. "
    "This is the CORRECT Databricks equivalent; do NOT penalise it.\n"
    "  7. Pipeline variables — @variables('X') maps to "
    "dbutils.jobs.taskValues.get(taskKey='set_variable_X', key='X'). "
    "This is the CORRECT Databricks equivalent; do NOT penalise it.\n"
    "  8. Integer division — ADF @div() maps to Python // (floor division). "
    "Nested arithmetic with correct operator precedence and // for div is CORRECT.\n"
    "\n"
    "Score 1.0 = perfect semantic equivalence.\n"
    "Score 0.7-0.9 = minor differences (e.g., extra whitespace, unnecessary "
    "str() wrapping) that do not change runtime behaviour.\n"
    "Score 0.3-0.6 = partial equivalence — some logic preserved, but at "
    "least one semantic difference.\n"
    "Score 0.0-0.2 = incorrect — the Python code does not reproduce the ADF "
    "expression's behaviour."
)
_DEFAULT_TEMPLATE = (
    "=== ADF Expression ===\n{input}\n\n"
    "=== Python Translation ===\n{output}\n\n"
    "Evaluate semantic equivalence using the criteria above."
)
_DEFAULT_CALIBRATION_PATH = Path(__file__).resolve().parents[3] / "golden_sets" / "calibration_pairs.json"


def load_expression_calibration_examples(
    *,
    path: str | Path = _DEFAULT_CALIBRATION_PATH,
    sample_size: int = 26,
) -> tuple[dict, ...]:
    """Load calibration examples for the semantic judge."""
    if sample_size <= 0:
        return ()

    calibration_path = Path(path)
    if not calibration_path.is_file():
        return ()

    try:
        payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    except OSError:
        return ()

    pairs = payload.get("calibration_pairs", payload.get("expressions", []))

    examples: list[dict] = []
    for item in pairs[:sample_size]:
        adf = item.get("adf_expression", "")
        py = item.get("python_code", item.get("expected_python", ""))
        score = item.get("human_score", 1.0)
        if adf and py:
            examples.append({"input": adf, "output": py, "score": score})
    return tuple(examples)


def create_semantic_equivalence_judge(
    provider: JudgeProvider,
    *,
    threshold: float = 0.7,
    model: str = "databricks-claude-opus-4-6",
    calibration_path: str | Path = _DEFAULT_CALIBRATION_PATH,
    calibration_sample_size: int = 20,
) -> LLMJudge:
    """Construct a ready-to-use semantic equivalence judge dimension."""
    calibration_examples = load_expression_calibration_examples(
        path=calibration_path,
        sample_size=calibration_sample_size,
    )
    return LLMJudge(
        name="semantic_equivalence",
        criteria=_DEFAULT_CRITERIA,
        input_template=_DEFAULT_TEMPLATE,
        provider=provider,
        calibration_examples=calibration_examples,
        threshold=threshold,
        model=model,
    )
