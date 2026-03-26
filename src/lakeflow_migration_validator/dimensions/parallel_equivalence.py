"""Parallel equivalence dimension for ADF-vs-Databricks output comparisons."""

from __future__ import annotations

from lakeflow_migration_validator.contract import ConversionSnapshot
from lakeflow_migration_validator.parallel.comparator import outputs_equivalent


def compute_parallel_equivalence(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of activity outputs where ADF output matches expected output."""
    if not snapshot.adf_run_outputs:
        return 1.0, {"status": "no_adf_outputs", "compared": 0}

    compared = 0
    matched = 0
    mismatches: list[dict[str, str]] = []

    for activity_name in sorted(snapshot.adf_run_outputs):
        adf_output = snapshot.adf_run_outputs[activity_name]
        expected = snapshot.expected_outputs.get(activity_name)
        if expected is None:
            continue

        compared += 1
        if outputs_equivalent(adf_output, expected):
            matched += 1
            continue

        mismatches.append(
            {
                "activity": activity_name,
                "adf": adf_output,
                "expected": expected,
            }
        )

    if compared == 0:
        return 1.0, {"status": "no_comparable_activities", "compared": 0}

    score = matched / compared
    return score, {
        "compared": compared,
        "matched": matched,
        "mismatches": mismatches,
    }
