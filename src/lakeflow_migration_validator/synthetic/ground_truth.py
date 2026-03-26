"""Ground-truth suite generation and converter evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from lakeflow_migration_validator import evaluate
from lakeflow_migration_validator.contract import (
    ConversionSnapshot,
    DependencyRef,
    ExpressionPair,
    NotebookSnapshot,
    SecretRef,
    TaskSnapshot,
)
from lakeflow_migration_validator.report import CaseReport, Report
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
        "expected_snapshot": _snapshot_to_dict(pipeline.expected_snapshot),
    }


def _synthetic_pipeline_from_dict(payload: dict) -> SyntheticPipeline:
    return SyntheticPipeline(
        adf_json=payload["adf_json"],
        description=payload["description"],
        difficulty=payload["difficulty"],
        expected_snapshot=_snapshot_from_dict(payload["expected_snapshot"]),
    )


def _snapshot_to_dict(snapshot: ConversionSnapshot) -> dict:
    return {
        "tasks": [
            {
                "task_key": task.task_key,
                "is_placeholder": task.is_placeholder,
            }
            for task in snapshot.tasks
        ],
        "notebooks": [
            {
                "file_path": notebook.file_path,
                "content": notebook.content,
            }
            for notebook in snapshot.notebooks
        ],
        "secrets": [
            {
                "scope": secret.scope,
                "key": secret.key,
            }
            for secret in snapshot.secrets
        ],
        "parameters": list(snapshot.parameters),
        "dependencies": [
            {
                "source_task": dependency.source_task,
                "target_task": dependency.target_task,
            }
            for dependency in snapshot.dependencies
        ],
        "not_translatable": list(snapshot.not_translatable),
        "resolved_expressions": [
            {
                "adf_expression": pair.adf_expression,
                "python_code": pair.python_code,
            }
            for pair in snapshot.resolved_expressions
        ],
        "source_pipeline": snapshot.source_pipeline,
        "total_source_dependencies": snapshot.total_source_dependencies,
        "expected_outputs": snapshot.expected_outputs,
        "adf_run_outputs": snapshot.adf_run_outputs,
    }


def _snapshot_from_dict(payload: dict) -> ConversionSnapshot:
    return ConversionSnapshot(
        tasks=tuple(
            TaskSnapshot(task_key=task["task_key"], is_placeholder=task["is_placeholder"])
            for task in payload["tasks"]
        ),
        notebooks=tuple(
            NotebookSnapshot(file_path=notebook["file_path"], content=notebook["content"])
            for notebook in payload["notebooks"]
        ),
        secrets=tuple(
            SecretRef(scope=secret["scope"], key=secret["key"])
            for secret in payload["secrets"]
        ),
        parameters=tuple(payload["parameters"]),
        dependencies=tuple(
            DependencyRef(source_task=dep["source_task"], target_task=dep["target_task"])
            for dep in payload["dependencies"]
        ),
        not_translatable=tuple(payload["not_translatable"]),
        resolved_expressions=tuple(
            ExpressionPair(adf_expression=pair["adf_expression"], python_code=pair["python_code"])
            for pair in payload["resolved_expressions"]
        ),
        source_pipeline=payload["source_pipeline"],
        total_source_dependencies=payload["total_source_dependencies"],
        expected_outputs=payload.get("expected_outputs", {}),
        adf_run_outputs=payload.get("adf_run_outputs", {}),
    )
