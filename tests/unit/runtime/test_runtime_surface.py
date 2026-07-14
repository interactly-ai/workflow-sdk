"""Tests for the runtime surface and typed run params.

Covers Phase B (WorkflowRuntime / client.runtime / execute command coercion +
typed run_input / stream payload) and the Phase E create_from_config name fix.
"""

from __future__ import annotations

from typing import Any, Dict

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    AsyncWorkflowRuntime,
    WorkflowClient,
    WorkflowCommand,
    WorkflowRuntime,
)
from interactly.configs import (
    DirectEdgeConfig,
    LLMNodeRunInput,
    NodesRunInputs,
    OPENAIModel,
    OpenAILLMConfig,
    SayLLMNodeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
    WorkflowRunInput,
)
from interactly.resources.runs.runs import _build_execute_body, _build_stream_payload
from interactly.runtime.handle import AsyncRuntimeAccessor, RuntimeAccessor
from tests.conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    TEST_TEAM_ID,
    TEST_USER_ID,
    WORKFLOW_RESPONSE,
)


# --------------------------------------------------------------------------- #
# Builders                                                                     #
# --------------------------------------------------------------------------- #


def _config(name: str = "runtime-test") -> WorkflowConfigFullyHydrated:
    llm = OpenAILLMConfig(model=OPENAIModel.GPT_5_4_NANO, max_tokens=50)
    greeting = SayStaticMessageNodeConfig(
        name="g",
        is_start=True,
        static_messages_config=StaticMessagesConfig(static_messages=["hi"]),
    )
    say = SayLLMNodeConfig(name="s", llms_config=llm)
    edge = DirectEdgeConfig(
        source_node_logical_id=greeting.logical_id,
        destination_node_logical_id=say.logical_id,
    )
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=name),
        node_configs=[greeting, say],
        edge_configs=[edge],
    )


def _empty_input() -> WorkflowRunInput:
    return WorkflowRunInput(thread_to_node_inputs={}, dynamic_variables={})


def _exec_response(run_id: str, *, completed: bool = False) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "completed" if completed else "running",
        "turn_number": 1,
        "events": [],
        "is_waiting_for_input": not completed,
        "is_completed": completed,
        "error": None,
        "next_input_hint": None,
    }


@pytest.fixture
def client() -> WorkflowClient:
    return WorkflowClient(
        api_key=TEST_API_KEY, team_id=TEST_TEAM_ID, user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL, max_retries=0,
    )


@pytest.fixture
def async_client() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(
        api_key=TEST_API_KEY, team_id=TEST_TEAM_ID, user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL, max_retries=0,
    )


# --------------------------------------------------------------------------- #
# WorkflowRuntime.from_config                                                  #
# --------------------------------------------------------------------------- #


