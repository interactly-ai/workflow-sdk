"""Tools and workflow fields against a running server: accepted on write, intact on read.

`schema-check` proves the models match what the server publishes. These prove the server accepts what
the SDK sends and hands it back unchanged, for the fields that used to be dropped silently:

* ``ExternalAPIToolConfig.result_as_media`` on a saved tool. Before it was mirrored, reading the tool and
  writing it back turned a media result into a parsed one.
* ``WorkflowConfig.voice_persona``.
* ``realtime_overrides`` on an LLM node. Before ``NodeRealtimeOverrides`` was mirrored, reading the
  workflow and writing it back erased every per-node realtime setting.
* A tool node calling a codebase function. Before ``CodebaseFunctionToolConfig`` was mirrored, the whole
  node hydrated as ``UnknownNodeConfig``. Codebase functions are staff-only, so this skips for a
  credential the server refuses, and when the server has no function registered.

No LLM calls and no tool execution: everything is stored, read back and deleted. Each test cleans up
after itself and asserts nothing tagged with this run is left behind.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from interactly import AsyncWorkflowClient, PermissionDeniedError
from interactly.configs import (
    CodebaseFunctionToolConfig,
    ExternalAPIToolConfig,
    NodeRealtimeOverrides,
    PromptConfig,
    SayLLMNodeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    ToolNodeConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]

RUN_TAG = f"SDK_E2E_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


async def _sweep_workflows(client: AsyncWorkflowClient) -> list[str]:
    raw = await client.get("/v1/workflows", params={"page": 1, "size": 100}, cast_to=dict)
    residual = [
        str(w.get("_id") or w.get("id"))
        for w in raw.get("workflows", [])
        if RUN_TAG in ((w.get("workflow_config") or {}).get("name") or "")
    ]
    for workflow_id in residual:
        await client.workflows.delete(workflow_id)
    return residual


async def _sweep_tools(client: AsyncWorkflowClient) -> list[str]:
    page = await client.tools.list(search=RUN_TAG, size=50)
    residual = [tool.id for tool in page.items if tool.id and RUN_TAG in (tool.name or "")]
    for tool_id in residual:
        await client.tools.delete(tool_id)
    return residual


async def test_a_media_result_survives_on_a_saved_tool():
    client = AsyncWorkflowClient()
    tool_id: str | None = None
    try:
        # Arrange / Act
        created = await client.tools.create(
            tool_config=ExternalAPIToolConfig(
                name=f"{RUN_TAG} recording",
                api_endpoint="https://example.com/recordings/latest",
                result_as_media=True,
            )
        )
        tool_id = created.id
        fetched = await client.tools.get(tool_id)

        # Assert
        assert isinstance(fetched.tool_config, ExternalAPIToolConfig)
        assert fetched.tool_config.result_as_media is True
    finally:
        if tool_id:
            await client.tools.delete(tool_id)
        residual = await _sweep_tools(client)
        await client.close()
        assert not residual, f"residual SDK_E2E tools remained: {residual}"


async def test_a_voice_persona_survives_on_a_workflow():
    persona = "You are Ada, the scheduling assistant for Riverside Clinic. You are warm and brief."
    start = SayStaticMessageNodeConfig(
        name="Hello", is_start=True, static_messages_config=StaticMessagesConfig(static_messages=["Hi."])
    )
    config = WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=f"{RUN_TAG} persona", category="System Examples", voice_persona=persona),
        node_configs=[start],
        edge_configs=[],
    )
    client = AsyncWorkflowClient()
    workflow_id: str | None = None
    try:
        workflow_id = (await client.workflows.create_from_config(config)).id
        hydrated = await client.workflows.get_fully_hydrated(workflow_id)
        assert hydrated.workflow_config.voice_persona == persona
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        residual = await _sweep_workflows(client)
        await client.close()
        assert not residual, f"residual SDK_E2E workflows remained: {residual}"


async def test_a_codebase_function_tool_node_hydrates_typed():
    client = AsyncWorkflowClient()
    workflow_id: str | None = None
    try:
        try:
            listing = await client.get("/v1/tools/codebase-functions", cast_to=dict)
        except PermissionDeniedError:
            pytest.skip("codebase functions are staff-only and this credential is not")
        functions = listing.get("codebase_functions") or []
        if not functions:
            pytest.skip("the server has no codebase function registered")
        function_id = functions[0]["id"]

        node = ToolNodeConfig(
            name="Estimate",
            is_start=True,
            tool_config=CodebaseFunctionToolConfig(name="estimate", function_id=function_id),
        )
        config = WorkflowConfigFullyHydrated(
            workflow_config=WorkflowConfig(name=f"{RUN_TAG} codebase", category="System Examples"),
            node_configs=[node],
            edge_configs=[],
        )
        workflow_id = (await client.workflows.create_from_config(config)).id

        hydrated = await client.workflows.get_fully_hydrated(workflow_id)
        fetched = hydrated.node_configs[0]
        assert isinstance(fetched, ToolNodeConfig), f"hydrated as {type(fetched).__name__}"
        assert isinstance(fetched.tool_config, CodebaseFunctionToolConfig)
        assert fetched.tool_config.function_id == function_id
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        residual = await _sweep_workflows(client)
        await client.close()
        assert not residual, f"residual SDK_E2E workflows remained: {residual}"


async def test_realtime_overrides_survive_on_an_llm_node():
    node = SayLLMNodeConfig(
        name="Collect member ID",
        is_start=True,
        main_response_config=PromptConfig(prompt="Ask for the member ID."),
        realtime_overrides=NodeRealtimeOverrides(reasoning_effort="high", transcription_keywords=["Aetna", "Cigna"]),
    )
    config = WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=f"{RUN_TAG} realtime", category="System Examples"),
        node_configs=[node],
        edge_configs=[],
    )
    client = AsyncWorkflowClient()
    workflow_id: str | None = None
    try:
        workflow_id = (await client.workflows.create_from_config(config)).id
        fetched = (await client.workflows.get_fully_hydrated(workflow_id)).node_configs[0]
        assert isinstance(fetched, SayLLMNodeConfig)
        assert fetched.realtime_overrides is not None, "the server dropped realtime_overrides"
        assert fetched.realtime_overrides.reasoning_effort == "high"
        assert fetched.realtime_overrides.transcription_keywords == ["Aetna", "Cigna"]
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        residual = await _sweep_workflows(client)
        await client.close()
        assert not residual, f"residual SDK_E2E workflows remained: {residual}"
