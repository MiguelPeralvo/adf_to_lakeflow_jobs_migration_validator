"""Closed-loop adversarial testing orchestrator.

Runs a continuous generate -> convert -> evaluate -> cluster -> feedback loop:

1. GENERATE: Use AgentPipelineGenerator to create ADF pipelines targeting weak spots
2. CONVERT: Run wkmigrate translation via the adapter
3. EVALUATE: Score with dimension scorers + LLM judge
4. CLUSTER: Group failures by signature (dev/wkmigrate-issue-map.json patterns)
5. FEEDBACK: Feed failure patterns back to the generator for next round

Each round uses FailureFeedback.suggest_config() to steer the next generation
toward patterns that caused the most failures. The loop terminates when:
- Max rounds reached
- Budget (LLM calls or time) exhausted
- No new failure clusters discovered for N consecutive rounds (convergence)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generator

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions.activity_coverage import (
    compute_activity_coverage,
)
from lakeflow_migration_validator.dimensions.expression_coverage import (
    compute_expression_coverage,
)
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.dimensions.notebook_validity import (
    compute_notebook_validity,
)
from lakeflow_migration_validator.dimensions.parameter_completeness import (
    compute_parameter_completeness,
)
from lakeflow_migration_validator.synthetic.agent_generator import (
    AgentPipelineGenerator,
    FailureFeedback,
    FailureRecord,
    GenerationConfig,
)

# Type alias for streaming events.
LoopEvent = dict[str, Any]


@dataclass(frozen=True, slots=True)
class LoopConfig:
    """Configuration for the adversarial loop orchestrator."""

    max_rounds: int = 10
    pipelines_per_round: int = 10
    convergence_patience: int = 3
    max_time_seconds: float = 3600.0
    max_llm_calls: int = 500
    failure_threshold: float = 0.75
    target_weak_spots: tuple[str, ...] = (
        "nested_expressions",
        "math_on_params",
        "foreach_expression_items",
        "complex_conditions",
    )
    golden_set_output_path: str | None = None
    issue_map_path: str = "dev/wkmigrate-issue-map.json"


@dataclass(frozen=True, slots=True)
class RoundResult:
    """Summary of a single adversarial round."""

    round_number: int
    pipelines_generated: int
    pipelines_failed: int
    conversions_attempted: int
    failures_found: int
    new_clusters: int
    cluster_signatures: tuple[str, ...]
    worst_dimension: str
    mean_scores: dict[str, float] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    llm_calls_used: int = 0


@dataclass(frozen=True, slots=True)
class LoopResult:
    """Final summary of the adversarial loop run."""

    rounds_completed: int
    total_pipelines: int
    total_failures: int
    unique_clusters: int
    termination_reason: str
    round_results: tuple[RoundResult, ...]
    all_failures: tuple[FailureRecord, ...]
    discovered_signatures: dict[str, int] = field(default_factory=dict)
    golden_set_path: str | None = None
    elapsed_seconds: float = 0.0


class AdversarialLoop:
    """Main adversarial testing orchestrator.

    Ties AgentPipelineGenerator + dimension scorers + FailureFeedback into a
    closed loop that progressively discovers wkmigrate bugs.
    """

    def __init__(
        self,
        provider: JudgeProvider,
        *,
        convert_fn: Callable[[dict], ConversionSnapshot],
        config: LoopConfig | None = None,
        model: str | None = None,
    ):
        self._provider = provider
        self._convert_fn = convert_fn
        self._config = config or LoopConfig()
        self._model = model
        self._generator = AgentPipelineGenerator(provider, model=model)
        self._feedback = FailureFeedback()
        self._llm_calls = 0
        self._all_failures: list[FailureRecord] = []
        self._seen_signatures: dict[str, int] = {}
        self._issue_map = self._load_issue_map()

    def run(self) -> LoopResult:
        """Run the full adversarial loop synchronously."""
        # Consume the stream, return the final result.
        result: LoopResult | None = None
        for event in self.run_stream():
            if event["type"] == "complete":
                result = event["result"]
        assert result is not None  # noqa: S101
        return result

    def run_stream(self) -> Generator[LoopEvent, None, LoopResult]:
        """Yield events for UI streaming, return LoopResult at the end."""
        start_time = time.monotonic()
        round_results: list[RoundResult] = []

        for round_num in range(1, self._config.max_rounds + 1):
            yield {
                "type": "round_start",
                "round": round_num,
                "config": {
                    "pipelines_per_round": self._config.pipelines_per_round,
                    "target_weak_spots": list(self._config.target_weak_spots),
                },
            }

            round_result, round_events = self._run_round(round_num, start_time)
            yield from round_events

            round_results.append(round_result)
            yield {"type": "round_end", "result": round_result}

            # Check termination criteria
            should_stop, reason = self._should_stop(round_results, start_time)
            if should_stop:
                result = self._build_result(round_results, reason, start_time)
                yield {"type": "complete", "result": result}
                return result

        # Reached max rounds
        result = self._build_result(round_results, "max_rounds", start_time)
        yield {"type": "complete", "result": result}
        return result

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    def _run_round(self, round_num: int, loop_start: float) -> tuple[RoundResult, list[LoopEvent]]:
        """Execute a single adversarial round."""
        events: list[LoopEvent] = []
        round_start = time.monotonic()

        # Use feedback to steer generation
        gen_config = self._feedback.suggest_config()
        # Override target_weak_spots from feedback with our config's defaults
        # if feedback has no data yet
        if not self._feedback.failures:
            gen_config = GenerationConfig(
                target_weak_spots=self._config.target_weak_spots,
            )

        # Generate pipelines
        pipelines_generated = 0
        pipelines_failed = 0
        conversions_attempted = 0
        failures_found = 0
        new_clusters_this_round: list[str] = []
        dim_scores: dict[str, list[float]] = {}

        for completed, total, pipeline, error in self._generator.generate_iter(
            count=self._config.pipelines_per_round, config=gen_config
        ):
            self._llm_calls += 1  # LLM call for generation

            if error or pipeline is None:
                pipelines_failed += 1
                events.append(
                    {
                        "type": "pipeline_result",
                        "round": round_num,
                        "index": completed,
                        "scores": {},
                        "is_failure": False,
                    }
                )
                continue

            pipelines_generated += 1
            adf_json = pipeline.adf_json

            # Convert via the adapter
            try:
                snapshot = self._convert_fn(adf_json)
                conversions_attempted += 1
            except Exception:
                conversions_attempted += 1
                # Conversion crash is itself a failure
                record = FailureRecord(
                    pipeline_name=adf_json.get("name", "unknown"),
                    dimension="conversion_crash",
                    score=0.0,
                    error="Conversion raised an exception",
                    adf_json=adf_json,
                )
                self._feedback.record(record)
                self._all_failures.append(record)
                failures_found += 1
                events.append(
                    {
                        "type": "pipeline_result",
                        "round": round_num,
                        "index": completed,
                        "scores": {"conversion_crash": 0.0},
                        "is_failure": True,
                    }
                )
                continue

            # Evaluate dimensions
            scores = self._evaluate_pipeline(adf_json, snapshot)
            is_failure = any(s < self._config.failure_threshold for s in scores.values())

            # Accumulate scores for averaging
            for dim_name, score in scores.items():
                dim_scores.setdefault(dim_name, []).append(score)

            if is_failure:
                failures_found += 1
                # Record failure for feedback
                worst_dim = min(scores, key=scores.get)  # type: ignore[arg-type]
                record = FailureRecord(
                    pipeline_name=adf_json.get("name", "unknown"),
                    dimension=worst_dim,
                    score=scores[worst_dim],
                    error=f"Below threshold on {worst_dim}",
                    adf_json=adf_json,
                )
                self._feedback.record(record)
                self._all_failures.append(record)

                # Classify against issue map
                signature = self._classify_failure(adf_json, scores, snapshot)
                if signature:
                    prev_count = self._seen_signatures.get(signature, 0)
                    self._seen_signatures[signature] = prev_count + 1
                    if prev_count == 0:
                        new_clusters_this_round.append(signature)
                        events.append(
                            {
                                "type": "new_cluster",
                                "signature": signature,
                                "count": 1,
                                "example_expression": _extract_first_expression(adf_json),
                            }
                        )

            events.append(
                {
                    "type": "pipeline_result",
                    "round": round_num,
                    "index": completed,
                    "scores": scores,
                    "is_failure": is_failure,
                }
            )

            # Check time/budget mid-round
            elapsed = time.monotonic() - loop_start
            if elapsed >= self._config.max_time_seconds:
                events.append(
                    {
                        "type": "budget_warning",
                        "resource": "time",
                        "used": elapsed,
                        "limit": self._config.max_time_seconds,
                    }
                )
                break
            if self._llm_calls >= self._config.max_llm_calls:
                events.append(
                    {
                        "type": "budget_warning",
                        "resource": "llm_calls",
                        "used": self._llm_calls,
                        "limit": self._config.max_llm_calls,
                    }
                )
                break

        # Compute mean scores
        mean_scores = {dim: sum(vals) / len(vals) for dim, vals in dim_scores.items() if vals}
        worst_dimension = min(mean_scores, key=mean_scores.get) if mean_scores else "none"  # type: ignore[arg-type]

        round_elapsed = time.monotonic() - round_start
        round_result = RoundResult(
            round_number=round_num,
            pipelines_generated=pipelines_generated,
            pipelines_failed=pipelines_failed,
            conversions_attempted=conversions_attempted,
            failures_found=failures_found,
            new_clusters=len(new_clusters_this_round),
            cluster_signatures=tuple(new_clusters_this_round),
            worst_dimension=worst_dimension,
            mean_scores=mean_scores,
            elapsed_seconds=round_elapsed,
            llm_calls_used=self._llm_calls,
        )
        return round_result, events

    def _evaluate_pipeline(self, adf_json: dict, snapshot: ConversionSnapshot) -> dict[str, float]:
        """Run all dimension scorers on a converted pipeline."""
        scores: dict[str, float] = {}

        # Activity coverage
        score, _ = compute_activity_coverage(snapshot)
        scores["activity_coverage"] = score

        # Expression coverage
        score, _ = compute_expression_coverage(snapshot)
        scores["expression_coverage"] = score

        # Notebook validity
        score, _ = compute_notebook_validity(snapshot)
        scores["notebook_validity"] = score

        # Parameter completeness
        score, _ = compute_parameter_completeness(snapshot)
        scores["parameter_completeness"] = score

        # Dependency preservation (inline — simple ratio)
        if snapshot.total_source_dependencies > 0:
            preserved = len(snapshot.dependencies)
            scores["dependency_preservation"] = min(1.0, preserved / snapshot.total_source_dependencies)
        else:
            scores["dependency_preservation"] = 1.0

        return scores

    def _classify_failure(
        self,
        adf_json: dict,
        scores: dict[str, float],
        snapshot: ConversionSnapshot | None = None,
    ) -> str | None:
        """Match a failure against issue_map signatures."""
        signatures = self._issue_map.get("failure_signatures", [])
        if not signatures:
            return None

        # Build text corpus to match against
        match_texts: list[str] = []

        # Add not_translatable messages from snapshot
        if snapshot:
            for entry in snapshot.not_translatable:
                if isinstance(entry, dict):
                    msg = entry.get("message", "")
                    if msg:
                        match_texts.append(msg)

        # Add pipeline JSON as string for regex matching (fallback)
        pipeline_str = json.dumps(adf_json)
        match_texts.append(pipeline_str)

        for sig in signatures:
            regex = sig.get("regex")
            if not regex:
                continue
            sig_key = sig.get("signature_key", "unknown")
            match_target = sig.get("match_target", "not_translatable.message")

            try:
                pattern = re.compile(regex)
            except re.error:
                continue

            # Match against appropriate target
            if match_target == "not_translatable.message" and snapshot:
                for entry in snapshot.not_translatable:
                    if isinstance(entry, dict):
                        msg = entry.get("message", "")
                        if msg and pattern.search(msg):
                            return sig_key
            elif match_target == "exception":
                # Match against the full pipeline string as proxy
                if pattern.search(pipeline_str):
                    return sig_key
            else:
                # Default: match against all collected texts
                for text in match_texts:
                    if pattern.search(text):
                        return sig_key

        return None

    def _should_stop(self, results: list[RoundResult], start_time: float) -> tuple[bool, str]:
        """Check termination criteria."""
        # Time budget
        elapsed = time.monotonic() - start_time
        if elapsed >= self._config.max_time_seconds:
            return True, "time_budget"

        # LLM call budget
        if self._llm_calls >= self._config.max_llm_calls:
            return True, "llm_budget"

        # Convergence: no new clusters for patience rounds
        if len(results) >= self._config.convergence_patience:
            recent = results[-self._config.convergence_patience :]
            if all(r.new_clusters == 0 for r in recent):
                return True, "converged"

        return False, ""

    def _build_result(
        self,
        round_results: list[RoundResult],
        reason: str,
        start_time: float,
    ) -> LoopResult:
        """Build the final LoopResult and optionally export golden set."""
        golden_set_path: str | None = None
        if self._config.golden_set_output_path and self._all_failures:
            golden_set_path = self._export_golden_set(self._all_failures)

        return LoopResult(
            rounds_completed=len(round_results),
            total_pipelines=sum(r.pipelines_generated for r in round_results),
            total_failures=sum(r.failures_found for r in round_results),
            unique_clusters=len(self._seen_signatures),
            termination_reason=reason,
            round_results=tuple(round_results),
            all_failures=tuple(self._all_failures),
            discovered_signatures=dict(self._seen_signatures),
            golden_set_path=golden_set_path,
            elapsed_seconds=time.monotonic() - start_time,
        )

    def _export_golden_set(self, failures: list[FailureRecord]) -> str:
        """Write failures as a golden set JSON file."""
        output_path = self._config.golden_set_output_path
        assert output_path is not None  # noqa: S101
        return export_as_golden_set(failures, output_path)

    def _load_issue_map(self) -> dict:
        """Load the issue map from disk."""
        path = Path(self._config.issue_map_path)
        if not path.exists():
            # Try relative to project root
            project_root = Path(__file__).resolve().parents[3]
            path = project_root / self._config.issue_map_path
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}


def export_as_golden_set(failures: list[FailureRecord], output_path: str) -> str:
    """Write a list of FailureRecords as a golden_set JSON file.

    Each entry includes: adf_expression (from the pipeline), python_code
    (from conversion if available), category (from failure dimension),
    and expected_dimensions.
    """
    entries: list[dict[str, Any]] = []

    for record in failures:
        # Extract the first expression from the pipeline if possible
        adf_expression = _extract_first_expression(record.adf_json)

        entries.append(
            {
                "adf_expression": adf_expression,
                "python_code": "",
                "category": record.dimension,
                "pipeline_name": record.pipeline_name,
                "score": record.score,
                "expected_dimensions": {
                    record.dimension: 1.0,
                },
            }
        )

    output = {
        "count": len(entries),
        "source": "adversarial_loop",
        "expressions": entries,
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2))
    return str(path)


def _extract_first_expression(adf_json: dict) -> str:
    """Extract the first ADF expression found in a pipeline JSON."""
    if not adf_json:
        return ""
    return _walk_for_expression(adf_json) or ""


def _walk_for_expression(obj: Any) -> str | None:
    """Recursively walk a dict/list looking for an ADF Expression value."""
    if isinstance(obj, dict):
        if obj.get("type") == "Expression" and "value" in obj:
            return str(obj["value"])
        for val in obj.values():
            result = _walk_for_expression(val)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _walk_for_expression(item)
            if result:
                return result
    return None
