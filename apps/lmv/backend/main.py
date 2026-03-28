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
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from lakeflow_migration_validator.api import create_app as create_service_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider factories — read environment, build what's available
# ---------------------------------------------------------------------------

def _build_judge_provider():
    """Build FMAPIJudgeProvider if DATABRICKS_HOST is set."""
    host = os.environ.get("DATABRICKS_HOST")
    if not host:
        logger.info("DATABRICKS_HOST not set — LLM judge and expression validation disabled")
        return None
    try:
        from lakeflow_migration_validator.providers.fmapi import FMAPIJudgeProvider

        token = os.environ.get("DATABRICKS_TOKEN")
        return FMAPIJudgeProvider(
            endpoint=f"{host.rstrip('/')}/serving-endpoints",
            token=token,
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

    # Include the REST API routes directly (they're already prefixed with /api/)
    service_app = create_service_app(
        judge_provider=judge,
        harness_runner=harness,
        parallel_runner=parallel,
    )
    root.router.include_router(service_app.router)

    # Mount MCP SSE at /mcp
    _mount_mcp(root, judge_provider=judge)

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
