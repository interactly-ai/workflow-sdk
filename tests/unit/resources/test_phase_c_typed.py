"""Phase C: typed-first resource params (templates + super_nodes) accept typed
configs and serialise them to the request body (dict still supported)."""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from interactly import WorkflowClient
from interactly.configs import (
    SuperNodeFieldMapping,
    SuperNodeInputField,
    SuperNodeInterface,
    WorkflowTemplateConfig,
)
from tests.conftest import TEST_API_KEY, TEST_BASE_URL, TEST_TEAM_ID, TEST_USER_ID


@pytest.fixture
def client() -> WorkflowClient:
    return WorkflowClient(
        api_key=TEST_API_KEY, team_id=TEST_TEAM_ID, user_id=TEST_USER_ID,
        base_url=TEST_BASE_URL, max_retries=0,
    )


_TEMPLATE_RESPONSE = {"id": "tpl-1", "name": "T", "workflow_config": {"name": "T"}}


class TestTypedResourceParams:
    @respx.mock
    def test_template_create_accepts_typed_config(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json=_TEMPLATE_RESPONSE)

        respx.post(f"{TEST_BASE_URL}/v1/templates").mock(side_effect=_capture)

        cfg = WorkflowTemplateConfig(workflow_id="wf-1")
        client.templates.create(config=cfg)

        body = json.loads(captured["json"])
        # Typed config serialised to a dict payload (not a Pydantic repr).
        assert isinstance(body, dict)
        assert body.get("workflow_id") == "wf-1"

    @respx.mock
    def test_template_create_still_accepts_dict(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json=_TEMPLATE_RESPONSE)

        respx.post(f"{TEST_BASE_URL}/v1/templates").mock(side_effect=_capture)

        client.templates.create(config={"workflow_id": "wf-2"})
        body = json.loads(captured["json"])
        assert body.get("workflow_id") == "wf-2"

    @respx.mock
    def test_super_node_publish_accepts_typed_interface(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}

        def _capture(request: httpx.Request) -> httpx.Response:
            captured["json"] = request.read()
            return httpx.Response(200, json={"message": "ok"})

        respx.put(f"{TEST_BASE_URL}/v1/workflows/wf-1/super-node-interface").mock(side_effect=_capture)

        iface = SuperNodeInterface(
            input_fields=[
                SuperNodeInputField(
                    name="patient_name",
                    field_mappings=[SuperNodeFieldMapping(target_type="dynamic_variable")],
                )
            ]
        )
        client.super_nodes.publish("wf-1", interface=iface)

        body = json.loads(captured["json"])
        # interface serialised to a nested dict under "interface".
        assert isinstance(body["interface"], dict)
        assert body["interface"]["input_fields"][0]["name"] == "patient_name"
