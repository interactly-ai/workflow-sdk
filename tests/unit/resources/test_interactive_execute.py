"""
Unit tests for the interactive execute() endpoint.

Covers both RunsResource (sync) and AsyncRunsResource (async).
All HTTP calls are intercepted by respx; no real network I/O is performed.

POST /v1/workflows/{workflow_id}/execute
  Turn 1  → omit run_id in request body; server creates session and returns run_id.
  Turn N  → echo run_id from previous response.
  Cancel  → echo run_id + command="stop".
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, InteractiveRunResponse, InternalServerError, NotFoundError, WorkflowClient
from tests.conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    TEST_TEAM_ID,
    TEST_USER_ID,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_WORKFLOW_ID = "wf-abc123"

_INTERACTIVE_RESPONSE = {
    "run_id": "run-session-001",
    "status": "waiting_for_user_input",
    "turn_number": 1,
    "events": [{"type": "llm_response", "output": "Hello! How can I help?"}],
    "is_waiting_for_input": True,
    "is_completed": False,
    "error": None,
    "next_input_hint": {"prompt": "Please describe your issue."},
}

_COMPLETED_RESPONSE = {
    "run_id": "run-session-001",
    "status": "completed",
    "turn_number": 2,
    "events": [{"type": "end_conversation", "output": "Goodbye!"}],
    "is_waiting_for_input": False,
    "is_completed": True,
    "error": None,
    "next_input_hint": None,
}

_EXECUTE_URL = f"{TEST_BASE_URL}/v1/workflows/{_WORKFLOW_ID}/execute"


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


# ---------------------------------------------------------------------------
# Test: request body shape
# ---------------------------------------------------------------------------


class TestExecuteRequestBody:
    @respx.mock
    def test_first_turn_omits_run_id_from_body(self, client: WorkflowClient):
        """First turn — run_id must NOT appear in the POSTed JSON body."""
        # Arrange
        route = respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RESPONSE)
        )

        # Act
        client.runs.execute(_WORKFLOW_ID)

        # Assert
        sent_body = json.loads(route.calls[0].request.content)
        assert "run_id" not in sent_body
        assert "run_input" in sent_body

    @respx.mock
    def test_subsequent_turn_echoes_run_id_in_body(self, client: WorkflowClient):
        """Subsequent turns — run_id must appear at the top level of the body."""
        # Arrange
        route = respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_COMPLETED_RESPONSE)
        )

        # Act
        client.runs.execute(_WORKFLOW_ID, run_id="run-session-001")

        # Assert
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["run_id"] == "run-session-001"
        assert "run_input" in sent_body

    @respx.mock
    def test_cancel_sends_stop_command_in_run_input(self, client: WorkflowClient):
        """Cancel turn — command='stop' must appear inside run_input, not at the top level."""
        # Arrange
        route = respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_COMPLETED_RESPONSE)
        )

        # Act
        client.runs.execute(_WORKFLOW_ID, run_id="run-session-001", command="stop")

        # Assert
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["run_input"]["command"] == "stop"
        assert sent_body["run_id"] == "run-session-001"

    @respx.mock
    def test_default_command_is_start(self, client: WorkflowClient):
        """When command is omitted it defaults to 'start'."""
        # Arrange
        route = respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RESPONSE)
        )

        # Act
        client.runs.execute(_WORKFLOW_ID)

        # Assert
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["run_input"]["command"] == "start"

    @respx.mock
    def test_dynamic_variables_nested_in_run_input(self, client: WorkflowClient):
        """dynamic_variables must be placed inside run_input, not at the top level."""
        # Arrange
        route = respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RESPONSE)
        )

        # Act
        client.runs.execute(_WORKFLOW_ID, dynamic_variables={"patient_name": "Alice"})

        # Assert
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["run_input"]["dynamic_variables"] == {"patient_name": "Alice"}


# ---------------------------------------------------------------------------
# Test: response parsing
# ---------------------------------------------------------------------------


class TestExecuteResponseParsing:
    @respx.mock
    def test_returns_interactive_run_response_type(self, client: WorkflowClient):
        """execute() must return an InteractiveRunResponse, not a Run."""
        # Arrange
        respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RESPONSE)
        )

        # Act
        response = client.runs.execute(_WORKFLOW_ID)

        # Assert
        assert isinstance(response, InteractiveRunResponse)

    @respx.mock
    def test_is_waiting_for_input_flag_parsed_correctly(self, client: WorkflowClient):
        """is_waiting_for_input=True is faithfully deserialised."""
        # Arrange
        respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RESPONSE)
        )

        # Act
        response = client.runs.execute(_WORKFLOW_ID)

        # Assert
        assert response.is_waiting_for_input is True
        assert response.next_input_hint == {"prompt": "Please describe your issue."}
        assert response.run_id == "run-session-001"
        assert response.turn_number == 1

    @respx.mock
    def test_is_completed_flag_parsed_correctly(self, client: WorkflowClient):
        """is_completed=True is faithfully deserialised for terminal responses."""
        # Arrange
        respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_COMPLETED_RESPONSE)
        )

        # Act
        response = client.runs.execute(_WORKFLOW_ID, run_id="run-session-001")

        # Assert
        assert response.is_completed is True
        assert response.is_waiting_for_input is False
        assert response.next_input_hint is None


# ---------------------------------------------------------------------------
# Test: error propagation
# ---------------------------------------------------------------------------


class TestExecuteErrorHandling:
    @respx.mock
    def test_raises_internal_server_error_on_503(self, client: WorkflowClient):
        """A 503 from the server (Redis unavailable) must raise InternalServerError."""
        # Arrange
        respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(503, json={"detail": "Service unavailable"})
        )

        # Act / Assert
        with pytest.raises(InternalServerError):
            client.runs.execute(_WORKFLOW_ID)

    @respx.mock
    def test_raises_not_found_error_on_404(self, client: WorkflowClient):
        """A 404 from the server (expired session or unknown workflow) must raise NotFoundError."""
        # Arrange
        respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(404, json={"detail": "Session not found"})
        )

        # Act / Assert
        with pytest.raises(NotFoundError):
            client.runs.execute(_WORKFLOW_ID, run_id="expired-session")


# ---------------------------------------------------------------------------
# Test: async variant
# ---------------------------------------------------------------------------


class TestAsyncExecute:
    @respx.mock
    async def test_async_execute_returns_interactive_run_response(
        self, async_client: AsyncWorkflowClient
    ):
        """AsyncRunsResource.execute() must return an InteractiveRunResponse."""
        # Arrange
        respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RESPONSE)
        )

        # Act
        response = await async_client.runs.execute(_WORKFLOW_ID)

        # Assert
        assert isinstance(response, InteractiveRunResponse)
        assert response.run_id == "run-session-001"

    @respx.mock
    async def test_async_execute_subsequent_turn_echoes_run_id(
        self, async_client: AsyncWorkflowClient
    ):
        """Subsequent async turns must include run_id in the request body."""
        # Arrange
        route = respx.post(_EXECUTE_URL).mock(
            return_value=httpx.Response(200, json=_COMPLETED_RESPONSE)
        )

        # Act
        await async_client.runs.execute(_WORKFLOW_ID, run_id="run-session-001")

        # Assert
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["run_id"] == "run-session-001"
