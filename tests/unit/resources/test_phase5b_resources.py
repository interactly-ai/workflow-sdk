"""
Unit tests for Phase 5b implementation additions:
    super_nodes.unpublish,
    webhooks.retry_event,
    runs.execute,
    runs.checkpoint.

All HTTP calls are intercepted by respx. No real network I/O occurs.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, InteractiveRunResponse, WorkflowClient
from interactly.types.runs.run import Run

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_API_KEY = "test-key"
TEST_TEAM_ID = "team-123"
TEST_USER_ID = "user-456"
TEST_BASE_URL = "http://test.interactly.ai"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_UNPUBLISH_RESPONSE = {
    "workflow_id": "wf-1",
    "workflow_version_number": 3,
    "message": "Workflow unpublished as a super node.",
    "workflows_referencing": ["wf-2", "wf-3"],
}

_RETRY_RESPONSE = {
    "message": "Webhook event retry triggered",
    "event_id": "evt-abc",
}

_RUN = {
    "id": "run-1",
    "workflow_id": "wf-1",
    "status": "completed",
    "run_by": "api",
    "version_number": 2,
    "team_id": "team-123",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:10Z",
}

_INTERACTIVE_RUN = {
    "run_id": "run-1",
    "status": "completed",
    "turn_number": 1,
    "events": [],
    "is_waiting_for_input": False,
    "is_completed": True,
    "error": None,
    "next_input_hint": None,
}


@pytest.fixture
def client() -> WorkflowClient:
    return WorkflowClient(
        api_key=TEST_API_KEY,
        team_id=TEST_TEAM_ID,
        user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL,
    )


@pytest.fixture
def async_client() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(
        api_key=TEST_API_KEY,
        team_id=TEST_TEAM_ID,
        user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL,
    )


# ===========================================================================
# Super Nodes — unpublish
# ===========================================================================


class TestSuperNodesUnpublish:
    @respx.mock
    def test_unpublish_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(
            return_value=httpx.Response(200, json=_UNPUBLISH_RESPONSE)
        )

        # Act
        result = client.super_nodes.unpublish("wf-1")

        # Assert
        assert isinstance(result, dict)
        assert result["workflow_id"] == "wf-1"
        assert result["message"] == "Workflow unpublished as a super node."

    @respx.mock
    def test_unpublish_returns_referencing_workflows(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(
            return_value=httpx.Response(200, json=_UNPUBLISH_RESPONSE)
        )

        # Act
        result = client.super_nodes.unpublish("wf-1")

        # Assert
        assert result["workflows_referencing"] == ["wf-2", "wf-3"]
        assert result["workflow_version_number"] == 3

    @respx.mock
    def test_unpublish_with_version_number_sends_query_param(self, client: WorkflowClient):
        # Arrange
        route = respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(
            return_value=httpx.Response(200, json=_UNPUBLISH_RESPONSE)
        )

        # Act
        client.super_nodes.unpublish("wf-1", version_number=3)

        # Assert
        assert route.called
        assert "version_number=3" in str(route.calls.last.request.url)

    @respx.mock
    def test_unpublish_without_version_number_no_query_param(self, client: WorkflowClient):
        # Arrange
        route = respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(
            return_value=httpx.Response(200, json=_UNPUBLISH_RESPONSE)
        )

        # Act
        client.super_nodes.unpublish("wf-1")

        # Assert
        assert route.called
        assert "version_number" not in str(route.calls.last.request.url)

    @respx.mock
    def test_unpublish_empty_referencing_list(self, client: WorkflowClient):
        # Arrange
        response = {**_UNPUBLISH_RESPONSE, "workflows_referencing": []}
        respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(
            return_value=httpx.Response(200, json=response)
        )

        # Act
        result = client.super_nodes.unpublish("wf-1")

        # Assert
        assert result["workflows_referencing"] == []

    @respx.mock
    async def test_async_unpublish(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(
            return_value=httpx.Response(200, json=_UNPUBLISH_RESPONSE)
        )

        # Act
        result = await async_client.super_nodes.unpublish("wf-1")

        # Assert
        assert isinstance(result, dict)
        assert result["workflow_id"] == "wf-1"

    @respx.mock
    async def test_async_unpublish_with_version_number(self, async_client: AsyncWorkflowClient):
        # Arrange
        route = respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(
            return_value=httpx.Response(200, json=_UNPUBLISH_RESPONSE)
        )

        # Act
        await async_client.super_nodes.unpublish("wf-1", version_number=2)

        # Assert
        assert "version_number=2" in str(route.calls.last.request.url)


# ===========================================================================
# Webhooks — retry_event
# ===========================================================================


class TestWebhookRetryEvent:
    @respx.mock
    def test_retry_event_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/evt-abc/retry").mock(
            return_value=httpx.Response(200, json=_RETRY_RESPONSE)
        )

        # Act
        result = client.webhooks.retry_event("evt-abc")

        # Assert
        assert isinstance(result, dict)
        assert result["message"] == "Webhook event retry triggered"
        assert result["event_id"] == "evt-abc"

    @respx.mock
    def test_retry_event_sends_post_to_correct_url(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/evt-xyz/retry").mock(
            return_value=httpx.Response(200, json={"message": "Webhook event retry triggered", "event_id": "evt-xyz"})
        )

        # Act
        client.webhooks.retry_event("evt-xyz")

        # Assert
        assert route.called
        assert route.calls.last.request.method == "POST"

    @respx.mock
    def test_retry_event_different_ids_hit_different_urls(self, client: WorkflowClient):
        # Arrange
        route_a = respx.post(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/id-a/retry").mock(
            return_value=httpx.Response(200, json={"message": "ok", "event_id": "id-a"})
        )
        route_b = respx.post(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/id-b/retry").mock(
            return_value=httpx.Response(200, json={"message": "ok", "event_id": "id-b"})
        )

        # Act
        client.webhooks.retry_event("id-a")
        client.webhooks.retry_event("id-b")

        # Assert
        assert route_a.called
        assert route_b.called

    @respx.mock
    async def test_async_retry_event(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/evt-abc/retry").mock(
            return_value=httpx.Response(200, json=_RETRY_RESPONSE)
        )

        # Act
        result = await async_client.webhooks.retry_event("evt-abc")

        # Assert
        assert isinstance(result, dict)
        assert result["event_id"] == "evt-abc"


# ===========================================================================
# Runs — execute
# ===========================================================================


class TestRunsExecute:
    @respx.mock
    def test_execute_returns_interactive_run_response(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RUN)
        )

        # Act
        result = client.runs.execute("wf-1")

        # Assert
        assert isinstance(result, InteractiveRunResponse)
        assert result.run_id == "run-1"
        assert result.is_completed is True

    @respx.mock
    def test_execute_run_status_is_completed(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RUN)
        )

        # Act
        result = client.runs.execute("wf-1")

        # Assert
        assert result.status == "completed"

    @respx.mock
    def test_execute_sends_dynamic_variables(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RUN)
        )

        # Act
        client.runs.execute("wf-1", dynamic_variables={"name": "Alice"})

        # Assert
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["run_input"]["dynamic_variables"]["name"] == "Alice"

    @respx.mock
    def test_execute_sends_version_number_in_run_input(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RUN)
        )

        # Act
        client.runs.execute("wf-1", version_number=2)

        # Assert
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["run_input"]["version_number"] == 2

    @respx.mock
    def test_execute_default_command_is_start(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RUN)
        )

        # Act
        client.runs.execute("wf-1")

        # Assert
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["run_input"]["command"] == "start"

    @respx.mock
    async def test_async_execute_returns_interactive_run_response(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/execute").mock(
            return_value=httpx.Response(200, json=_INTERACTIVE_RUN)
        )

        # Act
        result = await async_client.runs.execute("wf-1")

        # Assert
        assert isinstance(result, InteractiveRunResponse)
        assert result.run_id == "run-1"


# ===========================================================================
# Runs — checkpoint
# ===========================================================================


class TestRunsCheckpoint:
    @respx.mock
    def test_checkpoint_returns_run(self, client: WorkflowClient):
        # Arrange
        checkpoint_run = {**_RUN, "id": "run-2", "status": "running"}
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/runs/run-1/checkpoint-run").mock(
            return_value=httpx.Response(200, json=checkpoint_run)
        )

        # Act
        result = client.runs.checkpoint("wf-1", "run-1", resume_turn_index=2)

        # Assert
        assert isinstance(result, Run)
        assert result.id == "run-2"

    @respx.mock
    def test_checkpoint_sends_resume_turn_index(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/runs/run-1/checkpoint-run").mock(
            return_value=httpx.Response(200, json={**_RUN, "id": "run-2"})
        )

        # Act
        client.runs.checkpoint("wf-1", "run-1", resume_turn_index=3)

        # Assert
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["resume_turn_index"] == 3

    @respx.mock
    def test_checkpoint_sends_start_node_logical_id(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/runs/run-1/checkpoint-run").mock(
            return_value=httpx.Response(200, json={**_RUN, "id": "run-2"})
        )

        # Act
        client.runs.checkpoint("wf-1", "run-1", resume_turn_index=1, start_node_logical_id="node_abc")

        # Assert
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["start_node_logical_id"] == "node_abc"

    @respx.mock
    def test_checkpoint_omits_start_node_when_not_provided(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/runs/run-1/checkpoint-run").mock(
            return_value=httpx.Response(200, json={**_RUN, "id": "run-2"})
        )

        # Act
        client.runs.checkpoint("wf-1", "run-1", resume_turn_index=0)

        # Assert
        import json
        body = json.loads(route.calls.last.request.content)
        assert "start_node_logical_id" not in body

    @respx.mock
    def test_checkpoint_zero_turn_index_is_valid(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/runs/run-1/checkpoint-run").mock(
            return_value=httpx.Response(200, json={**_RUN, "id": "run-2"})
        )

        # Act
        result = client.runs.checkpoint("wf-1", "run-1", resume_turn_index=0)

        # Assert
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["resume_turn_index"] == 0
        assert isinstance(result, Run)

    @respx.mock
    async def test_async_checkpoint_returns_run(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/runs/run-1/checkpoint-run").mock(
            return_value=httpx.Response(200, json={**_RUN, "id": "run-2"})
        )

        # Act
        result = await async_client.runs.checkpoint("wf-1", "run-1", resume_turn_index=2)

        # Assert
        assert isinstance(result, Run)
        assert result.id == "run-2"
