"""Unit tests for the FastAPI REST surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lakeflow_migration_validator.api import create_app
from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.harness.harness_runner import HarnessResult
from lakeflow_migration_validator.synthetic.ground_truth import GroundTruthSuite
from lakeflow_migration_validator import evaluate
from tests.unit.validation.conftest import make_notebook, make_snapshot, make_task


def test_post_validate_returns_scorecard():
    """POST /api/validate with ADF JSON returns a scorecard response."""

    def convert_fn(_adf_json: dict) -> ConversionSnapshot:
        return make_snapshot(tasks=[make_task("task_a")], notebooks=[make_notebook()])

    client = TestClient(create_app(convert_fn=convert_fn))

    response = client.post("/api/validate", json={"adf_json": {"name": "pipeline_a"}})

    assert response.status_code == 200
    payload = response.json()
    assert "score" in payload
    assert "label" in payload
    assert "dimensions" in payload


def test_post_validate_invalid_json_returns_422():
    """POST /api/validate with invalid JSON returns HTTP 422."""

    client = TestClient(create_app(convert_fn=lambda _adf: make_snapshot()))

    response = client.post(
        "/api/validate",
        data="{this-is-not-json}",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_post_validate_expression_returns_judge_result():
    """POST /api/validate/expression returns score + reasoning."""

    class _Provider:
        def judge(self, _prompt: str, model: str | None = None):
            return {"score": 0.82, "reasoning": f"Equivalent ({model})"}

    client = TestClient(create_app(convert_fn=lambda _adf: make_snapshot(), judge_provider=_Provider()))

    response = client.post(
        "/api/validate/expression",
        json={"adf_expression": "@add(1,2)", "python_code": "(1 + 2)"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["score"] == 0.82
    assert "Equivalent" in payload["reasoning"]


def test_get_history_returns_past_scorecards():
    """GET /api/history/{pipeline_name} returns a list of past scorecards."""

    def convert_fn(_adf_json: dict) -> ConversionSnapshot:
        return make_snapshot(tasks=[make_task("task_a")], notebooks=[make_notebook()])

    client = TestClient(create_app(convert_fn=convert_fn))

    client.post("/api/validate", json={"adf_json": {"name": "pipeline_a"}})
    client.post("/api/validate", json={"adf_json": {"name": "pipeline_a"}})

    response = client.get("/api/history/pipeline_a")

    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 2
    assert all("scorecard" in entry for entry in entries)


def test_post_validate_batch_returns_report(tmp_path):
    """POST /api/validate/batch with golden set returns a Report."""

    suite = GroundTruthSuite.generate(count=3, difficulty="simple")
    path = tmp_path / "pipelines.json"
    suite.to_json(str(path))

    by_name = {
        pipeline.adf_json["name"]: pipeline.expected_snapshot
        for pipeline in suite.pipelines
    }

    def convert_fn(adf_json: dict) -> ConversionSnapshot:
        return by_name[adf_json["name"]]

    client = TestClient(create_app(convert_fn=convert_fn))

    response = client.post(
        "/api/validate/batch",
        json={"pipelines_path": str(path), "threshold": 90.0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert "mean_score" in payload
    assert "cases" in payload


def test_post_harness_run_returns_result():
    class _Runner:
        def run(self, pipeline_name: str) -> HarnessResult:
            snapshot = make_snapshot(tasks=[make_task("a")], notebooks=[make_notebook()])
            scorecard = evaluate(snapshot)
            return HarnessResult(
                pipeline_name=pipeline_name,
                scorecard=scorecard,
                snapshot=snapshot,
                fix_suggestions=({"dimension": "activity_coverage", "suggestion": "replace placeholder"},),
                iterations=2,
            )

    client = TestClient(create_app(convert_fn=lambda _adf: make_snapshot(), harness_runner=_Runner()))

    response = client.post("/api/harness/run", json={"pipeline_name": "pipeline_a"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["pipeline_name"] == "pipeline_a"
    assert "scorecard" in payload
    assert payload["iterations"] == 2
    assert payload["fix_suggestions"]


def test_post_harness_run_returns_503_when_not_configured():
    client = TestClient(create_app(convert_fn=lambda _adf: make_snapshot()))

    response = client.post("/api/harness/run", json={"pipeline_name": "pipeline_a"})

    assert response.status_code == 503
