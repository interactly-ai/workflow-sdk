"""
Unit tests for Phase 4 resources:
    webhooks, schedules, templates, categories, nodes, edges,
    super_nodes, tools, global_variables, node_libraries.

All HTTP calls are intercepted by respx. No real network I/O occurs.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    Edge,
    GlobalVariable,
    Node,
    NodeLibrary,
    Schedule,
    ScheduleStatus,
    SuperNodeDetail,
    SuperNodeSummary,
    Template,
    Tool,
    ToolExecuteResult,
    WebhookSubscription,
    WorkflowClient,
)
from tests.conftest import TEST_API_KEY, TEST_BASE_URL, TEST_TEAM_ID, TEST_USER_ID

# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
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
# Shared response stubs                                                        #
# --------------------------------------------------------------------------- #

_WEBHOOK = {
    "id": "wh-1",
    "name": "My Webhook",
    "url": "https://example.com/hook",
    "actions": ["workflow_run_started"],
    "enabled": True,
    "has_bearer_token": False,
    "timeout_seconds": 30,
    "max_retries": 3,
    "retry_backoff_seconds": 5,
}

_SCHEDULE = {
    "id": "sch-1",
    "workflow_id": "wf-123",
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "status": "pending",
    "scheduled_time": "2099-01-01T00:00:00",
    "run_input": {},
    "version": 1,
    "scheduled_by_name": "Alice",
    "error_message": None,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}

_TEMPLATE = {
    "id": "tpl-1",
    "workflow_template_config": {"name": "Starter"},
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "updated_by": TEST_USER_ID,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}

_NODE = {
    "id": "nd-1",
    "node_config": {"type": "llm"},
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "updated_by": TEST_USER_ID,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}

_EDGE = {
    "id": "eg-1",
    "edge_config": {"type": "default"},
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "updated_by": TEST_USER_ID,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}

_SUPER_NODE_SUMMARY = {
    "workflow_id": "wf-123",
    "workflow_version_number": 2,
    "name": "My Super Node",
    "description": "Does stuff",
    "num_input_fields": 3,
}

_SUPER_NODE_DETAIL = {
    **_SUPER_NODE_SUMMARY,
    "super_node_interface": {},
    "encapsulated_workflow_config": {},
}

_TOOL = {
    "id": "tl-1",
    "tool_config": {"type": "rest_api"},
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "updated_by": TEST_USER_ID,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}

_GLOBAL_VAR = {
    "id": "gv-1",
    "name": "API_ENDPOINT",
    "value": "https://api.example.com",
    "description": "Base API endpoint",
    "category": "config",
    "is_secret": False,
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "updated_by": TEST_USER_ID,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}

_NODE_LIBRARY = {
    "id": "nl-1",
    "node_library_config": {"name": "Utils v1"},
    "team_id": TEST_TEAM_ID,
    "created_by": TEST_USER_ID,
    "updated_by": TEST_USER_ID,
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
}

_PAGE = {"items": [], "total": 0, "page": 1, "size": 20, "pages": 0}


def _page_of(items: list) -> dict:
    return {"items": items, "total": len(items), "page": 1, "size": 20, "pages": 1}


# =========================================================================== #
# Webhooks                                                                     #
# =========================================================================== #


class TestWebhooks:
    @respx.mock
    def test_create_webhook_sends_correct_body(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflow-webhooks").mock(
            return_value=httpx.Response(200, json=_WEBHOOK)
        )

        # Act
        result = client.webhooks.create(
            name="My Webhook",
            url="https://example.com/hook",
            actions=["workflow_run_started"],
        )

        # Assert
        assert isinstance(result, WebhookSubscription)
        assert result.id == "wh-1"
        assert result.name == "My Webhook"
        sent = route.calls.last.request
        import json
        body = json.loads(sent.content)
        assert body["name"] == "My Webhook"
        assert body["url"] == "https://example.com/hook"

    @respx.mock
    def test_list_webhooks_returns_page(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks").mock(
            return_value=httpx.Response(200, json=_page_of([_WEBHOOK]))
        )

        # Act
        page = client.webhooks.list()

        # Assert
        assert len(page.items) == 1
        assert page.items[0].id == "wh-1"

    @respx.mock
    def test_get_webhook_by_id(self, client: WorkflowClient):
        # Arrange — the server has no single-item GET route (finding RS-3), so
        # get() walks the paginated list() results.
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks").mock(
            return_value=httpx.Response(200, json=_page_of([_WEBHOOK]))
        )

        # Act
        result = client.webhooks.get("wh-1")

        # Assert
        assert result.id == "wh-1"

    @respx.mock
    def test_update_webhook_sends_only_given_fields(self, client: WorkflowClient):
        # Arrange
        updated = {**_WEBHOOK, "enabled": False}
        route = respx.patch(f"{TEST_BASE_URL}/v1/workflow-webhooks/wh-1").mock(
            return_value=httpx.Response(200, json=updated)
        )

        # Act
        result = client.webhooks.update("wh-1", enabled=False)

        # Assert
        assert result.enabled is False
        import json
        body = json.loads(route.calls.last.request.content)
        assert body == {"enabled": False}

    @respx.mock
    def test_delete_webhook_returns_none(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/workflow-webhooks/wh-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert (no exception raised)
        result = client.webhooks.delete("wh-1")
        assert result is None

    @respx.mock
    async def test_async_get_webhook(self, async_client: AsyncWorkflowClient):
        # Arrange — get() walks list() since there is no single-item GET (finding RS-3).
        respx.get(f"{TEST_BASE_URL}/v1/workflow-webhooks").mock(
            return_value=httpx.Response(200, json=_page_of([_WEBHOOK]))
        )

        # Act
        result = await async_client.webhooks.get("wh-1")

        # Assert
        assert result.id == "wh-1"


# =========================================================================== #
# Schedules                                                                    #
# =========================================================================== #


class TestSchedules:
    @respx.mock
    def test_create_schedule(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-123/schedules").mock(
            return_value=httpx.Response(200, json=_SCHEDULE)
        )
        scheduled_at = datetime(2099, 1, 1, tzinfo=timezone.utc)

        # Act
        result = client.schedules.create("wf-123", scheduled_time=scheduled_at)

        # Assert
        assert isinstance(result, Schedule)
        assert result.id == "sch-1"
        import json
        body = json.loads(route.calls.last.request.content)
        assert "2099-01-01" in body["scheduled_time"]

    @respx.mock
    def test_list_schedules_for_workflow(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-123/schedules").mock(
            return_value=httpx.Response(200, json=[_SCHEDULE])
        )

        # Act
        results = client.schedules.list("wf-123")

        # Assert
        assert len(results) == 1
        assert results[0].id == "sch-1"

    @respx.mock
    def test_list_all_schedules(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-schedules").mock(
            return_value=httpx.Response(200, json=[_SCHEDULE])
        )

        # Act
        results = client.schedules.list_all()

        # Assert
        assert len(results) == 1

    @respx.mock
    def test_get_schedule(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-schedules/sch-1").mock(
            return_value=httpx.Response(200, json=_SCHEDULE)
        )

        # Act
        result = client.schedules.get("sch-1")

        # Assert
        assert result.status == ScheduleStatus.PENDING

    @respx.mock
    def test_cancel_schedule_returns_none(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/workflow-schedules/sch-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert
        assert client.schedules.cancel("sch-1") is None

    @respx.mock
    def test_update_schedule_sends_only_given_fields(self, client: WorkflowClient):
        # Arrange
        updated = {**_SCHEDULE, "version": 2}
        route = respx.patch(f"{TEST_BASE_URL}/v1/workflow-schedules/sch-1").mock(
            return_value=httpx.Response(200, json=updated)
        )

        # Act
        result = client.schedules.update("sch-1", version=2)

        # Assert
        assert result.version == 2
        import json
        body = json.loads(route.calls.last.request.content)
        assert body == {"version": 2}


# =========================================================================== #
# Templates                                                                    #
# =========================================================================== #


class TestTemplates:
    @respx.mock
    def test_create_template(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/templates").mock(
            return_value=httpx.Response(200, json=_TEMPLATE)
        )

        # Act
        result = client.templates.create(config={"name": "Starter"})

        # Assert
        assert isinstance(result, Template)
        assert result.id == "tpl-1"

    @respx.mock
    def test_list_templates(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/templates").mock(
            return_value=httpx.Response(200, json=_page_of([_TEMPLATE]))
        )

        # Act
        page = client.templates.list()

        # Assert
        assert page.metadata.total == 1

    @respx.mock
    def test_get_template(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/templates/tpl-1").mock(
            return_value=httpx.Response(200, json=_TEMPLATE)
        )

        # Act
        result = client.templates.get("tpl-1")

        # Assert
        assert result.id == "tpl-1"

    @respx.mock
    def test_delete_template(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/templates/tpl-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert
        assert client.templates.delete("tpl-1") is None

    @respx.mock
    def test_schema_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/templates/schema").mock(
            return_value=httpx.Response(200, json={"config_schema": {}})
        )

        # Act
        result = client.templates.schema()

        # Assert
        assert isinstance(result, dict)
        assert "config_schema" in result


# =========================================================================== #
# Categories                                                                   #
# =========================================================================== #


class TestCategories:
    @respx.mock
    def test_list_returns_string_list(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-categories").mock(
            return_value=httpx.Response(200, json={"categories": ["Sales", "Support", "HR"]})
        )

        # Act
        result = client.categories.list()

        # Assert
        assert result == ["Sales", "Support", "HR"]

    @respx.mock
    def test_list_returns_empty_list_when_no_categories(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-categories").mock(
            return_value=httpx.Response(200, json={"categories": []})
        )

        # Act
        result = client.categories.list()

        # Assert
        assert result == []

    @respx.mock
    async def test_async_list_categories(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflow-categories").mock(
            return_value=httpx.Response(200, json={"categories": ["Sales"]})
        )

        # Act
        result = await async_client.categories.list()

        # Assert
        assert "Sales" in result


# =========================================================================== #
# Nodes                                                                        #
# =========================================================================== #


class TestNodes:
    @respx.mock
    def test_create_node(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/nodes").mock(
            return_value=httpx.Response(200, json=_NODE)
        )

        # Act
        result = client.nodes.create(node_config={"type": "llm"})

        # Assert
        assert isinstance(result, Node)
        assert result.id == "nd-1"

    @respx.mock
    def test_list_nodes(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/nodes").mock(
            return_value=httpx.Response(200, json=_page_of([_NODE]))
        )

        # Act
        page = client.nodes.list()

        # Assert
        assert page.metadata.total == 1

    @respx.mock
    def test_get_node(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/nodes/nd-1").mock(
            return_value=httpx.Response(200, json=_NODE)
        )

        # Act
        result = client.nodes.get("nd-1")

        # Assert
        assert result.id == "nd-1"

    @respx.mock
    def test_delete_node(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/nodes/nd-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert
        assert client.nodes.delete("nd-1") is None

    @respx.mock
    def test_types_returns_list(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/nodes/types").mock(
            return_value=httpx.Response(200, json={"node_types": [{"type": "llm"}]})
        )

        # Act
        result = client.nodes.types()

        # Assert
        assert isinstance(result, list)
        assert result[0]["type"] == "llm"

    @respx.mock
    def test_schema_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/nodes/schema/llm").mock(
            return_value=httpx.Response(200, json={"config_schema": {}})
        )

        # Act
        result = client.nodes.schema("llm")

        # Assert
        assert isinstance(result, dict)


# =========================================================================== #
# Edges                                                                        #
# =========================================================================== #


class TestEdges:
    @respx.mock
    def test_create_edge(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/edges").mock(
            return_value=httpx.Response(200, json=_EDGE)
        )

        # Act
        result = client.edges.create(edge_config={"type": "default"})

        # Assert
        assert isinstance(result, Edge)
        assert result.id == "eg-1"

    @respx.mock
    def test_list_edges(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/edges").mock(
            return_value=httpx.Response(200, json=_page_of([_EDGE]))
        )

        # Act
        page = client.edges.list()

        # Assert
        assert page.metadata.total == 1

    @respx.mock
    def test_get_edge(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/edges/eg-1").mock(
            return_value=httpx.Response(200, json=_EDGE)
        )

        # Act
        result = client.edges.get("eg-1")

        # Assert
        assert result.id == "eg-1"

    @respx.mock
    def test_delete_edge(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/edges/eg-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert
        assert client.edges.delete("eg-1") is None

    @respx.mock
    def test_types_returns_list(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/edges/types").mock(
            return_value=httpx.Response(200, json={"edge_types": ["default", "conditional"]})
        )

        # Act
        result = client.edges.types()

        # Assert
        assert "default" in result


# =========================================================================== #
# Super Nodes                                                                  #
# =========================================================================== #


class TestSuperNodes:
    @respx.mock
    def test_list_super_nodes(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/super-nodes").mock(
            return_value=httpx.Response(200, json=[_SUPER_NODE_SUMMARY])
        )

        # Act
        result = client.super_nodes.list()

        # Assert
        assert len(result) == 1
        assert isinstance(result[0], SuperNodeSummary)
        assert result[0].workflow_id == "wf-123"

    @respx.mock
    def test_get_super_node(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/super-nodes/wf-123").mock(
            return_value=httpx.Response(200, json=_SUPER_NODE_DETAIL)
        )

        # Act
        result = client.super_nodes.get("wf-123")

        # Assert
        assert isinstance(result, SuperNodeDetail)
        assert result.workflow_id == "wf-123"

    @respx.mock
    def test_publish_super_node(self, client: WorkflowClient):
        # Arrange
        publish_resp = {
            "workflow_id": "wf-123",
            "workflow_version_number": 3,
            "message": "Published",
            "num_input_fields": 2,
        }
        # Publish is PUT /v1/workflows/{id}/super-node-interface (finding RS-2).
        respx.put(f"{TEST_BASE_URL}/v1/workflows/wf-123/super-node-interface").mock(
            return_value=httpx.Response(200, json=publish_resp)
        )

        # Act
        result = client.super_nodes.publish("wf-123", interface={"fields": []})

        # Assert
        assert result["workflow_version_number"] == 3

    @respx.mock
    def test_schema_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/super-nodes/wf-123/schema").mock(
            return_value=httpx.Response(200, json={"type": "object", "properties": {}})
        )

        # Act
        result = client.super_nodes.schema("wf-123")

        # Assert
        assert isinstance(result, dict)


# =========================================================================== #
# Tools                                                                        #
# =========================================================================== #


class TestTools:
    @respx.mock
    def test_create_tool(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/tools").mock(
            return_value=httpx.Response(200, json=_TOOL)
        )

        # Act
        result = client.tools.create(tool_config={"type": "rest_api"})

        # Assert
        assert isinstance(result, Tool)
        assert result.id == "tl-1"

    @respx.mock
    def test_list_tools(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/tools").mock(
            return_value=httpx.Response(200, json=_page_of([_TOOL]))
        )

        # Act
        page = client.tools.list()

        # Assert
        assert page.metadata.total == 1

    @respx.mock
    def test_get_tool(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/tools/tl-1").mock(
            return_value=httpx.Response(200, json=_TOOL)
        )

        # Act
        result = client.tools.get("tl-1")

        # Assert
        assert result.id == "tl-1"

    @respx.mock
    def test_delete_tool(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/tools/tl-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert
        assert client.tools.delete("tl-1") is None

    @respx.mock
    def test_inbuilt_tools_returns_list(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/tools/inbuilt").mock(
            return_value=httpx.Response(200, json={"inbuilt_tools": [{"tool_id": "math.add", "name": "Add"}]})
        )

        # Act
        result = client.tools.inbuilt()

        # Assert
        assert len(result) == 1
        assert result[0]["tool_id"] == "math.add"

    @respx.mock
    def test_execute_saved_tool(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/tools/tl-1/execute").mock(
            return_value=httpx.Response(200, json={"success": True, "result": 42.0, "latency_ms": 3})
        )

        # Act
        result = client.tools.execute("tl-1", args={"x": 21})

        # Assert
        assert isinstance(result, ToolExecuteResult)
        assert result.success is True
        assert result.result == 42.0
        assert result.latency_ms == 3
        # The args are sent in the request body.
        import json as _json

        assert _json.loads(route.calls[0].request.content)["args"] == {"x": 21}

    @respx.mock
    def test_execute_inline_tool(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/tools/execute").mock(
            return_value=httpx.Response(200, json={"success": True, "result": 42.0})
        )

        # Act
        result = client.tools.execute_inline(
            tool_config={"type": "inline_python", "name": "Add", "code": "def add(a, b): return a + b"},
            args={"a": 2, "b": 40},
        )

        # Assert
        assert isinstance(result, ToolExecuteResult)
        assert result.result == 42.0
        import json as _json

        body = _json.loads(route.calls[0].request.content)
        assert body["tool_config"]["type"] == "inline_python"
        assert body["args"] == {"a": 2, "b": 40}

    @respx.mock
    def test_execute_returns_failure_inline_not_raised(self, client: WorkflowClient):
        # Tool-level failure comes back as HTTP 200 with success=False.
        respx.post(f"{TEST_BASE_URL}/v1/tools/tl-1/execute").mock(
            return_value=httpx.Response(200, json={"success": False, "error": "boom", "latency_ms": 1})
        )

        # Act
        result = client.tools.execute("tl-1", args={})

        # Assert
        assert result.success is False
        assert result.error == "boom"

    @respx.mock
    async def test_async_execute_saved_tool(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/tools/tl-1/execute").mock(
            return_value=httpx.Response(200, json={"success": True, "result": 42.0})
        )

        # Act
        result = await async_client.tools.execute("tl-1", args={"x": 21})

        # Assert
        assert isinstance(result, ToolExecuteResult)
        assert result.result == 42.0


# =========================================================================== #
# Global Variables                                                             #
# =========================================================================== #


class TestGlobalVariables:
    @respx.mock
    def test_create_global_variable(self, client: WorkflowClient):
        # Arrange
        route = respx.post(f"{TEST_BASE_URL}/v1/global-variables").mock(
            return_value=httpx.Response(200, json=_GLOBAL_VAR)
        )

        # Act
        result = client.global_variables.create(name="API_ENDPOINT", value="https://api.example.com")

        # Assert
        assert isinstance(result, GlobalVariable)
        assert result.id == "gv-1"
        assert result.name == "API_ENDPOINT"
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["name"] == "API_ENDPOINT"
        assert body["is_secret"] is False

    @respx.mock
    def test_bulk_create_global_variables(self, client: WorkflowClient):
        # Arrange
        # Path is /global-variables/bulk and the server returns a "created" list
        # (finding RS-5).
        respx.post(f"{TEST_BASE_URL}/v1/global-variables/bulk").mock(
            return_value=httpx.Response(
                200,
                json={"created": [_GLOBAL_VAR], "errors": [], "total_created": 1, "total_errors": 0},
            )
        )

        # Act
        results = client.global_variables.bulk_create(
            variables=[{"name": "API_ENDPOINT", "value": "https://api.example.com"}]
        )

        # Assert
        assert len(results) == 1
        assert isinstance(results[0], GlobalVariable)

    @respx.mock
    def test_list_global_variables(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/global-variables").mock(
            return_value=httpx.Response(200, json=_page_of([_GLOBAL_VAR]))
        )

        # Act
        page = client.global_variables.list()

        # Assert
        assert page.metadata.total == 1

    @respx.mock
    def test_get_global_variable(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/global-variables/gv-1").mock(
            return_value=httpx.Response(200, json=_GLOBAL_VAR)
        )

        # Act
        result = client.global_variables.get("gv-1")

        # Assert
        assert result.name == "API_ENDPOINT"

    @respx.mock
    def test_update_global_variable_sends_only_given_fields(self, client: WorkflowClient):
        # Arrange
        updated = {**_GLOBAL_VAR, "value": "https://new.example.com"}
        route = respx.patch(f"{TEST_BASE_URL}/v1/global-variables/gv-1").mock(
            return_value=httpx.Response(200, json=updated)
        )

        # Act
        result = client.global_variables.update("gv-1", value="https://new.example.com")

        # Assert
        assert result.value == "https://new.example.com"
        import json
        body = json.loads(route.calls.last.request.content)
        assert body == {"value": "https://new.example.com"}

    @respx.mock
    def test_delete_global_variable(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/global-variables/gv-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert
        assert client.global_variables.delete("gv-1") is None

    @respx.mock
    def test_create_secret_variable_sets_is_secret_true(self, client: WorkflowClient):
        # Arrange
        secret_var = {**_GLOBAL_VAR, "is_secret": True, "value": "***"}
        route = respx.post(f"{TEST_BASE_URL}/v1/global-variables").mock(
            return_value=httpx.Response(200, json=secret_var)
        )

        # Act
        result = client.global_variables.create(name="API_ENDPOINT", value="secret", is_secret=True)

        # Assert
        assert result.is_secret is True
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["is_secret"] is True


# =========================================================================== #
# Node Libraries                                                               #
# =========================================================================== #


class TestNodeLibraries:
    @respx.mock
    def test_create_node_library(self, client: WorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/node-libraries").mock(
            return_value=httpx.Response(200, json=_NODE_LIBRARY)
        )

        # Act
        result = client.node_libraries.create(node_library_config={"name": "Utils v1"})

        # Assert
        assert isinstance(result, NodeLibrary)
        assert result.id == "nl-1"

    @respx.mock
    def test_list_node_libraries(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/node-libraries").mock(
            return_value=httpx.Response(200, json=_page_of([_NODE_LIBRARY]))
        )

        # Act
        page = client.node_libraries.list()

        # Assert
        assert page.metadata.total == 1

    @respx.mock
    def test_get_node_library(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/node-libraries/nl-1").mock(
            return_value=httpx.Response(200, json=_NODE_LIBRARY)
        )

        # Act
        result = client.node_libraries.get("nl-1")

        # Assert
        assert result.id == "nl-1"

    @respx.mock
    def test_delete_node_library(self, client: WorkflowClient):
        # Arrange
        respx.delete(f"{TEST_BASE_URL}/v1/node-libraries/nl-1").mock(
            return_value=httpx.Response(200)
        )

        # Act / Assert
        assert client.node_libraries.delete("nl-1") is None

    @respx.mock
    def test_schema_returns_dict(self, client: WorkflowClient):
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/node-libraries/schema").mock(
            return_value=httpx.Response(200, json={"config_schema": {}})
        )

        # Act
        result = client.node_libraries.schema()

        # Assert
        assert isinstance(result, dict)

    @respx.mock
    async def test_async_create_node_library(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/node-libraries").mock(
            return_value=httpx.Response(200, json=_NODE_LIBRARY)
        )

        # Act
        result = await async_client.node_libraries.create(node_library_config={"name": "Utils v1"})

        # Assert
        assert result.id == "nl-1"
