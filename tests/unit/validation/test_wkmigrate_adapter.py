"""Adapter boundary tests — IMPORTS wkmigrate.

These tests verify that from_wkmigrate() correctly maps wkmigrate types into
ConversionSnapshot. If wkmigrate changes a field name or restructures a class,
these tests break first (and only these tests break).
"""

import pytest


def test_adapter_maps_tasks_with_placeholder_detection():
    """Tasks pointing to /UNSUPPORTED_ADF_ACTIVITY get is_placeholder=True."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_maps_notebooks():
    """All NotebookArtifacts become NotebookSnapshots with file_path and content."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_maps_secrets():
    """All SecretInstructions become SecretRefs."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_maps_parameters():
    """Pipeline parameters become a tuple of name strings."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_maps_dependencies():
    """IR Dependency objects become DependencyRef pairs."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_maps_not_translatable():
    """Pipeline.not_translatable list is preserved."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_maps_expression_pairs():
    """SetVariableActivity tasks produce ExpressionPair entries."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_counts_source_dependencies():
    """total_source_dependencies matches the ADF JSON depends_on count."""
    pytest.skip("TDD: implement adapter first")


def test_adapter_handles_empty_pipeline():
    """A pipeline with no activities produces an empty snapshot."""
    pytest.skip("TDD: implement adapter first")


def test_roundtrip_evaluate_from_wkmigrate():
    """evaluate_from_wkmigrate() produces the same score as evaluate(from_wkmigrate(...))."""
    pytest.skip("TDD: implement adapter first")
