"""
Base classes for resource objects (e.g. WorkflowsResource, RunsResource).

Every resource holds a reference to the parent client so it can make requests
without knowing about the transport layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interactly._base_client import SyncAPIClient, AsyncAPIClient

__all__ = ["SyncAPIResource", "AsyncAPIResource"]


class SyncAPIResource:
    """
    Mixin for synchronous resource classes.
    Subclasses call ``self._client.get/post/patch/delete(...)`` to make requests.
    """

    _client: "SyncAPIClient"

    def __init__(self, client: "SyncAPIClient") -> None:
        self._client = client


class AsyncAPIResource:
    """
    Mixin for asynchronous resource classes.
    Subclasses call ``await self._client.get/post/patch/delete(...)`` to make requests.
    """

    _client: "AsyncAPIClient"

    def __init__(self, client: "AsyncAPIClient") -> None:
        self._client = client
