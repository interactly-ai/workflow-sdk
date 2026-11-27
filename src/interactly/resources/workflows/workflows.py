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
    GET    /v1/workflows/{id}/usage                 → usage
    GET    /v1/workflows/schema                     → schema
    GET    /v1/workflows/dynamic-variables/{id}     → dynamic_variables
    GET    /v1/workflows/{id}/lints                 → lints
    GET    /v1/workflows/{id}/realtime-compatibility → realtime_compatibility
    GET    /v1/workflows/{id}/counter-workflow      → counter_workflow
    POST   /v1/workflows/{id}/counter-workflow/generate → generate_counter_workflow
    POST   /v1/workflows/{id}/background-runs       → start_background_run

Sub-resource (versions) is exposed as ``resource.versions``.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union, cast

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr, is_given
from interactly._utils._serialise import serialise_config
from interactly.resources.workflows.versions import AsyncWorkflowVersionsResource, WorkflowVersionsResource
from interactly.types._config_types import WorkflowConfigOrDict
from interactly.types.runs.run_control import BackgroundRunStarted
from interactly.types.shared import WorkflowType
from interactly.types.usage import UsageReport
from interactly.types.workflows.analysis import (
    CounterGenerationState,
    CounterWorkflowStatus,
    RealtimeCompatibilityReport,
    WorkflowLintReport,
)
from interactly.types.workflows.workflow import Workflow

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from interactly._client import AsyncWorkflowClient, WorkflowClient
    from interactly.configs import WorkflowConfigFullyHydrated
    from interactly.runtime.handle import AsyncWorkflowHandle, WorkflowHandle

__all__ = ["WorkflowsResource", "AsyncWorkflowsResource"]

_PATH = "/v1/workflows"


def _version_and_model_params(
    version_number: Optional[int], model: Optional[str] = None, backend: Optional[str] = None
) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if version_number is not None:
        params["version_number"] = version_number
    if model is not None:
        params["model"] = model
    if backend is not None:
        params["backend"] = backend
    return params


