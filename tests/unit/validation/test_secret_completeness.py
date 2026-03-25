"""TDD tests for the secret completeness dimension."""

import pytest

from lakeflow_migration_validator.dimensions.secret_completeness import compute_secret_completeness
from tests.unit.validation.conftest import make_notebook, make_secret, make_snapshot


def test_all_secrets_defined_scores_1():
    """Every dbutils.secrets.get reference has a matching SecretInstruction."""
    snapshot = make_snapshot(
        notebooks=[
            make_notebook(
                content=(
                    'dbutils.secrets.get(scope="scope1", key="key1")\n'
                    'dbutils.secrets.get(scope="scope2", key="key2")'
                )
            )
        ],
        secrets=[make_secret("scope1", "key1"), make_secret("scope2", "key2")],
    )

    score, details = compute_secret_completeness(snapshot)

    assert score == 1.0
    assert details["missing"] == []


def test_missing_secret_lowers_score():
    """A notebook references (scope, key) not in secrets -> score < 1.0."""
    snapshot = make_snapshot(
        notebooks=[
            make_notebook(
                content=(
                    'dbutils.secrets.get(scope="scope1", key="key1")\n'
                    'dbutils.secrets.get(scope="scope2", key="key2")'
                )
            )
        ],
        secrets=[make_secret("scope1", "key1")],
    )

    score, details = compute_secret_completeness(snapshot)

    assert score == pytest.approx(0.5)
    assert details["missing"] == ["('scope2', 'key2')"]


def test_no_secret_references_scores_1():
    """A notebook with no dbutils.secrets.get calls scores 1.0."""
    snapshot = make_snapshot(
        notebooks=[make_notebook(content="x = 1")],
        secrets=[make_secret("scope1", "key1")],
    )

    score, details = compute_secret_completeness(snapshot)

    assert score == 1.0
    assert details == {"defined": [], "referenced": [], "missing": []}


def test_details_list_missing_scope_key_pairs():
    """The details dict lists the missing (scope, key) pairs."""
    snapshot = make_snapshot(
        notebooks=[make_notebook(content='dbutils.secrets.get(scope="sc", key="k")')],
        secrets=[],
    )

    _score, details = compute_secret_completeness(snapshot)

    assert details["missing"] == ["('sc', 'k')"]
