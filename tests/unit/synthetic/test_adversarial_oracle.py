"""Schema + provenance tests for golden_sets/expressions_adversarial.json (L-F3 starter).

These tests intentionally do NOT run the expressions through wkmigrate — that's
the JOB of future X-2 measurements (which compare wkmigrate's emitter output
against the human-derived expected_python in this file). The tests here just
validate that the file is loadable, well-formed, and carries the L-F3 provenance
metadata so future tooling can distinguish it from the wkmigrate-circular
golden_sets/expressions.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ADVERSARIAL_PATH = Path("golden_sets/expressions_adversarial.json")
LEGACY_PATH = Path("golden_sets/expressions.json")


@pytest.fixture(scope="module")
def adversarial_payload() -> dict:
    """Load the adversarial corpus once per test module."""
    return json.loads(ADVERSARIAL_PATH.read_text(encoding="utf-8"))


def test_adversarial_corpus_file_exists():
    """The L-F3 starter file is committed to the repo."""
    assert ADVERSARIAL_PATH.is_file()


def test_adversarial_corpus_count_matches_expressions_length(adversarial_payload):
    """count field equals len(expressions) — basic schema invariant matching expressions.json."""
    expressions = adversarial_payload["expressions"]
    assert adversarial_payload["count"] == len(expressions)


def test_adversarial_corpus_has_at_least_20_pairs(adversarial_payload):
    """The starter pledges at least 20 hand-curated pairs (per session 2 ledger)."""
    assert len(adversarial_payload["expressions"]) >= 20


def test_adversarial_corpus_carries_provenance_metadata(adversarial_payload):
    """Each L-F3 entry must carry the provenance / methodology / schema comments
    so future tooling can distinguish this corpus from the wkmigrate-circular
    legacy expressions.json. The `$comment_*` keys are the marker."""
    assert "$comment_provenance" in adversarial_payload
    assert "L-F3" in adversarial_payload["$comment_provenance"]
    assert "wkmigrate-circular" in adversarial_payload["$comment_provenance"]
    assert "$comment_methodology" in adversarial_payload
    assert "$comment_schema" in adversarial_payload


def test_each_adversarial_pair_has_required_fields(adversarial_payload):
    """Each pair must have adf_expression, category, expected_python (legacy
    schema fields) PLUS axis and rationale (L-F3-specific tagging).
    """
    required_fields = {"adf_expression", "category", "expected_python", "axis", "rationale"}
    for i, pair in enumerate(adversarial_payload["expressions"]):
        missing = required_fields - set(pair.keys())
        assert not missing, f"pair {i} ({pair.get('adf_expression', '?')}) missing fields: {missing}"


def test_each_adversarial_pair_has_non_empty_string_fields(adversarial_payload):
    """All string fields must be non-empty (defensive — catches typos like
    `expected_python: ""` that would silently pass byte-comparison)."""
    for i, pair in enumerate(adversarial_payload["expressions"]):
        for field in ("adf_expression", "category", "expected_python", "axis", "rationale"):
            value = pair[field]
            assert isinstance(value, str), f"pair {i} field {field!r} is not a string"
            assert value, f"pair {i} field {field!r} is empty"


def test_adversarial_categories_match_legacy_corpus(adversarial_payload):
    """Categories must be a subset of the legacy corpus's 6 categories so
    future X-6 by-category aggregations work uniformly across both."""
    legacy_payload = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
    legacy_categories = {pair["category"] for pair in legacy_payload["expressions"]}
    adversarial_categories = {pair["category"] for pair in adversarial_payload["expressions"]}
    extra = adversarial_categories - legacy_categories
    assert not extra, (
        f"adversarial corpus uses categories not in legacy: {extra}. " f"Legacy categories: {legacy_categories}"
    )


def test_adversarial_adf_expressions_start_with_at_sign(adversarial_payload):
    """All ADF expression strings must start with `@` (the canonical ADF
    expression marker) so wkmigrate's parser will accept them."""
    for i, pair in enumerate(adversarial_payload["expressions"]):
        adf = pair["adf_expression"]
        assert adf.startswith("@"), (
            f"pair {i} adf_expression {adf!r} doesn't start with '@' — "
            f"wkmigrate's expression parser would reject it"
        )


def test_adversarial_expected_python_is_not_byte_identical_to_legacy(adversarial_payload):
    """The whole point of L-F3 is INDEPENDENCE: at least one pair in the
    adversarial corpus must have an expected_python that does NOT match
    what wkmigrate's emitter (and therefore the legacy expressions.json)
    would produce.

    Two seeded oracle-disagreement candidates (datetime expressions) use
    `datetime.datetime.fromisoformat` while wkmigrate's legacy corpus uses
    a `_wkmigrate_format_datetime` helper, so the disagreement is provable
    even before any sweep runs.
    """
    legacy_payload = json.loads(LEGACY_PATH.read_text(encoding="utf-8"))
    legacy_by_adf = {pair["adf_expression"]: pair["expected_python"] for pair in legacy_payload["expressions"]}

    disagreements = []
    overlaps = 0
    for adv_pair in adversarial_payload["expressions"]:
        adv_adf = adv_pair["adf_expression"]
        adv_py = adv_pair["expected_python"]
        if adv_adf in legacy_by_adf:
            overlaps += 1
            if legacy_by_adf[adv_adf] != adv_py:
                disagreements.append((adv_adf, legacy_by_adf[adv_adf], adv_py))

    # If there's any overlap, at least one must disagree (otherwise we're
    # just duplicating the legacy corpus, defeating the L-F3 purpose).
    if overlaps > 0:
        assert disagreements, (
            f"All {overlaps} overlapping pairs match the legacy expected_python byte-for-byte. "
            f"L-F3 requires at least one independent disagreement to prove the oracle is "
            f"actually independent of wkmigrate's emitter."
        )
