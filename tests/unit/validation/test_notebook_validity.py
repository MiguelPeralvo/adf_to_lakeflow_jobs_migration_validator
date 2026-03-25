"""TDD tests for the notebook validity dimension."""

import pytest


def test_valid_notebook_scores_1():
    """A single syntactically valid notebook scores 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_invalid_notebook_scores_0():
    """A single notebook with a SyntaxError scores 0.0."""
    pytest.skip("TDD: implement dimension first")


def test_mixed_notebooks_returns_fraction():
    """2 valid + 1 invalid = 0.667."""
    pytest.skip("TDD: implement dimension first")


def test_no_notebooks_scores_1():
    """A workflow with no notebooks scores 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_details_list_error_file_paths():
    """The details dict lists file_path and error for each invalid notebook."""
    pytest.skip("TDD: implement dimension first")
