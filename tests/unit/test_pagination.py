"""
Unit tests for the pagination helpers (SyncPage, AsyncPage).
"""

from __future__ import annotations

import pytest

from interactly._pagination import AsyncPage, PageMetadata, SyncPage
from interactly._models import BaseAPIModel


class Item(BaseAPIModel):
    id: str
    name: str


def _make_page(items: list, total: int, page: int, size: int, pages: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


class TestSyncPage:
    def test_from_response_parses_items(self):
        raw = _make_page(
            items=[{"id": "1", "name": "Alpha"}, {"id": "2", "name": "Beta"}],
            total=2, page=1, size=20, pages=1,
        )

        def fetch(p: int) -> SyncPage[Item]:
            return SyncPage._from_response(_make_page([], 0, p, 20, 1), Item, fetch)

        page = SyncPage._from_response(raw, Item, fetch)
        assert len(page) == 2
        assert page.items[0].id == "1"
        assert page.items[1].name == "Beta"

    def test_iteration_yields_all_items(self):
        raw = _make_page(
            items=[{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            total=2, page=1, size=20, pages=1,
        )

        def fetch(p: int) -> SyncPage[Item]:
            return SyncPage._from_response(raw, Item, fetch)

        page = SyncPage._from_response(raw, Item, fetch)
        ids = [item.id for item in page]
        assert ids == ["a", "b"]

    def test_has_next_page_single_page(self):
        raw = _make_page(items=[{"id": "x", "name": "X"}], total=1, page=1, size=20, pages=1)

        def fetch(p: int) -> SyncPage[Item]:
            return SyncPage._from_response(raw, Item, fetch)

        page = SyncPage._from_response(raw, Item, fetch)
        assert page.has_next_page is False

    def test_has_next_page_multi_page(self):
        raw = _make_page(items=[{"id": "x", "name": "X"}], total=50, page=1, size=20, pages=3)

        def fetch(p: int) -> SyncPage[Item]:
            return SyncPage._from_response(raw, Item, fetch)

        page = SyncPage._from_response(raw, Item, fetch)
        assert page.has_next_page is True

    def test_list_all_single_page(self):
        raw = _make_page(
            items=[{"id": "1", "name": "A"}, {"id": "2", "name": "B"}],
            total=2, page=1, size=20, pages=1,
        )

        def fetch(p: int) -> SyncPage[Item]:
            return SyncPage._from_response(raw, Item, fetch)

        page = SyncPage._from_response(raw, Item, fetch)
        all_items = page.list_all()
        assert len(all_items) == 2

    def test_list_all_multi_page(self):
        page1_raw = _make_page(items=[{"id": "1", "name": "A"}], total=2, page=1, size=1, pages=2)
        page2_raw = _make_page(items=[{"id": "2", "name": "B"}], total=2, page=2, size=1, pages=2)

        def fetch(p: int) -> SyncPage[Item]:
            raw = page1_raw if p == 1 else page2_raw
            return SyncPage._from_response(raw, Item, fetch)

        page = SyncPage._from_response(page1_raw, Item, fetch)
        all_items = page.list_all()
        assert len(all_items) == 2
        assert all_items[0].id == "1"
        assert all_items[1].id == "2"


class TestAsyncPage:
    async def test_from_response_parses_items(self):
        raw = _make_page(items=[{"id": "1", "name": "A"}], total=1, page=1, size=20, pages=1)

        async def fetch(p: int) -> AsyncPage[Item]:
            return AsyncPage._from_response(raw, Item, fetch)

        page = AsyncPage._from_response(raw, Item, fetch)
        assert len(page.items) == 1

    async def test_aiter_yields_items(self):
        raw = _make_page(
            items=[{"id": "a", "name": "A"}, {"id": "b", "name": "B"}],
            total=2, page=1, size=20, pages=1,
        )

        async def fetch(p: int) -> AsyncPage[Item]:
            return AsyncPage._from_response(raw, Item, fetch)

        page = AsyncPage._from_response(raw, Item, fetch)
        collected = []
        async for item in page:
            collected.append(item)
        assert len(collected) == 2

    async def test_list_all_multi_page(self):
        page1_raw = _make_page(items=[{"id": "1", "name": "A"}], total=2, page=1, size=1, pages=2)
        page2_raw = _make_page(items=[{"id": "2", "name": "B"}], total=2, page=2, size=1, pages=2)

        async def fetch(p: int) -> AsyncPage[Item]:
            raw = page1_raw if p == 1 else page2_raw
            return AsyncPage._from_response(raw, Item, fetch)

        page = AsyncPage._from_response(page1_raw, Item, fetch)
        all_items = await page.list_all()
        assert len(all_items) == 2
