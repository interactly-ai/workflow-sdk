"""Every list pages past its first page, against the shape the list routes really answer with.

A list route sends the rows under a resource-named key and the total across all pages, and nothing about the page or
the page size it served (13 routes checked on a workflow-service: ``{"workflows": [...], "total": 138}``). Each list
method therefore tells the pager the page and size it asked for; without them the pager could not count pages, and
``list_all()`` stopped after the first.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, NoMorePagesError, WorkflowClient

BASE = "http://localhost:8611"
TOTAL = 5
SIZE = 2

_WEBHOOK = {
    "name": "hook",
    "url": "https://hooks.example.invalid/in",
    "actions": [],
    "enabled": True,
    "has_bearer_token": False,
    "timeout_seconds": 10,
    "max_retries": 3,
    "retry_backoff_seconds": 5,
}

#: (client attribute path, method, route, the key the route lists its rows under, the fields a row needs)
LISTS = [
    ("nodes", "list", "/v1/nodes", "nodes", {}),
    ("edges", "list", "/v1/edges", "edges", {}),
    ("tools", "list", "/v1/tools", "tools", {}),
    ("workflows", "list", "/v1/workflows", "workflows", {}),
    ("workflows.versions", "list_active", "/v1/workflows/versions/active", "versions", {"version_number": 0}),
    ("node_libraries", "list", "/v1/node-libraries", "node_libraries", {}),
    ("templates", "list", "/v1/templates", "workflow_templates", {}),
    ("llm_configs", "list", "/v1/llm-configs", "llm_configs", {}),
    ("global_variables", "list", "/v1/global-variables", "variables", {"name": "v"}),
    ("webhooks", "list", "/v1/workflow-webhooks", "webhooks", _WEBHOOK),
    ("runs", "list", "/v1/workflow-runs", "workflow_runs", {"workflow_id": "665f1c0a2b3c4d5e6f749999"}),
]


def _client() -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _aclient() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


def _resource(client: Any, path: str) -> Any:
    for name in path.split("."):
        client = getattr(client, name)
    return client


def _pages(calls: List[httpx.Request], key: str, row: Dict[str, Any]):
    """Answer as the list routes do: this page's rows and the total, no page or size."""

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        page, size = int(request.url.params["page"]), int(request.url.params["size"])
        numbers = range((page - 1) * size, min(page * size, TOTAL))
        rows = [{**row, "_id": f"665f1c0a2b3c4d5e6f74{n:04x}", "id": f"665f1c0a2b3c4d5e6f74{n:04x}"} for n in numbers]
        return httpx.Response(200, json={key: rows, "total": TOTAL})

    return _handler


class TestEveryListPages:
    @pytest.mark.parametrize("path, method, route, key, row", LISTS, ids=[f"{p}.{m}" for p, m, *_ in LISTS])
    @respx.mock
    def test_list_all_collects_every_page(self, path, method, route, key, row):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}{route}").mock(side_effect=_pages(calls, key, row))

        # Act
        first = getattr(_resource(_client(), path), method)(size=SIZE)
        everything = first.list_all()

        # Assert
        assert (first.page_number, first.size, first.pages, first.has_next_page) == (1, SIZE, 3, True)
        assert len({item.id for item in everything}) == TOTAL
        assert [(c.url.params["page"], c.url.params["size"]) for c in calls] == [("1", "2"), ("2", "2"), ("3", "2")]

    @pytest.mark.parametrize("path, method, route, key, row", LISTS, ids=[f"{p}.{m}" for p, m, *_ in LISTS])
    @respx.mock
    async def test_the_async_lists_page_too(self, path, method, route, key, row):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}{route}").mock(side_effect=_pages(calls, key, row))

        # Act
        everything = await (await getattr(_resource(_aclient(), path), method)(size=SIZE)).list_all()

        # Assert
        assert len({item.id for item in everything}) == TOTAL
        assert [c.url.params["page"] for c in calls] == ["1", "2", "3"]

    @respx.mock
    def test_the_last_page_says_so(self):
        # Arrange
        respx.get(f"{BASE}/v1/workflows").mock(side_effect=_pages([], "workflows", {}))
        last = _client().workflows.list(page=3, size=SIZE)

        # Act / Assert
        assert (last.page_number, last.has_next_page, len(last.items)) == (3, False, 1)
        with pytest.raises(NoMorePagesError):
            last.next_page()

    @respx.mock
    def test_a_page_and_size_the_server_sends_take_precedence(self):
        # Arrange: super-node dependents is the one list route that says which page and size it served.
        workflow = "665f1c0a2b3c4d5e6f740100"
        respx.get(f"{BASE}/v1/workflows/{workflow}/super-node-dependents").mock(
            return_value=httpx.Response(200, json={"workflows": [], "total": 5, "page": 1, "size": 5})
        )

        # Act
        page = _client().super_nodes.dependents(workflow, size=SIZE)

        # Assert
        assert (page.size, page.pages, page.has_next_page) == (5, 1, False)


def test_every_list_method_tells_the_pager_its_page_and_size():
    # A list method that hands the pager the server's body alone can't page: the body has no page size.
    resources = Path(__file__).resolve().parents[2] / "src" / "interactly" / "resources"
    missing = []
    for source in sorted(resources.rglob("*.py")):
        for node in ast.walk(ast.parse(source.read_text())):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "_from_response"):
                continue
            keywords = {k.arg for k in node.keywords}
            first = node.args[0] if node.args else None
            literal = (
                {k.value for k in first.keys if isinstance(k, ast.Constant)} if isinstance(first, ast.Dict) else set()
            )
            if not ({"page", "size"} <= keywords or {"page", "size"} <= literal):
                missing.append(f"{source.relative_to(resources)}:{node.lineno}")
    assert missing == []
