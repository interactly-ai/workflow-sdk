"""
Unit tests for WorkflowsResource using respx to mock HTTP calls.
"""

from __future__ import annotations

import json

import pytest
import respx
import httpx

from interactly import WorkflowClient, AsyncWorkflowClient, NotFoundError, Workflow
from tests.conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    TEST_TEAM_ID,
    TEST_USER_ID,
    WORKFLOW_RESPONSE,
    WORKFLOW_LIST_RESPONSE,
)


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


class TestWorkflowsGet:
    @respx.mock
    def test_get_returns_workflow(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-123").mock(
            return_value=httpx.Response(200, json=WORKFLOW_RESPONSE)
        )

        # Act
        workflow = client.workflows.get("wf-123")

        # Assert
        assert isinstance(workflow, Workflow)
        assert workflow.id == "wf-123"
        assert workflow.name == "Test Workflow"

    @respx.mock
    def test_get_raises_not_found_on_404(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/nonexistent").mock(
            return_value=httpx.Response(404, json={"detail": "Not found"})
        )

        # Act / Assert
        with pytest.raises(NotFoundError) as exc_info:
            client.workflows.get("nonexistent")
        assert exc_info.value.status_code == 404

    @respx.mock
    async def test_async_get_returns_workflow(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-123").mock(
            return_value=httpx.Response(200, json=WORKFLOW_RESPONSE)
        )

        # Act
        workflow = await async_client.workflows.get("wf-123")

        # Assert
        assert workflow.id == "wf-123"


class TestWorkflowsCreate:
    @respx.mock
    def test_create_sends_name_and_returns_workflow(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(201, json=WORKFLOW_RESPONSE)
        )

        # Act
        workflow = client.workflows.create(name="Test Workflow")

        # Assert
        assert workflow.name == "Test Workflow"
        assert workflow.id == "wf-123"

    @respx.mock
    def test_create_sends_description(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(201, json=WORKFLOW_RESPONSE)
        )

        # Act
        client.workflows.create(name="Test Workflow", description="My desc")

        # Assert — verify the body sent to the server.
        body = json.loads(route.calls[0].request.content)
        assert body["description"] == "My desc"


class TestWorkflowsUpdate:
    @respx.mock
    def test_update_sends_only_supplied_fields(self, client: WorkflowClient):
        # Arrange — patch the name only; description should NOT be in the body.
        route = respx.patch(f"{TEST_BASE_URL}/v1/workflows/wf-123").mock(
            return_value=httpx.Response(200, json={**WORKFLOW_RESPONSE, "name": "New Name"})
        )

        # Act
        workflow = client.workflows.update("wf-123", name="New Name")

        # Assert
        body = json.loads(route.calls[0].request.content)
        assert body == {"name": "New Name"}
        assert "description" not in body
        assert workflow.name == "New Name"


class TestWorkflowsList:
    @respx.mock
    def test_list_returns_page(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(200, json=WORKFLOW_LIST_RESPONSE)
        )

        # Act
        page = client.workflows.list()

        # Assert
        assert len(page) == 1
        assert page.items[0].id == "wf-123"
        assert page.has_next_page is False

    @respx.mock
    def test_list_with_search_includes_query_param(self, client: WorkflowClient):
        # Arrange
        route = respx.get(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(200, json=WORKFLOW_LIST_RESPONSE)
        )

        # Act
        client.workflows.list(search="hello")

        # Assert
        assert "search=hello" in str(route.calls[0].request.url)


class TestWorkflowsDelete:
    @respx.mock
    def test_delete_returns_none(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-123").mock(
            return_value=httpx.Response(204)
        )

        # Act / Assert — should not raise and returns None.
        result = client.workflows.delete("wf-123")
        assert result is None


class TestWorkflowsClone:
    @respx.mock
    def test_clone_returns_new_workflow(self, client: WorkflowClient):
        cloned = {**WORKFLOW_RESPONSE, "id": "wf-999", "name": "Copy of Test Workflow"}
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-123/clone").mock(
            return_value=httpx.Response(201, json=cloned)
        )

        workflow = client.workflows.clone("wf-123")
        assert workflow.id == "wf-999"


class TestAuthHeaders:
    @respx.mock
    def test_auth_headers_are_sent(self, client: WorkflowClient):
        # Arrange
        route = respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-123").mock(
            return_value=httpx.Response(200, json=WORKFLOW_RESPONSE)
        )

        # Act
        client.workflows.get("wf-123")

        # Assert — all three auth headers must be present.
        headers = route.calls[0].request.headers
        assert headers["authorization"] == f"Bearer {TEST_API_KEY}"
        assert headers["teamid"] == TEST_TEAM_ID
        assert headers["uuid"] == TEST_USER_ID
