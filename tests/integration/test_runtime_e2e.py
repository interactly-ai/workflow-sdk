"""Integration (E2E) tests against a live Interactly server.

Skipped by default. Run with real dev credentials in the environment::

    export INTERACTLY_BASE_URL=... INTERACTLY_TEAM_ID=... \
           INTERACTLY_USER_ID=... INTERACTLY_API_KEY=...
    pytest tests/integration/ -m integration

Every asset created is tagged with a unique RUN_TAG and torn down in a
``finally`` block; a verification sweep asserts zero residual ``SDK_E2E_*``
workflows remain in the org.

Coverage:
    * ``create_from_config`` CRUD lifecycle (create/get/list/delete + cleanup).
    * **Turn execution** of a static workflow via ``AsyncWorkflowRuntime`` —
      asserts the deterministic ``AssistantResponseEvent`` contents and that the
      run reaches a terminal ``EndWorkflowEvent`` with no ``WorkflowErrorEvent``.
    * **Turn execution** of an LLM workflow — asserts a real, non-empty
      assistant response is produced by the model (opt-in via ``--run-llm`` or
      ``INTERACTLY_RUN_LLM=1`` since it consumes model tokens).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from interactly import AsyncWorkflowClient, NotFoundError
from interactly.configs import (
    DirectEdgeConfig,
    LLMNodeRunInput,
    NodesRunInputs,
    OpenAILLMConfig,
    OPENAIModel,
    PromptConfig,
    SayLLMNodeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
    WorkflowRunInput,
)
from interactly.runtime import AsyncWorkflowRuntime
from interactly.runtime.events import (
    AssistantResponseEvent,
    EndWorkflowEvent,
    WorkflowErrorEvent,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]

RUN_TAG = f"SDK_E2E_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid.uuid4().hex[:6]}"


def _tiny_config(name: str) -> WorkflowConfigFullyHydrated:
    a = SayStaticMessageNodeConfig(
        name="A", is_start=True, static_messages_config=StaticMessagesConfig(static_messages=["hi"])
    )
    b = SayStaticMessageNodeConfig(
        name="B", static_messages_config=StaticMessagesConfig(static_messages=["bye"])
    )
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=f"{RUN_TAG} {name}", category="System Examples"),
        node_configs=[a, b],
        edge_configs=[
            DirectEdgeConfig(source_node_logical_id=a.logical_id, destination_node_logical_id=b.logical_id, name="a->b")
        ],
    )


async def _sweep(client: AsyncWorkflowClient) -> list[str]:
    """Delete any workflows whose name carries our RUN_TAG; return residuals."""
    raw = await client.get("/v1/workflows", params={"page": 1, "size": 100}, cast_to=dict)
    residual = [
        str(w.get("_id") or w.get("id"))
        for w in raw.get("workflows", [])
        if RUN_TAG in ((w.get("workflow_config") or {}).get("name") or "")
    ]
    for wid in residual:
        await client.workflows.delete(wid)
    return residual


async def test_create_from_config_lifecycle_and_cleanup():
    """create_from_config persists the name, is get/list-able, deletes to 404, leaves no residue."""
    client = AsyncWorkflowClient()
    created_id: str | None = None
    try:
        wf = await client.workflows.create_from_config(_tiny_config("crud"))
        created_id = wf.id
        # name persisted (Phase E fix: top-level name in hydrated body)
        assert RUN_TAG in (wf.name or ""), f"name not persisted: {wf.name!r}"

        got = await client.workflows.get(wf.id)
        assert got.id == wf.id

        page = await client.workflows.list(size=100, search="SDK_E2E")
        assert any(w.id == wf.id for w in page.items)

        await client.workflows.delete(wf.id)
        created_id = None
        with pytest.raises(NotFoundError):
            await client.workflows.get(wf.id)
    finally:
        if created_id:
            try:
                await client.workflows.delete(created_id)
            except Exception:  # noqa: BLE001
                pass
        residual = await _sweep(client)
        await client.close()
        assert not residual, f"residual SDK_E2E assets remained: {residual}"


async def test_static_workflow_turn_execution_reaches_terminal():
    """A static two-node workflow executes a turn end-to-end via the runtime.

    Drives the exact ``create_from_config -> AsyncWorkflowRuntime.from_config ->
    arun`` path that the SDK exposes as its runtime surface, and asserts the
    deterministic outcome: the two static messages are spoken, the run reaches a
    terminal ``EndWorkflowEvent``, and no ``WorkflowErrorEvent`` is emitted.
    """
    client = AsyncWorkflowClient()
    runtime: AsyncWorkflowRuntime | None = None
    try:
        runtime = await AsyncWorkflowRuntime.from_config(_tiny_config("turn"), client=client)
        run_input = WorkflowRunInput(thread_to_node_inputs={"0": NodesRunInputs(node_run_inputs=[])})

        events = [event async for event in runtime.arun(run_input)]

        errors = [e for e in events if isinstance(e, WorkflowErrorEvent)]
        assert not errors, f"unexpected workflow errors: {[e.model_dump() for e in errors]}"

        spoken = [e.content for e in events if isinstance(e, AssistantResponseEvent)]
        assert spoken == ["hi", "bye"], f"unexpected assistant contents: {spoken}"

        assert any(isinstance(e, EndWorkflowEvent) for e in events), "run did not reach EndWorkflowEvent"
        assert runtime.run_id, "run_id was not recorded after the turn"
    finally:
        if runtime is not None:
            try:
                await client.workflows.delete(runtime.workflow_id)
            except Exception:  # noqa: BLE001
                pass
        residual = await _sweep(client)
        await client.close()
        assert not residual, f"residual SDK_E2E assets remained: {residual}"


def _llm_config(name: str) -> WorkflowConfigFullyHydrated:
    """A minimal single-LLM-turn workflow: greet with the model, then end statically."""
    greeting = SayLLMNodeConfig(
        name="Greeting",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt="Greet the user warmly in fewer than 10 words."),
        llms_config=OpenAILLMConfig(model=OPENAIModel.GPT_5_4_NANO, max_tokens=100, temperature=0.5),
    )
    end = SayStaticMessageNodeConfig(
        name="End", static_messages_config=StaticMessagesConfig(static_messages=["Goodbye!"])
    )
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=f"{RUN_TAG} {name}", category="System Examples"),
        node_configs=[greeting, end],
        edge_configs=[
            DirectEdgeConfig(
                source_node_logical_id=greeting.logical_id,
                destination_node_logical_id=end.logical_id,
                name="greet->end",
            )
        ],
    )


@pytest.mark.skipif(
    not os.environ.get("INTERACTLY_RUN_LLM"),
    reason="LLM turn test consumes model tokens; opt in with INTERACTLY_RUN_LLM=1",
)
async def test_llm_workflow_turn_execution_produces_real_response():
    """An LLM node executes a real turn and yields non-empty model-generated text.

    Opt-in (``INTERACTLY_RUN_LLM=1``) because it spends provider tokens. Asserts
    the greeting LLM node produced a real, non-empty assistant response and that
    the run completed without a ``WorkflowErrorEvent``.
    """
    client = AsyncWorkflowClient()
    runtime: AsyncWorkflowRuntime | None = None
    try:
        runtime = await AsyncWorkflowRuntime.from_config(_llm_config("llm"), client=client)
        run_input = WorkflowRunInput(
            thread_to_node_inputs={
                "0": NodesRunInputs(node_run_inputs=[LLMNodeRunInput(messages=[])])
            }
        )

        events = [event async for event in runtime.arun(run_input)]

        errors = [e for e in events if isinstance(e, WorkflowErrorEvent)]
        assert not errors, f"unexpected workflow errors: {[e.model_dump() for e in errors]}"

        spoken = [e.content for e in events if isinstance(e, AssistantResponseEvent) and (e.content or "").strip()]
        assert spoken, "LLM node produced no assistant text"
        # The static end message is deterministic; there must be at least one
        # model-generated line *before* the static goodbye.
        assert spoken[0] != "Goodbye!", f"expected real LLM greeting, got only static: {spoken}"
    finally:
        if runtime is not None:
            try:
                await client.workflows.delete(runtime.workflow_id)
            except Exception:  # noqa: BLE001
                pass
        residual = await _sweep(client)
        await client.close()
        assert not residual, f"residual SDK_E2E assets remained: {residual}"
