"""
Top-level client classes: WorkflowClient (sync) and AsyncWorkflowClient (async).

These are the primary entry points into the SDK.  All resource access goes
through an instance of one of these classes.

Quick start::

    from interactly import WorkflowClient

    client = WorkflowClient(
        api_key="your_api_key",
        team_id="your_team_id",
        user_id="your_user_id",
    )
    workflow = client.workflows.create(name="Hello World")
    print(workflow.id)

Async quick start::

    import asyncio
    from interactly import AsyncWorkflowClient

    async def main():
        async with AsyncWorkflowClient(
            api_key="your_api_key",
            team_id="your_team_id",
            user_id="your_user_id",
        ) as client:
            workflow = await client.workflows.create(name="Hello World")
            print(workflow.id)

    asyncio.run(main())
"""

from __future__ import annotations

import httpx

from interactly._base_client import AsyncAPIClient, SyncAPIClient
from interactly.resources.categories.categories import AsyncCategoriesResource, CategoriesResource
from interactly.resources.edges.edges import AsyncEdgesResource, EdgesResource
from interactly.resources.global_variables.global_variables import AsyncGlobalVariablesResource, GlobalVariablesResource
from interactly.resources.llm_configs.llm_configs import AsyncLLMConfigsResource, LLMConfigsResource
from interactly.resources.node_libraries.node_libraries import AsyncNodeLibrariesResource, NodeLibrariesResource
from interactly.resources.nodes.nodes import AsyncNodesResource, NodesResource
from interactly.resources.runs.runs import AsyncRunsResource, RunsResource
from interactly.resources.schedules.schedules import AsyncSchedulesResource, SchedulesResource
from interactly.resources.simulations.simulations import AsyncSimulationsResource, SimulationsResource
from interactly.resources.super_nodes.super_nodes import AsyncSuperNodesResource, SuperNodesResource
from interactly.resources.templates.templates import AsyncTemplatesResource, TemplatesResource
from interactly.resources.tools.tools import AsyncToolsResource, ToolsResource
from interactly.resources.webhooks.webhooks import AsyncWorkflowWebhooksResource, WorkflowWebhooksResource
from interactly.resources.workflows.workflows import AsyncWorkflowsResource, WorkflowsResource
from interactly.runtime.handle import AsyncRuntimeAccessor, RuntimeAccessor

__all__ = ["WorkflowClient", "AsyncWorkflowClient"]


