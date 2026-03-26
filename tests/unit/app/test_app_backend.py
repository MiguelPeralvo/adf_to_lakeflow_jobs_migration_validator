"""Smoke tests for the Databricks app backend wrapper."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.lmv.backend.main import create_app
from tests.unit.validation.conftest import make_notebook, make_snapshot, make_task


def test_app_backend_healthz_route():
    client = TestClient(create_app(convert_fn=lambda _adf: make_snapshot()))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_backend_wraps_core_validation_routes():
    client = TestClient(
        create_app(
            convert_fn=lambda _adf: make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()])
        )
    )

    response = client.post("/api/validate", json={"adf_json": {"name": "pipeline_a"}})

    assert response.status_code == 200
    payload = response.json()
    assert "score" in payload
    assert "dimensions" in payload


def test_app_backend_exposes_parallel_route_contract():
    client = TestClient(create_app(convert_fn=lambda _adf: make_snapshot()))

    response = client.post("/api/parallel/run", json={"pipeline_name": "pipeline_a"})

    assert response.status_code == 503
