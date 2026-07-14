"""
Unit tests for RunsResource using respx mocks.
"""

from __future__ import annotations

import pytest
import respx
import httpx

from interactly import WorkflowClient, Run
from tests.conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    TEST_TEAM_ID,
    TEST_USER_ID,
    RUN_RESPONSE,
    RUN_LIST_RESPONSE,
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


class TestRunsGet:
    @respx.mock
    def test_get_returns_run(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs/run-456").mock(
            return_value=httpx.Response(200, json=RUN_RESPONSE)
        )

        # Act
        run = client.runs.get("run-456")

        # Assert
        assert isinstance(run, Run)
        assert run.id == "run-456"
        assert run.workflow_id == "wf-123"


class TestRunsList:
    @respx.mock
    def test_list_returns_page(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs").mock(
            return_value=httpx.Response(200, json=RUN_LIST_RESPONSE)
        )

        # Act
        page = client.runs.list()

        # Assert
        assert len(page) == 1
        assert page.items[0].id == "run-456"

    @respx.mock
    def test_list_with_workflow_id_filter(self, client: WorkflowClient):
        # Arrange
        route = respx.get(f"{TEST_BASE_URL}/v1/workflow-runs").mock(
            return_value=httpx.Response(200, json=RUN_LIST_RESPONSE)
        )

        # Act
        client.runs.list(workflow_id="wf-123")

        # Assert
        assert "workflow_id=wf-123" in str(route.calls[0].request.url)


class TestRunsDelete:
    @respx.mock
    def test_delete_returns_none(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/workflow-runs/run-456").mock(
            return_value=httpx.Response(204)
        )

        # Act / Assert
        result = client.runs.delete("run-456")
        assert result is None


class TestRunsAddComment:
    @respx.mock
    def test_add_comment_returns_comment(self, client: WorkflowClient):
        # Arrange
        comment_response = {
            "logical_id": "comment-1",
            "content": "Looks good",
            "created_by": TEST_USER_ID,
            "created_at": "2024-01-01T12:00:00Z",
        }
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/run-456/comments").mock(
            return_value=httpx.Response(201, json=comment_response)
        )

        # Act
        comment = client.runs.add_comment("run-456", content="Looks good")

        # Assert
        assert comment.logical_id == "comment-1"
        assert comment.content == "Looks good"


class TestRunStream:
    def test_stream_returns_stream_context_manager(self, client: WorkflowClient):
        # Arrange / Act — just check that stream() returns the right type.
        from interactly._streaming import Stream

        stream = client.runs.stream(workflow_id="wf-123")
        assert isinstance(stream, Stream)

    def test_stream_ws_url_is_ws_scheme(self, client: WorkflowClient):
        # Verify the WS URL uses the ws:// scheme.
        stream = client.runs.stream(workflow_id="wf-123")
        assert stream._ws_url.startswith("ws://")

    def test_stream_payload_contains_workflow_id(self, client: WorkflowClient):
        stream = client.runs.stream(workflow_id="wf-abc")
        assert stream._payload["workflow_id"] == "wf-abc"

    def test_stream_payload_defaults_to_start_command(self, client: WorkflowClient):
        stream = client.runs.stream(workflow_id="wf-abc")
        assert stream._payload["command"] == "start"


_COMMENT_RESPONSE = {
    "logical_id": "comment-1",
    "content": "Nice output",
    "created_by": TEST_USER_ID,
    "created_at": "2024-01-01T12:00:00Z",
}

_SCHEMA_RESPONSE = {
    "run_schema": {"title": "WorkflowRun", "type": "object"},
    "run_input_schema": {"title": "WorkflowRunInput", "type": "object"},
    "run_output_schema": {"title": "WorkflowRunOutput", "type": "object"},
    "run_input_output_pair_schema": {"title": "WorkflowRunInputOutputPair", "type": "object"},
}


