"""
WorkflowsResource — CRUD + utility operations for Workflow resources.

Endpoints implemented:
    POST   /v1/workflows                            → create
    GET    /v1/workflows                            → list (paginated)
    GET    /v1/workflows/{id}                       → get
    PATCH  /v1/workflows/{id}                       → update
    DELETE /v1/workflows/{id}                       → delete
    POST   /v1/workflows/{id}/clone                 → clone
    PATCH  /v1/workflows/{id}/concurrency           → update_concurrency
    GET    /v1/workflows/{id}/export                → export
    POST   /v1/workflows/import/bundle              → import_bundle
    GET    /v1/workflows/schema                     → schema
    GET    /v1/workflows/dynamic-variables/{id}     → dynamic_variables

Sub-resource (versions) is exposed as ``resource.versions``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr, is_given
from interactly._utils._serialise import serialise_config
from interactly.resources.workflows.versions import AsyncWorkflowVersionsResource, WorkflowVersionsResource
from interactly.types._config_types import WorkflowConfigOrDict
from interactly.types.workflows.workflow import Workflow

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from interactly._client import AsyncWorkflowClient, WorkflowClient
    from interactly.configs import WorkflowConfigFullyHydrated
    from interactly.runtime.handle import AsyncWorkflowHandle, WorkflowHandle

__all__ = ["WorkflowsResource", "AsyncWorkflowsResource"]

_PATH = "/v1/workflows"


def _is_hydrated_shape(candidate: Dict[str, Any]) -> bool:
    """True when this dict is the ``WorkflowConfigFullyHydrated`` payload itself.

    Keyed on the *presence* of the node/edge lists rather than their truthiness: a workflow with no
    nodes yet is still the hydrated shape, and treating an empty list as "keep looking" would walk
    straight past it.
    """
    return isinstance(candidate.get("node_configs"), list) or isinstance(candidate.get("edge_configs"), list)


def _extract_hydrated_config(raw: Any) -> Dict[str, Any]:
    """Unwrap a ``GET /workflows/{id}?fully_hydrate=true`` response.

    The server nests this two levels deep::

        {"workflow": {..., "workflow_config": {"workflow_config": {...},
                                               "node_configs": [...],
                                               "edge_configs": [...]}},
         "execution_url": "..."}

    The outer ``workflow`` is the stored document (team_id, _id, timestamps); the hydrated payload is
    its ``workflow_config``. This used to stop one level short and return the document, whose
    ``node_configs`` and ``edge_configs`` are absent — so every call silently produced a config with
    **zero nodes and zero edges** rather than failing. The unit tests missed it because they mocked
    the hydrated config directly under ``workflow``, a shape the server does not actually return.

    Descends while the payload is still a wrapper, so the flat and single-wrapped shapes that mocked
    backends return keep working.
    """
    if not isinstance(raw, dict):
        return cast(Dict[str, Any], raw)

    payload: Dict[str, Any] = raw
    if isinstance(payload.get("workflow"), dict):
        payload = payload["workflow"]

    # Bounded: the real response needs one descent, and a cycle would otherwise spin.
    for _ in range(4):
        if _is_hydrated_shape(payload):
            return payload
        inner = payload.get("workflow_config")
        if not isinstance(inner, dict):
            break
        payload = inner
    return payload


def _apply_hydrated_name(body: Dict[str, Any], *, name: Optional[str], description: Optional[str]) -> None:
    """Promote the workflow name/description to the **top level** of a hydrated create body.

    The ``POST /v1/workflows`` hydrated-import path reads ``name`` / ``description``
    from the top level of the body, not from the nested ``workflow_config`` (which
    it ignores on create). We therefore lift an explicit ``name`` / ``description``
    argument — or, when omitted, the value already inside ``config.workflow_config``
    — up to the top level so the server persists it. Without this the created
    workflow's name comes back ``null``.
    """
    # Bound once, then narrowed: `isinstance(body.get(...), dict)` narrows the call's result, not the
    # separate call on the other side of the ternary, so the old one-liner still typed as
    # `Any | dict | None` and `.get` below was unchecked.
    raw_config = body.get("workflow_config")
    workflow_config: Dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    effective_name = name if name is not None else workflow_config.get("name")
    effective_description = description if description is not None else workflow_config.get("description")
    if effective_name is not None:
        body["name"] = effective_name
    if effective_description is not None:
        body["description"] = effective_description


class WorkflowsResource(SyncAPIResource):
    """
    Synchronous interface to the Workflows API.

    Usage::

        client = WorkflowClient(api_key="...", team_id="...", user_id="...")
        wf = client.workflows.create(name="My Workflow")
        page = client.workflows.list(size=20)
        for workflow in page:
            print(workflow.id, workflow.name)
    """

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.versions = WorkflowVersionsResource(client)

    # ---------------------------------------------------------------------- #
    # CRUD                                                                     #
    # ---------------------------------------------------------------------- #

    def create(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        config: Optional[WorkflowConfigOrDict] = None,
    ) -> Workflow:
        """Create a new workflow."""
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if config is not None:
            body["config"] = serialise_config(config)
        return self._client.post(_PATH, body=body, cast_to=Workflow)

    def get(self, workflow_id: str) -> Workflow:
        """Retrieve a single workflow by ID."""
        return self._client.get(f"{_PATH}/{workflow_id}", cast_to=Workflow)

    def update(
        self,
        workflow_id: str,
        *,
        name: NotGivenOr[str] = NOT_GIVEN,
        description: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> Workflow:
        """
        Partially update a workflow.  Only supplied fields are sent.

        To explicitly set a field to ``null``, pass ``None``; to leave it
        unchanged omit it (the NOT_GIVEN default).
        """
        body: dict[str, Any] = {}
        if is_given(name):
            body["name"] = name
        if is_given(description):
            body["description"] = description
        return self._client.patch(f"{_PATH}/{workflow_id}", body=body, cast_to=Workflow)

    def delete(self, workflow_id: str) -> None:
        """Permanently delete a workflow and all its versions."""
        self._client.delete(f"{_PATH}/{workflow_id}", cast_to=type(None))

    # ---------------------------------------------------------------------- #
    # List / pagination                                                        #
    # ---------------------------------------------------------------------- #

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
    ) -> SyncPage[Workflow]:
        """
        List workflows for the authenticated team (paginated).

        Args:
            page:   Page number (1-based).
            size:   Items per page.
            search: Keyword filter applied to workflow name/description.

        Returns:
            SyncPage[Workflow] — call ``.list_all()`` to collect all pages.
        """
        params: dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search

        raw = self._client.get(_PATH, params=params, cast_to=dict)

        def fetch_page(p: int) -> SyncPage[Workflow]:
            return self.list(page=p, size=size, search=search)

        return SyncPage._from_response(raw, Workflow, fetch_page)

    # ---------------------------------------------------------------------- #
    # Utility operations                                                       #
    # ---------------------------------------------------------------------- #

    def clone(
        self,
        workflow_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        clone_all_versions: bool = True,
        version_numbers: Optional[List[int]] = None,
        fallback_active_version: Optional[int] = None,
    ) -> Workflow:
        """Duplicate a workflow (deep copy of nodes, edges, and versions).

        By default every version is cloned. Pass ``version_numbers`` to clone a
        specific subset instead (which sets ``clone_all_versions`` to ``False``).
        The server requires at least one version to be selected.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if version_numbers:
            body["version_numbers_to_clone"] = version_numbers
            body["clone_all_versions"] = False
        else:
            body["clone_all_versions"] = clone_all_versions
        if fallback_active_version is not None:
            body["fallback_active_version"] = fallback_active_version
        return self._client.post(f"{_PATH}/{workflow_id}/clone", body=body, cast_to=Workflow)

    def update_concurrency(
        self,
        workflow_id: str,
        *,
        max_concurrent_runs: int,
    ) -> Dict[str, Any]:
        """Set the maximum number of simultaneous runs for a workflow.

        Returns the raw ``ConcurrencyConfigResponse`` dict with
        ``workflow_id``, ``max_concurrent_runs``, and ``message`` keys (the
        server does not return a full ``Workflow`` here).
        """
        return self._client.patch(
            f"{_PATH}/{workflow_id}/concurrency",
            body={"max_concurrent_runs": max_concurrent_runs},
            cast_to=dict,
        )

    def export(
        self,
        workflow_id: str,
        *,
        version_numbers: List[int],
        active_version_number: int,
    ) -> Dict[str, Any]:
        """Export a workflow as a portable bundle dict.

        Args:
            workflow_id:           ObjectId of the workflow to export.
            version_numbers:       Version numbers to include in the bundle.
            active_version_number: Which of ``version_numbers`` is the active one
                                   (must be present in ``version_numbers``).
        """
        params: Dict[str, Any] = {
            "version_numbers": version_numbers,
            "active_version_number": active_version_number,
        }
        return self._client.get(f"{_PATH}/{workflow_id}/export", params=params, cast_to=dict)

    def import_bundle(
        self,
        bundle: Dict[str, Any],
        *,
        versions_to_import: Optional[List[int]] = None,
        active_version_number: Optional[int] = None,
        workflow_name: Optional[str] = None,
    ) -> Workflow:
        """Import a previously exported workflow bundle.

        The server expects a ``WorkflowBundleImportRequest`` wrapper, so the
        raw bundle is nested under ``bundle``.

        Args:
            bundle:                An exported bundle (from :meth:`export`).
            versions_to_import:    Version numbers to import from the bundle
                                   (server default: ``[0]``).
            active_version_number: Version number to set active in the new
                                   workflow (server default: ``0``).
            workflow_name:         Optional override for the imported workflow's name.
        """
        body: Dict[str, Any] = {"bundle": bundle}
        if versions_to_import is not None:
            body["versions_to_import"] = versions_to_import
        if active_version_number is not None:
            body["active_version_number"] = active_version_number
        if workflow_name is not None:
            body["workflow_name"] = workflow_name
        return self._client.post(f"{_PATH}/import/bundle", body=body, cast_to=Workflow)

    def schema(self) -> Dict[str, Any]:
        """Return the JSON schema for valid workflow configuration."""
        return self._client.get(f"{_PATH}/schema", cast_to=dict)

    def global_node_config_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for GlobalNodeConfig (used for Super Node routing)."""
        return self._client.get(f"{_PATH}/schemas/global-node-config", cast_to=dict)

    def dynamic_variables(self, workflow_id: str) -> Dict[str, Any]:
        """Return the dynamic variable definitions for a workflow."""
        return self._client.get(f"{_PATH}/dynamic-variables/{workflow_id}", cast_to=dict)

    # ---------------------------------------------------------------------- #
    # Typed-config upload + read-back                                          #
    # ---------------------------------------------------------------------- #

    def create_from_config(
        self,
        config: "WorkflowConfigFullyHydrated",
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Workflow:
        """Upload a fully-hydrated typed workflow (config + nodes + edges) in one POST.

        The backend's ``POST /v1/workflows`` natively accepts a
        ``WorkflowConfigFullyHydrated`` payload and imports it as a complete
        workflow.  If ``name``/``description`` are provided they override the
        values inside ``config.workflow_config``.

        Args:
            config:      Typed ``WorkflowConfigFullyHydrated`` instance.
            name:        Optional override for the workflow name.
            description: Optional override for the workflow description.

        Returns:
            The created :class:`Workflow`.
        """
        body: Dict[str, Any] = serialise_config(config)
        _apply_hydrated_name(body, name=name, description=description)
        return self._client.post(_PATH, body=body, cast_to=Workflow)

    def get_fully_hydrated(self, workflow_id: str) -> "WorkflowConfigFullyHydrated":
        """Fetch a workflow as a typed ``WorkflowConfigFullyHydrated`` instance.

        Issues ``GET /v1/workflows/{id}?fully_hydrate=true``, unwraps the
        ``WorkflowsResponse`` envelope, and validates the result with
        :class:`WorkflowConfigFullyHydrated`.

        Requires the ``[configs]`` extra to be installed.
        """
        from interactly.configs import WorkflowConfigFullyHydrated

        raw = self._client.get(
            f"{_PATH}/{workflow_id}", params={"fully_hydrate": True}, cast_to=dict
        )
        return WorkflowConfigFullyHydrated.model_validate(_extract_hydrated_config(raw))

    def handle(
        self,
        workflow_id: str,
        *,
        dynamic_variables: Optional[Dict[str, Any]] = None,
    ) -> "WorkflowHandle":
        """Construct a :class:`WorkflowHandle` pre-loaded with the hydrated config."""
        from interactly.runtime.handle import WorkflowHandle

        config = self.get_fully_hydrated(workflow_id)
        return WorkflowHandle(
            # `_client` is declared as the transport base `SyncAPIClient`, but a resource is only ever
            # constructed from the public `WorkflowClient` — which is what the handle needs, since it
            # reaches for `client.runs`. Narrowed here rather than widening the handle's parameter,
            # which would type away the very attribute it uses.
            client=cast("WorkflowClient", self._client),
            workflow_id=workflow_id,
            config=config,
            dynamic_variables=dynamic_variables,
        )

    def favorite(self, workflow_id: str) -> Dict[str, Any]:
        """Mark a workflow as a favorite for the requesting user (idempotent)."""
        return self._client.post(f"{_PATH}/{workflow_id}/favorite", cast_to=dict)

    def unfavorite(self, workflow_id: str) -> Dict[str, Any]:
        """Remove a workflow from the requesting user's favorites."""
        return self._client.delete(f"{_PATH}/{workflow_id}/favorite", cast_to=dict)


