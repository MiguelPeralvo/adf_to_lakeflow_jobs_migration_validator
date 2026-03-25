"""Secret completeness dimension."""

from __future__ import annotations

import re

from lakeflow_migration_validator.contract import ConversionSnapshot

_SECRET_GET_PATTERN = re.compile(
    r'dbutils\.secrets\.get\(\s*scope=["\']([^"\']+)["\'],\s*key=["\']([^"\']+)["\']\)'
)


def compute_secret_completeness(snapshot: ConversionSnapshot) -> tuple[float, dict]:
    """Fraction of dbutils.secrets.get references that have matching SecretRefs."""
    defined = {(secret.scope, secret.key) for secret in snapshot.secrets}
    referenced = set()
    for notebook in snapshot.notebooks:
        for match in _SECRET_GET_PATTERN.finditer(notebook.content):
            referenced.add((match.group(1), match.group(2)))

    if not referenced:
        return 1.0, {"defined": [], "referenced": [], "missing": []}

    missing = referenced - defined
    score = (len(referenced) - len(missing)) / len(referenced)
    return score, {
        "defined": sorted(str(secret_ref) for secret_ref in defined),
        "referenced": sorted(str(secret_ref) for secret_ref in referenced),
        "missing": sorted(str(secret_ref) for secret_ref in missing),
    }
