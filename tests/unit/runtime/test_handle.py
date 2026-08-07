"""Tests for ``WorkflowHandle`` and ``AsyncWorkflowHandle``."""

from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    AsyncWorkflowHandle,
    WorkflowClient,
    WorkflowHandle,
    aupload_and_get_handle,
    upload_and_get_handle,
)
from interactly.configs import (
    DirectEdgeConfig,
    OpenAILLMConfig,
    OPENAIModel,
    SayLLMNodeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
    WorkflowRunInput,
)
from interactly.runtime.events import BaseEvent
from tests.conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    TEST_TEAM_ID,
    TEST_USER_ID,
    WORKFLOW_RESPONSE,
)

# --------------------------------------------------------------------------- #
# Test data builders                                                          #
# --------------------------------------------------------------------------- #


def _minimal_config() -> WorkflowConfigFullyHydrated:
    llm = OpenAILLMConfig(model=OPENAIModel.GPT_5_4_NANO, max_tokens=50)
    wf_cfg = WorkflowConfig(
        name="handle-test",
        description="",
        llms_config=llm,
        default_prompt_prefix="",
        default_prompt_suffix="",
    )
    greeting = SayStaticMessageNodeConfig(
        name="g",
        is_start=True,
        static_messages_config=StaticMessagesConfig(messages=["hi"]),
    )
    say = SayLLMNodeConfig(name="s", prompt_config=None, llms_config=llm)
    edge = DirectEdgeConfig(
        source_node_logical_id=greeting.logical_id,
        target_node_logical_id=say.logical_id,
    )
    return WorkflowConfigFullyHydrated(
        workflow_config=wf_cfg,
        node_configs=[greeting, say],
        edge_configs=[edge],
    )


def _empty_workflow_input() -> WorkflowRunInput:
    return WorkflowRunInput(
        thread_to_node_inputs={},
        dynamic_variables={},
    )


def _exec_response(run_id: str, events: List[Dict[str, Any]] | None = None, *, completed: bool = False) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "completed" if completed else "running",
        "turn_number": 1,
        "events": events or [],
        "is_waiting_for_input": not completed,
        "is_completed": completed,
        "error": None,
        "next_input_hint": None,
    }


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def client() -> WorkflowClient:
    return WorkflowClient(
        api_key=TEST_API_KEY,
        team_id=TEST_TEAM_ID,
        user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL,
        max_retries=0,
    )


@pytest.fixture
def async_client() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(
        api_key=TEST_API_KEY,
        team_id=TEST_TEAM_ID,
        user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL,
        max_retries=0,
    )


# --------------------------------------------------------------------------- #
# Sync handle                                                                  #
# --------------------------------------------------------------------------- #


class TestWorkflowHandleSync:
    @respx.mock
    def test_run_echoes_run_id_on_subsequent_turns(self, client: WorkflowClient):
        # Arrange — two consecutive turn responses; second one must include run_id from first.
        captured_requests: List[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            turn = len(captured_requests)
            return httpx.Response(200, json=_exec_response("rid-1", completed=(turn == 2)))

        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(side_effect=_handler)
        handle = WorkflowHandle(
            client=client,
            workflow_id="wf-1",
            config=_minimal_config(),
            dynamic_variables=None,
        )

        # Act — drive two turns.
        list(handle.run(_empty_workflow_input()))
        assert handle.run_id == "rid-1"
        list(handle.run(_empty_workflow_input()))

        # Assert
        import json

        first_body = json.loads(captured_requests[0].read())
        second_body = json.loads(captured_requests[1].read())
        assert "run_id" not in first_body
        assert second_body["run_id"] == "rid-1"

    @respx.mock
    def test_run_yields_typed_events(self, client: WorkflowClient):
        # Arrange — a single AssistantResponseEvent payload.
        event_payload = {
            "type": "assistant_response",
            "workflow_run_id": "rid-1",
            "thread_id": "t1",
            "node_logical_id": "n1",
            "response": "hello user",
        }
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_exec_response("rid-1", events=[event_payload]))
        )
        handle = WorkflowHandle(
            client=client,
            workflow_id="wf-1",
            config=_minimal_config(),
        )

        # Act
        events = list(handle.run(_empty_workflow_input()))

        # Assert — each yielded event is a typed BaseEvent subclass.
        assert len(events) == 1
        assert isinstance(events[0], BaseEvent)
        assert getattr(events[0], "type", None) == "assistant_response"

    @respx.mock
    def test_reset_clears_run_id(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_exec_response("rid-1"))
        )
        handle = WorkflowHandle(client=client, workflow_id="wf-1", config=_minimal_config())
        list(handle.run(_empty_workflow_input()))
        assert handle.run_id == "rid-1"

        # Act
        handle.reset()

        # Assert
        assert handle.run_id is None

    @respx.mock
    def test_handle_dynamic_variables_merge_under_input(self, client: WorkflowClient):
        # Arrange — handle defaults provide "company", caller overrides "company" and adds "user_name".
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["body"] = request.read()
            return httpx.Response(200, json=_exec_response("rid-1"))

        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(side_effect=_capture)
        handle = WorkflowHandle(
            client=client,
            workflow_id="wf-1",
            config=_minimal_config(),
            dynamic_variables={"company": "default-co", "region": "us"},
        )
        wf_input = WorkflowRunInput(
            thread_to_node_inputs={},
            dynamic_variables={"company": "override-co", "user_name": "alice"},
        )

        # Act
        list(handle.run(wf_input))

        # Assert — caller's value wins; missing keys filled from handle defaults.
        import json

        body = json.loads(captured["body"])
        dyn = body["run_input"]["dynamic_variables"]
        assert dyn["company"] == "override-co"
        assert dyn["user_name"] == "alice"
        assert dyn["region"] == "us"


