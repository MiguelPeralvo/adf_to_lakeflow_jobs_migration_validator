"""Golden set materialization and loading utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lakeflow_migration_validator.synthetic.expression_generator import (
    ExpressionGenerator,
    ExpressionTestCase,
)
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite


@dataclass(frozen=True, slots=True)
class GoldenSetPaths:
    """Filesystem locations for generated golden set artifacts."""

    expressions_path: str
    pipelines_path: str


@dataclass(frozen=True, slots=True)
class GoldenSet:
    """Loaded expression and pipeline golden data."""

    expressions: tuple[ExpressionTestCase, ...]
    pipelines: GroundTruthSuite

    @classmethod
    def load(cls, expressions_path: str, pipelines_path: str) -> GoldenSet:
        """Load a golden set from JSON artifacts."""
        return cls(
            expressions=load_expression_golden_set(expressions_path),
            pipelines=load_pipeline_golden_set(pipelines_path),
        )


def materialize_golden_sets(
    *,
    output_dir: str = "golden_sets",
    expression_count: int = 200,
    pipeline_count: int = 60,
    categories: list[str] | None = None,
    **pipeline_kwargs,
) -> GoldenSetPaths:
    """Generate and write Week 2 golden set files."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    expressions = ExpressionGenerator().generate(count=expression_count, categories=categories)
    expressions_path = output / "expressions.json"
    with expressions_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "version": 1,
                "count": len(expressions),
                "expressions": [
                    {
                        "adf_expression": case.adf_expression,
                        "expected_python": case.expected_python,
                        "category": case.category,
                    }
                    for case in expressions
                ],
            },
            handle,
            indent=2,
            sort_keys=True,
        )

    pipelines = GroundTruthSuite.generate(count=pipeline_count, **pipeline_kwargs)
    pipelines_path = output / "pipelines.json"
    pipelines.to_json(str(pipelines_path))

    return GoldenSetPaths(
        expressions_path=str(expressions_path),
        pipelines_path=str(pipelines_path),
    )


def load_expression_golden_set(path: str) -> tuple[ExpressionTestCase, ...]:
    """Load expression golden set JSON into typed cases."""
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return tuple(
        ExpressionTestCase(
            adf_expression=item["adf_expression"],
            expected_python=item["expected_python"],
            category=item["category"],
        )
        for item in payload.get("expressions", [])
    )


def load_pipeline_golden_set(path: str) -> GroundTruthSuite:
    """Load pipeline golden set JSON into a GroundTruthSuite."""
    return GroundTruthSuite.from_json(path)
