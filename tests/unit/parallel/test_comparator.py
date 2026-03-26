"""Unit tests for OutputComparator."""

from __future__ import annotations

from lakeflow_migration_validator.parallel.comparator import OutputComparator, outputs_equivalent


def test_comparator_exact_match_and_stable_ordering():
    comparator = OutputComparator()

    results = comparator.compare(
        {"b": "2", "a": "1"},
        {"a": "1", "b": "2"},
    )

    assert [item.activity_name for item in results] == ["a", "b"]
    assert all(item.match for item in results)
    assert comparator.score(results) == 1.0


def test_comparator_numeric_tolerance_pass_and_fail():
    assert outputs_equivalent("1.0000004", "1.0000008", tolerance=1e-6)
    assert not outputs_equivalent("1.0", "1.01", tolerance=1e-6)


def test_comparator_datetime_normalization():
    assert outputs_equivalent("2024-01-01T00:00:00Z", "2024-01-01T00:00:00+00:00")


def test_comparator_marks_missing_keys_as_mismatch():
    comparator = OutputComparator()

    results = comparator.compare({"a": "1"}, {"a": "1", "b": "2"})

    assert len(results) == 2
    assert results[0].activity_name == "a" and results[0].match
    assert results[1].activity_name == "b" and not results[1].match
    assert results[1].diff == "missing in adf outputs"
    assert comparator.score(results) == 0.5


def test_comparator_normalizes_json_and_whitespace():
    assert outputs_equivalent(' { "x" : 1, "y": [1, 2] } ', '{"y":[1,2],"x":1}')


def test_comparator_score_is_one_for_empty_results():
    comparator = OutputComparator()
    assert comparator.score([]) == 1.0


def test_comparator_nan_equals_nan():
    assert outputs_equivalent("nan", "nan")


def test_comparator_nan_not_equal_to_number():
    assert not outputs_equivalent("nan", "1.0")


def test_comparator_inf_equals_inf():
    assert outputs_equivalent("inf", "inf")


def test_comparator_negative_inf_equals_negative_inf():
    assert outputs_equivalent("-inf", "-inf")


def test_comparator_special_float_token_casing_is_normalized():
    assert outputs_equivalent("NaN", "nan")
    assert outputs_equivalent("Infinity", "inf")
    assert outputs_equivalent("-Infinity", "-inf")


def test_comparator_empty_string_vs_null():
    assert not outputs_equivalent("", "null")


def test_comparator_none_string_treated_as_null():
    assert outputs_equivalent("None", "null")


def test_comparator_boolean_string_normalization():
    assert outputs_equivalent("TRUE", "true")


def test_comparator_zero_vs_false_not_equal():
    assert not outputs_equivalent("0", "false")
