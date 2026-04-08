"""FastAPI surface for validation, harness, and synthetic workflows."""

from __future__ import annotations

import json as _json
import logging
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from lakeflow_migration_validator import evaluate_batch, evaluate_full
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.dimensions.llm_judge import JudgeProvider
from lakeflow_migration_validator.golden_set import load_pipeline_golden_set
from lakeflow_migration_validator.serialization import snapshot_from_adf_payload
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite

logger = logging.getLogger(__name__)


class HistoryStore:
    """Persistent history store backed by SQLite (JSON file fallback).

    Stores validation scorecards and an activity log that survives server
    restarts. Falls back to a JSON file if SQLite is unavailable.
    """

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = Path(db_path) if db_path else Path(tempfile.gettempdir()) / "lmv_history.db"
        self._json_path = self._db_path.with_suffix(".json")
        self._use_sqlite = False
        self._conn: Any = None
        try:
            import sqlite3
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    type TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            # Migrate: add entity_id and results columns if missing
            try:
                self._conn.execute("ALTER TABLE activity_log ADD COLUMN entity_id TEXT")
            except Exception:
                pass
            try:
                self._conn.execute("ALTER TABLE activity_log ADD COLUMN results TEXT")
            except Exception:
                pass
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_type ON activity_log(type)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity_log(timestamp DESC)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_id ON activity_log(entity_id)")
            self._conn.commit()
            self._use_sqlite = True
        except Exception:
            self._use_sqlite = False

    def _write_event(self, event: dict[str, Any], entity_id: str, results: dict[str, Any] | None = None) -> None:
        event["entity_id"] = entity_id
        if self._use_sqlite:
            self._conn.execute(
                "INSERT INTO activity_log (timestamp, type, data, entity_id, results) VALUES (?, ?, ?, ?, ?)",
                (event["timestamp"], event["type"], _json.dumps(event), entity_id,
                 _json.dumps(results) if results is not None else None),
            )
            self._conn.commit()
        else:
            # JSON file fallback
            log = []
            if self._json_path.exists():
                try:
                    log = _json.loads(self._json_path.read_text(encoding="utf-8"))
                except Exception:
                    log = []
            if results is not None:
                event["_results"] = results
            log.append(event)
            self._json_path.write_text(_json.dumps(log, indent=2), encoding="utf-8")

    def append(self, pipeline_name: str, scorecard: dict[str, Any], full_result: dict[str, Any] | None = None) -> str:
        eid = str(uuid.uuid4())
        self._write_event({
            "type": "validation",
            "pipeline_name": pipeline_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scorecard": scorecard,
        }, entity_id=eid, results=full_result or scorecard)
        return eid

    def log_batch(self, folder: str, total: int, mean_score: float, below: int, threshold: float, full_result: dict[str, Any] | None = None) -> str:
        eid = str(uuid.uuid4())
        self._write_event({
            "type": "batch_validation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "folder": folder,
            "total": total,
            "mean_score": mean_score,
            "below_threshold": below,
            "threshold": threshold,
        }, entity_id=eid, results=full_result)
        return eid

    def log_synthetic(self, output_path: str, count: int, mode: str, full_result: dict[str, Any] | None = None) -> str:
        eid = str(uuid.uuid4())
        self._write_event({
            "type": "synthetic_generation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_path": output_path,
            "count": count,
            "mode": mode,
        }, entity_id=eid, results=full_result)
        return eid

    def log_expression(self, adf_expression: str, python_code: str, result: dict[str, Any]) -> str:
        eid = str(uuid.uuid4())
        self._write_event({
            "type": "expression",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "adf_expression": adf_expression,
            "python_code": python_code,
            "score": result.get("score", 0),
        }, entity_id=eid, results=result)
        return eid

    def log_harness(self, pipeline_name: str, result: dict[str, Any]) -> str:
        eid = str(uuid.uuid4())
        self._write_event({
            "type": "harness",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline_name": pipeline_name,
            "iterations": result.get("iterations", 0),
            "score": result.get("scorecard", {}).get("score", 0),
        }, entity_id=eid, results=result)
        return eid

    def log_parallel(self, pipeline_name: str, result: dict[str, Any]) -> str:
        eid = str(uuid.uuid4())
        self._write_event({
            "type": "parallel",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline_name": pipeline_name,
            "equivalence_score": result.get("equivalence_score", 0),
        }, entity_id=eid, results=result)
        return eid

    def get(self, pipeline_name: str) -> list[dict[str, Any]]:
        if self._use_sqlite:
            rows = self._conn.execute(
                "SELECT data FROM activity_log WHERE type = 'validation' AND data LIKE ? ORDER BY timestamp DESC",
                (f'%"pipeline_name": "{pipeline_name}"%',),
            ).fetchall()
            return [_json.loads(row[0]) for row in rows]
        # JSON fallback
        if not self._json_path.exists():
            return []
        try:
            log = _json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return [e for e in log if e.get("type") == "validation" and e.get("pipeline_name") == pipeline_name]

    def get_activity_log(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._use_sqlite:
            rows = self._conn.execute(
                "SELECT data FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [_json.loads(row[0]) for row in rows]
        # JSON fallback
        if not self._json_path.exists():
            return []
        try:
            log = _json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return list(reversed(log[-limit:]))

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        """Retrieve a single entity by its UUID, including full results."""
        if self._use_sqlite:
            row = self._conn.execute(
                "SELECT data, results FROM activity_log WHERE entity_id = ?", (entity_id,)
            ).fetchone()
            if row is None:
                return None
            event = _json.loads(row[0])
            if row[1]:
                event["results"] = _json.loads(row[1])
            return event
        # JSON fallback
        if not self._json_path.exists():
            return None
        try:
            log = _json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        for e in log:
            if e.get("entity_id") == entity_id:
                if "_results" in e:
                    e["results"] = e.pop("_results")
                return e
        return None

    def list_entities(self, entity_type: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """List entities, optionally filtered by type. Returns metadata (no full results)."""
        if self._use_sqlite:
            if entity_type:
                rows = self._conn.execute(
                    "SELECT data FROM activity_log WHERE type = ? ORDER BY id DESC LIMIT ?",
                    (entity_type, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT data FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [_json.loads(row[0]) for row in rows]
        # JSON fallback
        if not self._json_path.exists():
            return []
        try:
            log = _json.loads(self._json_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        filtered = [e for e in log if entity_type is None or e.get("type") == entity_type]
        return list(reversed(filtered[-limit:]))


# Backward-compatible alias
InMemoryHistoryStore = HistoryStore


class ValidateRequest(BaseModel):
    """Request payload for /api/validate.

    Accepts three input modes:
    - ``adf_json``: raw ADF pipeline JSON (dict) — creates a minimal snapshot
    - ``snapshot``: a pre-converted ConversionSnapshot dict (from wkmigrate adapter)
    - ``adf_yaml``: raw ADF pipeline definition as a YAML string — parsed to dict
    """

    adf_json: dict[str, Any] | None = None
    adf_yaml: str | None = None
    snapshot: dict[str, Any] | None = None
    pipeline_name: str | None = None
    input_mode: str | None = None  # "adf_json", "adf_yaml", "snapshot" — auto-detected if not set

    @model_validator(mode="after")
    def _validate_source(self):
        if self.adf_json is None and self.snapshot is None and self.adf_yaml is None:
            raise ValueError("provide one of: adf_json, adf_yaml, or snapshot")
        return self


class ValidateExpressionRequest(BaseModel):
    """Request payload for /api/validate/expression."""

    adf_expression: str = Field(min_length=1)
    python_code: str = Field(min_length=1)


class ValidateBatchRequest(BaseModel):
    """Request payload for /api/validate/batch."""

    pipelines_path: str
    threshold: float = 90.0


class ValidateFolderRequest(BaseModel):
    """Request payload for /api/validate/folder — scan a directory of ADF JSON files."""

    folder_path: str = Field(min_length=1)
    threshold: float = 90.0
    glob_pattern: str = "*.json"
    agent_analysis: bool = False  # run LLM agent analysis on failing dimensions


def _adf_credentials_from_env() -> dict[str, str]:
    """Read ADF credentials from environment variables.

    Expected env vars (also usable via .env or CLI ``--env``):
      ADF_TENANT_ID, ADF_CLIENT_ID, ADF_CLIENT_SECRET,
      ADF_SUBSCRIPTION_ID, ADF_RESOURCE_GROUP, ADF_FACTORY_NAME
    """
    import os
    return {
        "tenant_id": os.environ.get("ADF_TENANT_ID", ""),
        "client_id": os.environ.get("ADF_CLIENT_ID", ""),
        "client_secret": os.environ.get("ADF_CLIENT_SECRET", ""),
        "subscription_id": os.environ.get("ADF_SUBSCRIPTION_ID", ""),
        "resource_group": os.environ.get("ADF_RESOURCE_GROUP", ""),
        "factory_name": os.environ.get("ADF_FACTORY_NAME", ""),
    }


def _resolve_adf_credentials(request_data: dict[str, Any]) -> dict[str, str]:
    """Merge request fields over env-var defaults. Raises HTTPException if any are missing."""
    env = _adf_credentials_from_env()
    resolved = {}
    for key in ("tenant_id", "client_id", "client_secret", "subscription_id", "resource_group", "factory_name"):
        val = request_data.get(key) or env.get(key, "")
        if not val:
            raise HTTPException(
                status_code=422,
                detail=f"Missing ADF credential: {key}. Set ADF_{key.upper()} env var or pass in request.",
            )
        resolved[key] = val
    return resolved


class DownloadPipelinesRequest(BaseModel):
    """Request payload for /api/adf/download — fetch pipelines from Azure Data Factory.

    Credentials are optional — falls back to ADF_* environment variables.
    """

    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    subscription_id: str | None = None
    resource_group: str | None = None
    factory_name: str | None = None
    pipeline_names: list[str] | None = None  # None = download all
    output_folder: str | None = None         # None = auto-generate in temp


class UploadPipelinesRequest(BaseModel):
    """Request payload for /api/adf/upload — push local ADF JSON pipelines to Azure Data Factory.

    Credentials are optional — falls back to ADF_* environment variables.
    """

    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    subscription_id: str | None = None
    resource_group: str | None = None
    factory_name: str | None = None
    folder_path: str = Field(min_length=1)   # local folder with pipeline subfolders or *.json
    name_prefix: str = ""                    # optional prefix for uploaded pipeline names


class HarnessRunRequest(BaseModel):
    """Request payload for /api/harness/run."""

    pipeline_name: str = Field(min_length=1)


class SyntheticGenerateRequest(BaseModel):
    """Request payload for /api/synthetic/generate.

    Modes:
    - ``template``: deterministic templates (fast, no LLM)
    - ``llm``: LLM generation using a preset or custom prompt
    - ``custom``: user-provided prompt (free-form)
    """

    count: int = 10
    difficulty: str = "medium"
    max_activities: int = 20
    mode: str = "template"
    preset: str | None = None           # key from PROMPT_TEMPLATES (for llm mode)
    custom_prompt: str | None = None    # user-edited prompt (for custom mode)
    generate_test_data: bool = False    # also generate test data for parallel testing
    output_path: str | None = None
    spec: dict[str, Any] | None = None  # pre-generated spec — skips planning


class ParallelRunRequest(BaseModel):
    """Request payload for /api/parallel/run."""

    pipeline_name: str = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)
    snapshot: dict[str, Any] | None = None


def create_app(
    *,
    convert_fn: Callable[[dict], ConversionSnapshot] | None = None,
    judge_provider: JudgeProvider | None = None,
    history_store: HistoryStore | None = None,
    harness_runner=None,
    parallel_runner=None,
) -> FastAPI:
    """Create the FastAPI app with injectable dependencies for tests and runtime."""

    app = FastAPI(title="lakeflow-migration-validator", version="0.1.0")
    convert = convert_fn or snapshot_from_adf_payload
    history = history_store or HistoryStore()

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        """Return which capabilities are active."""
        adf_env = _adf_credentials_from_env()
        adf_configured = all(adf_env.get(k) for k in ("tenant_id", "client_id", "client_secret", "subscription_id", "resource_group", "factory_name"))
        return {
            "validator": True,
            "judge": judge_provider is not None,
            "harness": harness_runner is not None,
            "parallel": parallel_runner is not None,
            "adf": adf_configured,
            "adf_factory_name": adf_env.get("factory_name", "") if adf_configured else None,
        }

    @app.get("/api/adf/config")
    def get_adf_config() -> dict[str, Any]:
        """Return ADF connection status — which env vars are set (no secrets exposed)."""
        env = _adf_credentials_from_env()
        return {
            "configured": all(env.get(k) for k in ("tenant_id", "client_id", "client_secret", "subscription_id", "resource_group", "factory_name")),
            "factory_name": env.get("factory_name", ""),
            "resource_group": env.get("resource_group", ""),
            "subscription_id": env.get("subscription_id", ""),
            "has_tenant_id": bool(env.get("tenant_id")),
            "has_client_id": bool(env.get("client_id")),
            "has_client_secret": bool(env.get("client_secret")),
        }

    @app.post("/api/validate")
    def post_validate(request: ValidateRequest) -> dict[str, Any]:
        snapshot = _resolve_snapshot(request, convert)
        scorecard = evaluate_full(snapshot, judge_provider=judge_provider)

        if request.pipeline_name:
            pipeline_name = request.pipeline_name
        elif request.adf_json:
            pipeline_name = str(request.adf_json.get("name", "<unknown>"))
        elif request.adf_yaml:
            pipeline_name = str(snapshot.source_pipeline.get("name", "<yaml>"))
        else:
            pipeline_name = "<snapshot>"

        payload = scorecard.to_dict()
        entity_id = history.append(pipeline_name, payload)
        payload["entity_id"] = entity_id
        return payload

    @app.post("/api/validate/expression")
    def post_validate_expression(request: ValidateExpressionRequest) -> dict[str, Any]:
        if judge_provider is None:
            raise HTTPException(status_code=503, detail="judge_provider is not configured")

        prompt = (
            "Evaluate semantic equivalence between ADF and Python code. "
            f"ADF: {request.adf_expression}\nPython: {request.python_code}"
        )
        response = judge_provider.judge(prompt)
        try:
            score = float(response.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        result = {
            "score": max(0.0, min(1.0, score)),
            "reasoning": str(response.get("reasoning", "")),
            "adf_expression": request.adf_expression,
            "python_code": request.python_code,
        }
        entity_id = history.log_expression(request.adf_expression, request.python_code, result)
        result["entity_id"] = entity_id
        return result

    @app.get("/api/history/{pipeline_name}")
    def get_history(pipeline_name: str) -> list[dict[str, Any]]:
        return history.get(pipeline_name)

    @app.get("/api/history")
    def get_activity_log(limit: int = Query(100)) -> list[dict[str, Any]]:
        """Return the unified activity log — validations, batch runs, synthetic generations."""
        return history.get_activity_log(limit)

    @app.get("/api/entities/{entity_id}")
    def get_entity(entity_id: str) -> dict[str, Any]:
        """Retrieve a past run by entity ID, including full results."""
        result = history.get_entity(entity_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        return result

    @app.get("/api/entities")
    def list_entities(type: str | None = Query(None), limit: int = Query(20)) -> list[dict[str, Any]]:
        """List past runs, optionally filtered by type."""
        return history.list_entities(entity_type=type, limit=limit)

    @app.post("/api/validate/batch")
    def post_validate_batch(request: ValidateBatchRequest) -> dict[str, Any]:
        suite = load_pipeline_golden_set(request.pipelines_path)
        report = evaluate_batch(suite, convert, threshold=request.threshold)
        return report.to_dict()

    @app.post("/api/validate/folder")
    def post_validate_folder(
        request: ValidateFolderRequest,
        stream: bool = Query(False),
    ):
        """Scan a folder of ADF JSON files, translate each through wkmigrate, and evaluate.

        Supports two folder layouts:
        - **Flat**: ``folder/*.json`` — each JSON file is an ADF pipeline
        - **Synthetic**: ``folder/*/adf_pipeline.json`` — subfolders from synthetic generation
        """
        folder = Path(request.folder_path)
        if not folder.is_dir():
            raise HTTPException(status_code=422, detail=f"Not a directory: {request.folder_path}")

        # Discover pipeline JSON files — check synthetic subfolder structure first
        subfolder_files = sorted(folder.glob("*/adf_pipeline.json"))
        if subfolder_files:
            files = subfolder_files
        else:
            # Flat layout: glob in root, exclude suite.json
            files = sorted(
                f for f in folder.glob(request.glob_pattern)
                if f.is_file() and f.name != "suite.json"
            )
        if not files:
            raise HTTPException(status_code=422, detail=f"No ADF pipeline files found in {request.folder_path}")

        if stream:
            return StreamingResponse(
                _validate_folder_stream(
                    files, convert, request.threshold,
                    judge_provider=judge_provider,
                    analysis_agent=judge_provider if request.agent_analysis else None,
                ),
                media_type="application/x-ndjson",
            )

        # Non-streaming: evaluate all and return report
        cases = []
        scores = []
        below = 0
        for file_path in files:
            with open(file_path, encoding="utf-8") as f:
                adf_json = _json.load(f)
            name = adf_json.get("name", file_path.stem)
            try:
                snapshot = convert(adf_json)
                scorecard = evaluate_full(snapshot, judge_provider=judge_provider)
                score = scorecard.score
                label = scorecard.label
            except Exception:
                score = 0.0
                label = "ERROR"
            is_below = score < request.threshold
            if is_below:
                below += 1
            scores.append(score)
            cases.append({
                "pipeline_name": name,
                "file": str(file_path),
                "score": score,
                "label": label,
                "ccs_below_threshold": is_below,
            })

        mean = sum(scores) / len(scores) if scores else 0.0
        return {
            "total": len(cases),
            "threshold": request.threshold,
            "mean_score": mean,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "below_threshold": below,
            "cases": cases,
        }

    def _validate_folder_stream(
        files: list,
        convert_fn,
        threshold: float,
        *,
        judge_provider=None,
        analysis_agent=None,
    ):
        """Yield NDJSON progress events for folder validation.

        ``judge_provider`` is always passed to ``evaluate_full`` so LLM-judged
        dimensions score on every run (matching the non-streaming and
        single-pipeline paths).

        ``analysis_agent`` is the LLM used for the optional per-pipeline
        diagnosis phase. It is only set when the caller requested
        ``agent_analysis``; failing pipelines then get an additional LLM
        analysis pass that diagnoses each failing dimension and suggests
        concrete fixes.

        Event types:
          progress — per-pipeline programmatic + LLM score
          analysis — per-pipeline agent diagnosis (only when analysis_agent is set)
          complete — final report with all cases
        """
        total = len(files)
        cases = []
        scores = []
        below = 0
        for i, file_path in enumerate(files):
            name = file_path.stem
            snapshot = None
            try:
                with open(file_path, encoding="utf-8") as f:
                    adf_json = _json.load(f)
                name = adf_json.get("name", name)
                snapshot = convert_fn(adf_json)
                scorecard = evaluate_full(snapshot, judge_provider=judge_provider)
                score = scorecard.score
                label = scorecard.label
                dims = scorecard.to_dict().get("dimensions", {})
                error = None
            except Exception as exc:
                score = 0.0
                label = "ERROR"
                dims = {}
                adf_json = {}
                error = f"{type(exc).__name__}: {exc}"

            is_below = score < threshold
            if is_below:
                below += 1
            scores.append(score)

            case: dict[str, Any] = {
                "pipeline_name": name,
                "file": str(file_path),
                "score": score,
                "label": label,
                "ccs_below_threshold": is_below,
                "dimensions": dims,
            }

            yield _json.dumps({
                "type": "progress",
                "completed": i + 1,
                "total": total,
                "pipeline_name": name,
                "score": score,
                "label": label,
                "ok": error is None,
                "error": error,
            }) + "\n"

            # Agent analysis — run whenever any dimension is imperfect (not just below threshold)
            has_imperfect = any(not v.get("passed", True) for v in dims.values()) if dims else False
            if analysis_agent is not None and (is_below or has_imperfect) and dims and snapshot is not None:
                yield _json.dumps({
                    "type": "analysis_start",
                    "pipeline_name": name,
                    "pipeline_index": i,
                }) + "\n"

                failing_dims = {
                    k: v for k, v in dims.items()
                    if not v.get("passed", True)
                }
                analyses = []
                for dim_name, dim_data in failing_dims.items():
                    try:
                        source_acts = adf_json.get("properties", {}).get("activities", adf_json.get("activities", []))
                        prompt = (
                            f"You are an ADF-to-Databricks migration expert.\n\n"
                            f"Pipeline: {name}\n"
                            f"Dimension: {dim_name} — score: {dim_data['score']:.2f}\n"
                            f"Details: {_json.dumps(dim_data.get('details', {}))}\n\n"
                            f"Source ADF activities ({len(source_acts)}):\n"
                            f"{_json.dumps([a.get('name', '?') + ' (' + a.get('type', '?') + ')' for a in source_acts[:20]])}\n\n"
                            f"Converted tasks ({len(snapshot.tasks)}):\n"
                            f"{_json.dumps([t.task_key + (' [placeholder]' if t.is_placeholder else '') for t in snapshot.tasks[:20]])}\n\n"
                            f"1. Diagnose WHY this dimension scored {dim_data['score']:.2f}. "
                            f"What specifically was lost or broken in the translation?\n"
                            f"2. Suggest a concrete fix — either in wkmigrate's translator/preparer "
                            f"code or in the ADF pipeline structure.\n\n"
                            f"Be specific and actionable. Reference actual activity names and types."
                        )
                        if hasattr(analysis_agent, "complete"):
                            reasoning = analysis_agent.complete(prompt, max_tokens=2048)
                        else:
                            resp = analysis_agent.judge(prompt)
                            reasoning = resp.get("reasoning", "")
                    except Exception as exc:
                        reasoning = f"Analysis failed: {type(exc).__name__}"

                    analysis_entry = {
                        "dimension": dim_name,
                        "score": dim_data["score"],
                        "diagnosis": reasoning,
                    }
                    analyses.append(analysis_entry)

                    yield _json.dumps({
                        "type": "analysis",
                        "pipeline_name": name,
                        "pipeline_index": i,
                        "dimension": dim_name,
                        "score": dim_data["score"],
                        "diagnosis": reasoning,
                    }) + "\n"

                case["agent_analysis"] = analyses

            cases.append(case)

        mean = sum(scores) / len(scores) if scores else 0.0
        folder_path = str(files[0].parent) if files else ""
        batch_result = {
            "total": len(cases),
            "threshold": threshold,
            "mean_score": mean,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "below_threshold": below,
            "cases": cases,
        }
        entity_id = history.log_batch(folder_path, len(cases), mean, below, threshold, full_result=batch_result)
        batch_result["entity_id"] = entity_id
        yield _json.dumps({
            "type": "complete",
            "result": batch_result,
        }) + "\n"

    @app.post("/api/harness/run")
    def post_harness_run(request: HarnessRunRequest) -> dict[str, Any]:
        if harness_runner is None:
            raise HTTPException(status_code=503, detail="harness_runner is not configured")
        result = harness_runner.run(request.pipeline_name)
        payload = {
            "pipeline_name": result.pipeline_name,
            "scorecard": result.scorecard.to_dict(),
            "iterations": result.iterations,
            "fix_suggestions": list(result.fix_suggestions),
        }
        entity_id = history.log_harness(request.pipeline_name, payload)
        payload["entity_id"] = entity_id
        return payload

    # ------------------------------------------------------------------
    # ADF pipeline download
    # ------------------------------------------------------------------

    @app.post("/api/adf/download")
    def post_adf_download(
        request: DownloadPipelinesRequest,
        stream: bool = Query(False),
    ):
        """Download ADF pipelines from Azure Data Factory to a local folder.

        Credentials are resolved from the request body first, then from
        ADF_* environment variables. No secrets need to be in the UI.
        """
        try:
            from wkmigrate.clients.factory_client import FactoryClient
        except ImportError:
            raise HTTPException(status_code=503, detail="wkmigrate is not installed — FactoryClient unavailable")

        creds = _resolve_adf_credentials(request.model_dump())

        try:
            client = FactoryClient(
                tenant_id=creds["tenant_id"],
                client_id=creds["client_id"],
                client_secret=creds["client_secret"],
                subscription_id=creds["subscription_id"],
                resource_group_name=creds["resource_group"],
                factory_name=creds["factory_name"],
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to ADF: {type(exc).__name__}: {exc}")

        factory_name = creds["factory_name"]

        # Determine output folder
        if request.output_folder:
            out_dir = Path(request.output_folder)
        else:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            out_dir = Path(tempfile.gettempdir()) / "lmv_adf_download" / f"{factory_name}_{ts}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Get pipeline list
        if request.pipeline_names:
            pipeline_names = request.pipeline_names
        else:
            try:
                pipeline_names = client.list_pipelines()
            except Exception as exc:
                raise HTTPException(status_code=502, detail=f"Failed to list pipelines: {exc}")

        if stream:
            return StreamingResponse(
                _download_pipelines_stream(client, pipeline_names, out_dir),
                media_type="application/x-ndjson",
            )

        # Non-streaming
        downloaded = []
        errors = []
        for name in pipeline_names:
            try:
                pipeline_json = client.get_pipeline(name)
                pipeline_json["name"] = name
                safe = name.replace("/", "_").replace(" ", "_")[:60]
                pipe_dir = out_dir / safe
                pipe_dir.mkdir(parents=True, exist_ok=True)
                with open(pipe_dir / "adf_pipeline.json", "w", encoding="utf-8") as fh:
                    _json.dump(pipeline_json, fh, indent=2)
                downloaded.append(name)
            except Exception as exc:
                errors.append({"pipeline": name, "error": f"{type(exc).__name__}: {exc}"})

        return {
            "folder": str(out_dir),
            "factory_name": request.factory_name,
            "total": len(pipeline_names),
            "downloaded": len(downloaded),
            "errors": errors,
            "pipelines": downloaded,
        }

    def _download_pipelines_stream(client, pipeline_names: list[str], out_dir: Path):
        """Stream NDJSON progress while downloading ADF pipelines."""
        total = len(pipeline_names)
        downloaded = []
        errors = []
        for i, name in enumerate(pipeline_names):
            try:
                pipeline_json = client.get_pipeline(name)
                pipeline_json["name"] = name
                safe = name.replace("/", "_").replace(" ", "_")[:60]
                pipe_dir = out_dir / safe
                pipe_dir.mkdir(parents=True, exist_ok=True)
                with open(pipe_dir / "adf_pipeline.json", "w", encoding="utf-8") as fh:
                    _json.dump(pipeline_json, fh, indent=2)
                downloaded.append(name)
                yield _json.dumps({
                    "type": "progress", "completed": i + 1, "total": total,
                    "pipeline_name": name, "ok": True,
                }) + "\n"
            except Exception as exc:
                errors.append({"pipeline": name, "error": f"{type(exc).__name__}: {exc}"})
                yield _json.dumps({
                    "type": "progress", "completed": i + 1, "total": total,
                    "pipeline_name": name, "ok": False, "error": str(exc),
                }) + "\n"

        yield _json.dumps({
            "type": "complete",
            "result": {
                "folder": str(out_dir),
                "total": total,
                "downloaded": len(downloaded),
                "errors": errors,
                "pipelines": downloaded,
            },
        }) + "\n"

    @app.post("/api/adf/upload")
    def post_adf_upload(
        request: UploadPipelinesRequest,
        stream: bool = Query(False),
    ):
        """Upload local ADF pipeline JSONs to an Azure Data Factory.

        Reads pipeline JSON files from a local folder (synthetic output or
        downloaded pipelines) and creates/updates them in the target factory.
        Useful for setting up parallel testing or E2E harness runs.
        """
        try:
            from wkmigrate.clients.factory_client import FactoryClient
            from azure.mgmt.datafactory.models import PipelineResource
        except ImportError:
            raise HTTPException(status_code=503, detail="wkmigrate/azure SDK not installed")

        creds = _resolve_adf_credentials(request.model_dump())

        try:
            client = FactoryClient(
                tenant_id=creds["tenant_id"],
                client_id=creds["client_id"],
                client_secret=creds["client_secret"],
                subscription_id=creds["subscription_id"],
                resource_group_name=creds["resource_group"],
                factory_name=creds["factory_name"],
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to connect to ADF: {exc}")

        # Discover pipeline files (same logic as folder validation)
        folder = Path(request.folder_path)
        if not folder.is_dir():
            raise HTTPException(status_code=422, detail=f"Not a directory: {request.folder_path}")
        subfolder_files = sorted(folder.glob("*/adf_pipeline.json"))
        if subfolder_files:
            files = subfolder_files
        else:
            files = sorted(f for f in folder.glob("*.json") if f.is_file() and f.name != "suite.json")
        if not files:
            raise HTTPException(status_code=422, detail=f"No ADF pipeline files found in {request.folder_path}")

        if stream:
            return StreamingResponse(
                _upload_pipelines_stream(client, files, request.name_prefix, PipelineResource),
                media_type="application/x-ndjson",
            )

        uploaded = []
        errors = []
        for file_path in files:
            with open(file_path, encoding="utf-8") as fh:
                adf_json = _json.load(fh)
            name = request.name_prefix + adf_json.get("name", file_path.parent.name)
            try:
                props = adf_json.get("properties", adf_json)
                resource = PipelineResource(**props)
                client.management_client.pipelines.create_or_update(
                    client.resource_group_name, client.factory_name, name, resource,
                )
                uploaded.append(name)
            except Exception as exc:
                errors.append({"pipeline": name, "error": f"{type(exc).__name__}: {exc}"})

        return {
            "factory_name": request.factory_name,
            "total": len(files),
            "uploaded": len(uploaded),
            "errors": errors,
            "pipelines": uploaded,
        }

    def _upload_pipelines_stream(client, files, name_prefix, PipelineResource):
        total = len(files)
        uploaded = []
        errors = []
        for i, file_path in enumerate(files):
            with open(file_path, encoding="utf-8") as fh:
                adf_json = _json.load(fh)
            name = name_prefix + adf_json.get("name", file_path.parent.name)
            try:
                props = adf_json.get("properties", adf_json)
                resource = PipelineResource(**props)
                client.management_client.pipelines.create_or_update(
                    client.resource_group_name, client.factory_name, name, resource,
                )
                uploaded.append(name)
                yield _json.dumps({"type": "progress", "completed": i + 1, "total": total, "pipeline_name": name, "ok": True}) + "\n"
            except Exception as exc:
                errors.append({"pipeline": name, "error": str(exc)})
                yield _json.dumps({"type": "progress", "completed": i + 1, "total": total, "pipeline_name": name, "ok": False, "error": str(exc)}) + "\n"

        yield _json.dumps({"type": "complete", "result": {"total": total, "uploaded": len(uploaded), "errors": errors, "pipelines": uploaded}}) + "\n"

    @app.get("/api/adf/list")
    def get_adf_list_pipelines() -> list[str]:
        """List all pipeline names in an Azure Data Factory.

        Uses ADF_* environment variables for credentials.
        """
        try:
            from wkmigrate.clients.factory_client import FactoryClient
        except ImportError:
            raise HTTPException(status_code=503, detail="wkmigrate not installed")
        creds = _resolve_adf_credentials({})
        try:
            client = FactoryClient(
                tenant_id=creds["tenant_id"], client_id=creds["client_id"],
                client_secret=creds["client_secret"], subscription_id=creds["subscription_id"],
                resource_group_name=creds["resource_group"], factory_name=creds["factory_name"],
            )
            return client.list_pipelines()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to list pipelines: {exc}")

    # ------------------------------------------------------------------
    # wkmigrate repo/branch configuration
    # ------------------------------------------------------------------
    _wkmigrate_config: dict[str, Any] = {
        "repos": [
            {"url": "https://github.com/MiguelPeralvo/wkmigrate", "default_branch": "alpha"},
            {"url": "https://github.com/ghanse/wkmigrate", "default_branch": "main"},
        ],
        "active_repo": "https://github.com/MiguelPeralvo/wkmigrate",
        "active_branch": "alpha",
    }

    @app.get("/api/config/wkmigrate")
    def get_wkmigrate_config() -> dict[str, Any]:
        """Return the current wkmigrate repo/branch configuration."""
        return _wkmigrate_config

    @app.post("/api/config/wkmigrate")
    def set_wkmigrate_config(request: dict[str, Any]) -> dict[str, Any]:
        """Update the active wkmigrate repo and/or branch.

        Note: changing the repo/branch stores the selection but does NOT
        hot-swap the running wkmigrate. A server restart with the new
        package installed is required for changes to take effect.
        """
        if "active_repo" in request:
            _wkmigrate_config["active_repo"] = request["active_repo"]
        if "active_branch" in request:
            _wkmigrate_config["active_branch"] = request["active_branch"]
        if "repos" in request:
            _wkmigrate_config["repos"] = request["repos"]
        return _wkmigrate_config

    @app.get("/api/config/wkmigrate/branches")
    def get_wkmigrate_branches(repo_url: str = Query(...)) -> list[dict[str, Any]]:
        """Fetch branches for a GitHub repo, sorted by most recent commit.

        Example: ``/api/config/wkmigrate/branches?repo_url=https://github.com/MiguelPeralvo/wkmigrate``
        """
        from urllib.request import Request, urlopen
        from urllib.error import URLError

        # Parse owner/repo from URL
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            raise HTTPException(status_code=422, detail="Invalid repo URL")
        owner, repo = parts[-2], parts[-1]

        try:
            api_url = f"https://api.github.com/repos/{owner}/{repo}/branches?per_page=100"
            req = Request(api_url, headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "LMV"})
            with urlopen(req, timeout=10) as resp:
                branches = _json.loads(resp.read().decode("utf-8"))
        except (URLError, Exception) as exc:
            raise HTTPException(status_code=502, detail=f"Failed to fetch branches: {exc}") from exc

        # Sort by commit date (most recent first)
        for b in branches:
            sha = b.get("commit", {}).get("sha", "")
            b["_sha"] = sha
        # Fetch commit dates for sorting (batch — just use the sha order as proxy)
        # GitHub branches API doesn't include commit dates, so we fetch each commit
        # For performance, just return as-is and let the frontend sort if needed
        return [
            {"name": b["name"], "sha": b.get("_sha", "")[:8], "protected": b.get("protected", False)}
            for b in branches
        ]

    # ------------------------------------------------------------------
    # Synthetic run history (list past batch directories)
    # ------------------------------------------------------------------
    @app.get("/api/synthetic/runs")
    def get_synthetic_runs() -> list[dict[str, Any]]:
        """List past synthetic generation runs from the temp directory."""
        base = Path(tempfile.gettempdir()) / "lmv_synthetic"
        if not base.is_dir():
            return []
        runs = []
        for d in sorted(base.iterdir(), reverse=True):
            if not d.is_dir():
                continue
            suite_file = d / "suite.json"
            pipeline_count = 0
            if suite_file.exists():
                try:
                    with open(suite_file, encoding="utf-8") as f:
                        data = _json.load(f)
                    pipeline_count = len(data.get("pipelines", []))
                except Exception:
                    pass
            # Count pipeline subfolders
            subfolders = [p for p in d.iterdir() if p.is_dir()]
            runs.append({
                "path": str(d),
                "name": d.name,
                "pipeline_count": pipeline_count,
                "subfolder_count": len(subfolders),
                "has_suite": suite_file.exists(),
            })
        return runs

    @app.get("/api/synthetic/templates")
    def get_synthetic_templates() -> list[dict[str, str]]:
        from lakeflow_migration_validator.synthetic.prompt_templates import list_templates
        return list_templates()

    @app.post("/api/synthetic/resolve-template")
    def post_resolve_template(request: dict[str, Any]) -> dict[str, str]:
        from lakeflow_migration_validator.synthetic.prompt_templates import resolve_template
        base = resolve_template(
            request.get("preset", "complex_expressions"),
            count=request.get("count", 10),
            max_activities=request.get("max_activities", 10),
        )
        # Append extra params so the spec reflects all user choices
        extras: list[str] = []
        difficulty = request.get("difficulty")
        if difficulty and difficulty != "medium":
            extras.append(f"Target difficulty: {difficulty}.")
        if request.get("generate_test_data"):
            extras.append("Also generate parallel test data (CSV source files + SQL seed scripts) for each pipeline.")
        if extras:
            base += "\n\n" + " ".join(extras)
        return {"prompt": base}

    @app.post("/api/synthetic/spec")
    def post_synthetic_spec(request: dict[str, Any]) -> dict[str, Any]:
        """Generate an editable spec from prompt + options, without generating pipelines."""
        req_count = int(request.get("count", 10))
        req_mode = request.get("mode", "template")
        req_preset = request.get("preset")
        req_prompt = request.get("custom_prompt", "")
        req_difficulty = request.get("difficulty", "medium")
        req_max_activities = int(request.get("max_activities", 20))

        if req_mode in ("llm", "custom") and judge_provider is not None:
            from lakeflow_migration_validator.synthetic.agent_generator import (
                AgentPipelineGenerator,
                GenerationConfig,
            )
            weak_spots = _PRESET_WEAK_SPOTS.get(req_preset or "", ("nested_expressions",))
            config = GenerationConfig(
                target_weak_spots=weak_spots,
                extra_instructions=req_prompt,
            )
            agent = AgentPipelineGenerator(judge_provider=judge_provider)
            plan = agent._create_plan(req_count, config)
            return {
                "count": plan.count,
                "pipelines": [
                    {
                        "name": s.name,
                        "activity_count": s.activity_count,
                        "activity_types": list(s.activity_types),
                        "stress_area": s.stress_area,
                        "expression_complexity": s.expression_complexity,
                        "parameters": list(s.parameters),
                    }
                    for s in plan.specs
                ],
            }
        # Template / fallback: deterministic spec
        from lakeflow_migration_validator.synthetic.pipeline_generator import _DEFAULT_ACTIVITY_TYPES
        specs = []
        for i in range(req_count):
            specs.append({
                "name": f"synthetic_pipeline_{i:03d}",
                "activity_count": 1 + (i % req_max_activities),
                "activity_types": list(_DEFAULT_ACTIVITY_TYPES),
                "stress_area": req_difficulty,
                "expression_complexity": "mixed",
                "parameters": ["param1", "param2"],
            })
        return {"count": req_count, "pipelines": specs}

    _PRESET_WEAK_SPOTS: dict[str, tuple[str, ...]] = {
        "complex_expressions": ("nested_expressions", "math_on_params"),
        "deep_nesting": ("deep_nesting", "complex_conditions"),
        "activity_mix": ("activity_output_chaining", "unsupported_types"),
        "math_on_params": ("math_on_params",),
        "unsupported_types": ("unsupported_types",),
        "pipeline_invocation": ("activity_output_chaining", "deep_nesting"),
        "full_coverage": ("nested_expressions", "math_on_params", "deep_nesting", "complex_conditions"),
    }

    def _persist_suite(suite: GroundTruthSuite, output_path: str | None = None) -> str:
        """Persist suite to disk with per-pipeline subfolders.

        Structure::

            {batch_dir}/
                suite.json                          # full suite (for batch validation)
                000_pipeline_name/
                    adf_pipeline.json               # raw ADF JSON
                001_other_pipeline/
                    adf_pipeline.json
        """
        if output_path:
            suite.to_json(output_path)
            return output_path
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        batch_dir = Path(tempfile.gettempdir()) / "lmv_synthetic" / ts
        batch_dir.mkdir(parents=True, exist_ok=True)

        # Full suite JSON (loadable by batch validation)
        suite.to_json(str(batch_dir / "suite.json"))

        # Individual pipeline subfolders
        for i, pipeline in enumerate(suite.pipelines):
            name = pipeline.adf_json.get("name", f"pipeline_{i:03d}")
            safe = f"{i:03d}_{name.replace('/', '_').replace(' ', '_')[:60]}"
            pipe_dir = batch_dir / safe
            pipe_dir.mkdir(parents=True, exist_ok=True)
            with open(pipe_dir / "adf_pipeline.json", "w", encoding="utf-8") as fh:
                _json.dump(pipeline.adf_json, fh, indent=2)

        return str(batch_dir)

    def _build_result(
        suite: GroundTruthSuite,
        persist_path: str,
        fallback_note: str | None,
        generate_test_data: bool,
    ) -> dict[str, Any]:
        pipelines_payload = [
            {
                "name": p.adf_json.get("name", "<unknown>"),
                "adf_json": p.adf_json,
                "description": p.description,
                "difficulty": p.difficulty,
            }
            for p in suite.pipelines
        ]
        result: dict[str, Any] = {
            "count": len(suite.pipelines),
            "pipelines": pipelines_payload,
            "output_path": persist_path,
        }
        if fallback_note:
            result["fallback_note"] = fallback_note
        if generate_test_data:
            from lakeflow_migration_validator.synthetic.test_data_generator import TestDataGenerator
            gen = TestDataGenerator()
            test_data = gen.generate_for_suite([p.adf_json for p in suite.pipelines])
            result["test_data"] = [td.to_dict() for td in test_data]
        return result

    def _generate_stream(request: SyntheticGenerateRequest):
        """Yield NDJSON lines with per-pipeline progress."""
        mode = request.mode
        fallback_note: str | None = None

        if mode in ("llm", "custom") and judge_provider is None:
            fallback_note = f"Mode '{mode}' requires an LLM provider; using 'template' mode."
            mode = "template"

        suite = None

        if mode in ("llm", "custom") and judge_provider is not None:
            try:
                from lakeflow_migration_validator.synthetic.agent_generator import (
                    AgentPipelineGenerator,
                    GenerationConfig,
                )
                weak_spots = _PRESET_WEAK_SPOTS.get(request.preset or "", ("nested_expressions",))
                config = GenerationConfig(
                    target_weak_spots=weak_spots,
                    extra_instructions=request.custom_prompt or "",
                )
                agent_gen = AgentPipelineGenerator(judge_provider=judge_provider)
                # Build pre-built plan from spec if provided
                pre_plan = None
                if request.spec and "pipelines" in request.spec:
                    from lakeflow_migration_validator.synthetic.agent_generator import (
                        GenerationPlan,
                        PipelineSpec,
                    )
                    pre_specs = []
                    for item in request.spec["pipelines"]:
                        pre_specs.append(PipelineSpec(
                            name=item.get("name", f"pipeline_{len(pre_specs):03d}"),
                            activity_count=int(item.get("activity_count", 5)),
                            activity_types=tuple(item.get("activity_types", ("SetVariable", "DatabricksNotebook"))),
                            stress_area=item.get("stress_area", "nested_expressions"),
                            expression_complexity=item.get("expression_complexity", "nested"),
                            parameters=tuple(item.get("parameters", ("env",))),
                        ))
                    pre_plan = GenerationPlan(
                        count=len(pre_specs),
                        specs=tuple(pre_specs),
                        raw_plan=request.spec,
                    )
                collected = []
                for ev in agent_gen.generate_stream(
                    count=request.count, config=config, plan=pre_plan,
                ):
                    if ev["type"] == "plan":
                        plan = ev["plan"]
                        plan_specs = [
                            {"name": s.name, "stress_area": s.stress_area,
                             "activity_count": s.activity_count}
                            for s in plan.specs
                        ]
                        yield _json.dumps({
                            "type": "plan",
                            "count": plan.count,
                            "specs": plan_specs,
                        }) + "\n"
                    elif ev["type"] == "stage":
                        stage_event: dict[str, Any] = {
                            "type": "stage",
                            "pipeline_index": ev["pipeline_index"],
                            "pipeline_name": ev["pipeline_name"],
                            "stage": ev["stage"],
                            "pct": ev.get("pct", 0),
                            "total": ev["total"],
                        }
                        if ev.get("attempt"):
                            stage_event["attempt"] = ev["attempt"]
                            stage_event["max_attempts"] = ev.get("max_attempts", 1)
                        if ev.get("error"):
                            stage_event["error"] = ev["error"]
                        yield _json.dumps(stage_event) + "\n"
                    elif ev["type"] == "pipeline":
                        pipeline = ev.get("pipeline")
                        name = pipeline.adf_json.get("name") if pipeline else ev.get("spec_name")
                        event: dict[str, Any] = {
                            "type": "progress",
                            "completed": ev["completed"],
                            "total": ev["total"],
                            "pipeline_name": name,
                            "ok": pipeline is not None,
                        }
                        if ev.get("error"):
                            event["error"] = ev["error"]
                        yield _json.dumps(event) + "\n"
                        if pipeline:
                            collected.append(pipeline)

                if collected:
                    suite = GroundTruthSuite(pipelines=tuple(collected))
                    if len(collected) < plan.count:
                        fallback_note = f"LLM generated {len(collected)}/{plan.count} pipelines."
                else:
                    fallback_note = "LLM produced no valid pipelines; using template mode."
                    mode = "template"
            except Exception:
                logger.exception("LLM generation failed in streaming path")
                fallback_note = "LLM generation failed; using template mode."
                mode = "template"

        if mode == "template":
            suite = GroundTruthSuite.generate(
                count=request.count,
                difficulty=request.difficulty,
                max_activities=request.max_activities,
                mode="template",
            )
            yield _json.dumps({
                "type": "progress",
                "completed": len(suite.pipelines),
                "total": request.count,
                "pipeline_name": None,
                "ok": True,
            }) + "\n"

        persist_path = _persist_suite(suite, request.output_path)
        result = _build_result(suite, persist_path, fallback_note, request.generate_test_data)
        entity_id = history.log_synthetic(persist_path, result["count"], request.mode, full_result=result)
        result["entity_id"] = entity_id
        yield _json.dumps({"type": "complete", "result": result}) + "\n"

    @app.post("/api/synthetic/generate")
    def post_synthetic_generate(
        request: SyntheticGenerateRequest,
        stream: bool = Query(False),
    ):
        if stream:
            return StreamingResponse(
                _generate_stream(request),
                media_type="application/x-ndjson",
            )
        mode = request.mode
        fallback_note: str | None = None

        if mode in ("llm", "custom") and judge_provider is None:
            fallback_note = f"Mode '{mode}' requires an LLM provider; using 'template' mode."
            mode = "template"

        if mode in ("llm", "custom") and judge_provider is not None:
            try:
                from lakeflow_migration_validator.synthetic.agent_generator import (
                    AgentPipelineGenerator,
                    GenerationConfig,
                )
                weak_spots = _PRESET_WEAK_SPOTS.get(request.preset or "", ("nested_expressions",))
                config = GenerationConfig(
                    target_weak_spots=weak_spots,
                    extra_instructions=request.custom_prompt or "",
                )
                agent_gen = AgentPipelineGenerator(judge_provider=judge_provider)
                pre_plan = None
                if request.spec and "pipelines" in request.spec:
                    from lakeflow_migration_validator.synthetic.agent_generator import (
                        GenerationPlan,
                        PipelineSpec,
                    )
                    pre_specs = []
                    for item in request.spec["pipelines"]:
                        pre_specs.append(PipelineSpec(
                            name=item.get("name", f"pipeline_{len(pre_specs):03d}"),
                            activity_count=int(item.get("activity_count", 5)),
                            activity_types=tuple(item.get("activity_types", ("SetVariable", "DatabricksNotebook"))),
                            stress_area=item.get("stress_area", "nested_expressions"),
                            expression_complexity=item.get("expression_complexity", "nested"),
                            parameters=tuple(item.get("parameters", ("env",))),
                        ))
                    pre_plan = GenerationPlan(
                        count=len(pre_specs),
                        specs=tuple(pre_specs),
                        raw_plan=request.spec,
                    )
                pipelines = [
                    p for ev in agent_gen.generate_stream(count=request.count, config=config, plan=pre_plan)
                    if ev["type"] == "pipeline" and ev.get("pipeline")
                    for p in [ev["pipeline"]]
                ]
                if pipelines:
                    suite = GroundTruthSuite(pipelines=tuple(pipelines))
                    if len(pipelines) < request.count:
                        fallback_note = f"LLM generated {len(pipelines)}/{request.count} pipelines."
                else:
                    fallback_note = "LLM produced no valid pipelines; using template mode."
                    mode = "template"
            except Exception:
                logger.exception("LLM generation failed in non-streaming path")
                fallback_note = "LLM generation failed; using template mode."
                mode = "template"

        if mode == "template":
            suite = GroundTruthSuite.generate(
                count=request.count,
                difficulty=request.difficulty,
                max_activities=request.max_activities,
                mode="template",
            )

        persist_path = _persist_suite(suite, request.output_path)
        result = _build_result(suite, persist_path, fallback_note, request.generate_test_data)
        entity_id = history.log_synthetic(persist_path, len(suite.pipelines), request.mode, full_result=result)
        result["entity_id"] = entity_id
        return result

    @app.post("/api/parallel/run")
    def post_parallel_run(request: ParallelRunRequest) -> dict[str, Any]:
        if parallel_runner is None:
            raise HTTPException(status_code=503, detail="parallel_runner is not configured")
        snapshot = convert(request.snapshot) if request.snapshot is not None else None
        result = parallel_runner.run(
            request.pipeline_name,
            parameters=request.parameters,
            snapshot=snapshot,
        )
        payload = result.to_dict()
        entity_id = history.log_parallel(request.pipeline_name, payload)
        payload["entity_id"] = entity_id
        return payload

    return app


def _resolve_snapshot(
    request: ValidateRequest,
    convert_fn: Callable[[dict], ConversionSnapshot],
) -> ConversionSnapshot:
    if request.snapshot is not None:
        return convert_fn(request.snapshot)
    if request.adf_yaml is not None:
        try:
            import yaml
            parsed = yaml.safe_load(request.adf_yaml)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=422, detail="YAML must parse to an object (dict)")
        return convert_fn(parsed)
    if request.adf_json is not None:
        return convert_fn(request.adf_json)
    raise HTTPException(status_code=422, detail="provide one of: adf_json, adf_yaml, or snapshot")
