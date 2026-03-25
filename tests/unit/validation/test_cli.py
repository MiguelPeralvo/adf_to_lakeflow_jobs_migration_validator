"""TDD tests for the Typer CLI surface."""

import pytest


def test_evaluate_writes_scorecard_json(tmp_path):
    """'lmv evaluate --adf-json ... --output ...' writes a valid JSON scorecard."""
    pytest.skip("TDD: implement CLI first")


def test_evaluate_batch_prints_report(capsys):
    """'lmv evaluate-batch --golden-set ...' prints aggregate scores."""
    pytest.skip("TDD: implement CLI first")


def test_regression_check_exits_0_on_pass():
    """'lmv regression-check' exits 0 when no regression detected."""
    pytest.skip("TDD: implement CLI first")


def test_regression_check_exits_1_on_regression():
    """'lmv regression-check' exits 1 when regression detected."""
    pytest.skip("TDD: implement CLI first")