# --------------------------------------------------------------------------- #
# Async handle                                                                 #
# --------------------------------------------------------------------------- #


class TestAsyncWorkflowHandle:
    @respx.mock
    async def test_arun_echoes_run_id(self, async_client: AsyncWorkflowClient):
        # Arrange
        captured: List[httpx.Request] = []

        def _handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=_exec_response("rid-2"))

        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-2/execute").mock(side_effect=_handler)
        handle = AsyncWorkflowHandle(
            client=async_client,
            workflow_id="wf-2",
            config=_minimal_config(),
        )

        # Act
        async for _ in handle.arun(_empty_workflow_input()):
            pass
        async for _ in handle.arun(_empty_workflow_input()):
            pass

        # Assert
        import json

        assert json.loads(captured[1].read())["run_id"] == "rid-2"

    @respx.mock
    async def test_arun_handles_unknown_event_type_gracefully(self, async_client: AsyncWorkflowClient):
        # Arrange — server adds a new event the SDK doesn't know about yet.
        unknown_event = {
            "type": "future_event_type_v999",
            "workflow_run_id": "rid-x",
            "thread_id": "t1",
        }
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-x/execute").mock(
            return_value=httpx.Response(200, json=_exec_response("rid-x", events=[unknown_event]))
        )
        handle = AsyncWorkflowHandle(
            client=async_client,
            workflow_id="wf-x",
            config=_minimal_config(),
        )

        # Act
        events = [e async for e in handle.arun(_empty_workflow_input())]

        # Assert — falls back to BaseEvent rather than raising.
        assert len(events) == 1
        assert isinstance(events[0], BaseEvent)


# --------------------------------------------------------------------------- #
# Convenience factories                                                       #
# --------------------------------------------------------------------------- #


class TestUploadAndGetHandle:
    @respx.mock
    def test_sync_factory_uploads_then_returns_handle(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(200, json=WORKFLOW_RESPONSE)
        )
        cfg = _minimal_config().model_dump(mode="json")
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-123").mock(
            return_value=httpx.Response(200, json={"workflow": cfg, "execution_url": ""})
        )

        # Act
        handle = upload_and_get_handle(client, _minimal_config(), dynamic_variables={"k": 1})

        # Assert
        assert isinstance(handle, WorkflowHandle)
        assert handle.workflow_id == "wf-123"

    @respx.mock
    async def test_async_factory_uploads_then_returns_handle(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(200, json=WORKFLOW_RESPONSE)
        )
        cfg = _minimal_config().model_dump(mode="json")
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-123").mock(
            return_value=httpx.Response(200, json={"workflow": cfg, "execution_url": ""})
        )

        # Act
        handle = await aupload_and_get_handle(async_client, _minimal_config())

        # Assert
        assert isinstance(handle, AsyncWorkflowHandle)
        assert handle.workflow_id == "wf-123"