class TestRunsAddEventComment:
    @respx.mock
    def test_add_event_comment_returns_run_comment(self, client: WorkflowClient):
        # Arrange
        respx.post(
            f"{TEST_BASE_URL}/v1/workflow-runs/run-456/events/evt-1/comments"
        ).mock(return_value=httpx.Response(201, json=_COMMENT_RESPONSE))

        # Act
        from interactly.types.runs.run import RunComment

        result = client.runs.add_event_comment("run-456", "evt-1", content="Nice output")

        # Assert
        assert isinstance(result, RunComment)
        assert result.logical_id == "comment-1"
        assert result.content == "Nice output"

    @respx.mock
    def test_add_event_comment_posts_to_correct_url(self, client: WorkflowClient):
        # Arrange
        route = respx.post(
            f"{TEST_BASE_URL}/v1/workflow-runs/run-789/events/evt-abc/comments"
        ).mock(return_value=httpx.Response(201, json=_COMMENT_RESPONSE))

        # Act
        client.runs.add_event_comment("run-789", "evt-abc", content="Nice output")

        # Assert
        assert route.called

    @respx.mock
    def test_add_event_comment_sends_content_in_body(self, client: WorkflowClient):
        # Arrange
        import json

        route = respx.post(
            f"{TEST_BASE_URL}/v1/workflow-runs/run-456/events/evt-1/comments"
        ).mock(return_value=httpx.Response(201, json=_COMMENT_RESPONSE))

        # Act
        client.runs.add_event_comment("run-456", "evt-1", content="Test comment")

        # Assert
        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body["content"] == "Test comment"

    @respx.mock
    async def test_async_add_event_comment(self, client: WorkflowClient):
        # Arrange
        from interactly import AsyncWorkflowClient

        async_client = AsyncWorkflowClient(
            api_key=TEST_API_KEY, team_id=TEST_TEAM_ID, user_id=TEST_USER_ID,
            base_url=TEST_BASE_URL, max_retries=0,
        )
        respx.post(
            f"{TEST_BASE_URL}/v1/workflow-runs/run-456/events/evt-1/comments"
        ).mock(return_value=httpx.Response(201, json=_COMMENT_RESPONSE))

        # Act
        result = await async_client.runs.add_event_comment("run-456", "evt-1", content="Nice output")

        # Assert
        assert result.content == "Nice output"


class TestRunsDeleteEventComment:
    @respx.mock
    def test_delete_event_comment_calls_correct_url(self, client: WorkflowClient):
        # Arrange
        route = respx.delete(
            f"{TEST_BASE_URL}/v1/workflow-runs/run-456/events/evt-1/comments/cmt-1"
        ).mock(return_value=httpx.Response(200, json={}))

        # Act
        client.runs.delete_event_comment("run-456", "evt-1", "cmt-1")

        # Assert
        assert route.called

    @respx.mock
    def test_delete_event_comment_returns_none(self, client: WorkflowClient):
        # Arrange
        respx.delete(
            f"{TEST_BASE_URL}/v1/workflow-runs/run-456/events/evt-1/comments/cmt-1"
        ).mock(return_value=httpx.Response(200, json={}))

        # Act
        result = client.runs.delete_event_comment("run-456", "evt-1", "cmt-1")

        # Assert
        assert result is None

    @respx.mock
    async def test_async_delete_event_comment(self, client: WorkflowClient):
        # Arrange
        from interactly import AsyncWorkflowClient

        async_client = AsyncWorkflowClient(
            api_key=TEST_API_KEY, team_id=TEST_TEAM_ID, user_id=TEST_USER_ID,
            base_url=TEST_BASE_URL, max_retries=0,
        )
        route = respx.delete(
            f"{TEST_BASE_URL}/v1/workflow-runs/run-456/events/evt-1/comments/cmt-1"
        ).mock(return_value=httpx.Response(200, json={}))

        # Act
        await async_client.runs.delete_event_comment("run-456", "evt-1", "cmt-1")

        # Assert
        assert route.called


class TestRunsSchema:
    @respx.mock
    def test_schema_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs/schema").mock(
            return_value=httpx.Response(200, json=_SCHEMA_RESPONSE)
        )

        # Act
        result = client.runs.schema()

        # Assert
        assert isinstance(result, dict)
        assert "run_schema" in result
        assert "run_input_schema" in result
        assert "run_output_schema" in result
        assert "run_input_output_pair_schema" in result

    @respx.mock
    def test_schema_hits_correct_url(self, client: WorkflowClient):
        # Arrange
        route = respx.get(f"{TEST_BASE_URL}/v1/workflow-runs/schema").mock(
            return_value=httpx.Response(200, json=_SCHEMA_RESPONSE)
        )

        # Act
        client.runs.schema()

        # Assert
        assert route.called

    @respx.mock
    async def test_async_schema(self, client: WorkflowClient):
        # Arrange
        from interactly import AsyncWorkflowClient

        async_client = AsyncWorkflowClient(
            api_key=TEST_API_KEY, team_id=TEST_TEAM_ID, user_id=TEST_USER_ID,
            base_url=TEST_BASE_URL, max_retries=0,
        )
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs/schema").mock(
            return_value=httpx.Response(200, json=_SCHEMA_RESPONSE)
        )

        # Act
        result = await async_client.runs.schema()

        # Assert
        assert "run_schema" in result
