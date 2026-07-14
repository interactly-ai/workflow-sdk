"""
Unit tests for the coverage-gap resources/methods added to close the audit gaps:

    G1 llm_configs (new resource)         G5 super_nodes.snapshot_status
    G2 workflows.favorite / unfavorite    G6 tools.configurable_inbuilt(+_schema)
    G3 super_nodes.dependents             G7 workflows.versions.list_active
    G4 super_nodes.expand_preview

All HTTP calls are intercepted by respx. No real network I/O occurs. Paginated
tests deliberately return the server's resource-named envelope keys
(``llm_configs``, ``versions``, ``workflows``) to also exercise the
``_extract_items`` envelope handling.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    LLMConfig,
    LLMConfigTestResult,
    WorkflowClient,
)
from tests.conftest import TEST_API_KEY, TEST_BASE_URL, TEST_TEAM_ID, TEST_USER_ID


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


_LLM_CONFIG = {
    "id": "llm-1",
    "name": "Team GPT",
    "description": "default",
    "is_default": True,
    "config": {"type": "openai_llm", "model": "gpt-5", "api_key": None},
    "team_id": TEST_TEAM_ID,
}

_TEST_RESULT = {
    "success": True,
    "response": "hi",
    "provider": "openai",
    "model": "gpt-5",
    "prompt_tokens": 3,
    "completion_tokens": 1,
    "total_tokens": 4,
    "latency_ms": 42,
}


# --------------------------------------------------------------------------- #
# G1 — llm_configs                                                            #
# --------------------------------------------------------------------------- #


class TestLLMConfigsResource:
    @respx.mock
    def test_schema_hits_schemas_llm_config(self, client: WorkflowClient):
        route = respx.get(f"{TEST_BASE_URL}/v1/schemas/llm-config").mock(
            return_value=httpx.Response(200, json={"config_schema": {}})
        )
        result = client.llm_configs.schema()
        assert route.called
        assert result == {"config_schema": {}}

    @respx.mock
    def test_create_sends_config_and_flags(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/llm-configs").mock(
            return_value=httpx.Response(200, json=_LLM_CONFIG)
        )
        result = client.llm_configs.create(
            name="Team GPT",
            config={"type": "openai_llm", "model": "gpt-5"},
            is_default=True,
            override_default=True,
        )
        assert isinstance(result, LLMConfig)
        assert result.id == "llm-1"
        body = json.loads(route.calls.last.request.content)
        assert body["name"] == "Team GPT"
        assert body["config"]["model"] == "gpt-5"
        assert body["is_default"] is True
        assert body["override_default"] is True

    @respx.mock
    def test_list_reads_llm_configs_envelope(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs").mock(
            return_value=httpx.Response(
                200, json={"llm_configs": [_LLM_CONFIG], "total": 1, "page": 1, "size": 20}
            )
        )
        page = client.llm_configs.list()
        assert len(page.items) == 1
        assert page.items[0].id == "llm-1"
        assert page.metadata.total == 1

    @respx.mock
    def test_get_default(self, client: WorkflowClient):
        route = respx.get(f"{TEST_BASE_URL}/v1/llm-configs/default").mock(
            return_value=httpx.Response(200, json=_LLM_CONFIG)
        )
        result = client.llm_configs.get_default()
        assert route.called
        assert result.name == "Team GPT"

    @respx.mock
    def test_get_by_id(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs/llm-1").mock(
            return_value=httpx.Response(200, json=_LLM_CONFIG)
        )
        assert client.llm_configs.get("llm-1").id == "llm-1"

    @respx.mock
    def test_update_only_sends_supplied_fields(self, client: WorkflowClient):
        route = respx.patch(f"{TEST_BASE_URL}/v1/llm-configs/llm-1").mock(
            return_value=httpx.Response(200, json=_LLM_CONFIG)
        )
        client.llm_configs.update("llm-1", name="Renamed")
        body = json.loads(route.calls.last.request.content)
        assert body["name"] == "Renamed"
        # description/config/is_default were NOT_GIVEN → omitted
        assert "description" not in body
        assert "config" not in body
        assert "is_default" not in body
        # override_default always sent (has a concrete default)
        assert body["override_default"] is False

    @respx.mock
    def test_delete(self, client: WorkflowClient):
        route = respx.delete(f"{TEST_BASE_URL}/v1/llm-configs/llm-1").mock(
            return_value=httpx.Response(200, json={"message": "deleted"})
        )
        assert client.llm_configs.delete("llm-1") is None
        assert route.called

    @respx.mock
    def test_test_saved_config(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/llm-configs/llm-1/test").mock(
            return_value=httpx.Response(200, json=_TEST_RESULT)
        )
        result = client.llm_configs.test(
            "llm-1", system_prompt="You are helpful", messages=[{"role": "human", "content": "hi"}]
        )
        assert isinstance(result, LLMConfigTestResult)
        assert result.success is True
        body = json.loads(route.calls.last.request.content)
        assert body["system_prompt"] == "You are helpful"
        assert body["messages"] == [{"role": "human", "content": "hi"}]

    @respx.mock
    def test_test_inline_requires_config(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/llm-configs/test").mock(
            return_value=httpx.Response(200, json=_TEST_RESULT)
        )
        result = client.llm_configs.test_inline(
            system_prompt="sp", config={"type": "openai_llm", "model": "gpt-5", "api_key": "sk-x"}
        )
        assert result.model == "gpt-5"
        body = json.loads(route.calls.last.request.content)
        assert body["config"]["api_key"] == "sk-x"
        assert body["messages"] == []

    @respx.mock
    async def test_async_list(self, async_client: AsyncWorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/llm-configs").mock(
            return_value=httpx.Response(200, json={"llm_configs": [_LLM_CONFIG], "total": 1, "size": 20})
        )
        page = await async_client.llm_configs.list()
        assert page.items[0].id == "llm-1"
        await async_client.close()


# --------------------------------------------------------------------------- #
# G2 — workflows.favorite / unfavorite                                        #
# --------------------------------------------------------------------------- #


class TestWorkflowFavorites:
    @respx.mock
    def test_favorite_posts(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/favorite").mock(
            return_value=httpx.Response(200, json={"message": "Marked as favorite"})
        )
        result = client.workflows.favorite("wf-1")
        assert route.called
        assert result["message"] == "Marked as favorite"

    @respx.mock
    def test_unfavorite_deletes(self, client: WorkflowClient):
        route = respx.delete(f"{TEST_BASE_URL}/v1/workflows/wf-1/favorite").mock(
            return_value=httpx.Response(200, json={"message": "Unmarked as favorite"})
        )
        result = client.workflows.unfavorite("wf-1")
        assert route.called
        assert result["message"] == "Unmarked as favorite"

    @respx.mock
    async def test_async_favorite(self, async_client: AsyncWorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/favorite").mock(
            return_value=httpx.Response(200, json={"message": "ok"})
        )
        result = await async_client.workflows.favorite("wf-1")
        assert result["message"] == "ok"
        await async_client.close()


# --------------------------------------------------------------------------- #
# G3-G5 — super_nodes.dependents / expand_preview / snapshot_status           #
# --------------------------------------------------------------------------- #


class TestSuperNodeExtras:
    @respx.mock
    def test_dependents_returns_page(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-dependents").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflows": [{"workflow_id": "wf-2", "name": "Caller", "description": None}],
                    "total": 1,
                    "page": 1,
                    "size": 20,
                },
            )
        )
        page = client.super_nodes.dependents("wf-1")
        assert len(page.items) == 1
        assert page.items[0].workflow_id == "wf-2"
        assert page.items[0].name == "Caller"

    @respx.mock
    def test_expand_preview_posts_and_parses(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows/wf-1/expand-preview").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflow_id": "wf-1",
                    "version_number": 3,
                    "expanded_config": {"nodes": [], "edges": []},
                    "super_node_origins": ["sn-a"],
                    "expansion_report": {"projected_exits": 2},
                },
            )
        )
        result = client.super_nodes.expand_preview("wf-1", version_number=3)
        assert route.called
        assert result.workflow_id == "wf-1"
        assert result.version_number == 3
        assert result.super_node_origins == ["sn-a"]
        assert result.expansion_report == {"projected_exits": 2}
        # version_number went on the query string, not the body.
        assert route.calls.last.request.url.params["version_number"] == "3"

    @respx.mock
    def test_snapshot_status(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-snapshot-status").mock(
            return_value=httpx.Response(200, json={"is_stale": False})
        )
        assert client.super_nodes.snapshot_status("wf-1") == {"is_stale": False}


# --------------------------------------------------------------------------- #
# G6 — tools.configurable_inbuilt(+ _schema)                                   #
# --------------------------------------------------------------------------- #


class TestConfigurableInbuiltTools:
    @respx.mock
    def test_configurable_inbuilt_list(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/tools/configurable-inbuilt").mock(
            return_value=httpx.Response(
                200,
                json={
                    "configurable_inbuilt_tools": [
                        {"key": "kb_search", "title": "KB Search", "registry_tool_id": "reg-1", "config_schema": {}}
                    ]
                },
            )
        )
        result = client.tools.configurable_inbuilt()
        assert result[0]["key"] == "kb_search"

    @respx.mock
    def test_configurable_inbuilt_schema(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/tools/configurable-inbuilt/kb_search").mock(
            return_value=httpx.Response(
                200, json={"key": "kb_search", "title": "KB Search", "registry_tool_id": "reg-1", "config_schema": {}}
            )
        )
        result = client.tools.configurable_inbuilt_schema("kb_search")
        assert result["registry_tool_id"] == "reg-1"


# --------------------------------------------------------------------------- #
# G7 — workflows.versions.list_active                                          #
# --------------------------------------------------------------------------- #


class TestListActiveVersions:
    @respx.mock
    def test_list_active_reads_versions_envelope(self, client: WorkflowClient):
        route = respx.get(f"{TEST_BASE_URL}/v1/workflows/versions/active").mock(
            return_value=httpx.Response(
                200,
                json={"versions": [{"version_number": 2, "is_active": True}], "total": 1, "page": 1, "size": 20},
            )
        )
        page = client.workflows.versions.list_active(favorites=True, category="Sales")
        assert len(page.items) == 1
        assert page.items[0].version_number == 2
        # filters serialised onto the query string
        params = route.calls.last.request.url.params
        assert params["favorites"] == "true"
        assert params["category"] == "Sales"

    @respx.mock
    async def test_async_list_active(self, async_client: AsyncWorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/workflows/versions/active").mock(
            return_value=httpx.Response(200, json={"versions": [{"version_number": 1, "is_active": True}], "total": 1})
        )
        page = await async_client.workflows.versions.list_active()
        assert page.items[0].version_number == 1
        await async_client.close()
