"""Single-process Databricks App backend.

Serves three surfaces from one ``uvicorn`` process:

*  ``/api/*``  — REST API (FastAPI)
*  ``/mcp``    — MCP SSE transport for Claude / agentic workflows
*  ``/``       — React SPA (pre-built static files from ``frontend/dist/``)

Environment variables configure optional providers. The app degrades
gracefully — ``/api/validate`` always works; endpoints that need a provider
return 503 when the provider is not configured.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

# Load .env from repo root (gitignored) for local dev; no-op in Databricks Apps
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:
    pass

import sys
import types as _types

# ---------------------------------------------------------------------------
# Mock azure + autopep8 — only needed for local dev when these aren't
# installed.  The mocks are harmless: wkmigrate's JSON-based translation
# path never calls into the real Azure SDK.
# ---------------------------------------------------------------------------
def _ensure_azure_mocks():
    if "azure" in sys.modules:
        return
    _az = _types.ModuleType("azure")
    for _sub in (
        "identity", "common", "common.credentials", "mgmt",
        "mgmt.datafactory", "mgmt.datafactory.models", "mgmt.core",
        "core", "core.exceptions",
    ):
        _mod = _types.ModuleType(f"azure.{_sub}")
        sys.modules[f"azure.{_sub}"] = _mod
        _parts = _sub.split(".")
        _parent = _az
        for _p in _parts[:-1]:
            _parent = getattr(_parent, _p)
        setattr(_parent, _parts[-1], _mod)
    sys.modules["azure"] = _az
    sys.modules["azure.identity"].ClientSecretCredential = type("ClientSecretCredential", (), {})
    sys.modules["azure.mgmt.datafactory"].DataFactoryManagementClient = type("DataFactoryManagementClient", (), {})

    if "autopep8" not in sys.modules:
        _ap = _types.ModuleType("autopep8")
        _ap.fix_code = lambda code, **kw: code
        sys.modules["autopep8"] = _ap

_ensure_azure_mocks()

# Add wkmigrate alpha src to path if available locally
_WKMIGRATE_LOCAL = Path(__file__).resolve().parents[4] / "wkmigrate-wip" / "src"
if _WKMIGRATE_LOCAL.is_dir() and str(_WKMIGRATE_LOCAL) not in sys.path:
    sys.path.insert(0, str(_WKMIGRATE_LOCAL))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from lakeflow_migration_validator.api import create_app as create_service_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider factories — read environment, build what's available
# ---------------------------------------------------------------------------

def _normalize_host(host: str) -> str:
    """Extract scheme + authority from a Databricks workspace URL.

    Handles URLs like ``https://adb-123.azuredatabricks.net/compute/apps?o=123``
    by stripping the path and query components.
    """
    from urllib.parse import urlparse
    parsed = urlparse(host)
    return f"{parsed.scheme}://{parsed.netloc}"


def _build_judge_provider():
    """Build FMAPIJudgeProvider if DATABRICKS_HOST is set."""
    host = os.environ.get("DATABRICKS_HOST")
    if not host:
        logger.info("DATABRICKS_HOST not set — LLM judge and expression validation disabled")
        return None
    try:
        from lakeflow_migration_validator.providers.fmapi import FMAPIJudgeProvider

        base = _normalize_host(host)
        token = os.environ.get("DATABRICKS_TOKEN")
        logger.info("Building FMAPIJudgeProvider with endpoint %s/serving-endpoints", base)
        return FMAPIJudgeProvider(
            endpoint=f"{base}/serving-endpoints",
            token=token,
            timeout_seconds=60,
        )
    except Exception as exc:
        logger.warning("Failed to build FMAPIJudgeProvider: %s", exc)
        return None


def _build_harness_runner(judge_provider=None):
    """Build HarnessRunner if ADF credentials are set."""
    required = ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
                "AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", "AZURE_FACTORY_NAME"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        logger.info("ADF credentials not fully set (missing %s) — harness disabled", missing)
        return None
    try:
        from lakeflow_migration_validator.harness import ADFConnector, HarnessRunner
        from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate

        connector = ADFConnector.from_credentials(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"],
            subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
            resource_group=os.environ["AZURE_RESOURCE_GROUP"],
            factory_name=os.environ["AZURE_FACTORY_NAME"],
        )
        return HarnessRunner(
            adf_connector=connector,
            wkmigrate_adapter=from_wkmigrate,
            judge_provider=judge_provider,
            max_iterations=1,
        )
    except (NotImplementedError, ImportError) as exc:
        logger.info("ADFConnector not available (%s) — harness disabled", exc)
        return None
    except Exception as exc:
        logger.warning("Failed to build HarnessRunner: %s", exc)
        return None


def _build_parallel_runner():
    """Parallel runner requires custom wiring — return None by default."""
    return None


def _build_convert_fn():
    """Build a convert_fn that runs wkmigrate translation on ADF JSON.

    Returns a function ``(dict) -> ConversionSnapshot`` that:
    1. If the payload is already a snapshot (has ``tasks``+``notebooks``), deserializes it
    2. Otherwise, translates the ADF JSON through wkmigrate (with camelCase
       normalization via JsonDefinitionStore) and returns a real snapshot
    """
    try:
        from wkmigrate.definition_stores.json_definition_store import JsonDefinitionStore
        from wkmigrate.preparers.preparer import prepare_workflow
        from lakeflow_migration_validator.adapters.wkmigrate_adapter import from_wkmigrate
        from lakeflow_migration_validator.serialization import snapshot_from_dict

        def convert(payload: dict):
            # Already a snapshot?
            if "tasks" in payload and "notebooks" in payload:
                return snapshot_from_dict(payload)
            # Pre-wrapped with expected_snapshot?
            if "expected_snapshot" in payload and isinstance(payload.get("expected_snapshot"), dict):
                return snapshot_from_dict(payload["expected_snapshot"])
            # Run wkmigrate translation via JsonDefinitionStore (handles camelCase normalization)
            # Write JSON to temp file, load through store, prepare, adapt
            import json as _json
            import tempfile
            name = payload.get("name", "pipeline")
            with tempfile.TemporaryDirectory() as tmpdir:
                pipelines_dir = Path(tmpdir) / "pipelines"
                pipelines_dir.mkdir()
                (pipelines_dir / f"{name}.json").write_text(_json.dumps(payload))
                store = JsonDefinitionStore(source_directory=tmpdir)
                pipeline_ir = store.load(name)
                prepared = prepare_workflow(pipeline_ir)
                return from_wkmigrate(payload, prepared)

        logger.info("wkmigrate converter available — validation will run full ADF→Databricks translation")
        return convert
    except (ImportError, Exception) as exc:
        logger.info("wkmigrate not available (%s) — validation will use passthrough snapshots", exc)
        return None


# ---------------------------------------------------------------------------
# MCP SSE mount
# ---------------------------------------------------------------------------

def _mount_mcp(app: FastAPI, judge_provider=None, convert_fn=None):
    """Mount MCP SSE transport at /mcp if the mcp extra is installed."""
    try:
        from lakeflow_migration_validator.mcp_server import create_mcp_server

        mcp = create_mcp_server(
            convert_fn=convert_fn,
            judge_provider=judge_provider,
        )
        # FastMCP exposes an ASGI app via .sse_app() for SSE transport
        if hasattr(mcp, "sse_app"):
            app.mount("/mcp", mcp.sse_app())
            logger.info("MCP SSE transport mounted at /mcp")
        else:
            logger.info("MCP server created but no SSE transport available")
    except (ImportError, RuntimeError) as exc:
        logger.info("MCP not mounted: %s", exc)


# ---------------------------------------------------------------------------
# Static files mount
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _mount_frontend(app: FastAPI):
    """Serve the pre-built React SPA from frontend/dist/."""
    if _FRONTEND_DIST.is_dir() and (_FRONTEND_DIST / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
        logger.info("Frontend served from %s", _FRONTEND_DIST)
    else:
        logger.warning("Frontend dist not found at %s — UI will not be available", _FRONTEND_DIST)

        @app.get("/")
        def _no_frontend():
            return {
                "message": "LMV API is running. Frontend not built.",
                "hint": "Run 'cd apps/lmv/frontend && npm run build' to build the UI.",
                "api_docs": "/api/docs",
            }


# ---------------------------------------------------------------------------
# App assembly
# ---------------------------------------------------------------------------

_WKMIGRATE_CACHE = Path(tempfile.gettempdir()) / "lmv_wkmigrate_cache"


def _hot_swap_wkmigrate(repo_url: str, branch: str) -> str:
    """Clone repo, checkout branch, pip install -e, reload modules.

    Returns a status message. Raises on failure.
    """
    import importlib
    import subprocess
    import sys

    parts = repo_url.rstrip("/").split("/")
    owner, repo = parts[-2], parts[-1]
    clone_dir = _WKMIGRATE_CACHE / f"{owner}__{repo}"

    # Clone or fetch
    if (clone_dir / ".git").is_dir():
        logger.info("Fetching %s/%s...", owner, repo)
        subprocess.run(["git", "fetch", "--all", "--prune"], cwd=clone_dir, check=True,
                       capture_output=True, timeout=60)
    else:
        clone_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Cloning %s/%s...", owner, repo)
        subprocess.run(
            ["git", "clone", "--no-checkout", repo_url, str(clone_dir)],
            check=True, capture_output=True, timeout=120,
        )

    # Checkout branch
    logger.info("Checking out %s...", branch)
    subprocess.run(["git", "checkout", branch], cwd=clone_dir, check=True,
                   capture_output=True, timeout=30)
    subprocess.run(["git", "pull", "--ff-only", "origin", branch], cwd=clone_dir,
                   capture_output=True, timeout=60)

    # Install in dev mode
    logger.info("Installing wkmigrate from %s@%s...", owner, branch)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(clone_dir), "--quiet", "--no-deps"],
        check=True, capture_output=True, timeout=120,
    )

    # Reload modules so new code takes effect
    mods_to_reload = sorted(k for k in sys.modules if k.startswith("wkmigrate"))
    for mod_name in mods_to_reload:
        try:
            importlib.reload(sys.modules[mod_name])
        except Exception:
            pass  # some submodules may fail on reload; that's OK

    return f"Switched to {owner}/{repo}@{branch} ({len(mods_to_reload)} modules reloaded)"


def create_app() -> FastAPI:
    """Assemble the complete Databricks App."""
    root = FastAPI(
        title="Lakeflow Migration Validator",
        version="0.1.0",
        description="ADF-to-Databricks conversion validation — App + API + MCP",
    )

    # Health check (always available, not under /api)
    @root.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Build providers from environment
    judge = _build_judge_provider()
    harness = _build_harness_runner(judge_provider=judge)
    parallel = _build_parallel_runner()

    # Mutable convert_fn wrapper — allows hot-swapping wkmigrate at runtime
    convert_holder: dict[str, Any] = {"fn": _build_convert_fn()}

    def convert_proxy(payload: dict) -> Any:
        fn = convert_holder["fn"]
        if fn is None:
            from lakeflow_migration_validator.serialization import snapshot_from_adf_payload
            return snapshot_from_adf_payload(payload)
        return fn(payload)

    # Include the REST API routes directly (they're already prefixed with /api/)
    service_app = create_service_app(
        convert_fn=convert_proxy,
        judge_provider=judge,
        harness_runner=harness,
        parallel_runner=parallel,
    )
    root.router.include_router(service_app.router)

    # Hot-swap endpoint — apply repo/branch change without restart
    @root.post("/api/config/wkmigrate/apply")
    def apply_wkmigrate_config(request: dict[str, Any]) -> dict[str, Any]:
        """Clone, install, and reload a wkmigrate repo+branch at runtime."""
        repo_url = request.get("repo_url", "")
        branch = request.get("branch", "")
        if not repo_url or not branch:
            raise HTTPException(status_code=422, detail="repo_url and branch are required")
        try:
            msg = _hot_swap_wkmigrate(repo_url, branch)
            convert_holder["fn"] = _build_convert_fn()
            return {"status": "ok", "message": msg}
        except Exception as exc:
            logger.exception("Failed to hot-swap wkmigrate")
            raise HTTPException(status_code=500, detail=f"Hot-swap failed: {exc}") from exc

    # Mount MCP SSE at /mcp
    _mount_mcp(root, judge_provider=judge, convert_fn=convert_proxy)

    # Serve frontend static files (catch-all, must be last)
    _mount_frontend(root)

    capabilities = []
    if judge:
        capabilities.append("judge")
    if harness:
        capabilities.append("harness")
    if parallel:
        capabilities.append("parallel")
    logger.info(
        "LMV app ready — capabilities: %s",
        capabilities or ["validate-only (no providers configured)"],
    )

    return root


app = create_app()
