"""ADF connector boundary used by the harness workflow.

Two construction modes:

*  **Callable injection** (``__init__``) — for testing and custom integrations.
   Pass lambdas/functions for list, fetch, and translate_prepare.

*  **from_credentials** — for production use. Builds a real wkmigrate
   ``FactoryClient`` + ``FactoryDefinitionStore`` from Azure SP credentials.
   Requires ``pip install lmv[wkmigrate]`` (wkmigrate + azure-identity).
"""

from __future__ import annotations

from typing import Any, Callable


class ADFConnector:
    """Injectable boundary for listing, fetching, and translating ADF pipelines."""

    @classmethod
    def from_credentials(
        cls,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        subscription_id: str,
        resource_group: str,
        factory_name: str,
    ) -> ADFConnector:
        """Build a real connector backed by wkmigrate FactoryClient.

        This imports wkmigrate and azure-identity at call time so the core
        lmv package can be installed without those dependencies.

        Args:
            tenant_id: Azure AD tenant identifier.
            client_id: Service principal application (client) ID.
            client_secret: Service principal client secret.
            subscription_id: Azure subscription hosting the ADF resources.
            resource_group: Resource group containing the Data Factory.
            factory_name: Name of the Azure Data Factory instance.

        Returns:
            A fully-configured ``ADFConnector`` that can list, fetch, and
            translate ADF pipelines via wkmigrate.
        """
        try:
            from wkmigrate.clients.factory_client import FactoryClient
            from wkmigrate.definition_stores.factory_definition_store import FactoryDefinitionStore
            from wkmigrate.preparers.preparer import prepare_workflow
        except ImportError as exc:
            raise NotImplementedError(
                "ADFConnector.from_credentials requires wkmigrate and azure-identity. "
                "Install with: pip install lmv[wkmigrate]"
            ) from exc

        factory_client = FactoryClient(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            subscription_id=subscription_id,
            resource_group_name=resource_group,
            factory_name=factory_name,
        )

        factory_store = FactoryDefinitionStore(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
            subscription_id=subscription_id,
            resource_group_name=resource_group,
            factory_name=factory_name,
        )

        def _list_pipelines() -> list[str]:
            return factory_client.list_pipelines()

        def _fetch_pipeline(name: str) -> dict:
            return factory_client.get_pipeline(name)

        def _translate_and_prepare(pipeline_json: dict) -> tuple[dict, Any]:
            pipeline_name = pipeline_json.get("name")
            if not pipeline_name:
                raise ValueError("Pipeline JSON must contain a 'name' key for translation")
            pipeline_ir = factory_store.load(pipeline_name)
            prepared = prepare_workflow(pipeline=pipeline_ir)
            return pipeline_json, prepared

        return cls(
            list_pipelines_fn=_list_pipelines,
            fetch_pipeline_fn=_fetch_pipeline,
            translate_prepare_fn=_translate_and_prepare,
        )

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
