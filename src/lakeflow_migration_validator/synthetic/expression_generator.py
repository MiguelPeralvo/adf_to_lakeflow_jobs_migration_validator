"""Template-based ADF expression generation for Week 2 synthetic testing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

_CATEGORIES = ("string", "math", "datetime", "logical", "collection", "nested")


@dataclass(frozen=True, slots=True)
class ExpressionTestCase:
    """An ADF expression and its expected Python translation."""

    adf_expression: str
    expected_python: str
    category: str


_TEMPLATES: dict[str, tuple[tuple[str, str], ...]] = {
    "string": (
        ("@concat('hello', 'world')", "str('hello') + str('world')"),
        ("@replace('abc', 'a', 'z')", "str('abc').replace('a', 'z')"),
        ("@toUpper('abc')", "str('abc').upper()"),
        ("@toLower('ABC')", "str('ABC').lower()"),
        ("@trim('  hi  ')", "str('  hi  ').strip()"),
        ("@substring('abcdef', 1, 3)", "str('abcdef')[1:1 + 3]"),
        ("@indexOf('abcd', 'bc')", "str('abcd').find('bc')"),
        ("@startsWith('abcd', 'ab')", "str('abcd').startswith('ab')"),
        ("@endsWith('abcd', 'cd')", "str('abcd').endswith('cd')"),
        ("@contains('abcd', 'bc')", "('bc' in str('abcd'))"),
    ),
    "math": (
        ("@add(1, 2)", "(1 + 2)"),
        ("@sub(10, 4)", "(10 - 4)"),
        ("@mul(3, 7)", "(3 * 7)"),
        ("@div(9, 2)", "int(9 / 2)"),
        ("@mod(9, 2)", "(9 % 2)"),
        ("@int('42')", "int('42')"),
        ("@float('3.14')", "float('3.14')"),
    ),
    "datetime": (
        (
            "@formatDateTime('2024-01-01T00:00:00Z', 'yyyy-MM-dd')",
            "_wkmigrate_format_datetime('2024-01-01T00:00:00Z', 'yyyy-MM-dd')",
        ),
        ("@utcNow()", "_wkmigrate_utc_now()"),
    ),
    "logical": (
        ("@equals(1, 1)", "(1 == 1)"),
        ("@greater(3, 2)", "(3 > 2)"),
        ("@less(2, 3)", "(2 < 3)"),
        ("@and(equals(1, 1), greater(3, 2))", "((1 == 1) and (3 > 2))"),
        ("@or(less(1, 0), equals('x', 'x'))", "((1 < 0) or ('x' == 'x'))"),
        ("@not(false)", "(not False)"),
        ("@bool(1)", "bool(1)"),
        ("@if(equals(1, 1), 'yes', 'no')", "('yes' if (1 == 1) else 'no')"),
    ),
    "collection": (
        ("@length(createArray(1, 2, 3))", "len([1, 2, 3])"),
        ("@first(createArray('a', 'b'))", "(['a', 'b'])[0]"),
        ("@last(createArray('a', 'b'))", "(['a', 'b'])[-1]"),
        ("@coalesce(null, 'x')", "next((v for v in [None, 'x'] if v is not None), None)"),
        ("@empty(createArray())", "(len([]) == 0)"),
        ("@string(42)", "str(42)"),
    ),
    "nested": (
        ("@concat(toUpper('x'), string(add(1, 2)))", "str(str('x').upper()) + str(str((1 + 2)))"),
        ("@if(equals(mod(5, 2), 1), 'odd', 'even')", "('odd' if ((5 % 2) == 1) else 'even')"),
        ("@string(length(split('a-b-c', '-')))", "str(len(str('a-b-c').split('-')))"),
    ),
}


def _wkmigrate_utc_now() -> datetime:
    """Mirror wkmigrate's inline datetime helper for utcNow()."""
    return datetime.now(timezone.utc)


def _wkmigrate_format_datetime(dt: datetime | str, adf_format: str) -> str:
    """Minimal formatter compatible with common ADF tokens used in synthetic tests."""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    format_mapping = {
        "yyyy": "%Y",
        "MM": "%m",
        "dd": "%d",
        "HH": "%H",
        "mm": "%M",
        "ss": "%S",
    }
    python_format = adf_format
    for adf_token, py_token in format_mapping.items():
        python_format = python_format.replace(adf_token, py_token)
    return dt.strftime(python_format)


class ExpressionGenerator:
    """Generates deterministic ADF expression test cases by category."""

    def generate(self, count: int = 50, categories: list[str] | None = None) -> list[ExpressionTestCase]:
        """Generate deterministic expression cases.

        Args:
            count: Number of test cases to emit.
            categories: Optional subset of expression categories.
        """
        if count < 0:
            raise ValueError("count must be >= 0")
        if count == 0:
            return []

        selected = list(_CATEGORIES) if categories is None else categories
        if not selected:
            return []
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
