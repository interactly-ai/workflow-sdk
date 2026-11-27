"""Evaluation workflows, ``workflow_type``, and the workflow reads that name a version, on the wire.

Every answer replayed here was captured from a workflow-service (``fixtures/evaluation_workflows.json``), with its ids
replaced. The node presets are cut to the two with no LLM prompt; the rest are whole.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import (
    AnalysisNodePreset,
    AsyncWorkflowClient,
    EvaluationTemplate,
    EvaluationWorkflow,
    NotFoundError,
    Workflow,
    WorkflowClient,
    WorkflowType,
    WorkflowVersion,
)

BASE = "http://localhost:8611"
ANSWERS: Dict[str, Dict[str, Any]] = json.loads(
    (Path(__file__).parent / "fixtures" / "evaluation_workflows.json").read_text()
)
CREATED = ANSWERS["from_template"]["body"]["workflow_id"]


def _client() -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _aclient() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _replay(calls: List[httpx.Request], name: str):
    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(ANSWERS[name]["status"], json=ANSWERS[name]["body"])

    return _handler


def _query(request: httpx.Request) -> Dict[str, Any]:
    pairs = request.url.params.multi_items()
    keys = [k for k, _ in pairs]
    return {k: ([v for kk, v in pairs if kk == k] if keys.count(k) > 1 else dict(pairs)[k]) for k in dict(pairs)}


class TestEvaluationWorkflows:
    @respx.mock
    def test_templates_and_node_presets_are_typed(self):
        # Arrange
        respx.get(f"{BASE}/v1/evaluation-workflows/templates").mock(side_effect=_replay([], "templates"))
        respx.get(f"{BASE}/v1/evaluation-workflows/node-presets").mock(side_effect=_replay([], "node_presets"))

        # Act
        templates = _client().evaluation_workflows.templates()
        presets = _client().evaluation_workflows.node_presets()

        # Assert
        assert all(isinstance(t, EvaluationTemplate) for t in templates)
        assert [t.template_id for t in templates] == ["default_framework", "custom"]
        assert all(isinstance(p, AnalysisNodePreset) for p in presets)
        assert [(p.preset_id, p.node_type) for p in presets] == [
            ("conversation_fetch", "conversation_fetch"),
            ("store_analysis", "store_analysis"),
        ]
        assert presets[0].config["type"] == "conversation_fetch"

    @respx.mock
    def test_create_from_template_sends_the_template_and_name_and_returns_the_workflow(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/evaluation-workflows/from-template").mock(side_effect=_replay(calls, "from_template"))

        # Act
        workflow = _client().evaluation_workflows.create_from_template(
            template_id="default_framework", name="SDK_E2E evaluation"
        )

        # Assert
        assert json.loads(calls[0].content) == {"template_id": "default_framework", "name": "SDK_E2E evaluation"}
        assert isinstance(workflow, Workflow)
        assert (workflow.id, workflow.name, workflow.active_version_number) == (CREATED, "SDK_E2E evaluation", 0)

    @respx.mock
    def test_an_unknown_template_is_not_found(self):
        # Arrange
        respx.post(f"{BASE}/v1/evaluation-workflows/from-template").mock(
            side_effect=_replay([], "from_unknown_template")
        )

        # Act / Assert
        with pytest.raises(NotFoundError, match="Unknown template 'no_such_template'"):
            _client().evaluation_workflows.create_from_template(template_id="no_such_template", name="x")

    @respx.mock
    def test_the_list_gives_each_workflows_versions_and_their_phi_masking(self):
        # Arrange
        respx.get(f"{BASE}/v1/evaluation-workflows").mock(side_effect=_replay([], "list"))

        # Act
        workflows = _client().evaluation_workflows.list()

        # Assert
        assert all(isinstance(w, EvaluationWorkflow) for w in workflows)
        assert [(w.workflow_id, w.active_version_number) for w in workflows] == [(CREATED, 0)]
        assert [(v.version_number, v.has_phi_masking) for v in workflows[0].versions] == [(0, True)]

    @respx.mock
    async def test_the_async_resource_does_the_same(self):
        # Arrange
        respx.get(f"{BASE}/v1/evaluation-workflows/templates").mock(side_effect=_replay([], "templates"))
        respx.get(f"{BASE}/v1/evaluation-workflows/node-presets").mock(side_effect=_replay([], "node_presets"))
        respx.post(f"{BASE}/v1/evaluation-workflows/from-template").mock(side_effect=_replay([], "from_template"))
        respx.get(f"{BASE}/v1/evaluation-workflows").mock(side_effect=_replay([], "list"))
        resource = _aclient().evaluation_workflows

        # Act
        templates = await resource.templates()
        presets = await resource.node_presets()
        workflow = await resource.create_from_template(template_id="custom", name="n")
        workflows = await resource.list()

        # Assert
        assert (len(templates), len(presets), workflow.id, len(workflows)) == (2, 2, CREATED, 1)


class TestWorkflowType:
    @respx.mock
    def test_the_workflow_list_sends_its_type_and_filters_on_every_page(self):
        # Arrange
        calls: List[httpx.Request] = []

        def _page(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"workflows": [{"_id": CREATED}], "total": 2})

        respx.get(f"{BASE}/v1/workflows").mock(side_effect=_page)

        # Act
        _client().workflows.list(
            size=1,
            workflow_type=WorkflowType.EVALUATION,
            logical_id="workflow_abc",
            categories=["Sales", "Support"],
            created_by=["u1"],
            favorites=True,
        ).next_page()

        # Assert
        expected = {
            "size": "1",
            "workflow_type": "evaluation",
            "logical_id": "workflow_abc",
            "categories": ["Sales", "Support"],
            "created_by": "u1",
            "favorites": "true",
        }
        assert [_query(c) for c in calls] == [{"page": "1", **expected}, {"page": "2", **expected}]

    @respx.mock
    def test_node_types_and_active_versions_take_the_workflow_type(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/nodes/types").mock(
            side_effect=lambda r: calls.append(r) or httpx.Response(200, json={"node_types": []})
        )
        respx.get(f"{BASE}/v1/workflows/versions/active").mock(
            side_effect=lambda r: calls.append(r) or httpx.Response(200, json={"versions": [], "total": 0})
        )

        # Act
        _client().nodes.types(workflow_type="evaluation")
        _client().nodes.types()
        _client().workflows.versions.list_active(workflow_type=WorkflowType.STANDARD)

        # Assert
        assert [c.url.params.get("workflow_type") for c in calls] == ["evaluation", None, "standard"]

    def test_the_enum_holds_the_servers_two_types(self):
        assert [t.value for t in WorkflowType] == ["standard", "evaluation"]


class TestReadingAVersion:
    @respx.mock
    def test_get_asks_for_the_workflow_with_its_active_version(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/{CREATED}").mock(side_effect=_replay(calls, "get_find_active"))

        # Act
        workflow = _client().workflows.get(CREATED)

        # Assert
        assert _query(calls[0]) == {"find_active_version": "true"}
        assert (workflow.id, workflow.active_version_number) == (CREATED, 0)

    @respx.mock
    def test_versions_get_reads_one_version_and_a_missing_one_is_not_found(self):
        # Arrange
        route = respx.get(f"{BASE}/v1/workflows/{CREATED}")
        route.side_effect = [
            httpx.Response(200, json=ANSWERS["get_version_0"]["body"]),
            httpx.Response(404, json=ANSWERS["get_version_missing"]["body"]),
        ]

        # Act
        version = _client().workflows.versions.get(CREATED, 0)
        with pytest.raises(NotFoundError, match="Version 7 not found"):
            _client().workflows.versions.get(CREATED, 7)

        # Assert
        assert [r.request.url.params["version_number"] for r in route.calls] == ["0", "7"]
        assert isinstance(version, WorkflowVersion)
        assert (version.version_number, version.version_name, version.is_active) == (0, "Default framework", True)
        assert version.config is not None

    @respx.mock
    def test_a_version_0_read_answered_with_the_workflow_itself_becomes_that_version(self):
        # A workflow stored before versions were has no snapshot of version 0; the server answers with the workflow.
        respx.get(f"{BASE}/v1/workflows/{CREATED}").mock(side_effect=_replay([], "get_find_active"))

        version = _client().workflows.versions.get(CREATED, 0)

        assert (version.version_number, version.is_active) == (0, True)
        assert version.config is not None

    @respx.mock
    def test_get_fully_hydrated_and_the_realtime_check_name_their_version_and_backend(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/{CREATED}").mock(
            side_effect=lambda r: (
                calls.append(r)
                or httpx.Response(200, json={"workflow": {"_id": CREATED, "workflow_config": {"workflow_config": {}}}})
            )
        )
        respx.get(f"{BASE}/v1/workflows/{CREATED}/realtime-compatibility").mock(
            side_effect=_replay(calls, "realtime_vertex")
        )

        # Act
        _client().workflows.get_fully_hydrated(CREATED, version_number=0)
        report = _client().workflows.realtime_compatibility(CREATED, model="gemini-live", backend="vertex")

        # Assert
        assert [_query(c) for c in calls] == [
            {"fully_hydrate": "true", "version_number": "0"},
            {"model": "gemini-live", "backend": "vertex"},
        ]
        assert report.model_dump().get("supported") is not None

    @respx.mock
    async def test_the_async_client_names_versions_too(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/{CREATED}").mock(side_effect=_replay(calls, "get_version_0"))
        client = _aclient()

        # Act
        version = await client.workflows.versions.get(CREATED, 0)

        # Assert
        assert (_query(calls[0]), version.version_number) == ({"version_number": "0"}, 0)
