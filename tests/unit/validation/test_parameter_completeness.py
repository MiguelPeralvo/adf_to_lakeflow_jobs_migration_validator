"""TDD tests for the parameter completeness dimension."""

import pytest


def test_all_params_defined_scores_1():
    """Every dbutils.widgets.get reference has a matching JobParameterDefinition."""
    pytest.skip("TDD: implement dimension first")


def test_missing_param_lowers_score():
    """A notebook references param 'X' but pipeline.parameters has no 'X' -> score < 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_no_widget_references_scores_1():
    """A notebook with no dbutils.widgets.get calls scores 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_details_list_missing_params():
    """The details dict lists the missing parameter names."""
    pytest.skip("TDD: implement dimension first")


def test_multiple_notebooks_aggregate_references():
    """References across all notebooks are collected, not just the first."""
    pytest.skip("TDD: implement dimension first")
