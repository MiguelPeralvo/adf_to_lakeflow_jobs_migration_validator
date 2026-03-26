"""Unit tests for synthetic expression generation."""

import pytest

from lakeflow_migration_validator.synthetic.expression_generator import (
    ExpressionGenerator,
    _TEMPLATES,
    _wkmigrate_format_datetime,
    _wkmigrate_utc_now,
)

_EVAL_GLOBALS = {
    "__builtins__": {},
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "len": len,
    "next": next,
    "list": list,
    "dict": dict,
    "set": set,
    "None": None,
    "True": True,
    "False": False,
    "_wkmigrate_utc_now": _wkmigrate_utc_now,
    "_wkmigrate_format_datetime": _wkmigrate_format_datetime,
}


def evaluate_expected_python(expected_python: str) -> object:
    """Evaluate trusted synthetic template output (test-only helper)."""
    return eval(expected_python, _EVAL_GLOBALS, {})  # noqa: S307


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


def test_generate_with_explicit_empty_categories_returns_empty_list():
    generator = ExpressionGenerator()

    cases = generator.generate(count=5, categories=[])

    assert cases == []


def test_generate_negative_count_raises_value_error():
    generator = ExpressionGenerator()

    with pytest.raises(ValueError, match="count must be >= 0"):
        generator.generate(count=-1)


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


def test_all_template_expected_python_values_are_valid_eval_expressions():
    generator = ExpressionGenerator()

    all_cases = []
    for category, templates in _TEMPLATES.items():
        all_cases.extend(generator.generate(count=len(templates), categories=[category]))

    for case in all_cases:
        compile(case.expected_python, "<test>", "eval")


def test_all_template_expected_python_values_evaluate_at_runtime():
    generator = ExpressionGenerator()

    all_cases = []
    for category, templates in _TEMPLATES.items():
        all_cases.extend(generator.generate(count=len(templates), categories=[category]))

    for case in all_cases:
        result = evaluate_expected_python(case.expected_python)
        assert result is not None or case.expected_python.endswith("None)")