class WorkflowClient(SyncAPIClient):
    """
    Synchronous client for the Interactly Workflow API.

    All I/O operations block until complete.  For concurrent workloads
    prefer ``AsyncWorkflowClient``.

    Args:
        api_key:      Bearer token. Reads from INTERACTLY_API_KEY env var if omitted.
        team_id:      Team identifier. Reads from INTERACTLY_TEAM_ID env var if omitted.
        user_id:      User identifier. Reads from INTERACTLY_USER_ID env var if omitted.
        base_url:     Override server URL. Reads from INTERACTLY_BASE_URL env var if omitted.
        timeout:      Request timeout in seconds (default: 60 s).
        max_retries:  Retry attempts on transient failures (default: 2).
        http_client:  Custom httpx.Client for full transport control.

    Attributes:
        workflows:        :class:`WorkflowsResource` — CRUD for workflows.
        runs:             :class:`RunsResource` — list / get / stream workflow runs.
        webhooks:         :class:`WorkflowWebhooksResource` — manage webhook subscriptions.
        schedules:        :class:`SchedulesResource` — manage scheduled workflow runs.
        templates:        :class:`TemplatesResource` — CRUD for workflow templates.
        categories:       :class:`CategoriesResource` — read workflow categories.
        nodes:            :class:`NodesResource` — CRUD for standalone nodes.
        edges:            :class:`EdgesResource` — CRUD for standalone edges.
        super_nodes:      :class:`SuperNodesResource` — manage super node publications.
        tools:            :class:`ToolsResource` — CRUD for custom LLM tools.
        global_variables: :class:`GlobalVariablesResource` — manage team-scoped global variables.
        node_libraries:   :class:`NodeLibrariesResource` — manage node library packages.
        simulations:      :class:`SimulationsResource` — manage simulation configs and runs.
        llm_configs:      :class:`LLMConfigsResource` — manage saved (named) LLM configs.
        runtime:          :class:`RuntimeAccessor` — ``runtime.from_config(config)``.
    """

    workflows: WorkflowsResource
    runs: RunsResource
    webhooks: WorkflowWebhooksResource
    schedules: SchedulesResource
    templates: TemplatesResource
    categories: CategoriesResource
    nodes: NodesResource
    edges: EdgesResource
    super_nodes: SuperNodesResource
    tools: ToolsResource
    global_variables: GlobalVariablesResource
    node_libraries: NodeLibrariesResource
    simulations: SimulationsResource
    llm_configs: LLMConfigsResource
    runtime: RuntimeAccessor

    def __init__(
        self,
        api_key: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
        base_url: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            team_id=team_id,
            user_id=user_id,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self.workflows = WorkflowsResource(self)
        self.runs = RunsResource(self)
        self.webhooks = WorkflowWebhooksResource(self)
        self.schedules = SchedulesResource(self)
        self.templates = TemplatesResource(self)
        self.categories = CategoriesResource(self)
        self.nodes = NodesResource(self)
        self.edges = EdgesResource(self)
        self.super_nodes = SuperNodesResource(self)
        self.tools = ToolsResource(self)
        self.global_variables = GlobalVariablesResource(self)
        self.node_libraries = NodeLibrariesResource(self)
        self.simulations = SimulationsResource(self)
        self.llm_configs = LLMConfigsResource(self)
        # Framework-shaped runtime: client.runtime.from_config(config) / client.runtime(config)
        self.runtime = RuntimeAccessor(self)


class AsyncWorkflowClient(AsyncAPIClient):
    """
    Async client for the Interactly Workflow API.

    Use as an async context manager for automatic connection cleanup::

        async with AsyncWorkflowClient(api_key=..., team_id=..., user_id=...) as client:
            wf = await client.workflows.get("my-id")

    Or instantiate directly and call ``await client.close()`` when done.

    Attributes:
        workflows:        :class:`AsyncWorkflowsResource` — async CRUD for workflows.
        runs:             :class:`AsyncRunsResource` — async list / get / stream runs.
        webhooks:         :class:`AsyncWorkflowWebhooksResource` — manage webhook subscriptions.
        schedules:        :class:`AsyncSchedulesResource` — manage scheduled workflow runs.
        templates:        :class:`AsyncTemplatesResource` — CRUD for workflow templates.
        categories:       :class:`AsyncCategoriesResource` — read workflow categories.
        nodes:            :class:`AsyncNodesResource` — CRUD for standalone nodes.
        edges:            :class:`AsyncEdgesResource` — CRUD for standalone edges.
        super_nodes:      :class:`AsyncSuperNodesResource` — manage super node publications.
        tools:            :class:`AsyncToolsResource` — CRUD for custom LLM tools.
        global_variables: :class:`AsyncGlobalVariablesResource` — manage team-scoped global variables.
        node_libraries:   :class:`AsyncNodeLibrariesResource` — manage node library packages.
        simulations:      :class:`AsyncSimulationsResource` — manage simulation configs and runs.
        llm_configs:      :class:`AsyncLLMConfigsResource` — manage saved (named) LLM configs.
        runtime:          :class:`AsyncRuntimeAccessor` — ``await runtime.from_config(config)``.
    """

    workflows: AsyncWorkflowsResource
    runs: AsyncRunsResource
    webhooks: AsyncWorkflowWebhooksResource
    schedules: AsyncSchedulesResource
    templates: AsyncTemplatesResource
    categories: AsyncCategoriesResource
    nodes: AsyncNodesResource
    edges: AsyncEdgesResource
    super_nodes: AsyncSuperNodesResource
    tools: AsyncToolsResource
    global_variables: AsyncGlobalVariablesResource
    node_libraries: AsyncNodeLibrariesResource
    simulations: AsyncSimulationsResource
    llm_configs: AsyncLLMConfigsResource
    runtime: AsyncRuntimeAccessor

    def __init__(
        self,
        api_key: str | None = None,
        team_id: str | None = None,
        user_id: str | None = None,
        base_url: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        max_retries: int | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            team_id=team_id,
            user_id=user_id,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
        )
        self.workflows = AsyncWorkflowsResource(self)
        self.runs = AsyncRunsResource(self)
        self.webhooks = AsyncWorkflowWebhooksResource(self)
        self.schedules = AsyncSchedulesResource(self)
        self.templates = AsyncTemplatesResource(self)
        self.categories = AsyncCategoriesResource(self)
        self.nodes = AsyncNodesResource(self)
        self.edges = AsyncEdgesResource(self)
        self.super_nodes = AsyncSuperNodesResource(self)
        self.tools = AsyncToolsResource(self)
        self.global_variables = AsyncGlobalVariablesResource(self)
        self.node_libraries = AsyncNodeLibrariesResource(self)
        self.simulations = AsyncSimulationsResource(self)
        self.llm_configs = AsyncLLMConfigsResource(self)
        # Framework-shaped runtime: await client.runtime.from_config(config)
        self.runtime = AsyncRuntimeAccessor(self)
