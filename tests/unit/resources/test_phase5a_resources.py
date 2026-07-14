"""
Unit tests for Phase 5a additions:
    webhooks.list_events, webhooks.list_delivery_attempts,
    global_variables.resolve,
    workflows.versions.diff,
    simulations (all 13 methods),
    copilot.workflows.schema, copilot.medical.schema,
    super_nodes.unpublish removed.

All HTTP calls are intercepted by respx. No real network I/O occurs.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    WorkflowClient,
    WebhookAction,
    WebhookEventStatus,
    WebhookEvent,
    WebhookDeliveryAttempt,
    Simulation,
    SimulationGroup,
    SimulationRun,
    SimulationStatus,
    CopilotSchema,
    VersionDiff,
)
from interactly._pagination import SyncPage

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

_WEBHOOK_EVENT = {
    "event_id": "evt-1",
    "subscription_id": "sub-1",
    "action": "workflow_run_started",
    "workflow_id": "wf-1",
    "workflow_name": "My Workflow",
    "workflow_run_id": "run-1",
    "workflow_run_status": "running",
    "payload": {},
    "status": "delivered",
    "attempts_count": 1,
    "delivered_at": "2024-01-01T00:00:00Z",
    "last_attempt_at": "2024-01-01T00:00:00Z",
    "last_status_code": 200,
    "last_error": None,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}

_DELIVERY_ATTEMPT = {
    "event_id": "evt-1",
    "subscription_id": "sub-1",
    "attempt_number": 1,
    "action": "workflow_run_started",
    "request_url": "https://example.com/hook",
    "success": True,
    "response_status_code": 200,
    "response_body": "ok",
    "error_message": None,
    "latency_ms": 120,
    "created_at": "2024-01-01T00:00:00Z",
}

_SIMULATION = {
    "id": "sim-1",
    "simulation_config": {"name": "Test Sim"},
    "status": "pending",
    "team_id": "team-123",
    "created_by": "user-456",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}

_SIMULATION_GROUP = {
    "id": "grp-1",
    "simulation_config_id": "sim-1",
    "status": "running",
    "total_runs": 10,
    "completed_runs": 5,
    "failed_runs": 1,
    "team_id": "team-123",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}

_SIMULATION_RUN = {
    "id": "run-1",
    "simulation_group_id": "grp-1",
    "selected_workflow_run_id": "wfrun-1",
    "counter_workflow_run_id": "wfrun-2",
    "status": "completed",
    "error_message": None,
    "team_id": "team-123",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
}

_DIFF = {
    "version1_number": 1,
    "version1_name": "v1",
    "version2_number": 2,
    "version2_name": "v2",
    "workflow_config_changes": [],
    "nodes": [
        {
            "logical_id": "node_greet",
            "name": "Greet User",
            "node_type": "say_llm",
            "status": "modified",
            "changes": [
                {
                    "path": "main_response_config.prompt",
                    "old_value": "Greet the user.",
                    "new_value": "Greet the user by name.",
                }
            ],
        }
    ],
    "edges": [],
    "summary": {"nodes_added": 0, "nodes_removed": 0, "nodes_modified": 1},
}

_COPILOT_SCHEMA = {
    "copilot_input_schema": {"type": "object"},
    "copilot_event_schema": {"type": "object"},
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
# Webhook Events
# ===========================================================================


class TestWebhookListEvents:
    @respx.mock
    def test_list_events_returns_page(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events").mock(
            return_value=httpx.Response(200, json={"events": [_WEBHOOK_EVENT], "total": 1})
        )

        # Act
        page = client.webhooks.list_events()

        # Assert
        assert isinstance(page, SyncPage)
        assert page.metadata.total == 1
        assert len(page.items) == 1

    @respx.mock
    def test_list_events_item_is_webhook_event(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events").mock(
            return_value=httpx.Response(200, json={"events": [_WEBHOOK_EVENT], "total": 1})
        )

        # Act
        page = client.webhooks.list_events()
        item = page.items[0]

        # Assert
        assert isinstance(item, WebhookEvent)
        assert item.event_id == "evt-1"
        assert item.status == WebhookEventStatus.DELIVERED
        assert item.action == WebhookAction.WORKFLOW_RUN_STARTED

    @respx.mock
    def test_list_events_filters_by_subscription(self, client: WorkflowClient):
        # Arrange
        route = respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events").mock(
            return_value=httpx.Response(200, json={"events": [], "total": 0})
        )

        # Act
        client.webhooks.list_events(subscription_id="sub-1")

        # Assert
        assert route.called
        assert "subscription_id=sub-1" in str(route.calls.last.request.url)

    @respx.mock
    def test_list_events_empty_list(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events").mock(
            return_value=httpx.Response(200, json={"events": [], "total": 0})
        )

        # Act
        page = client.webhooks.list_events()

        # Assert
        assert page.metadata.total == 0
        assert page.items == []

    @respx.mock
    def test_list_events_filters_by_status(self, client: WorkflowClient):
        # Arrange
        route = respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events").mock(
            return_value=httpx.Response(200, json={"events": [], "total": 0})
        )

        # Act
        client.webhooks.list_events(status="failed")

        # Assert
        assert "status=failed" in str(route.calls.last.request.url)

    @respx.mock
    async def test_async_list_events(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events").mock(
            return_value=httpx.Response(200, json={"events": [_WEBHOOK_EVENT], "total": 1})
        )

        # Act
        page = await async_client.webhooks.list_events()

        # Assert
        assert page.metadata.total == 1
        assert isinstance(page.items[0], WebhookEvent)


class TestWebhookListDeliveryAttempts:
    @respx.mock
    def test_list_attempts_returns_page(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/evt-1/attempts").mock(
            return_value=httpx.Response(200, json={"attempts": [_DELIVERY_ATTEMPT], "total": 1})
        )

        # Act
        page = client.webhooks.list_delivery_attempts("evt-1")

        # Assert
        assert isinstance(page, SyncPage)
        assert page.metadata.total == 1

    @respx.mock
    def test_list_attempts_item_is_delivery_attempt(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/evt-1/attempts").mock(
            return_value=httpx.Response(200, json={"attempts": [_DELIVERY_ATTEMPT], "total": 1})
        )

        # Act
        page = client.webhooks.list_delivery_attempts("evt-1")
        item = page.items[0]

        # Assert
        assert isinstance(item, WebhookDeliveryAttempt)
        assert item.event_id == "evt-1"
        assert item.success is True
        assert item.response_status_code == 200

    @respx.mock
    def test_list_attempts_empty(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/evt-2/attempts").mock(
            return_value=httpx.Response(200, json={"attempts": [], "total": 0})
        )

        # Act
        page = client.webhooks.list_delivery_attempts("evt-2")

        # Assert
        assert page.items == []
        assert page.metadata.total == 0

    @respx.mock
    async def test_async_list_attempts(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks/events/evt-1/attempts").mock(
            return_value=httpx.Response(200, json={"attempts": [_DELIVERY_ATTEMPT], "total": 1})
        )

        # Act
        page = await async_client.webhooks.list_delivery_attempts("evt-1")

        # Assert
        assert page.metadata.total == 1
        assert isinstance(page.items[0], WebhookDeliveryAttempt)


# ===========================================================================
# Global Variables — resolve
# ===========================================================================


class TestGlobalVariablesResolve:
    @respx.mock
    def test_resolve_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/global-variables/resolve").mock(
            return_value=httpx.Response(200, json={"variables": {"key": "value"}})
        )

        # Act
        result = client.global_variables.resolve()

        # Assert
        assert isinstance(result, dict)
        assert result["key"] == "value"

    @respx.mock
    def test_resolve_unwraps_variables_key(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/global-variables/resolve").mock(
            return_value=httpx.Response(200, json={"variables": {"host": "db.local", "port": "5432"}})
        )

        # Act
        result = client.global_variables.resolve()

        # Assert
        assert "host" in result
        assert "port" in result
        assert "variables" not in result

    @respx.mock
    def test_resolve_empty_variables(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/global-variables/resolve").mock(
            return_value=httpx.Response(200, json={"variables": {}})
        )

        # Act
        result = client.global_variables.resolve()

        # Assert
        assert result == {}

    @respx.mock
    async def test_async_resolve(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/global-variables/resolve").mock(
            return_value=httpx.Response(200, json={"variables": {"x": "1"}})
        )

        # Act
        result = await async_client.global_variables.resolve()

        # Assert
        assert result["x"] == "1"


# ===========================================================================
# Workflow Versions — diff
# ===========================================================================


class TestWorkflowVersionsDiff:
    @respx.mock
    def test_diff_returns_typed_version_diff(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=_DIFF)
        )

        # Act
        result = client.workflows.versions.diff("wf-1", 1, 2)

        # Assert
        assert isinstance(result, VersionDiff)

    @respx.mock
    def test_diff_contains_version_numbers(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=_DIFF)
        )

        # Act
        result = client.workflows.versions.diff("wf-1", 1, 2)

        # Assert
        assert result.version1_number == 1
        assert result.version2_number == 2

    @respx.mock
    def test_diff_contains_summary(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=_DIFF)
        )

        # Act
        result = client.workflows.versions.diff("wf-1", 1, 2)

        # Assert
        assert result.summary["nodes_modified"] == 1

    @respx.mock
    def test_diff_surfaces_field_level_node_changes(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=_DIFF)
        )

        # Act
        result = client.workflows.versions.diff("wf-1", 1, 2)

        # Assert — the modified node exposes the exact prompt change.
        node = result.nodes[0]
        assert node.status == "modified"
        change = node.changes[0]
        assert change.path == "main_response_config.prompt"
        assert change.old_value == "Greet the user."
        assert change.new_value == "Greet the user by name."

    @respx.mock
    async def test_async_diff(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-1/versions/1/diff/2").mock(
            return_value=httpx.Response(200, json=_DIFF)
        )

        # Act
        result = await async_client.workflows.versions.diff("wf-1", 1, 2)

        # Assert
        assert isinstance(result, VersionDiff)
        assert result.version1_number == 1


# ===========================================================================
# Simulations
# ===========================================================================


class TestSimulations:
    @respx.mock
    def test_create_returns_simulation(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/simulations").mock(
            return_value=httpx.Response(200, json=_SIMULATION)
        )

        # Act
        result = client.simulations.create(config={"name": "Test Sim"})

        # Assert
        assert isinstance(result, Simulation)
        assert result.id == "sim-1"
        assert result.status == SimulationStatus.PENDING

    @respx.mock
    def test_get_returns_simulation(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/simulations/sim-1").mock(
            return_value=httpx.Response(200, json=_SIMULATION)
        )

        # Act
        result = client.simulations.get("sim-1")

        # Assert
        assert isinstance(result, Simulation)
        assert result.id == "sim-1"

    @respx.mock
    def test_list_returns_page(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/simulations").mock(
            return_value=httpx.Response(200, json={"simulations": [_SIMULATION], "total": 1})
        )

        # Act
        page = client.simulations.list()

        # Assert
        assert isinstance(page, SyncPage)
        assert page.metadata.total == 1
        assert isinstance(page.items[0], Simulation)

    @respx.mock
    def test_delete_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/simulations/sim-1").mock(
            return_value=httpx.Response(200, json={"message": "deleted"})
        )

        # Act
        result = client.simulations.delete("sim-1")

        # Assert
        assert isinstance(result, dict)

    @respx.mock
    def test_run_returns_simulation_group(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/simulations/sim-1/run").mock(
            return_value=httpx.Response(200, json=_SIMULATION_GROUP)
        )

        # Act
        result = client.simulations.run("sim-1")

        # Assert
        assert isinstance(result, SimulationGroup)
        assert result.id == "grp-1"
        assert result.total_runs == 10

    @respx.mock
    def test_list_runs_returns_page_of_groups(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/simulations/sim-1/runs").mock(
            return_value=httpx.Response(
                200, json={"simulation_groups": [_SIMULATION_GROUP], "total": 1}
            )
        )

        # Act
        page = client.simulations.list_runs("sim-1")

        # Assert
        assert isinstance(page, SyncPage)
        assert isinstance(page.items[0], SimulationGroup)

    @respx.mock
    def test_schema_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/simulations/schema").mock(
            return_value=httpx.Response(200, json={"schema": {"type": "object"}})
        )

        # Act
        result = client.simulations.schema()

        # Assert
        assert isinstance(result, dict)

    @respx.mock
    def test_get_run_returns_simulation_group(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/simulation-runs/grp-1").mock(
            return_value=httpx.Response(200, json=_SIMULATION_GROUP)
        )

        # Act
        result = client.simulations.get_run("grp-1")

        # Assert
        assert isinstance(result, SimulationGroup)
        assert result.simulation_config_id == "sim-1"

    @respx.mock
    def test_stop_run_returns_simulation_group(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/simulation-runs/grp-1/stop").mock(
            return_value=httpx.Response(200, json={**_SIMULATION_GROUP, "status": "cancelled"})
        )

        # Act
        result = client.simulations.stop_run("grp-1")

        # Assert
        assert isinstance(result, SimulationGroup)
        assert result.status == SimulationStatus.CANCELLED

    @respx.mock
    def test_list_executions_returns_page_of_runs(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/simulation-runs/grp-1/executions").mock(
            return_value=httpx.Response(
                200, json={"individual_runs": [_SIMULATION_RUN], "total": 1}
            )
        )

        # Act
        page = client.simulations.list_executions("grp-1")

        # Assert
        assert isinstance(page, SyncPage)
        assert isinstance(page.items[0], SimulationRun)

    @respx.mock
    async def test_async_create_simulation(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/simulations").mock(
            return_value=httpx.Response(200, json=_SIMULATION)
        )

        # Act
        result = await async_client.simulations.create(config={"name": "Test"})

        # Assert
        assert isinstance(result, Simulation)


# ===========================================================================
# Copilot schema endpoints
# ===========================================================================


# ===========================================================================
# super_nodes.unpublish no longer exists
# ===========================================================================


class TestSuperNodesUnpublishRestored:
    def test_unpublish_attribute_present(self, client: WorkflowClient):
        # The unpublish method was re-added in Phase 5b at the correct path:
        # DELETE /v1/workflows/{workflow_id}/super-node-interface
        assert hasattr(client.super_nodes, "unpublish")
        assert callable(client.super_nodes.unpublish)
