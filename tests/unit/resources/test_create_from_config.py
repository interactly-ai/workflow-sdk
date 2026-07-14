"""Tests for ``WorkflowsResource.create_from_config`` (sync + async)."""

from __future__ import annotations

from typing import Any, Dict

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, Workflow, WorkflowClient
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
)
from tests.conftest import (
    TEST_API_KEY,
    TEST_BASE_URL,
    TEST_TEAM_ID,
    TEST_USER_ID,
    WORKFLOW_RESPONSE,
)


def _minimal_config() -> WorkflowConfigFullyHydrated:
    """Build the smallest valid hydrated config that exercises the typed-upload path."""
    llm = OpenAILLMConfig(model=OPENAIModel.GPT_5_4_NANO, max_tokens=50)
    wf_cfg = WorkflowConfig(
        name="unit-test-wf",
        description="from unit tests",
        llms_config=llm,
        default_prompt_prefix="",
        default_prompt_suffix="",
    )
    greeting = SayStaticMessageNodeConfig(
        name="greeting",
        is_start=True,
        static_messages_config=StaticMessagesConfig(messages=["hello"]),
    )
    say = SayLLMNodeConfig(
        name="say",
        prompt_config=None,
        llms_config=llm,
    )
    edge = DirectEdgeConfig(
        source_node_logical_id=greeting.logical_id,
        target_node_logical_id=say.logical_id,
    )
    return WorkflowConfigFullyHydrated(
        workflow_config=wf_cfg,
        node_configs=[greeting, say],
        edge_configs=[edge],
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


class TestCreateFromConfig:
    @respx.mock
    def test_posts_full_hydrated_payload(self, client: WorkflowClient):
        # Arrange
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json=WORKFLOW_RESPONSE)

        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(side_effect=_capture)
        config = _minimal_config()

        # Act
        workflow = client.workflows.create_from_config(config)

        # Assert
        assert isinstance(workflow, Workflow)
        assert workflow.id == "wf-123"
        import json

        body = json.loads(captured["json"])
        assert "workflow_config" in body
        assert "node_configs" in body and len(body["node_configs"]) == 2
        assert "edge_configs" in body and len(body["edge_configs"]) == 1

    @respx.mock
    def test_node_configs_serialise_with_type_discriminator(self, client: WorkflowClient):
        """Regression: hydrated node_configs must keep their ``type`` discriminator.

        ``WorkflowConfigFullyHydrated.node_configs`` is typed as the base
        ``BaseNodeConfig``; without ``SerializeAsAny`` Pydantic would dump each
        node using only the base fields, dropping ``type`` (and the subclass
        payload). The server then can't retag the discriminated ``NodeConfig``
        union and silently creates an empty workflow.
        """
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json=WORKFLOW_RESPONSE)

        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(side_effect=_capture)

        client.workflows.create_from_config(_minimal_config())

        import json

        body = json.loads(captured["json"])
        # Every node must carry a non-empty ``type`` tag and its subclass payload.
        for node in body["node_configs"]:
            assert node.get("type"), f"node missing type discriminator: {node!r}"
        types = {n["type"] for n in body["node_configs"]}
        assert types == {"say_static", "say_llm"}
        # Edges likewise carry their discriminator.
        for edge in body["edge_configs"]:
            assert edge.get("type"), f"edge missing type discriminator: {edge!r}"



        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json=WORKFLOW_RESPONSE)

        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(side_effect=_capture)
        config = _minimal_config()

        # Act
        client.workflows.create_from_config(config, name="override-name", description="override-desc")

        # Assert
        import json

        body = json.loads(captured["json"])
        # The hydrated-create endpoint reads name/description from the TOP LEVEL
        # of the body (the nested workflow_config is ignored on create).
        assert body["name"] == "override-name"
        assert body["description"] == "override-desc"

    @respx.mock
    async def test_async_create_from_config(self, async_client: AsyncWorkflowClient):
        # Arrange
        respx.post(f"{TEST_BASE_URL}/v1/workflows").mock(
            return_value=httpx.Response(200, json=WORKFLOW_RESPONSE)
        )
        config = _minimal_config()

        # Act
        workflow = await async_client.workflows.create_from_config(config)

        # Assert
        assert isinstance(workflow, Workflow)
        assert workflow.id == "wf-123"


class TestGetFullyHydrated:
    @respx.mock
    def test_unwraps_workflowsresponse_envelope(self, client: WorkflowClient):
        # Arrange — backend canonical shape: ``{workflow: {workflow_config, node_configs, edge_configs}, execution_url}``.
        cfg = _minimal_config().model_dump(mode="json")
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(
                200,
                json={"workflow": cfg, "execution_url": "wss://example.com/ws"},
            )
        )

        # Act
        result = client.workflows.get_fully_hydrated("wf-xyz")

        # Assert
        assert isinstance(result, WorkflowConfigFullyHydrated)
        assert len(result.node_configs) == 2
        assert len(result.edge_configs) == 1

    @respx.mock
    def test_accepts_flat_hydrated_shape(self, client: WorkflowClient):
        # Arrange — some mocked backends return the hydrated config flat.
        cfg = _minimal_config().model_dump(mode="json")
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(200, json=cfg)
        )

        # Act
        result = client.workflows.get_fully_hydrated("wf-xyz")

        # Assert
        assert isinstance(result, WorkflowConfigFullyHydrated)

    @respx.mock
    def test_sends_fully_hydrate_query_param(self, client: WorkflowClient):
        # Arrange
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            cfg = _minimal_config().model_dump(mode="json")
            return httpx.Response(200, json={"workflow": cfg, "execution_url": ""})

        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(side_effect=_capture)

        # Act
        client.workflows.get_fully_hydrated("wf-xyz")

        # Assert
        assert "fully_hydrate=true" in captured["url"].lower()

    @respx.mock
    async def test_async_get_fully_hydrated(self, async_client: AsyncWorkflowClient):
        # Arrange
        cfg = _minimal_config().model_dump(mode="json")
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(200, json={"workflow": cfg, "execution_url": ""})
        )

        # Act
        result = await async_client.workflows.get_fully_hydrated("wf-xyz")

        # Assert
        assert isinstance(result, WorkflowConfigFullyHydrated)


class TestHandleFactory:
    @respx.mock
    def test_handle_returns_workflow_handle_with_config(self, client: WorkflowClient):
        # Arrange
        cfg = _minimal_config().model_dump(mode="json")
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(200, json={"workflow": cfg, "execution_url": ""})
        )

        # Act
        from interactly import WorkflowHandle

        handle = client.workflows.handle("wf-xyz", dynamic_variables={"x": 1})

        # Assert
        assert isinstance(handle, WorkflowHandle)
        assert handle.workflow_id == "wf-xyz"
        assert handle.run_id is None
        assert isinstance(handle.config, WorkflowConfigFullyHydrated)


# Helper used by the assertion above; placed last for clarity.
def _is_dict_subset(superset: Dict[str, Any], subset: Dict[str, Any]) -> bool:
    return all(superset.get(k) == v for k, v in subset.items())
