"""Semantic equivalence dimension factory based on LLMJudge."""

from __future__ import annotations

import json
from pathlib import Path

from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider, LLMJudge

_DEFAULT_CRITERIA = (
    "Determine whether the Python output preserves the semantics of the ADF "
    "expression, including type coercion, branching, and function behavior."
)
_DEFAULT_TEMPLATE = (
    "Input ADF expression:\n{input}\n\n" "Output Python code:\n{output}\n\n" "Score semantic equivalence."
)
_DEFAULT_CALIBRATION_PATH = Path(__file__).resolve().parents[3] / "golden_sets" / "expressions.json"


def load_expression_calibration_examples(
    *,
    path: str | Path = _DEFAULT_CALIBRATION_PATH,
    sample_size: int = 20,
) -> tuple[dict, ...]:
    """Load deterministic expression calibration examples from Week 2 golden set."""
    if sample_size <= 0:
        return ()

    calibration_path = Path(path)
    if not calibration_path.is_file():
        return ()

    try:
        payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    except OSError:
        return ()

    expressions = payload.get("expressions", [])

    examples: list[dict] = []
    for item in expressions[:sample_size]:
        examples.append(
            {
                "input": item["adf_expression"],
                "output": item["expected_python"],
                "score": 1.0,
            }
        )
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
