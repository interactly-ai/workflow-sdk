"""The query fields the SDK sends do what they say: a version's nodes and edges are listed and guarded, and the list
filters narrow as the server reads them.

The one workflow created has two HTTP Request nodes joined by an edge, and is never run; it is deleted. Everything
else is read only.

    pytest tests/integration/test_query_fields_e2e.py -m integration
"""

from __future__ import annotations

import os
import uuid
from typing import Iterator, Tuple

import pytest

from interactly import NotFoundError, WorkflowClient
from interactly.configs import DirectEdgeConfig, HttpRequestNodeConfig, WorkflowConfig, WorkflowConfigFullyHydrated

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]


@pytest.fixture
def two_versions() -> Iterator[Tuple[WorkflowClient, str, str]]:
    """A client, and a throwaway workflow with versions 0 (active) and 1, as (client, workflow id, name)."""
    client = WorkflowClient()
    name = f"SDK_E2E query fields {uuid.uuid4().hex[:8]}"
    a = HttpRequestNodeConfig(name="A", is_start=True, url="https://api.unreachable.invalid/a")
    b = HttpRequestNodeConfig(name="B", url="https://api.unreachable.invalid/b")
    edge = DirectEdgeConfig(name="a->b", source_node_logical_id=a.logical_id, destination_node_logical_id=b.logical_id)
    workflow_id = client.workflows.create_from_config(
        WorkflowConfigFullyHydrated(workflow_config=WorkflowConfig(name=name), node_configs=[a, b], edge_configs=[edge])
    ).id
    try:
        client.workflows.versions.create(workflow_id, version_name="v1", source_version_number=0)
        yield client, workflow_id, name
    finally:
        client.workflows.delete(workflow_id)
        client.close()


@pytest.mark.parametrize("kind", ["nodes", "edges"])
def test_a_versions_nodes_and_edges_are_listed_and_guarded(two_versions, kind):
    client, workflow_id, _ = two_versions
    resource = getattr(client, kind)

    active = list(resource.list(workflow_id=workflow_id))
    in_v1 = list(resource.list(workflow_id=workflow_id, version_number=1))
    item = active[0]
    logical_id = (item.model_dump().get(f"{kind[:-1]}_config") or {}).get("logical_id") or item.logical_id
    same_logical = list(resource.list(workflow_id=workflow_id, logical_id=logical_id))

    assert len(active) == len(in_v1) == {"nodes": 2, "edges": 1}[kind]
    assert {i.id for i in active}.isdisjoint({i.id for i in in_v1})
    assert [i.id for i in same_logical] == [item.id]
    assert resource.get(item.id, version_number=0).id == item.id
    with pytest.raises(NotFoundError):
        resource.get(item.id, version_number=1)
    with pytest.raises(NotFoundError):
        resource.delete(item.id, version_number=1)
    assert resource.get(item.id).id == item.id


def test_a_version_is_named_for_its_dynamic_variables_and_super_node_status(two_versions):
    client, workflow_id, _ = two_versions

    status = client.super_nodes.snapshot_status(workflow_id, version_number=1)
    client.workflows.dynamic_variables(workflow_id, version_number=1)

    assert (status["version_number"], status["super_nodes"]) == (1, [])
    with pytest.raises(NotFoundError):
        client.workflows.dynamic_variables(workflow_id, version_number=9)


def test_the_list_filters_narrow_as_the_server_reads_them(two_versions):
    client, workflow_id, name = two_versions

    found = list(client.workflows.versions.list_active(search=name))
    by_nobody = client.workflows.versions.list_active(created_by=["0" * 24], size=1)
    tools = list(client.tools.list(size=100))
    named = list(client.tools.list(name=tools[0].name, size=100)) if tools else []
    no_events = client.webhooks.list_events(search="sdk-e2e-no-such-event", size=1)

    assert [v.model_dump().get("workflow_id") for v in found] == [workflow_id]
    assert by_nobody.total == 0
    assert tools and 0 < len(named) < len(tools)
    assert no_events.total == 0
