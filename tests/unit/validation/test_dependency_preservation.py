"""TDD tests for the dependency preservation dimension."""

import pytest


def test_all_deps_preserved_scores_1():
    """Every ADF depends_on entry has a corresponding IR Dependency."""
    pytest.skip("TDD: implement dimension first")


def test_missing_dep_lowers_score():
    """An ADF depends_on entry with no matching IR task_key -> score < 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_no_deps_scores_1():
    """A pipeline with no depends_on entries scores 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_details_list_missing_deps():
    """The details dict lists which activities lost which dependencies."""
    pytest.skip("TDD: implement dimension first")
