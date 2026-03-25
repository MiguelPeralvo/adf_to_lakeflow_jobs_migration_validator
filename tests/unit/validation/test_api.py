"""TDD tests for the FastAPI REST surface."""

import pytest


def test_post_validate_returns_scorecard():
    """POST /api/validate with ADF JSON returns a scorecard response."""
    pytest.skip("TDD: implement API first")


def test_post_validate_invalid_json_returns_422():
    """POST /api/validate with invalid JSON returns HTTP 422."""
    pytest.skip("TDD: implement API first")


def test_post_validate_expression_returns_judge_result():
    """POST /api/validate/expression returns score + reasoning."""
    pytest.skip("TDD: implement API first")


def test_get_history_returns_past_scorecards():
    """GET /api/history/{pipeline_name} returns a list of past scorecards."""
    pytest.skip("TDD: implement API first")


def test_post_validate_batch_returns_report():
    """POST /api/validate/batch with golden set returns a Report."""
    pytest.skip("TDD: implement API first")
