"""Template-based ADF expression generation for Week 2 synthetic testing."""

from __future__ import annotations

from dataclasses import dataclass

_CATEGORIES = ("string", "math", "datetime", "logical", "collection", "nested")


@dataclass(frozen=True, slots=True)
class ExpressionTestCase:
    """An ADF expression and its expected Python translation."""

    adf_expression: str
    expected_python: str
    category: str


_TEMPLATES: dict[str, tuple[tuple[str, str], ...]] = {
    "string": (
        ("@concat('hello', 'world')", "'hello' + 'world'"),
        ("@toUpper('abc')", "'abc'.upper()"),
        ("@substring('abcdef', 1, 3)", "'abcdef'[1:4]"),
    ),
    "math": (
        ("@add(1, 2)", "1 + 2"),
        ("@sub(10, 4)", "10 - 4"),
        ("@mul(3, 7)", "3 * 7"),
        ("@div(9, 2)", "9 / 2"),
    ),
    "datetime": (
        (
            "@formatDateTime('2024-01-01T00:00:00Z', 'yyyy-MM-dd')",
            "format_datetime('2024-01-01T00:00:00Z', 'yyyy-MM-dd')",
        ),
        ("@dayOfMonth('2024-01-15T00:00:00Z')", "day_of_month('2024-01-15T00:00:00Z')"),
    ),
    "logical": (
        ("@equals(1, 1)", "1 == 1"),
        ("@and(equals(1, 1), greater(3, 2))", "(1 == 1) and (3 > 2)"),
        ("@or(less(1, 0), equals('x', 'x'))", "(1 < 0) or ('x' == 'x')"),
    ),
    "collection": (
        ("@length(createArray(1, 2, 3))", "len([1, 2, 3])"),
        ("@first(createArray('a', 'b'))", "['a', 'b'][0]"),
        ("@last(createArray('a', 'b'))", "['a', 'b'][-1]"),
    ),
    "nested": (
        ("@concat(toUpper('x'), string(add(1, 2)))", "'x'.upper() + str(1 + 2)"),
        ("@if(equals(mod(5, 2), 1), 'odd', 'even')", "'odd' if ((5 % 2) == 1) else 'even'"),
        ("@string(length(split('a-b-c', '-')))", "str(len('a-b-c'.split('-')))"),
    ),
}


class ExpressionGenerator:
    """Generates deterministic ADF expression test cases by category."""

    def generate(self, count: int = 50, categories: list[str] | None = None) -> list[ExpressionTestCase]:
        """Generate deterministic expression cases.

        Args:
            count: Number of test cases to emit.
            categories: Optional subset of expression categories.
        """
        if count <= 0:
            return []

        selected = categories or list(_CATEGORIES)
        unknown = sorted(set(selected) - set(_CATEGORIES))
        if unknown:
            raise ValueError(f"Unknown expression categories: {unknown}")

        cases: list[ExpressionTestCase] = []
        while len(cases) < count:
            idx = len(cases)
            category = selected[idx % len(selected)]
            templates = _TEMPLATES[category]
            template_idx = (idx // len(selected)) % len(templates)
            adf_expression, expected_python = templates[template_idx]
            cases.append(
                ExpressionTestCase(
                    adf_expression=adf_expression,
                    expected_python=expected_python,
                    category=category,
                )
            )

        return cases
