"""
Pagination helpers: SyncPage[T] and AsyncPage[T].

The backend returns list results as:
    {
        "items": [...],       # or "data"
        "total": 100,
        "page": 1,
        "size": 10,
        "pages": 10
    }

SyncPage / AsyncPage implement the iterator protocol and provide a
``list_all()`` / ``alist_all()`` convenience that auto-pages until exhausted.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Generic, Iterator, Optional, Type, TypeVar

from interactly._exceptions import NoMorePagesError
from interactly._models import BaseAPIModel

ItemT = TypeVar("ItemT")

__all__ = ["SyncPage", "AsyncPage"]


class PageMetadata(BaseAPIModel):
    """Common pagination metadata returned by the server.

    ``pages`` is ``None`` when the server did not supply enough information to
    know the total page count — in that case ``has_next`` is authoritative and
    we do NOT fabricate a page count from ``len(items)`` (which would falsely
    signal a single page and stop iteration early — see TR-5).
    """

    total: Optional[int] = None
    page: int = 1
    size: int = 0
    pages: Optional[int] = None
    # An explicit next-page signal / cursor from the server, when present.
    has_next: Optional[bool] = None


def _extract_items(raw: dict[str, Any]) -> list[Any]:
    # The server keys the list payload by resource name (e.g. ``workflows``,
    # ``versions``, ``variables``, ``workflow_runs``) rather than a uniform
    # ``items`` field. Recognise the common uniform keys first, then fall back
    # to the first list-valued entry that isn't pagination/aggregation metadata
    # (so any resource-named envelope — ``tools``, ``nodes``, ``schedules``,
    # ``simulations``, ``subscriptions``, … — works without an explicit entry).
    for key in ("items", "data", "workflows", "versions", "llm_configs"):
        value = raw.get(key)
        if isinstance(value, list):
            return value

    # Metadata/aggregation keys that are lists but are NOT the result rows.
    _non_item_lists = {"categories", "pages"}
    for key, value in raw.items():
        if key not in _non_item_lists and isinstance(value, list):
            return value
    return []


def _build_metadata(raw: dict[str, Any]) -> PageMetadata:
    """Build page metadata WITHOUT inferring the page count from ``len(items)``.

    Precedence for deciding whether more pages exist:
      1. An explicit ``pages`` count from the server (compute nothing).
      2. A ``total`` + ``size`` from the server → derive ``pages``.
      3. An explicit ``has_next`` / cursor signal.
    If none are present, ``pages``/``has_next`` stay ``None`` and iteration
    stops after the current page rather than fabricating a count.
    """
    page = raw.get("page", 1)
    size = raw.get("size")
    total = raw.get("total")
    pages = raw.get("pages")

    # Derive pages from total/size only when the server actually sent total.
    if pages is None and total is not None and size:
        try:
            pages = math.ceil(total / size)
        except (TypeError, ZeroDivisionError):
            pages = None

    # Recognise a few common explicit next-page signals / cursors.
    has_next = raw.get("has_next")
    if has_next is None:
        has_next = raw.get("has_more")
    if has_next is None and (raw.get("next_cursor") or raw.get("next_page")):
        has_next = True

    return PageMetadata.model_validate(
        {
            "total": total,
            "page": page,
            "size": size if size is not None else 0,
            "pages": pages,
            "has_next": has_next,
        }
    )


def _compute_has_next_page(meta: PageMetadata) -> bool:
    """Decide whether another page exists, favouring explicit server signals."""
    if meta.has_next is not None:
        return bool(meta.has_next)
    if meta.pages is not None:
        return meta.page < meta.pages
    # No page count and no explicit signal → assume this is the last page.
    return False


class SyncPage(Generic[ItemT]):
    """
    A single page of results.  Implements ``__iter__`` for straightforward
    iteration over items in the current page.

    For multi-page traversal use ``iter_pages()`` or ``list_all()``.
    """

    def __init__(
        self,
        *,
        items: list[ItemT],
        metadata: PageMetadata,
        fetch_page: Callable[[int], "SyncPage[ItemT]"],
    ) -> None:
        self.items = items
        self.metadata = metadata
        self._fetch_page = fetch_page

    @classmethod
    def _from_response(
        cls,
        raw: dict[str, Any],
        item_type: Type[ItemT],
        fetch_page: Callable[[int], "SyncPage[ItemT]"],
    ) -> "SyncPage[ItemT]":
        raw_items: list[Any] = _extract_items(raw)
        items = [item_type.model_validate(i) if hasattr(item_type, "model_validate") else item_type(i) for i in raw_items]  # type: ignore[attr-defined]
        meta = _build_metadata(raw)
        return cls(items=items, metadata=meta, fetch_page=fetch_page)

    # Iterator over items in this page.
    def __iter__(self) -> Iterator[ItemT]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def has_next_page(self) -> bool:
        return _compute_has_next_page(self.metadata)

    @property
    def total(self) -> Optional[int]:
        """Total number of items across all pages (``None`` if the server omits it)."""
        return self.metadata.total

    @property
    def page_number(self) -> int:
        """The 1-based index of this page."""
        return self.metadata.page

    @property
    def size(self) -> int:
        """The page size requested from the server."""
        return self.metadata.size

    @property
    def pages(self) -> Optional[int]:
        """Total number of pages (``None`` if the server omits enough info)."""
        return self.metadata.pages

    def next_page(self) -> "SyncPage[ItemT]":
        """Fetch the next page of results.

        Raises ``NoMorePagesError`` (not ``StopIteration``) when called on the
        last page, so it is safe to call from inside a caller's generator.
        """
        if not self.has_next_page:
            raise NoMorePagesError("No more pages")
        return self._fetch_page(self.metadata.page + 1)

    def iter_pages(self) -> Iterator["SyncPage[ItemT]"]:
        """Yield this page and all subsequent pages."""
        page: SyncPage[ItemT] = self
        while True:
            yield page
            if not page.has_next_page:
                break
            page = page.next_page()

    def list_all(self) -> list[ItemT]:
        """Collect all items across all pages into a single list."""
        result: list[ItemT] = []
        for page in self.iter_pages():
            result.extend(page.items)
        return result


class AsyncPage(Generic[ItemT]):
    """Async variant of SyncPage.  Use ``async for item in page:`` or ``await page.list_all()``."""

    def __init__(
        self,
        *,
        items: list[ItemT],
        metadata: PageMetadata,
        fetch_page: Callable[[int], "Any"],  # Coroutine returning AsyncPage[ItemT]
    ) -> None:
        self.items = items
        self.metadata = metadata
        self._fetch_page = fetch_page

    @classmethod
    def _from_response(
        cls,
        raw: dict[str, Any],
        item_type: Type[ItemT],
        fetch_page: Callable[[int], "Any"],
    ) -> "AsyncPage[ItemT]":
        raw_items: list[Any] = _extract_items(raw)
        items = [item_type.model_validate(i) if hasattr(item_type, "model_validate") else item_type(i) for i in raw_items]  # type: ignore[attr-defined]
        meta = _build_metadata(raw)
        return cls(items=items, metadata=meta, fetch_page=fetch_page)

    def __aiter__(self) -> "AsyncPage[ItemT]":
        self._iter_index = 0
        return self

    async def __anext__(self) -> ItemT:
        if self._iter_index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self._iter_index]
        self._iter_index += 1
        return item

    @property
    def has_next_page(self) -> bool:
        return _compute_has_next_page(self.metadata)

    @property
    def total(self) -> Optional[int]:
        """Total number of items across all pages (``None`` if the server omits it)."""
        return self.metadata.total

    @property
    def page_number(self) -> int:
        """The 1-based index of this page."""
        return self.metadata.page

    @property
    def size(self) -> int:
        """The page size requested from the server."""
        return self.metadata.size

    @property
    def pages(self) -> Optional[int]:
        """Total number of pages (``None`` if the server omits enough info)."""
        return self.metadata.pages

    async def next_page(self) -> "AsyncPage[ItemT]":
        """Fetch the next page of results.

        Raises ``NoMorePagesError`` (not ``StopAsyncIteration``) when called on
        the last page, so it is safe to call from inside a caller's async
        generator.
        """
        if not self.has_next_page:
            raise NoMorePagesError("No more pages")
        return await self._fetch_page(self.metadata.page + 1)

    async def list_all(self) -> list[ItemT]:
        result: list[ItemT] = []
        page: AsyncPage[ItemT] = self
        while True:
            result.extend(page.items)
            if not page.has_next_page:
                break
            page = await page.next_page()
        return result
