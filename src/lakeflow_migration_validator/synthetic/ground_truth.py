"""Ground-truth suite generation and converter evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from lakeflow_migration_validator import evaluate
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.report import CaseReport, Report
from lakeflow_migration_validator.serialization import snapshot_from_dict, snapshot_to_dict
from lakeflow_migration_validator.synthetic.pipeline_generator import PipelineGenerator, SyntheticPipeline


@dataclass(frozen=True, slots=True)
class GroundTruthSuite:
    """A suite of synthetic pipelines with known-correct expected outputs."""

    pipelines: tuple[SyntheticPipeline, ...]

    @classmethod
    def generate(cls, count: int = 50, **kwargs) -> GroundTruthSuite:
        """Generate a synthetic suite with template-based pipelines."""
        generator = PipelineGenerator(mode=kwargs.pop("mode", "template"))
        pipelines = generator.generate(count=count, **kwargs)
        return cls(pipelines=tuple(pipelines))

    @classmethod
    def from_json(cls, path: str) -> GroundTruthSuite:
        """Load a previously generated suite from disk."""
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        pipelines = tuple(_synthetic_pipeline_from_dict(item) for item in payload["pipelines"])
        return cls(pipelines=pipelines)

    def to_json(self, path: str) -> None:
        """Serialize the suite to disk for replay or calibration."""
        payload = {
            "pipelines": [_synthetic_pipeline_to_dict(pipeline) for pipeline in self.pipelines],
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

    def evaluate_converter(
        self,
        convert_fn: Callable[[dict], ConversionSnapshot],
        threshold: float = 90.0,
    ) -> Report:
        """Run a converter over all pipelines and aggregate score results."""
        case_reports: list[CaseReport] = []
        scores: list[float] = []
        below_threshold = 0
        expression_mismatch_cases = 0

        for pipeline in self.pipelines:
            converted = convert_fn(pipeline.adf_json)
            if not isinstance(converted, ConversionSnapshot):
                raise TypeError("convert_fn must return ConversionSnapshot")

            scorecard = evaluate(converted)
            mismatches = _expression_mismatches(pipeline.expected_snapshot, converted)
            if mismatches:
                expression_mismatch_cases += 1

            is_below_threshold = scorecard.score < threshold
            if is_below_threshold:
                below_threshold += 1

            case_reports.append(
                CaseReport(
                    pipeline_name=pipeline.adf_json.get("name", "<unknown>"),
                    description=pipeline.description,
                    difficulty=pipeline.difficulty,
                    score=scorecard.score,
                    label=scorecard.label,
                    ccs_below_threshold=is_below_threshold,
                    expression_mismatches=tuple(mismatches),
                )
            )
            scores.append(scorecard.score)

        if scores:
            min_score = min(scores)
            max_score = max(scores)
            mean_score = sum(scores) / len(scores)
        else:
            min_score = 0.0
            max_score = 0.0
            mean_score = 0.0

        return Report(
            total=len(case_reports),
            threshold=threshold,
            mean_score=mean_score,
            min_score=min_score,
            max_score=max_score,
            below_threshold=below_threshold,
            expression_mismatch_cases=expression_mismatch_cases,
            cases=tuple(case_reports),
        )


def _expression_mismatches(expected: ConversionSnapshot, actual: ConversionSnapshot) -> list[dict[str, str]]:
    expected_pairs = {(pair.adf_expression, pair.python_code) for pair in expected.resolved_expressions}
    actual_pairs = {(pair.adf_expression, pair.python_code) for pair in actual.resolved_expressions}

    mismatches: list[dict[str, str]] = []
    for adf_expression, python_code in sorted(expected_pairs - actual_pairs):
        mismatches.append(
            {
                "kind": "missing",
                "adf_expression": adf_expression,
                "python_code": python_code,
            }
        )
    for adf_expression, python_code in sorted(actual_pairs - expected_pairs):
        mismatches.append(
            {
                "kind": "unexpected",
                "adf_expression": adf_expression,
                "python_code": python_code,
            }
        )
    return mismatches


def _synthetic_pipeline_to_dict(pipeline: SyntheticPipeline) -> dict:
    return {
        "adf_json": pipeline.adf_json,
        "description": pipeline.description,
        "difficulty": pipeline.difficulty,
        "expected_snapshot": snapshot_to_dict(pipeline.expected_snapshot),
    }


def _synthetic_pipeline_from_dict(payload: dict) -> SyntheticPipeline:
    return SyntheticPipeline(
        adf_json=payload["adf_json"],
        description=payload["description"],
        difficulty=payload["difficulty"],
        expected_snapshot=snapshot_from_dict(payload["expected_snapshot"]),
    )
