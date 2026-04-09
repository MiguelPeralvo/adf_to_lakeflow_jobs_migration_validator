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


# ---------------------------------------------------------------------------
# Optional-field schema (introduced by the L-F3 corpus growth follow-up to L-F19)
# ---------------------------------------------------------------------------


def test_adversarial_referenced_params_when_present_have_name_and_type(adversarial_payload):
    """Pairs that reference @pipeline().parameters.X carry an optional
    `referenced_params: [{name, type}]` array. The activity_context_wrapper
    helpers inject these into the synthetic pipeline's parameters block.

    The field is optional — pairs without parameter references omit it. When
    present, every entry must have a non-empty `name` and a non-empty `type`
    string so the wrapper can build a wkmigrate-compatible parameters dict.
    """
    for i, pair in enumerate(adversarial_payload["expressions"]):
        rps = pair.get("referenced_params")
        if rps is None:
            continue  # Optional field — absence is fine.
        assert isinstance(rps, list), f"pair {i} referenced_params must be a list, got {type(rps).__name__}"
        for j, rp in enumerate(rps):
            assert isinstance(rp, dict), f"pair {i} referenced_params[{j}] must be a dict"
            name = rp.get("name")
            type_ = rp.get("type")
            assert isinstance(name, str) and name, f"pair {i} referenced_params[{j}] missing/empty 'name' field"
            assert isinstance(type_, str) and type_, f"pair {i} referenced_params[{j}] missing/empty 'type' field"


def test_adversarial_referenced_params_match_pipeline_parameters_in_expression(adversarial_payload):
    """Cross-check: every name listed in `referenced_params` must actually
    appear inside the `adf_expression` as `pipeline().parameters.<name>`.
    Unused declared params are a corpus authoring smell — they would cause
    the wrapper to inject parameters wkmigrate doesn't need, which doesn't
    break anything but indicates the test author confused themselves about
    which params the expression really uses.
    """
    import re

    for i, pair in enumerate(adversarial_payload["expressions"]):
        rps = pair.get("referenced_params") or []
        adf = pair["adf_expression"]
        for j, rp in enumerate(rps):
            name = rp["name"]
            pattern = rf"pipeline\(\)\.parameters\.{re.escape(name)}\b"
            assert re.search(pattern, adf), (
                f"pair {i} declares referenced_params[{j}].name={name!r} "
                f"but {adf!r} does not contain pipeline().parameters.{name}"
            )


def test_adversarial_targets_when_present_reference_known_w_findings(adversarial_payload):
    """Pairs added in the corpus growth carry an optional `targets` array of
    W-finding IDs (e.g. `["W-2", "W-3"]`). When present, every value must
    look like a `W-N` ID so cross-references with dev/wkmigrate-issue-map.json
    are unambiguous.
    """
    import re

    pattern = re.compile(r"^W-\d+$")
    for i, pair in enumerate(adversarial_payload["expressions"]):
        targets = pair.get("targets")
        if targets is None:
            continue  # Optional field.
        assert isinstance(targets, list), f"pair {i} targets must be a list"
        for t in targets:
            assert isinstance(t, str) and pattern.match(t), f"pair {i} targets entry {t!r} is not a valid W-N ID"


def test_adversarial_corpus_exercises_w2_w3_w10(adversarial_payload):
    """The corpus growth pledged to exercise W-2 (param refs in non-notebook
    contexts), W-3 (math on parameters), and W-10 (bare ForEach arrays).
    Pin that pledge so a future trim of the corpus can't silently revert it.
    """
    targets_seen: set[str] = set()
    for pair in adversarial_payload["expressions"]:
        targets_seen.update(pair.get("targets") or [])
    for required in ("W-2", "W-3", "W-10"):
        assert required in targets_seen, (
            f"corpus is missing pairs targeting {required}. " f"Currently exercised: {sorted(targets_seen)}"
        )


def test_adversarial_expected_python_is_not_byte_identical_to_legacy(adversarial_payload):
    """The whole point of L-F3 is INDEPENDENCE: the adversarial corpus must
    contain at least one pair whose ADF expression ALSO exists in the legacy
    corpus AND whose expected_python disagrees byte-for-byte. Both conditions
    are required:

    - If there's no overlap at all, "independence" is unprovable from this
      file alone — we'd just be writing a different set of expressions, which
      doesn't demonstrate that the human-derived oracle disagrees with
      wkmigrate's emitter.
    - If overlap exists but every overlapping pair matches byte-for-byte,
      we're effectively duplicating the legacy corpus (which is itself
      generated by wkmigrate's emitter), so the oracle is NOT independent.

    The test is intentionally strict so a future contributor who adds 20
    zero-overlap pairs (or 20 pairs that happen to match legacy byte-for-byte)
    gets a clear failure pointing them at the L-F3 invariant.

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

    # L-F3 invariant 1: must have at least one overlap with legacy, otherwise
    # the test passes vacuously and "independence" is unprovable.
    assert overlaps > 0, (
        "L-F3 corpus has zero overlap with legacy expressions.json — cannot "
        "prove independence. Add at least one pair whose adf_expression ALSO "
        "exists in the legacy corpus AND whose expected_python differs."
    )

    # L-F3 invariant 2: at least one of the overlapping pairs must disagree
    # byte-for-byte. Otherwise we're duplicating the legacy corpus (which IS
    # generated by wkmigrate's emitter) and the oracle is not independent.
    assert disagreements, (
        f"All {overlaps} overlapping pairs match the legacy expected_python "
        f"byte-for-byte. L-F3 requires at least one independent disagreement "
        f"to prove the oracle is actually independent of wkmigrate's emitter."
    )