def _counter_generation_body(
    *,
    num_cases: int,
    instructions: Optional[str],
    version_number: Optional[int],
    workflow_name: Optional[str],
    new_workflow: bool,
    provider: Optional[str],
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"num_cases": num_cases, "new_workflow": new_workflow}
    for key, value in (
        ("instructions", instructions),
        ("version_number", version_number),
        ("workflow_name", workflow_name),
        ("provider", provider),
    ):
        if value is not None:
            body[key] = value
    return body


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
        """Retrieve a single workflow by ID, with its ``active_version_number``. For one version's snapshot, use
        :meth:`WorkflowVersionsResource.get`."""
        # The workflow comes back either way; naming find_active_version keeps the server from logging the read as one
        # that relies on its old default.
        return self._client.get(f"{_PATH}/{workflow_id}", params={"find_active_version": True}, cast_to=Workflow)

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
        workflow_type: Union[WorkflowType, str, None] = None,
        logical_id: Optional[str] = None,
        categories: Optional[List[str]] = None,
        created_by: Optional[List[str]] = None,
        favorites: Optional[bool] = None,
    ) -> SyncPage[Workflow]:
        """
        List workflows for the authenticated team (paginated). Every filter given must match.

        Args:
            page:          Page number (1-based).
            size:          Items per page.
            search:        Keyword filter applied to workflow name/description.
            workflow_type: ``standard`` workflows (the ones that run calls), or ``evaluation`` workflows (post-call
                           analysis). The server lists standard ones unless ``evaluation`` is asked for.
            logical_id:    Only the workflow with this logical id.
            categories:    Only workflows in one of these categories; ``"User Created"`` also matches workflows with
                           no category.
            created_by:    Only workflows created by one of these users (user ids; with an API key, the id of the
                           member who created the key).
            favorites:     Only the workflows the calling user marked as favourites.

        Returns:
            SyncPage[Workflow] — call ``.list_all()`` to collect all pages.
        """
        filters: Dict[str, Any] = dict(
            search=search,
            workflow_type=workflow_type,
            logical_id=logical_id,
            categories=categories,
            created_by=created_by,
            favorites=favorites,
        )
        raw = self._client.get(_PATH, params=_list_params(page=page, size=size, **filters), cast_to=dict)

        def fetch_page(p: int) -> SyncPage[Workflow]:
            return self.list(page=p, size=size, **filters)

        return SyncPage._from_response(raw, Workflow, fetch_page, page=page, size=size)

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
        include_secrets: bool = False,
    ) -> Dict[str, Any]:
        """Export a workflow as a portable bundle dict, for :meth:`import_bundle` here or on another server.

        By default the workflow's secrets are cleared from the bundle: a secret field becomes ``None``, and a
        sensitive header or body entry (an ``Authorization`` header, say) becomes ``""``. ``bundle["redactions"]``
        lists each one, as ``{"path", "reason", "node_name", "segments"}``, and ``bundle["secrets_included"]`` says
        whether they were kept. Supply them again on import with ``secret_overrides``.

        Args:
            workflow_id:           ObjectId of the workflow to export.
            version_numbers:       Version numbers to include in the bundle.
            active_version_number: Which of ``version_numbers`` is the active one
                                   (must be present in ``version_numbers``).
            include_secrets:       Keep the secrets in the bundle, in plain text. Anything that stores the bundle
                                   then holds the workflow's credentials. Refused to a viewer.

        Raises:
            PermissionDeniedError: ``include_secrets`` asked by a viewer.
        """
        return self._client.get(
            f"{_PATH}/{workflow_id}/export",
            params=_export_params(version_numbers, active_version_number, include_secrets),
            cast_to=dict,
        )

    def import_bundle(
        self,
        bundle: Dict[str, Any],
        *,
        versions_to_import: Optional[List[int]] = None,
        active_version_number: Optional[int] = None,
        workflow_name: Optional[str] = None,
        secret_overrides: Optional[Dict[str, str]] = None,
    ) -> Workflow:
        """Import a previously exported workflow bundle as a new workflow.

        The server expects a ``WorkflowBundleImportRequest`` wrapper, so the
        raw bundle is nested under ``bundle``.

        Args:
            bundle:                An exported bundle (from :meth:`export`).
            versions_to_import:    Version numbers to import from the bundle
                                   (server default: ``[0]``).
            active_version_number: Version number to set active in the new
                                   workflow (server default: ``0``).
            workflow_name:         Optional override for the imported workflow's name.
            secret_overrides:      Values for the secrets the export cleared, keyed by their ``path`` in
                                   ``bundle["redactions"]``: ``{r["path"]: value for r in bundle["redactions"]}``.
                                   In a path, the number after ``versions.`` is the version's position in
                                   ``bundle["versions"]``, not its version number. A blank value counts as not
                                   supplied. Each secret not supplied stays empty and adds a line to the returned
                                   workflow's ``warnings``.

        Raises:
            UnprocessableEntityError: a ``secret_overrides`` path the bundle doesn't list, or a bundle whose
                ``redactions`` were edited; ``err.body["field_errors"]`` names the paths.
        """
        return self._client.post(
            f"{_PATH}/import/bundle",
            body=_import_body(bundle, versions_to_import, active_version_number, workflow_name, secret_overrides),
            cast_to=Workflow,
        )

    def usage(self, workflow_id: str) -> UsageReport:
        """The team's workflows that use this one, in any version: as a super node's workflow, an evaluator, or a
        warm-transfer target.

        A delete doesn't consult this: deleting the workflow still succeeds, and leaves these with a reference that
        no longer resolves. An id that names no workflow answers an empty report.
        """
        return self._client.get(f"{_PATH}/{workflow_id}/usage", cast_to=UsageReport)

    def schema(self) -> Dict[str, Any]:
        """Return the JSON schema for valid workflow configuration."""
        return self._client.get(f"{_PATH}/schema", cast_to=dict)

    def global_node_config_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for GlobalNodeConfig (used for Super Node routing)."""
        return self._client.get(f"{_PATH}/schemas/global-node-config", cast_to=dict)

    def dynamic_variables(self, workflow_id: str, *, version_number: Optional[int] = None) -> Dict[str, Any]:
        """Return the dynamic variable definitions for a workflow.

        Args:
            workflow_id:    ObjectId of the workflow.
            version_number: The version to read them from. Without it, the server reads the workflow's own record
                            rather than a version.

        Raises:
            NotFoundError: no such workflow, or no such version of it.
        """
        return self._client.get(
            f"{_PATH}/dynamic-variables/{workflow_id}",
            params=_version_and_model_params(version_number),
            cast_to=dict,
        )

    def lints(self, workflow_id: str, *, version_number: Optional[int] = None) -> WorkflowLintReport:
        """Every advisory lint for a stored workflow, run against the whole graph.

        Read-only. The same checks a fully-hydrated create runs, but graph-wide, which is the only way to
        catch a cross-thread reference to a thread that does not exist or a waiting condition that could
        never fire — the editor saves a node at a time and cannot see either. ``version_number``
        defaults to the active version.
        """
        return self._client.get(
            f"{_PATH}/{workflow_id}/lints",
            cast_to=WorkflowLintReport,
            params=_version_and_model_params(version_number),
        )

    def realtime_compatibility(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
        model: Optional[str] = None,
        backend: Optional[str] = None,
    ) -> RealtimeCompatibilityReport:
        """Whether this workflow can run its voice calls on a realtime (speech-to-speech) model.

        Pass the realtime ``model`` the call would use to sharpen the verdict: the two realtime protocols
        differ enough that a workflow can be ready on one and not the other. Without it, the findings
        describe what holds on either.

        For a Gemini model, ``backend`` is the assistant's Gemini backend (``vertex`` or ``ai_studio``). The
        check then agrees with the one a call makes as it starts about which tool names collide.
        """
        return self._client.get(
            f"{_PATH}/{workflow_id}/realtime-compatibility",
            cast_to=RealtimeCompatibilityReport,
            params=_version_and_model_params(version_number, model, backend),
        )

    def counter_workflow(self, workflow_id: str) -> CounterWorkflowStatus:
        """The simulated-caller workflow generated from this one, and the state of the newest generation."""
        return self._client.get(f"{_PATH}/{workflow_id}/counter-workflow", cast_to=CounterWorkflowStatus)

    def generate_counter_workflow(
        self,
        workflow_id: str,
        *,
        num_cases: int = 10,
        instructions: Optional[str] = None,
        version_number: Optional[int] = None,
        workflow_name: Optional[str] = None,
        new_workflow: bool = False,
        provider: Optional[str] = None,
    ) -> CounterGenerationState:
        """Start generating a counter workflow: simulated callers written from this workflow's config.

        **Returns immediately**; generation runs on the server and makes several LLM calls. Poll
        :meth:`counter_workflow` until ``generation.status`` is ``completed`` or ``failed``.

        Args:
            num_cases:      Test cases to generate, 1–200.
            instructions:   Extra guidance for the generator.
            version_number: Source version; defaults to the active one.
            workflow_name:  Name for the counter workflow; derived from the source when omitted.
            new_workflow:   Force a new counter workflow. By default a regeneration is appended to the
                            existing one as a new version.
            provider:       ``"gemini"`` (the server default) or ``"claude"``.

        Raises:
            BadRequestError: When ``workflow_id`` is itself a counter workflow.
            ConflictError: When a generation is already running for this workflow.
        """
        body = _counter_generation_body(
            num_cases=num_cases,
            instructions=instructions,
            version_number=version_number,
            workflow_name=workflow_name,
            new_workflow=new_workflow,
            provider=provider,
        )
        raw: Dict[str, Any] = self._client.post(
            f"{_PATH}/{workflow_id}/counter-workflow/generate", body=body, cast_to=dict
        )
        return CounterGenerationState.model_validate(raw.get("generation") or {})

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

    def get_fully_hydrated(
        self, workflow_id: str, *, version_number: Optional[int] = None
    ) -> "WorkflowConfigFullyHydrated":
        """Fetch a workflow as a typed ``WorkflowConfigFullyHydrated`` instance.

        Issues ``GET /v1/workflows/{id}?fully_hydrate=true``, unwraps the
        ``WorkflowsResponse`` envelope, and validates the result with
        :class:`WorkflowConfigFullyHydrated`.

        Args:
            workflow_id:    ObjectId of the workflow.
            version_number: The version to hydrate. Without it, the server hydrates the workflow's own record.

        Requires the ``[configs]`` extra to be installed.
        """
        from interactly.configs import WorkflowConfigFullyHydrated

        raw = self._client.get(f"{_PATH}/{workflow_id}", params=_hydrate_params(version_number), cast_to=dict)
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

    def start_background_run(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        run_by: Optional[str] = None,
    ) -> BackgroundRunStarted:
        """Start the workflow now as a durable run in the background, with no user and no socket.

        It runs as a scheduled run does, so its nodes can wait on a timer, a signal, an external job or a person, and
        it can be paused, resumed, cancelled and signalled through ``client.runs``. The answer comes once the run
        exists; its first turn runs after it. A turn that ends waiting for a user's message fails the run: nothing
        would answer it.

        Args:
            version_number:    The version to run; the workflow's active version when unset.
            dynamic_variables: The run's dynamic variables, over the team's global variables.
            run_by:            Who started it, as Execution History shows it.

        Raises:
            NotFoundError: no such workflow, or version, in the team.
            ConflictError: durable runs aren't available on this server; nothing was started.
            RateLimitError: the workflow or team is at its concurrency limit.
        """
        return self._client.post(
            f"{_PATH}/{workflow_id}/background-runs",
            body={
                name: value
                for name, value in {
                    "version_number": version_number,
                    "dynamic_variables": dynamic_variables,
                    "run_by": run_by,
                }.items()
                if value is not None
            },
            cast_to=BackgroundRunStarted,
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
        """Retrieve a single workflow by ID; see :meth:`WorkflowsResource.get`."""
        return await self._client.get(f"{_PATH}/{workflow_id}", params={"find_active_version": True}, cast_to=Workflow)

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
        workflow_type: Union[WorkflowType, str, None] = None,
        logical_id: Optional[str] = None,
        categories: Optional[List[str]] = None,
        created_by: Optional[List[str]] = None,
        favorites: Optional[bool] = None,
    ) -> AsyncPage[Workflow]:
        """List workflows for the authenticated team; the filters are :meth:`WorkflowsResource.list`'s."""
        filters: Dict[str, Any] = dict(
            search=search,
            workflow_type=workflow_type,
            logical_id=logical_id,
            categories=categories,
            created_by=created_by,
            favorites=favorites,
        )
        raw = await self._client.get(_PATH, params=_list_params(page=page, size=size, **filters), cast_to=dict)

        async def fetch_page(p: int) -> AsyncPage[Workflow]:
            return await self.list(page=p, size=size, **filters)

        return AsyncPage._from_response(raw, Workflow, fetch_page, page=page, size=size)

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
        include_secrets: bool = False,
    ) -> Dict[str, Any]:
        """Export a workflow as a portable bundle dict; see :meth:`WorkflowsResource.export`."""
        return await self._client.get(
            f"{_PATH}/{workflow_id}/export",
            params=_export_params(version_numbers, active_version_number, include_secrets),
            cast_to=dict,
        )

    async def import_bundle(
        self,
        bundle: Dict[str, Any],
        *,
        versions_to_import: Optional[List[int]] = None,
        active_version_number: Optional[int] = None,
        workflow_name: Optional[str] = None,
        secret_overrides: Optional[Dict[str, str]] = None,
    ) -> Workflow:
        """Import a previously exported workflow bundle; see :meth:`WorkflowsResource.import_bundle`."""
        return await self._client.post(
            f"{_PATH}/import/bundle",
            body=_import_body(bundle, versions_to_import, active_version_number, workflow_name, secret_overrides),
            cast_to=Workflow,
        )

    async def usage(self, workflow_id: str) -> UsageReport:
        """The team's workflows that use this one; see :meth:`WorkflowsResource.usage`."""
        return await self._client.get(f"{_PATH}/{workflow_id}/usage", cast_to=UsageReport)

    async def schema(self) -> Dict[str, Any]:
        return await self._client.get(f"{_PATH}/schema", cast_to=dict)

    async def global_node_config_schema(self) -> Dict[str, Any]:
        return await self._client.get(f"{_PATH}/schemas/global-node-config", cast_to=dict)

    async def dynamic_variables(self, workflow_id: str, *, version_number: Optional[int] = None) -> Dict[str, Any]:
        """Return the dynamic variable definitions for a workflow; see :meth:`WorkflowsResource.dynamic_variables`."""
        return await self._client.get(
            f"{_PATH}/dynamic-variables/{workflow_id}",
            params=_version_and_model_params(version_number),
            cast_to=dict,
        )

    async def lints(self, workflow_id: str, *, version_number: Optional[int] = None) -> WorkflowLintReport:
        """Every advisory lint for a stored workflow, run against the whole graph. See the sync counterpart."""
        return await self._client.get(
            f"{_PATH}/{workflow_id}/lints",
            cast_to=WorkflowLintReport,
            params=_version_and_model_params(version_number),
        )

    async def realtime_compatibility(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
        model: Optional[str] = None,
        backend: Optional[str] = None,
    ) -> RealtimeCompatibilityReport:
        """Whether this workflow can run on a realtime model. See the sync counterpart."""
        return await self._client.get(
            f"{_PATH}/{workflow_id}/realtime-compatibility",
            cast_to=RealtimeCompatibilityReport,
            params=_version_and_model_params(version_number, model, backend),
        )

    async def counter_workflow(self, workflow_id: str) -> CounterWorkflowStatus:
        """The counter workflow generated from this one, and the newest generation's state."""
        return await self._client.get(f"{_PATH}/{workflow_id}/counter-workflow", cast_to=CounterWorkflowStatus)

    async def generate_counter_workflow(
        self,
        workflow_id: str,
        *,
        num_cases: int = 10,
        instructions: Optional[str] = None,
        version_number: Optional[int] = None,
        workflow_name: Optional[str] = None,
        new_workflow: bool = False,
        provider: Optional[str] = None,
    ) -> CounterGenerationState:
        """Start generating a counter workflow; returns immediately. See the sync counterpart."""
        body = _counter_generation_body(
            num_cases=num_cases,
            instructions=instructions,
            version_number=version_number,
            workflow_name=workflow_name,
            new_workflow=new_workflow,
            provider=provider,
        )
        raw: Dict[str, Any] = await self._client.post(
            f"{_PATH}/{workflow_id}/counter-workflow/generate", body=body, cast_to=dict
        )
        return CounterGenerationState.model_validate(raw.get("generation") or {})

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

    async def get_fully_hydrated(
        self, workflow_id: str, *, version_number: Optional[int] = None
    ) -> "WorkflowConfigFullyHydrated":
        """Async variant of :meth:`WorkflowsResource.get_fully_hydrated`."""
        from interactly.configs import WorkflowConfigFullyHydrated

        raw = await self._client.get(f"{_PATH}/{workflow_id}", params=_hydrate_params(version_number), cast_to=dict)
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

    async def start_background_run(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
        dynamic_variables: Optional[Dict[str, Any]] = None,
        run_by: Optional[str] = None,
    ) -> BackgroundRunStarted:
        """Start the workflow now as a durable run in the background, with no user and no socket.

        It runs as a scheduled run does, so its nodes can wait on a timer, a signal, an external job or a person, and
        it can be paused, resumed, cancelled and signalled through ``client.runs``. The answer comes once the run
        exists; its first turn runs after it. A turn that ends waiting for a user's message fails the run: nothing
        would answer it.

        Args:
            version_number:    The version to run; the workflow's active version when unset.
            dynamic_variables: The run's dynamic variables, over the team's global variables.
            run_by:            Who started it, as Execution History shows it.

        Raises:
            NotFoundError: no such workflow, or version, in the team.
            ConflictError: durable runs aren't available on this server; nothing was started.
            RateLimitError: the workflow or team is at its concurrency limit.
        """
        return await self._client.post(
            f"{_PATH}/{workflow_id}/background-runs",
            body={
                name: value
                for name, value in {
                    "version_number": version_number,
                    "dynamic_variables": dynamic_variables,
                    "run_by": run_by,
                }.items()
                if value is not None
            },
            cast_to=BackgroundRunStarted,
        )

    async def favorite(self, workflow_id: str) -> Dict[str, Any]:
        """Mark a workflow as a favorite for the requesting user (idempotent)."""
        return await self._client.post(f"{_PATH}/{workflow_id}/favorite", cast_to=dict)

    async def unfavorite(self, workflow_id: str) -> Dict[str, Any]:
        """Remove a workflow from the requesting user's favorites."""
        return await self._client.delete(f"{_PATH}/{workflow_id}/favorite", cast_to=dict)


def _export_params(version_numbers: List[int], active_version_number: int, include_secrets: bool) -> Dict[str, Any]:
    params: Dict[str, Any] = {"version_numbers": version_numbers, "active_version_number": active_version_number}
    if include_secrets:
        params["include_secrets"] = True
    return params


def _import_body(
    bundle: Dict[str, Any],
    versions_to_import: Optional[List[int]],
    active_version_number: Optional[int],
    workflow_name: Optional[str],
    secret_overrides: Optional[Dict[str, str]],
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"bundle": bundle}
    if versions_to_import is not None:
        body["versions_to_import"] = versions_to_import
    if active_version_number is not None:
        body["active_version_number"] = active_version_number
    if workflow_name is not None:
        body["workflow_name"] = workflow_name
    if secret_overrides:
        body["secret_overrides"] = secret_overrides
    return body


def _list_params(**params: Any) -> Dict[str, Any]:
    """A list's query: the parameters given, enums as their values."""
    return {name: (value.value if isinstance(value, Enum) else value) for name, value in params.items() if value is not None}


def _hydrate_params(version_number: Optional[int]) -> Dict[str, Any]:
    params: Dict[str, Any] = {"fully_hydrate": True}
    if version_number is not None:
        params["version_number"] = version_number
    return params
