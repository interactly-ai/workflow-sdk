"""
Unit tests for typed parameter acceptance in resource methods (Phase B).

Verifies that all resource create/update methods:
  - Accept plain dicts (backward-compatible)
  - Accept Pydantic BaseModel objects and serialise them correctly
  - Pass the correct serialised body to the HTTP client

All HTTP calls are intercepted by respx — no real network I/O.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from interactly import WorkflowClient
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


# Minimal response stubs
_NODE_RESP = {"id": "n-1", "node_config": {"node_type": "llm"}}
_EDGE_RESP = {"id": "e-1", "edge_config": {"edge_type": "direct"}}
_TOOL_RESP = {"id": "t-1", "tool_config": {"tool_type": "api_call"}}
_LIB_RESP = {"id": "l-1", "node_library_config": {"node_type": "llm"}}
_WF_RESP = {"id": "wf-1", "name": "Test"}
_VER_RESP = {"version_number": 1, "is_active": True}


# --------------------------------------------------------------------------- #
# Nodes                                                                        #
# --------------------------------------------------------------------------- #


class TestNodesTypedParams:
    @respx.mock
    def test_create_accepts_plain_dict(self, client: WorkflowClient):
        """create() with a plain dict must POST the dict as the body."""
        route = respx.post(f"{TEST_BASE_URL}/v1/nodes").mock(
            return_value=httpx.Response(200, json=_NODE_RESP)
        )
        cfg = {"node_type": "say_llm", "name": "Test Node"}
        node = client.nodes.create(node_config=cfg)
        assert node.id == "n-1"
        sent = route.calls.last.request
        import json
        body = json.loads(sent.content)
        assert body["node_type"] == "say_llm"

    @respx.mock
    def test_create_accepts_pydantic_model(self, client: WorkflowClient):
        """create() with a Pydantic model must serialise it before sending."""
        try:
            from pydantic import BaseModel

            class _FakeNodeConfig(BaseModel):
                node_type: str
                name: str

        except ImportError:
            pytest.skip("pydantic not available")

        route = respx.post(f"{TEST_BASE_URL}/v1/nodes").mock(
            return_value=httpx.Response(200, json=_NODE_RESP)
        )
        cfg = _FakeNodeConfig(node_type="say_llm", name="Test")
        client.nodes.create(node_config=cfg)
        import json
        body = json.loads(route.calls.last.request.content)
        assert body == {"node_type": "say_llm", "name": "Test"}

    @respx.mock
    def test_update_accepts_plain_dict(self, client: WorkflowClient):
        route = respx.patch(f"{TEST_BASE_URL}/v1/nodes/n-1").mock(
            return_value=httpx.Response(200, json=_NODE_RESP)
        )
        client.nodes.update("n-1", node_config={"node_type": "llm"})
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["node_type"] == "llm"


# --------------------------------------------------------------------------- #
# Edges                                                                        #
# --------------------------------------------------------------------------- #


class TestEdgesTypedParams:
    @respx.mock
    def test_create_accepts_plain_dict(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/edges").mock(
            return_value=httpx.Response(200, json=_EDGE_RESP)
        )
        cfg = {"edge_type": "direct", "source_node_logical_id": "a", "destination_node_logical_id": "b"}
        edge = client.edges.create(edge_config=cfg)
        assert edge.id == "e-1"

    @respx.mock
    def test_create_serialises_pydantic_model(self, client: WorkflowClient):
        try:
            from pydantic import BaseModel

            class _FakeEdgeConfig(BaseModel):
                edge_type: str

        except ImportError:
            pytest.skip("pydantic not available")

        route = respx.post(f"{TEST_BASE_URL}/v1/edges").mock(
            return_value=httpx.Response(200, json=_EDGE_RESP)
        )
        client.edges.create(edge_config=_FakeEdgeConfig(edge_type="direct"))
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["edge_type"] == "direct"


# --------------------------------------------------------------------------- #
# Tools                                                                        #
# --------------------------------------------------------------------------- #


class TestToolsTypedParams:
    @respx.mock
    def test_create_accepts_plain_dict(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/tools").mock(
            return_value=httpx.Response(200, json=_TOOL_RESP)
        )
        cfg = {"tool_type": "api_call", "name": "My Tool"}
        tool = client.tools.create(tool_config=cfg)
        assert tool.id == "t-1"

    @respx.mock
    def test_create_serialises_pydantic_model(self, client: WorkflowClient):
        try:
            from pydantic import BaseModel

            class _FakeToolConfig(BaseModel):
                tool_type: str

        except ImportError:
            pytest.skip("pydantic not available")

        route = respx.post(f"{TEST_BASE_URL}/v1/tools").mock(
            return_value=httpx.Response(200, json=_TOOL_RESP)
        )
        client.tools.create(tool_config=_FakeToolConfig(tool_type="api_call"))
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["tool_type"] == "api_call"


# --------------------------------------------------------------------------- #
# Workflows                                                                    #
# --------------------------------------------------------------------------- #


class TestWorkflowsTypedParams:
    @respx.mock
    def test_create_with_dict_config(self, client: WorkflowClient):
        route = respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(200, json=_WF_RESP)
        )
        cfg = {"nodes": [], "edges": []}
        wf = client.workflows.create(name="Test", config=cfg)
        assert wf.id == "wf-1"
        import json
        body = json.loads(route.calls.last.request.content)
        assert body["config"] == {"nodes": [], "edges": []}

    @respx.mock
    def test_create_without_config(self, client: WorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(200, json=_WF_RESP)
        )
        wf = client.workflows.create(name="Test")
        assert wf.name == "Test"


# --------------------------------------------------------------------------- #
# Versions                                                                     #
# --------------------------------------------------------------------------- #


class TestVersionsTypedParams:
    @respx.mock
    def test_update_config_accepts_plain_dict(self, client: WorkflowClient):
        route = respx.patch(f"{TEST_BASE_URL}/v1/workflows/wf-1/versions/1/config").mock(
            return_value=httpx.Response(200, json=_VER_RESP)
        )
        cfg = {"nodes": [], "edges": []}
        ver = client.workflows.versions.update_config("wf-1", 1, config=cfg)
        assert ver.version_number == 1
        import json
        body = json.loads(route.calls.last.request.content)
        assert body == {"config": {"nodes": [], "edges": []}}

    @respx.mock
    def test_update_config_serialises_pydantic_model(self, client: WorkflowClient):
        try:
            from pydantic import BaseModel

            class _FakeWFConfig(BaseModel):
                nodes: list
                edges: list

        except ImportError:
            pytest.skip("pydantic not available")

        route = respx.patch(f"{TEST_BASE_URL}/v1/workflows/wf-1/versions/2/config").mock(
            return_value=httpx.Response(200, json={**_VER_RESP, "version_number": 2})
        )
        client.workflows.versions.update_config("wf-1", 2, config=_FakeWFConfig(nodes=[], edges=[]))
        import json
        body = json.loads(route.calls.last.request.content)
        assert body == {"config": {"nodes": [], "edges": []}}
