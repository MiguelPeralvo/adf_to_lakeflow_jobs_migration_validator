"""Smoke tests for frontend scaffold files."""

from __future__ import annotations

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("relative_path", "tokens"),
    [
        ("apps/lmv/frontend/src/pages/Validate.tsx", ("ValidatePage", "ScorecardGauge")),
        ("apps/lmv/frontend/src/pages/Parallel.tsx", ("ParallelPage", "parallelRun")),
        ("apps/lmv/frontend/src/pages/Harness.tsx", ("HarnessPage", "harnessRun")),
        ("apps/lmv/frontend/src/pages/History.tsx", ("HistoryPage", "history")),
        ("apps/lmv/frontend/src/components/DimensionBreakdown.tsx", ("DimensionBreakdown", "DetailPanel")),
        ("apps/lmv/frontend/src/components/ScorecardGauge.tsx", ("ScorecardGauge", "MiniGauge")),
        ("apps/lmv/frontend/src/App.tsx", ("App", "Sidebar")),
    ],
)
def test_frontend_scaffold_files(relative_path: str, tokens: tuple[str, ...]):
    path = _REPO_ROOT / relative_path
    assert path.exists()
    content = _read(path)
    for token in tokens:
        assert token in content
