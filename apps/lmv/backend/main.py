"""FastAPI app wrapper for Databricks App deployment."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from lakeflow_migration_validator.api import create_app as create_service_app


def create_app(**dependencies: Any) -> FastAPI:
    """Create LMV app backend by wrapping the core service API."""
    app = create_service_app(**dependencies)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
