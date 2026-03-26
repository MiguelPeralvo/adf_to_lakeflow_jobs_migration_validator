"""Smoke tests for frontend scaffold files."""

from __future__ import annotations

from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_frontend_validate_page_scaffold_exists():
    path = _REPO_ROOT / "apps/lmv/frontend/src/pages/Validate.tsx"
    assert path.exists()
    content = _read(path)
    assert "ValidatePage" in content
    assert "ScorecardCard" in content


def test_frontend_parallel_page_references_parallel_endpoint():
    path = _REPO_ROOT / "apps/lmv/frontend/src/pages/Parallel.tsx"
    assert path.exists()
    content = _read(path)
    assert "ParallelPage" in content
    assert "/api/parallel/run" in content


def test_frontend_comparison_component_exists():
    path = _REPO_ROOT / "apps/lmv/frontend/src/components/ParallelComparisonTable.tsx"
    assert path.exists()
    content = _read(path)
    assert "ParallelComparisonTable" in content
    assert "activity_name" in content
