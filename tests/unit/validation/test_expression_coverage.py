"""TDD tests for the expression coverage dimension."""

import pytest


def test_all_expressions_resolved_scores_1():
    """A pipeline with only SetVariableActivity tasks (all resolved) scores 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_unsupported_expressions_lower_score():
    """not_translatable entries mentioning 'expression' reduce the score."""
    pytest.skip("TDD: implement dimension first")


def test_no_expressions_scores_1():
    """A pipeline with no expression properties scores 1.0."""
    pytest.skip("TDD: implement dimension first")
