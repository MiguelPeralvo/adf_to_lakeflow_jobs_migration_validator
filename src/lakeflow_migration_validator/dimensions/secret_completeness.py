"""Secret completeness dimension."""

from __future__ import annotations

import re

from lakeflow_migration_validator.contract import ConversionSnapshot

_SECRET_GET_CALL_PATTERN = re.compile(r"dbutils\.secrets\.get\(\s*(?P<args>[^)]*)\)")
_SCOPE_ARG_PATTERN = re.compile(r'scope\s*=\s*["\'](?P<scope>[^"\']+)["\']')
_KEY_ARG_PATTERN = re.compile(r'key\s*=\s*["\'](?P<key>[^"\']+)["\']')


def _as_records(secret_refs: set[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"scope": scope, "key": key} for scope, key in sorted(secret_refs)]


def compute_secret_completeness(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of dbutils.secrets.get references that have matching SecretRefs."""
    defined = {(secret.scope, secret.key) for secret in snapshot.secrets}
    referenced = set()
    for notebook in snapshot.notebooks:
        for call in _SECRET_GET_CALL_PATTERN.finditer(notebook.content):
            args = call.group("args")
            scope_match = _SCOPE_ARG_PATTERN.search(args)
            key_match = _KEY_ARG_PATTERN.search(args)
            if scope_match and key_match:
                referenced.add((scope_match.group("scope"), key_match.group("key")))

    if not referenced:
        return 1.0, {"defined": _as_records(defined), "referenced": [], "missing": []}

    missing = referenced - defined
    score = (len(referenced) - len(missing)) / len(referenced)
    return score, {
        "defined": _as_records(defined),
        "referenced": _as_records(referenced),
        "missing": _as_records(missing),
    }
