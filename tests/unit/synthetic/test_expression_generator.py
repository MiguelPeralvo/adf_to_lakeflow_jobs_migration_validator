"""Unit tests for synthetic expression generation."""

import pytest

from lakeflow_migration_validator.synthetic.expression_generator import ExpressionGenerator


@pytest.mark.parametrize(
    "categories",
    [
        None,
        ["string", "math", "nested"],
    ],
)
def test_generate_returns_requested_count(categories):
    generator = ExpressionGenerator()

    cases = generator.generate(count=12, categories=categories)

    assert len(cases) == 12


def test_generate_only_returns_requested_categories():
    generator = ExpressionGenerator()

    cases = generator.generate(count=18, categories=["string", "logical"])

    assert {case.category for case in cases} == {"string", "logical"}


def test_generate_zero_count_returns_empty_list():
    generator = ExpressionGenerator()

    cases = generator.generate(count=0)

    assert cases == []


def test_generate_is_deterministic_for_same_inputs():
    generator = ExpressionGenerator()

    first = generator.generate(count=20, categories=["math", "collection", "nested"])
    second = generator.generate(count=20, categories=["math", "collection", "nested"])

    assert first == second


def test_unknown_category_raises_value_error():
    generator = ExpressionGenerator()

    with pytest.raises(ValueError, match="Unknown expression categories"):
        generator.generate(count=5, categories=["string", "unknown"])


def test_generated_cases_have_non_empty_fields():
    generator = ExpressionGenerator()

    cases = generator.generate(count=10)

    for case in cases:
        assert case.adf_expression.startswith("@")
        assert case.expected_python
        assert case.category
