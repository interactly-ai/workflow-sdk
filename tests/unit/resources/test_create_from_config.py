"""Tests for ``WorkflowsResource.create_from_config`` (sync + async)."""

from __future__ import annotations

from typing import Any, Dict

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, Workflow, WorkflowClient
from interactly.configs import (
    DirectEdgeConfig,
    OpenAILLMConfig,
    OPENAIModel,
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
    def test_unwraps_the_real_server_envelope(self, client: WorkflowClient):
        """The shape the server actually returns, captured from dev.

        The hydrated payload sits TWO levels down: the ``workflow`` key holds the stored document
        (team_id, _id, timestamps) and *its* ``workflow_config`` is the hydrated config. The unwrap
        used to stop one level short and return the document, whose ``node_configs`` are absent — so
        every call produced a config with zero nodes and zero edges instead of failing. The old test
        here mocked the hydrated config directly under ``workflow``, a shape the server never sends,
        which is exactly why the bug survived.
        """
        # Arrange
        cfg = _minimal_config().model_dump(mode="json")
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflow": {
                        "_id": "wf-xyz",
                        "team_id": "t-1",
                        "active_version_number": 0,
                        "workflow_config": cfg,
                    },
                    "execution_url": "wss://example.com/ws",
                },
            )
        )

        # Act
        result = client.workflows.get_fully_hydrated("wf-xyz")

        # Assert
        assert isinstance(result, WorkflowConfigFullyHydrated)
        assert len(result.node_configs) == 2
        assert len(result.edge_configs) == 1

    @respx.mock
    def test_accepts_the_single_wrapped_shape(self, client: WorkflowClient):
        # Arrange — some mocked backends put the hydrated config directly under ``workflow``.
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
        assert len(result.node_configs) == 2
        assert len(result.edge_configs) == 1

    @respx.mock
    def test_nodes_keep_their_concrete_subclass_and_fields(self, client: WorkflowClient):
        """A fetched node must survive as its real type, not be flattened to BaseNodeConfig.

        ``SerializeAsAny`` governs serialization only, so validating a plain dict against
        ``List[SerializeAsAny[BaseNodeConfig]]`` used to discard every subclass field — the fetched
        config could not be re-uploaded because it no longer carried ``type``.
        """
        # Arrange
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflow": {
                        "workflow_config": {
                            "workflow_config": {"name": "wf"},
                            "node_configs": [
                                {"type": "say_llm", "name": "greet", "wait_for_user_message": True}
                            ],
                            "edge_configs": [],
                        }
                    }
                },
            )
        )

        # Act
        node = client.workflows.get_fully_hydrated("wf-xyz").node_configs[0]

        # Assert
        assert type(node).__name__ == "SayLLMNodeConfig"
        dumped = node.model_dump()
        assert dumped["type"] == "say_llm"
        assert dumped["wait_for_user_message"] is True

    @respx.mock
    def test_unknown_node_type_is_preserved_rather_than_failing(self, client: WorkflowClient):
        # A client necessarily lags the server, so a node type newer than this package must neither
        # fail the workflow nor lose its fields.
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflow": {
                        "workflow_config": {
                            "workflow_config": {"name": "wf"},
                            "node_configs": [
                                {"type": "future_node_2027", "name": "n", "some_new_field": 7}
                            ],
                            "edge_configs": [],
                        }
                    }
                },
            )
        )

        node = client.workflows.get_fully_hydrated("wf-xyz").node_configs[0]

        assert type(node).__name__ == "UnknownNodeConfig"
        assert node.model_dump()["some_new_field"] == 7

    @respx.mock
    def test_empty_workflow_is_still_recognised_as_hydrated(self, client: WorkflowClient):
        # Keyed on key presence, not truthiness: a workflow with no nodes yet is still the hydrated
        # shape, and treating empty lists as "keep looking" would walk straight past it.
        respx.get(f"{TEST_BASE_URL}/v1/workflows/wf-xyz").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflow": {
                        "workflow_config": {
                            "workflow_config": {"name": "empty"},
                            "node_configs": [],
                            "edge_configs": [],
                        }
                    }
                },
            )
        )

        result = client.workflows.get_fully_hydrated("wf-xyz")

        assert result.workflow_config is not None
        assert result.workflow_config.name == "empty"

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
