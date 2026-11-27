"""Lists page past their first page against a live server, whose list routes send only the rows and the total.

Read only.

    pytest tests/integration/test_list_paging_e2e.py -m integration
"""

from __future__ import annotations

import os

import pytest

from interactly import AsyncWorkflowClient, WorkflowClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]


@pytest.mark.parametrize("resource", ["workflows", "nodes", "runs"])
def test_three_pages_follow_one_another(resource):
    # Rows are not compared across pages: the server orders some lists by a time that rows written together share,
    # so a row can fall on two pages. Which page is asked for, and what the page says of itself, is the SDK's part.
    with WorkflowClient() as client:
        first = getattr(client, resource).list(size=3)
        if (first.total or 0) <= 9:
            pytest.skip(f"the team has {first.total} {resource}; this needs more than nine")
        pages = [first, first.next_page()]
        pages.append(pages[-1].next_page())

    assert [p.page_number for p in pages] == [1, 2, 3]
    assert all(p.has_next_page and len(p.items) == 3 for p in pages)
    assert {p.pages for p in pages} == {-(-first.total // 3)}


def test_list_all_collects_every_tool():
    # The tools list is short and changes rarely, so its total is a fair check of a complete collection.
    with WorkflowClient() as client:
        first = client.tools.list(size=7)
        everything = first.list_all()

    assert first.has_next_page == ((first.total or 0) > 7)
    assert len(everything) == first.total


async def test_the_async_client_pages_too():
    async with AsyncWorkflowClient() as client:
        first = await client.workflows.list(size=3)
        second = await first.next_page()

    assert (first.has_next_page, second.page_number, len(second.items)) == (True, 2, 3)
