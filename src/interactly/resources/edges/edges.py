"""
EdgesResource — CRUD for standalone workflow edges.

Endpoints:
    GET    /v1/edges/types               → types
    GET    /v1/edges/schema/{edge_type}  → schema
    POST   /v1/edges                     → create
    GET    /v1/edges                     → list (paginated)
    GET    /v1/edges/{id}                → get
    PATCH  /v1/edges/{id}                → update
    DELETE /v1/edges/{id}                → delete
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import EdgeConfigOrDict
from interactly.types.edges.edge import Edge

__all__ = ["EdgesResource", "AsyncEdgesResource"]

_PATH = "/v1/edges"


class EdgesResource(SyncAPIResource):
    """Synchronous interface to the Edges API."""

    def types(self) -> List[str]:
        """
        Retrieve all available edge type identifiers.

        Returns:
            A list of edge type strings.
        """
        raw: Dict = self._client.get(f"{_PATH}/types", cast_to=dict)
        return raw.get("edge_types", [])

    def schema(self, edge_type: str) -> Dict[str, Any]:
        """
        Retrieve the JSON Schema for a specific edge type.

        Args:
            edge_type: The edge type string.

        Returns:
            A dict with ``config_schema`` and ``run_input_schema``.
        """
        return self._client.get(f"{_PATH}/schema/{edge_type}", cast_to=dict)

    def create(self, *, edge_config: EdgeConfigOrDict) -> Edge:
        """
        Create a new standalone edge.

        Args:
            edge_config: Full ``EdgeConfig`` compatible dict or typed ``EdgeConfig`` object.

        Returns:
            The created :class:`Edge`.
        """
        return self._client.post(_PATH, body=serialise_config(edge_config), cast_to=Edge)

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        edge_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> SyncPage[Edge]:
        """
        List edges.

        Args:
            page:        Page number (1-indexed, default 1).
            size:        Items per page (default 20).
            search:      Fuzzy name filter.
            edge_type:   Filter by edge type.
            workflow_id: Filter to edges belonging to a workflow.

        Returns:
            A :class:`SyncPage` of :class:`Edge` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if edge_type is not None:
            params["type"] = edge_type
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, Edge, lambda p: self.list(page=p, size=size, search=search, edge_type=edge_type, workflow_id=workflow_id))

    def get(self, edge_id: str) -> Edge:
        """
        Retrieve a single edge by ID.

        Args:
            edge_id: ObjectId of the edge.

        Returns:
            The :class:`Edge`.

        Raises:
            NotFoundError: If no edge with the given ID exists.
        """
        return self._client.get(f"{_PATH}/{edge_id}", cast_to=Edge)

    def update(
        self,
        edge_id: str,
        *,
        edge_config: NotGivenOr[Optional[EdgeConfigOrDict]] = NOT_GIVEN,
    ) -> Edge:
        """
        Update an edge's config.

        Args:
            edge_id:     ObjectId of the edge.
            edge_config: Updated ``EdgeConfig`` compatible dict or typed ``EdgeConfig`` object.

        Returns:
            The updated :class:`Edge`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(edge_config) and edge_config is not None:
            # Partial update: only send fields the caller set, so the server
            # preserves unspecified fields (e.g. the edge's existing logical_id)
            # instead of overwriting them with fresh config defaults.
            body = serialise_config(edge_config, exclude_unset=True)
        return self._client.patch(f"{_PATH}/{edge_id}", body=body, cast_to=Edge)

    def delete(self, edge_id: str) -> None:
        """
        Delete an edge.

        Args:
            edge_id: ObjectId of the edge to delete.
        """
        self._client.delete(f"{_PATH}/{edge_id}", cast_to=type(None))


class AsyncEdgesResource(AsyncAPIResource):
    """Asynchronous interface to the Edges API."""

    async def types(self) -> List[str]:
        """Retrieve all available edge type identifiers."""
        raw: Dict = await self._client.get(f"{_PATH}/types", cast_to=dict)
        return raw.get("edge_types", [])

    async def schema(self, edge_type: str) -> Dict[str, Any]:
        """Retrieve the JSON Schema for a specific edge type."""
        return await self._client.get(f"{_PATH}/schema/{edge_type}", cast_to=dict)

    async def create(self, *, edge_config: EdgeConfigOrDict) -> Edge:
        """Create a new standalone edge."""
        return await self._client.post(_PATH, body=serialise_config(edge_config), cast_to=Edge)

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        edge_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> AsyncPage[Edge]:
        """List edges."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if edge_type is not None:
            params["type"] = edge_type
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, Edge, lambda p: self.list(page=p, size=size, search=search, edge_type=edge_type, workflow_id=workflow_id))

    async def get(self, edge_id: str) -> Edge:
        """Retrieve a single edge by ID."""
        return await self._client.get(f"{_PATH}/{edge_id}", cast_to=Edge)

    async def update(
        self,
        edge_id: str,
        *,
        edge_config: NotGivenOr[Optional[EdgeConfigOrDict]] = NOT_GIVEN,
    ) -> Edge:
        """Update an edge's config."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(edge_config) and edge_config is not None:
            # Partial update: only send fields the caller set, so the server
            # preserves unspecified fields (e.g. the edge's existing logical_id)
            # instead of overwriting them with fresh config defaults.
            body = serialise_config(edge_config, exclude_unset=True)
        return await self._client.patch(f"{_PATH}/{edge_id}", body=body, cast_to=Edge)

    async def delete(self, edge_id: str) -> None:
        """Delete an edge."""
        await self._client.delete(f"{_PATH}/{edge_id}", cast_to=type(None))
