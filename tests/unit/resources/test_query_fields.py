"""The query fields the SDK sends: version guards and filters on nodes and edges, super-node versions, and the list
filters the server reads in place of ones it ignored.

The answers that carry content (a version guard's 404, a snapshot status, an unpublished dry run) were captured from a
workflow-service (``fixtures/query_fields.json``), with their ids replaced; the rest are empty pages. A next page is
asked for through the page's own fetch function: the server sends no page size, so the page can't tell there is one.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, NotFoundError, WorkflowClient
from interactly.resources.tools.tools import AsyncToolsResource, ToolsResource
from interactly.resources.workflows.versions import AsyncWorkflowVersionsResource, WorkflowVersionsResource

BASE = "http://localhost:8611"
ANSWERS: Dict[str, Dict[str, Any]] = json.loads((Path(__file__).parent / "fixtures" / "query_fields.json").read_text())
ITEM = "665f1c0a2b3c4d5e6f730000"
WORKFLOW = "665f1c0a2b3c4d5e6f730001"


def _client() -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _aclient() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _recording(calls: List[httpx.Request], body: Any, status: int = 200):
    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status, json=body)

    return _handler


def _query(request: httpx.Request) -> Dict[str, Any]:
    pairs = request.url.params.multi_items()
    keys = [k for k, _ in pairs]
    return {k: ([v for kk, v in pairs if kk == k] if keys.count(k) > 1 else dict(pairs)[k]) for k in dict(pairs)}


class TestNodesAndEdges:
    @pytest.mark.parametrize("kind", ["nodes", "edges"])
    @respx.mock
    def test_a_list_sends_the_logical_id_and_version_and_the_next_page_keeps_them(self, kind):
        # Arrange
        calls: List[httpx.Request] = []
        page = {kind: [{"_id": ITEM}], "total": 2}
        respx.get(f"{BASE}/v1/{kind}").mock(side_effect=_recording(calls, page))
        resource = getattr(_client(), kind)

        # Act
        resource.list(size=1, workflow_id=WORKFLOW, logical_id="node_abc", version_number=0)._fetch_page(2)

        # Assert
        assert [_query(c) for c in calls] == [
            {"page": str(n), "size": "1", "workflow_id": WORKFLOW, "logical_id": "node_abc", "version_number": "0"}
            for n in (1, 2)
        ]

    @pytest.mark.parametrize("kind", ["nodes", "edges"])
    @respx.mock
    def test_a_version_guard_goes_only_when_given_and_a_mismatch_is_not_found(self, kind):
        # Arrange
        calls: List[httpx.Request] = []
        answer = ANSWERS[f"{kind}_get_wrong_version"]
        respx.get(f"{BASE}/v1/{kind}/{ITEM}").mock(side_effect=_recording(calls, answer["body"], answer["status"]))
        resource = getattr(_client(), kind)

        # Act
        with pytest.raises(NotFoundError, match="not found in specified version"):
            resource.get(ITEM, version_number=1)
        with pytest.raises(NotFoundError):
            resource.get(ITEM)

        # Assert
        assert [_query(c) for c in calls] == [{"version_number": "1"}, {}]

    @pytest.mark.parametrize("kind", ["nodes", "edges"])
    @respx.mock
    def test_update_and_delete_carry_the_version_guard(self, kind):
        # Arrange
        calls: List[httpx.Request] = []
        respx.patch(f"{BASE}/v1/{kind}/{ITEM}").mock(side_effect=_recording(calls, {"_id": ITEM}))
        respx.delete(f"{BASE}/v1/{kind}/{ITEM}").mock(side_effect=_recording(calls, None))
        resource = getattr(_client(), kind)
        config_arg = {f"{kind[:-1]}_config": {"description": "x"}}

        # Act
        resource.update(ITEM, version_number=2, **config_arg)
        resource.delete(ITEM, version_number=2)
        resource.delete(ITEM)

        # Assert
        assert [(c.method, _query(c)) for c in calls] == [
            ("PATCH", {"version_number": "2"}),
            ("DELETE", {"version_number": "2"}),
            ("DELETE", {}),
        ]


class TestSuperNodesAndDynamicVariables:
    @respx.mock
    def test_publish_names_the_version_and_snapshot_status_reads_one(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.put(f"{BASE}/v1/workflows/{WORKFLOW}/super-node-interface").mock(side_effect=_recording(calls, {}))
        respx.get(f"{BASE}/v1/workflows/{WORKFLOW}/super-node-snapshot-status").mock(
            side_effect=_recording(calls, ANSWERS["snapshot_status_v1"]["body"])
        )

        # Act
        _client().super_nodes.publish(WORKFLOW, interface={"input_fields": []}, version_number=1)
        status = _client().super_nodes.snapshot_status(WORKFLOW, version_number=1)

        # Assert
        assert [_query(c) for c in calls] == [{"version_number": "1"}, {"version_number": "1"}]
        assert json.loads(calls[0].content) == {"interface": {"input_fields": []}}
        assert (status["version_number"], status["super_nodes"]) == (1, [])

    @respx.mock
    def test_a_dry_run_unpublish_says_so_and_a_real_one_does_not(self):
        # Arrange
        calls: List[httpx.Request] = []
        answer = ANSWERS["unpublish_dry_run_unpublished"]
        respx.delete(f"{BASE}/v1/workflows/{WORKFLOW}/super-node-interface").mock(
            side_effect=_recording(calls, answer["body"], answer["status"])
        )

        # Act
        for kwargs in ({"dry_run": True}, {"version_number": 0}):
            with pytest.raises(NotFoundError):
                _client().super_nodes.unpublish(WORKFLOW, **kwargs)

        # Assert
        assert [_query(c) for c in calls] == [{"dry_run": "true"}, {"version_number": "0"}]

    @respx.mock
    def test_dynamic_variables_can_name_a_version(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/dynamic-variables/{WORKFLOW}").mock(side_effect=_recording(calls, {}))

        # Act
        _client().workflows.dynamic_variables(WORKFLOW, version_number=1)
        _client().workflows.dynamic_variables(WORKFLOW)

        # Assert
        assert [_query(c) for c in calls] == [{"version_number": "1"}, {}]


class TestListFilters:
    @respx.mock
    def test_tools_list_sends_the_servers_filters_on_every_page(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/tools").mock(side_effect=_recording(calls, {"tools": [{"_id": ITEM}], "total": 2}))

        # Act
        _client().tools.list(
            size=1, tool_type="http", logical_id="tool_abc", name="book", category="Patients"
        )._fetch_page(2)

        # Assert
        expected = {"size": "1", "type": "http", "logical_id": "tool_abc", "name": "book", "category": "Patients"}
        assert [_query(c) for c in calls] == [{"page": "1", **expected}, {"page": "2", **expected}]

    @respx.mock
    def test_active_versions_send_search_and_every_creator(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflows/versions/active").mock(
            side_effect=_recording(calls, {"versions": [], "total": 0})
        )

        # Act
        _client().workflows.versions.list_active(search="intake", created_by=["u1", "u2"], categories=["Sales"])

        # Assert
        assert _query(calls[0]) == {
            "page": "1",
            "size": "20",
            "search": "intake",
            "categories": "Sales",
            "created_by": ["u1", "u2"],
        }

    def test_the_filters_the_server_ignored_are_gone(self):
        for method in (ToolsResource.list, AsyncToolsResource.list):
            assert "workflow_id" not in inspect.signature(method).parameters
        for method in (WorkflowVersionsResource.list_active, AsyncWorkflowVersionsResource.list_active):
            assert {"category", "created_by_me"}.isdisjoint(inspect.signature(method).parameters)

    @respx.mock
    def test_webhook_events_send_search_on_every_page(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflow-webhooks/events").mock(side_effect=_recording(calls, {"events": [], "total": 2}))

        # Act
        _client().webhooks.list_events(size=1, search="evt_")._fetch_page(2)

        # Assert
        assert [c.url.params.get("search") for c in calls] == ["evt_", "evt_"]

    @respx.mock
    async def test_the_async_client_sends_the_same_fields(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/nodes").mock(side_effect=_recording(calls, {"nodes": [], "total": 0}))
        respx.get(f"{BASE}/v1/tools").mock(side_effect=_recording(calls, {"tools": [], "total": 0}))
        respx.get(f"{BASE}/v1/workflows/versions/active").mock(
            side_effect=_recording(calls, {"versions": [], "total": 0})
        )
        respx.delete(f"{BASE}/v1/workflows/{WORKFLOW}/super-node-interface").mock(side_effect=_recording(calls, {}))
        client = _aclient()

        # Act
        await client.nodes.list(workflow_id=WORKFLOW, version_number=1)
        await client.tools.list(name="book")
        await client.workflows.versions.list_active(created_by=["u1"])
        await client.super_nodes.unpublish(WORKFLOW, dry_run=True)

        # Assert
        assert [c.url.params.get(k) for c, k in zip(calls, ("version_number", "name", "created_by", "dry_run"))] == [
            "1",
            "book",
            "u1",
            "true",
        ]
