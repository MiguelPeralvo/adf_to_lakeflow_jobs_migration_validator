"""TDD tests for the activity coverage dimension."""

import pytest


def test_all_activities_translated_returns_1():
    """A workflow with no placeholder activities scores 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_all_activities_placeholder_returns_0():
    """A workflow where every task points to /UNSUPPORTED_ADF_ACTIVITY scores 0.0."""
    pytest.skip("TDD: implement dimension first")


def test_mixed_activities_returns_fraction():
    """3 real + 1 placeholder = 0.75."""
    pytest.skip("TDD: implement dimension first")


def test_empty_workflow_returns_1():
    """A workflow with no activities scores 1.0 (vacuously true)."""
    pytest.skip("TDD: implement dimension first")


def test_details_list_placeholder_task_keys():
    """The details dict lists the task_keys of placeholder activities."""
    pytest.skip("TDD: implement dimension first")
