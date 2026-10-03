"""The LLM catalogue against a running server: what the SDK sends is accepted, and survives a round trip.

`schema-check` proves the models match the schemas the server *publishes*. It cannot prove the server
*accepts* a config built from them, or that reading a config back and writing it again keeps every field.
Those are the two ways the new providers could still fail a customer, so both are driven here:

* **Create → read → update → read**, with no LLM call. A Grok node, a Gemini 3.8 node with a thinking
  level and a pinned backend, and an Anthropic node on the Vertex backend. Before these models were
  mirrored, the first two came back as `UnknownNodeConfig` and the third lost its backend on the way back.
* **One real Grok turn**, opt-in with ``INTERACTLY_RUN_LLM=1`` because it spends provider tokens. Proves
  the server executes the new provider, not merely stores it.

Every workflow is tagged and swept, and the sweep asserts nothing was left behind.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from interactly import AsyncWorkflowClient
from interactly.configs import (
    AnthropicBackend,
    AnthropicLLMConfig,
    ANTHROPICModel,
    DirectEdgeConfig,
    GeminiThinkingLevel,
    GoogleBackend,
    GoogleLLMConfig,
    GOOGLEModel,
    LLMNodeRunInput,
    NodesRunInputs,
    PromptConfig,
    SayLLMNodeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
    WorkflowRunInput,
    XAILLMConfig,
    XAIModel,
)
from interactly.runtime import AsyncWorkflowRuntime
from interactly.runtime.events import AssistantResponseEvent, WorkflowErrorEvent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]

RUN_TAG = f"SDK_E2E_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


async def _sweep(client: AsyncWorkflowClient) -> list[str]:
    """Delete any workflow whose name carries this run's tag; return what had been left behind."""
    raw = await client.get("/v1/workflows", params={"page": 1, "size": 100}, cast_to=dict)
    residual = [
        str(w.get("_id") or w.get("id"))
        for w in raw.get("workflows", [])
        if RUN_TAG in ((w.get("workflow_config") or {}).get("name") or "")
    ]
    for workflow_id in residual:
        await client.workflows.delete(workflow_id)
    return residual


def _three_provider_config() -> WorkflowConfigFullyHydrated:
    grok = SayLLMNodeConfig(
        name="Grok",
        is_start=True,
        main_response_config=PromptConfig(prompt="Say hello."),
        llms_config=XAILLMConfig(model=XAIModel.GROK_4_1_FAST_NON_REASONING, max_tokens=40),
    )
    gemini = SayLLMNodeConfig(
        name="Gemini",
        main_response_config=PromptConfig(prompt="Say hello."),
        llms_config=GoogleLLMConfig(
            model=GOOGLEModel.GEMINI_3_8_FLASH, thinking_level="low", backend=GoogleBackend.VERTEX
        ),
    )
    claude = SayLLMNodeConfig(
        name="Claude",
        main_response_config=PromptConfig(prompt="Say hello."),
        llms_config=AnthropicLLMConfig(model=ANTHROPICModel.CLAUDE_SONNET_4_6, backend=AnthropicBackend.VERTEX),
    )
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=f"{RUN_TAG} catalogue", category="System Examples"),
        node_configs=[grok, gemini, claude],
        edge_configs=[
            DirectEdgeConfig(source_node_logical_id=grok.logical_id, destination_node_logical_id=gemini.logical_id),
            DirectEdgeConfig(source_node_logical_id=gemini.logical_id, destination_node_logical_id=claude.logical_id),
        ],
    )


