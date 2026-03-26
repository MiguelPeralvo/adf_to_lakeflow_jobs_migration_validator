"""ADF connector boundary used by the harness workflow."""

from __future__ import annotations

from typing import Any, Callable


class ADFConnector:
    """Injectable boundary for listing, fetching, and translating ADF pipelines."""

    def __init__(
        self,
        *,
        list_pipelines_fn: Callable[[], list[str]] | None = None,
        fetch_pipeline_fn: Callable[[str], dict] | None = None,
        translate_prepare_fn: Callable[[dict], tuple[dict, Any]] | None = None,
    ):
        self._list_pipelines_fn = list_pipelines_fn
        self._fetch_pipeline_fn = fetch_pipeline_fn
        self._translate_prepare_fn = translate_prepare_fn

    def list_pipelines(self) -> list[str]:
        """Return all pipeline names available in the backing source."""
        if self._list_pipelines_fn is None:
            raise NotImplementedError("ADFConnector.list_pipelines is not configured")
        return self._list_pipelines_fn()

    def fetch_pipeline(self, name: str) -> dict:
        """Fetch one pipeline JSON payload by name."""
        if self._fetch_pipeline_fn is None:
            raise NotImplementedError("ADFConnector.fetch_pipeline is not configured")
        return self._fetch_pipeline_fn(name)

    def translate_and_prepare(self, pipeline_json: dict) -> tuple[dict, Any]:
        """Translate source JSON and prepare conversion artifacts."""
        if self._translate_prepare_fn is None:
            raise NotImplementedError("ADFConnector.translate_and_prepare is not configured")
        return self._translate_prepare_fn(pipeline_json)
