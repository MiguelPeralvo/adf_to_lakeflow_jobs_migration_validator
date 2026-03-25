"""TDD tests for the top-level evaluate_pipeline function."""

import pytest

from lakeflow_migration_validator import evaluate
from lakeflow_migration_validator.scorecard import Scorecard
from tests.unit.validation.conftest import (
    make_expression,
    make_notebook,
    make_secret,
    make_snapshot,
    make_task,
)


def test_evaluate_returns_scorecard():
    """evaluate_pipeline returns a Scorecard instance."""
    scorecard = evaluate(make_snapshot())
    assert isinstance(scorecard, Scorecard)


def test_evaluate_includes_all_7_dimensions():
    """The scorecard has results for all 7 programmatic dimensions."""
    scorecard = evaluate(make_snapshot())
    assert set(scorecard.results.keys()) == {
        "activity_coverage",
        "expression_coverage",
        "dependency_preservation",
        "notebook_validity",
        "parameter_completeness",
        "secret_completeness",
        "not_translatable_ratio",
    }


def test_evaluate_perfect_pipeline_scores_above_90():
    """A well-translated pipeline (no placeholders, valid notebooks, complete params) scores >= 90."""
    snapshot = make_snapshot(
        tasks=[make_task("a"), make_task("b")],
        notebooks=[
            make_notebook(
                content=(
                    "dbutils.widgets.get('param1')\n"
                    'dbutils.secrets.get(scope="scope1", key="key1")\n'
                    "x = 1"
                )
            )
        ],
        secrets=[make_secret("scope1", "key1")],
        parameters=("param1",),
        dependencies=[],
        total_source_dependencies=0,
        not_translatable=[],
        resolved_expressions=[make_expression()],
    )

    scorecard = evaluate(snapshot)
    assert scorecard.score >= 90.0


def test_evaluate_degraded_pipeline_scores_below_70():
    """A pipeline with mostly placeholders and missing params scores < 70."""
    snapshot = make_snapshot(
        tasks=[make_task("missing1", True), make_task("missing2", True)],
        notebooks=[
            make_notebook(
                content=(
                    "if True print('x')\n"
                    "dbutils.widgets.get('missing_param')\n"
                    'dbutils.secrets.get(scope="missing", key="secret")'
                )
            )
        ],
        secrets=[],
        parameters=(),
        dependencies=[],
        total_source_dependencies=2,
        not_translatable=[
            {"message": "Unsupported expression found"},
            {"message": "Expression parsing failed"},
        ],
        resolved_expressions=[],
    )

    scorecard = evaluate(snapshot)
    assert scorecard.score < 70.0


def test_evaluate_works_with_real_fixtures():
    """Run evaluate_pipeline against existing wkmigrate test fixtures."""
    snapshot = make_snapshot(
        tasks=[make_task("one"), make_task("two", True)],
        notebooks=[make_notebook(content="x = dbutils.widgets.get('p')")],
        parameters=("p",),
    )

    scorecard = evaluate(snapshot)
    as_dict = scorecard.to_dict()
    assert "score" in as_dict
    assert "dimensions" in as_dict