class AsyncWorkflowsResource(AsyncAPIResource):
    """
    Async interface to the Workflows API.  All methods are coroutines.

    Usage::

        async with AsyncWorkflowClient(...) as client:
            wf = await client.workflows.create(name="My Workflow")
            page = await client.workflows.list()
            all_workflows = await page.list_all()
    """

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.versions = AsyncWorkflowVersionsResource(client)

    async def create(
        self,
        *,
        name: str,
        description: Optional[str] = None,
        config: Optional[WorkflowConfigOrDict] = None,
    ) -> Workflow:
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        if config is not None:
            body["config"] = serialise_config(config)
        return await self._client.post(_PATH, body=body, cast_to=Workflow)

    async def get(self, workflow_id: str) -> Workflow:
        return await self._client.get(f"{_PATH}/{workflow_id}", cast_to=Workflow)

    async def update(
        self,
        workflow_id: str,
        *,
        name: NotGivenOr[str] = NOT_GIVEN,
        description: NotGivenOr[Optional[str]] = NOT_GIVEN,
    ) -> Workflow:
        body: dict[str, Any] = {}
        if is_given(name):
            body["name"] = name
        if is_given(description):
            body["description"] = description
        return await self._client.patch(f"{_PATH}/{workflow_id}", body=body, cast_to=Workflow)

    async def delete(self, workflow_id: str) -> None:
        await self._client.delete(f"{_PATH}/{workflow_id}", cast_to=type(None))

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
    ) -> AsyncPage[Workflow]:
        params: dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search

        raw = await self._client.get(_PATH, params=params, cast_to=dict)

        async def fetch_page(p: int) -> AsyncPage[Workflow]:
            return await self.list(page=p, size=size, search=search)

        return AsyncPage._from_response(raw, Workflow, fetch_page)

    async def clone(
        self,
        workflow_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        clone_all_versions: bool = True,
        version_numbers: Optional[List[int]] = None,
        fallback_active_version: Optional[int] = None,
    ) -> Workflow:
        """Duplicate a workflow (deep copy of nodes, edges, and versions).

        By default every version is cloned. Pass ``version_numbers`` to clone a
        specific subset instead (which sets ``clone_all_versions`` to ``False``).
        The server requires at least one version to be selected.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if version_numbers:
            body["version_numbers_to_clone"] = version_numbers
            body["clone_all_versions"] = False
        else:
            body["clone_all_versions"] = clone_all_versions
        if fallback_active_version is not None:
            body["fallback_active_version"] = fallback_active_version
        return await self._client.post(f"{_PATH}/{workflow_id}/clone", body=body, cast_to=Workflow)

    async def update_concurrency(self, workflow_id: str, *, max_concurrent_runs: int) -> Dict[str, Any]:
        """Set the maximum number of simultaneous runs for a workflow.

        Returns the raw ``ConcurrencyConfigResponse`` dict with
        ``workflow_id``, ``max_concurrent_runs``, and ``message`` keys.
        """
        return await self._client.patch(
            f"{_PATH}/{workflow_id}/concurrency",
            body={"max_concurrent_runs": max_concurrent_runs},
            cast_to=dict,
        )

    async def export(
        self,
        workflow_id: str,
        *,
        version_numbers: List[int],
        active_version_number: int,
    ) -> Dict[str, Any]:
        """Export a workflow as a portable bundle dict.

        Requires ``version_numbers`` and ``active_version_number`` query params
        (the server rejects the request otherwise).
        """
        params: Dict[str, Any] = {
            "version_numbers": version_numbers,
            "active_version_number": active_version_number,
        }
        return await self._client.get(f"{_PATH}/{workflow_id}/export", params=params, cast_to=dict)

    async def import_bundle(
        self,
        bundle: Dict[str, Any],
        *,
        versions_to_import: Optional[List[int]] = None,
        active_version_number: Optional[int] = None,
        workflow_name: Optional[str] = None,
    ) -> Workflow:
        """Import a previously exported workflow bundle.

        The server expects a ``WorkflowBundleImportRequest`` wrapper, so the
        raw bundle is nested under ``bundle``.
        """
        body: Dict[str, Any] = {"bundle": bundle}
        if versions_to_import is not None:
            body["versions_to_import"] = versions_to_import
        if active_version_number is not None:
            body["active_version_number"] = active_version_number
        if workflow_name is not None:
            body["workflow_name"] = workflow_name
        return await self._client.post(f"{_PATH}/import/bundle", body=body, cast_to=Workflow)

    async def schema(self) -> Dict[str, Any]:
        return await self._client.get(f"{_PATH}/schema", cast_to=dict)

    async def global_node_config_schema(self) -> Dict[str, Any]:
        return await self._client.get(f"{_PATH}/schemas/global-node-config", cast_to=dict)

    async def dynamic_variables(self, workflow_id: str) -> Dict[str, Any]:
        return await self._client.get(f"{_PATH}/dynamic-variables/{workflow_id}", cast_to=dict)

    # ---------------------------------------------------------------------- #
    # Typed-config upload + read-back                                          #
    # ---------------------------------------------------------------------- #

    async def create_from_config(
        self,
        config: "WorkflowConfigFullyHydrated",
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Workflow:
        """Async variant of :meth:`WorkflowsResource.create_from_config`."""
        body: Dict[str, Any] = serialise_config(config)
        _apply_hydrated_name(body, name=name, description=description)
        return await self._client.post(_PATH, body=body, cast_to=Workflow)

    async def get_fully_hydrated(self, workflow_id: str) -> "WorkflowConfigFullyHydrated":
        """Async variant of :meth:`WorkflowsResource.get_fully_hydrated`."""
        from interactly.configs import WorkflowConfigFullyHydrated

        raw = await self._client.get(
            f"{_PATH}/{workflow_id}", params={"fully_hydrate": True}, cast_to=dict
        )
        return WorkflowConfigFullyHydrated.model_validate(_extract_hydrated_config(raw))

    async def handle(
        self,
        workflow_id: str,
        *,
        dynamic_variables: Optional[Dict[str, Any]] = None,
    ) -> "AsyncWorkflowHandle":
        """Async variant of :meth:`WorkflowsResource.handle`."""
        from interactly.runtime.handle import AsyncWorkflowHandle

        config = await self.get_fully_hydrated(workflow_id)
        return AsyncWorkflowHandle(
            # See the sync counterpart above.
            client=cast("AsyncWorkflowClient", self._client),
            workflow_id=workflow_id,
            config=config,
            dynamic_variables=dynamic_variables,
        )

    async def favorite(self, workflow_id: str) -> Dict[str, Any]:
        """Mark a workflow as a favorite for the requesting user (idempotent)."""
        return await self._client.post(f"{_PATH}/{workflow_id}/favorite", cast_to=dict)

    async def unfavorite(self, workflow_id: str) -> Dict[str, Any]:
        """Remove a workflow from the requesting user's favorites."""
        return await self._client.delete(f"{_PATH}/{workflow_id}/favorite", cast_to=dict)
