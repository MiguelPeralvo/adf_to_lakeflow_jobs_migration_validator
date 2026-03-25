"""TDD tests for the secret completeness dimension."""

import pytest


def test_all_secrets_defined_scores_1():
    """Every dbutils.secrets.get reference has a matching SecretInstruction."""
    pytest.skip("TDD: implement dimension first")


def test_missing_secret_lowers_score():
    """A notebook references (scope, key) not in secrets -> score < 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_no_secret_references_scores_1():
    """A notebook with no dbutils.secrets.get calls scores 1.0."""
    pytest.skip("TDD: implement dimension first")


def test_details_list_missing_scope_key_pairs():
    """The details dict lists the missing (scope, key) pairs."""
    pytest.skip("TDD: implement dimension first")