def _assert_new_fields_intact(hydrated: WorkflowConfigFullyHydrated) -> None:
    by_name = {node.name: node for node in hydrated.node_configs}
    for name in ("Grok", "Gemini", "Claude"):
        assert type(by_name[name]).__name__ == "SayLLMNodeConfig", f"{name} lost its node type"

    grok = by_name["Grok"].llms_config
    assert isinstance(grok, XAILLMConfig)
    assert grok.model is XAIModel.GROK_4_1_FAST_NON_REASONING

    gemini = by_name["Gemini"].llms_config
    assert isinstance(gemini, GoogleLLMConfig)
    assert gemini.model is GOOGLEModel.GEMINI_3_8_FLASH
    assert gemini.thinking_level is GeminiThinkingLevel.LOW
    assert gemini.backend is GoogleBackend.VERTEX

    claude = by_name["Claude"].llms_config
    assert isinstance(claude, AnthropicLLMConfig)
    assert claude.backend is AnthropicBackend.VERTEX


async def test_new_providers_survive_create_read_update_read():
    client = AsyncWorkflowClient()
    workflow_id: str | None = None
    try:
        # Arrange / Act: create, then read back.
        workflow = await client.workflows.create_from_config(_three_provider_config())
        workflow_id = workflow.id
        _assert_new_fields_intact(await client.workflows.get_fully_hydrated(workflow_id))

        # Act: the read-then-write an SDK user does — fetch a node, change one field, send it back.
        page = await client.nodes.list(workflow_id=workflow_id, size=20)
        claude_node = next(n for n in page.items if n.node_config.name == "Claude")
        edited = claude_node.node_config
        edited.name = "Claude (edited)"
        await client.nodes.update(claude_node.id, node_config=edited)

        # Assert: the edit landed and nothing else was lost on the way through.
        hydrated = await client.workflows.get_fully_hydrated(workflow_id)
        names = {node.name for node in hydrated.node_configs}
        assert "Claude (edited)" in names
        for node in hydrated.node_configs:
            if node.name == "Claude (edited)":
                node.name = "Claude"
        _assert_new_fields_intact(hydrated)
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        residual = await _sweep(client)
        await client.close()
        assert not residual, f"residual SDK_E2E assets remained: {residual}"


@pytest.mark.skipif(
    not os.environ.get("INTERACTLY_RUN_LLM"),
    reason="spends provider tokens; opt in with INTERACTLY_RUN_LLM=1",
)
async def test_a_grok_node_produces_a_real_reply():
    greeting = SayLLMNodeConfig(
        name="Greeting",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt="Greet the user warmly in fewer than 10 words."),
        llms_config=XAILLMConfig(model=XAIModel.GROK_4_1_FAST_NON_REASONING, max_tokens=60),
    )
    end = SayStaticMessageNodeConfig(
        name="End", static_messages_config=StaticMessagesConfig(static_messages=["Goodbye!"])
    )
    config = WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=f"{RUN_TAG} grok-turn", category="System Examples"),
        node_configs=[greeting, end],
        edge_configs=[
            DirectEdgeConfig(source_node_logical_id=greeting.logical_id, destination_node_logical_id=end.logical_id)
        ],
    )
    client = AsyncWorkflowClient()
    runtime: AsyncWorkflowRuntime | None = None
    try:
        runtime = await AsyncWorkflowRuntime.from_config(config, client=client)
        run_input = WorkflowRunInput(
            thread_to_node_inputs={"0": NodesRunInputs(node_run_inputs=[LLMNodeRunInput(messages=[])])}
        )

        events = [event async for event in runtime.arun(run_input)]

        errors = [e for e in events if isinstance(e, WorkflowErrorEvent)]
        assert not errors, f"workflow errors: {[e.model_dump() for e in errors]}"
        spoken = [e.content for e in events if isinstance(e, AssistantResponseEvent) and (e.content or "").strip()]
        assert spoken and spoken[0] != "Goodbye!", f"expected a Grok greeting before the static goodbye, got {spoken}"
    finally:
        if runtime is not None:
            try:
                await client.workflows.delete(runtime.workflow_id)
            except Exception:  # noqa: BLE001
                pass
        residual = await _sweep(client)
        await client.close()
        assert not residual, f"residual SDK_E2E assets remained: {residual}"
