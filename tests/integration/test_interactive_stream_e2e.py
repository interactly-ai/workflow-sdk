"""One stream holds a whole conversation: each later turn goes as a ``resume`` frame, and ``stop()`` cancels the run.

The workflow's one node waits for the user's message, then answers through an LLM gateway whose host can never resolve
(the ``.invalid`` domain is reserved for exactly that). The first turn makes no LLM call, and the second fails at once
without reaching any provider. The server tolerates that failure: the turn ends with ``workflow_error`` and the socket
stays open for the next message. No LLM is billed; the workflow it uploads is deleted.

    pytest tests/integration/test_interactive_stream_e2e.py -m integration
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Callable, List

import pytest

from interactly import (
    AsyncStream,
    AsyncWorkflowClient,
    StreamNotFoundError,
    StreamServerError,
    TakeBackRefusedError,
)
from interactly.configs import CustomLLMConfig, SayLLMNodeConfig, WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.types.runs.run_event import RunEvent

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]

#: Long enough for a turn on a busy dev server; a stream that never hands over fails rather than hangs.
_TURN_TIMEOUT_SECONDS = 60


def _unreachable_llm() -> CustomLLMConfig:
    return CustomLLMConfig(
        base_url="https://llm.unreachable.invalid/v1",
        model="none",
        api_key="unused",
        max_retries=0,
        request_timeout_ms=2000,
        streaming=False,
    )


def _conversation_workflow(**settings: Any) -> WorkflowConfigFullyHydrated:
    """One node that waits for the user and answers through a gateway that can never be reached, so each turn after
    the first fails at once. ``settings`` go into the workflow's ``miscellaneous``, where its error limits live."""
    ask = SayLLMNodeConfig(
        name="Ask", is_start=True, llms_config=_unreachable_llm(), wait_for_user_message=True, self_loop=True
    )
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(
            name=f"SDK_E2E interactive stream {uuid.uuid4().hex[:8]}",
            llms_config=_unreachable_llm(),
            miscellaneous=settings,
        ),
        node_configs=[ask],
        edge_configs=[],
    )


async def _read_until(stream: AsyncStream[RunEvent], done: Callable[[RunEvent], bool], seen: List[RunEvent]) -> None:
    async def read() -> None:
        async for event in stream:
            seen.append(event)
            if done(event):
                return

    await asyncio.wait_for(read(), _TURN_TIMEOUT_SECONDS)


def _user_texts(events: List[RunEvent]) -> List[str]:
    return [
        message.get("content")
        for event in events
        if event.type == "user_messages"
        for message in (event.model_extra or {}).get("messages") or []
    ]


async def test_one_stream_holds_a_conversation_and_stop_cancels_the_run():
    client = AsyncWorkflowClient()
    workflow_id = None
    try:
        workflow_id = (await client.workflows.create_from_config(_conversation_workflow())).id
        first: List[RunEvent] = []
        second: List[RunEvent] = []
        after_stop: List[RunEvent] = []

        async with client.runs.stream(workflow_id=workflow_id) as stream:
            await _read_until(stream, lambda e: e.is_ready_for_input(), first)
            await stream.send("hello there")
            await _read_until(stream, lambda e: e.type == "workflow_error", second)
            await stream.stop()
            await _read_until(stream, lambda e: False, after_stop)
            run_id = stream.run_id

        run = await client.runs.get(run_id)
        # The first turn hands over once, at its end: no fork companion runs, so the stream marks it.
        assert [e.type for e in first if e.is_ready_for_input()] == ["end_workflow_iteration"]
        assert _user_texts(second) == ["hello there"]
        assert any("stopped successfully" in str((e.model_extra or {}).get("message")) for e in after_stop)
        assert (run.status, run.termination_source) == ("cancelled", "client_stop")
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()


async def test_a_turn_sent_before_the_first_ends_is_taken_after_it():
    # The server reads the socket only between turns, so a turn sent early waits rather than being refused or lost.
    client = AsyncWorkflowClient()
    workflow_id = None
    try:
        workflow_id = (await client.workflows.create_from_config(_conversation_workflow())).id
        events: List[RunEvent] = []

        async with client.runs.stream(workflow_id=workflow_id) as stream:
            await stream.send("sent straight away")
            await _read_until(stream, lambda e: e.type == "workflow_error", events)
            await stream.stop()

        kinds = [e.type for e in events]
        assert kinds.index("end_workflow_iteration") < kinds.index("user_messages")
        assert _user_texts(events) == ["sent straight away"]
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()


async def test_taking_back_a_run_that_does_not_exist_raises_not_found():
    client = AsyncWorkflowClient()
    workflow_id = None
    try:
        workflow_id = (await client.workflows.create_from_config(_conversation_workflow())).id
        try:
            async with client.runs.stream(workflow_id=workflow_id, workflow_run_id="0" * 24) as stream:
                await _read_until(stream, lambda e: False, [])
        except TakeBackRefusedError as refused:
            # Checked before the run is looked up: a server without durable socket runs refuses every take-back.
            if "can't be continued in the editor here" in str(refused.server_message):
                pytest.skip("durable socket runs are off on this server, so no run can be taken back")
            raise
        pytest.fail("taking back a run that does not exist was not refused")
    except StreamNotFoundError as missing:
        assert missing.code == 4040
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()


async def test_a_failure_the_server_tolerates_ends_only_its_turn():
    # Under the default error limits the server tolerates the node's failure: the error is the turn's last frame, the
    # socket stays open, and the next message runs.
    client = AsyncWorkflowClient()
    workflow_id = None
    try:
        workflow_id = (await client.workflows.create_from_config(_conversation_workflow())).id
        failed: List[RunEvent] = []
        again: List[RunEvent] = []

        async with client.runs.stream(workflow_id=workflow_id) as stream:
            await _read_until(stream, lambda e: e.is_ready_for_input(), [])
            await stream.send("first")
            await _read_until(stream, lambda e: e.type == "workflow_error", failed)
            await stream.send("second")
            await _read_until(stream, lambda e: e.type == "workflow_error", again)
            await stream.stop()
            await _read_until(stream, lambda e: False, [])

        error = failed[-1]
        assert (error.fatal, error.is_terminal(), error.is_ready_for_input()) == (False, False, True)
        assert _user_texts(again) == ["second"]
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()


async def test_a_workflow_that_stops_on_error_ends_the_stream_with_a_server_error():
    # The server sends the tolerated error before it checks the workflow's error settings; stopping on error, it then
    # sends the whole reason in a last error and closes the socket with 1011.
    client = AsyncWorkflowClient()
    workflow_id = None
    try:
        workflow_id = (
            await client.workflows.create_from_config(_conversation_workflow(stop_workflow_on_error="true"))
        ).id
        seen: List[RunEvent] = []

        with pytest.raises(StreamServerError) as caught:
            async with client.runs.stream(workflow_id=workflow_id) as stream:
                await _read_until(stream, lambda e: e.is_ready_for_input(), [])
                await stream.send("hello")
                await _read_until(stream, lambda e: False, seen)

        errors = [e for e in seen if e.type == "workflow_error"]
        assert errors[0].is_ready_for_input() and not errors[0].is_terminal()
        assert errors[-1].is_terminal()
        assert caught.value.code == 1011
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()