class TestWorkflowRuntime:
    @respx.mock
    def test_from_config_uploads_and_runs(self, client: WorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(return_value=httpx.Response(200, json=WORKFLOW_RESPONSE))
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-123/execute").mock(
            return_value=httpx.Response(200, json=_exec_response("run-1"))
        )

        runtime = WorkflowRuntime.from_config(_config(), client=client)
        assert isinstance(runtime, WorkflowRuntime)
        assert runtime.workflow_id == "wf-123"
        assert runtime.run_id is None

        list(runtime.run(_empty_input()))
        assert runtime.run_id == "run-1"

        runtime.reset()
        assert runtime.run_id is None

    @respx.mock
    async def test_async_from_config(self, async_client: AsyncWorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(return_value=httpx.Response(200, json=WORKFLOW_RESPONSE))
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-123/execute").mock(
            return_value=httpx.Response(200, json=_exec_response("run-9"))
        )

        runtime = await AsyncWorkflowRuntime.from_config(_config(), client=async_client)
        assert isinstance(runtime, AsyncWorkflowRuntime)
        assert runtime.workflow_id == "wf-123"

        events = [e async for e in runtime.arun(_empty_input())]
        assert isinstance(events, list)
        assert runtime.run_id == "run-9"

    @respx.mock
    def test_client_runtime_accessor(self, client: WorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(return_value=httpx.Response(200, json=WORKFLOW_RESPONSE))
        assert isinstance(client.runtime, RuntimeAccessor)

        runtime = client.runtime.from_config(_config())
        assert isinstance(runtime, WorkflowRuntime)
        # __call__ shorthand
        runtime2 = client.runtime(_config())
        assert isinstance(runtime2, WorkflowRuntime)

    async def test_async_client_runtime_accessor_type(self, async_client: AsyncWorkflowClient):
        assert isinstance(async_client.runtime, AsyncRuntimeAccessor)


# --------------------------------------------------------------------------- #
# execute() command coercion + typed run_input                                 #
# --------------------------------------------------------------------------- #


class TestExecuteBody:
    def test_command_enum_coerced_to_string(self):
        body = _build_execute_body(
            run_id=None, command=WorkflowCommand.STOP, run_by=None, version_number=None,
            dynamic_variables=None, runtime_variables=None, miscellaneous=None, run_input=None,
        )
        assert body["run_input"]["command"] == "stop"

    def test_command_string_passthrough(self):
        body = _build_execute_body(
            run_id="r", command="start", run_by=None, version_number=None,
            dynamic_variables=None, runtime_variables=None, miscellaneous=None, run_input=None,
        )
        assert body["run_input"]["command"] == "start"
        assert body["run_id"] == "r"

    def test_typed_run_input_forwarded(self):
        ri = WorkflowRunInput(thread_to_node_inputs={}, dynamic_variables={"k": "v"})
        body = _build_execute_body(
            run_id="r2", command="start", run_by=None, version_number=None,
            dynamic_variables=None, runtime_variables=None, miscellaneous=None, run_input=ri,
        )
        assert body["run_id"] == "r2"
        assert body["run_input"]["dynamic_variables"] == {"k": "v"}

    def test_typed_run_input_mutually_exclusive_with_loose_kwargs(self):
        ri = WorkflowRunInput(thread_to_node_inputs={}, dynamic_variables={})
        with pytest.raises(ValueError, match="either a typed"):
            _build_execute_body(
                run_id=None, command="stop", run_by=None, version_number=None,
                dynamic_variables=None, runtime_variables=None, miscellaneous=None, run_input=ri,
            )

    @respx.mock
    def test_execute_sends_coerced_command(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json=_exec_response("run-x"))

        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(side_effect=_capture)
        client.runs.execute("wf-1", command=WorkflowCommand.STOP)

        import json

        assert json.loads(captured["json"])["run_input"]["command"] == "stop"


# --------------------------------------------------------------------------- #
# stream payload                                                               #
# --------------------------------------------------------------------------- #


class TestStreamPayload:
    def test_minimal_payload(self):
        payload = _build_stream_payload(
            workflow_id="w", command=WorkflowCommand.START, run_by="api",
            version_number=None, dynamic_variables=None, runtime_variables=None, run_input=None,
        )
        # A bare command seeds the default thread "0" so the server accepts the
        # run (it rejects inputs with "Found 0 threads").
        assert payload == {
            "workflow_id": "w",
            "command": "start",
            "run_by": "api",
            "thread_to_node_inputs": {"0": {"node_run_inputs": []}},
        }

    def test_dynamic_variables_layered(self):
        payload = _build_stream_payload(
            workflow_id="w", command=WorkflowCommand.START, run_by="api",
            version_number=2, dynamic_variables={"a": 1}, runtime_variables={"b": 2}, run_input=None,
        )
        assert payload["dynamic_variables"] == {"a": 1}
        assert payload["runtime_variables"] == {"b": 2}
        assert payload["version_number"] == 2

    def test_typed_run_input_is_base(self):
        ri = WorkflowRunInput(thread_to_node_inputs={}, dynamic_variables={"k": "v"})
        payload = _build_stream_payload(
            workflow_id="w", command=WorkflowCommand.START, run_by="api",
            version_number=None, dynamic_variables=None, runtime_variables=None, run_input=ri,
        )
        assert payload["workflow_id"] == "w"
        assert payload["dynamic_variables"] == {"k": "v"}


# --------------------------------------------------------------------------- #
# create_from_config name promotion (Phase E fix)                              #
# --------------------------------------------------------------------------- #


class TestCreateFromConfigNamePromotion:
    @respx.mock
    def test_config_name_promoted_to_top_level(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json=WORKFLOW_RESPONSE)

        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(side_effect=_capture)
        client.workflows.create_from_config(_config(name="promoted-name"))

        import json

        body = json.loads(captured["json"])
        # The server reads name from the top level of the hydrated body.
        assert body["name"] == "promoted-name"
