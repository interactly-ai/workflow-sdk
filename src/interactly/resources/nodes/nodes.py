"""
NodesResource — CRUD for standalone workflow nodes.

Endpoints:
    GET    /v1/nodes/types               → types
    GET    /v1/nodes/schema/{node_type}  → schema
    POST   /v1/nodes                     → create
    GET    /v1/nodes                     → list (paginated)
    GET    /v1/nodes/{id}                → get
    PATCH  /v1/nodes/{id}                → update
    DELETE /v1/nodes/{id}                → delete
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import NodeConfigOrDict
from interactly.types.nodes.node import Node

__all__ = ["NodesResource", "AsyncNodesResource"]

_PATH = "/v1/nodes"


class NodesResource(SyncAPIResource):
    """Synchronous interface to the Nodes API."""

    def types(self) -> List[Dict[str, Any]]:
        """
        Retrieve all available node types with their categories.

        Returns:
            A list of dicts with ``type``, ``primary_category``, ``secondary_category``.
        """
        raw: Dict = self._client.get(f"{_PATH}/types", cast_to=dict)
        return raw.get("node_types", [])

    def schema(self, node_type: str) -> Dict[str, Any]:
        """
        Retrieve the JSON Schema for a specific node type.

        Args:
            node_type: The node type string (e.g. ``"llm"``).

        Returns:
            A dict with ``config_schema``, ``run_input_schema``, ``run_output_schema``.
        """
        return self._client.get(f"{_PATH}/schema/{node_type}", cast_to=dict)

    def create(self, *, node_config: NodeConfigOrDict) -> Node:
        """
        Create a new standalone node.

        Args:
            node_config: Full ``NodeConfig`` compatible dict or typed ``BaseNodeConfig`` object.

        Returns:
            The created :class:`Node`.
        """
        return self._client.post(_PATH, body=serialise_config(node_config), cast_to=Node)

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        node_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> SyncPage[Node]:
        """
        List nodes.

        Args:
            page:        Page number (1-indexed, default 1).
            size:        Items per page (default 20).
            search:      Fuzzy name filter.
            node_type:   Filter by node type.
            workflow_id: Filter to nodes belonging to a workflow.

        Returns:
            A :class:`SyncPage` of :class:`Node` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if node_type is not None:
            params["type"] = node_type
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, Node, lambda p: self.list(page=p, size=size, search=search, node_type=node_type, workflow_id=workflow_id))

    def get(self, node_id: str) -> Node:
        """
        Retrieve a single node by ID.

        Args:
            node_id: ObjectId of the node.

        Returns:
            The :class:`Node`.

        Raises:
            NotFoundError: If no node with the given ID exists.
        """
        return self._client.get(f"{_PATH}/{node_id}", cast_to=Node)

    def update(
        self,
        node_id: str,
        *,
        node_config: NotGivenOr[Optional[NodeConfigOrDict]] = NOT_GIVEN,
    ) -> Node:
        """
        Update a node's config.

        Args:
            node_id:     ObjectId of the node.
            node_config: Updated ``NodeConfig`` compatible dict or typed ``BaseNodeConfig`` object.

        Returns:
            The updated :class:`Node`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(node_config) and node_config is not None:
            # Partial update: only send fields the caller set, so the server
            # preserves unspecified fields (e.g. the node's existing logical_id
            # and name) instead of overwriting them with fresh config defaults.
            body = serialise_config(node_config, exclude_unset=True)
        return self._client.patch(f"{_PATH}/{node_id}", body=body, cast_to=Node)

    def delete(self, node_id: str) -> None:
        """
        Delete a node.

        Args:
            node_id: ObjectId of the node to delete.
        """
        self._client.delete(f"{_PATH}/{node_id}", cast_to=type(None))


class AsyncNodesResource(AsyncAPIResource):
    """Asynchronous interface to the Nodes API."""

    async def types(self) -> List[Dict[str, Any]]:
        """Retrieve all available node types with their categories."""
        raw: Dict = await self._client.get(f"{_PATH}/types", cast_to=dict)
        return raw.get("node_types", [])

    async def schema(self, node_type: str) -> Dict[str, Any]:
        """Retrieve the JSON Schema for a specific node type."""
        return await self._client.get(f"{_PATH}/schema/{node_type}", cast_to=dict)

    async def create(self, *, node_config: NodeConfigOrDict) -> Node:
        """Create a new standalone node."""
        return await self._client.post(_PATH, body=serialise_config(node_config), cast_to=Node)

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        node_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> AsyncPage[Node]:
        """List nodes."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if node_type is not None:
            params["type"] = node_type
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, Node, lambda p: self.list(page=p, size=size, search=search, node_type=node_type, workflow_id=workflow_id))

    async def get(self, node_id: str) -> Node:
        """Retrieve a single node by ID."""
        return await self._client.get(f"{_PATH}/{node_id}", cast_to=Node)

    async def update(
        self,
        node_id: str,
        *,
        node_config: NotGivenOr[Optional[NodeConfigOrDict]] = NOT_GIVEN,
    ) -> Node:
        """Update a node's config."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(node_config) and node_config is not None:
            # Partial update: only send fields the caller set, so the server
            # preserves unspecified fields (e.g. the node's existing logical_id
            # and name) instead of overwriting them with fresh config defaults.
            body = serialise_config(node_config, exclude_unset=True)
        return await self._client.patch(f"{_PATH}/{node_id}", body=body, cast_to=Node)

    async def delete(self, node_id: str) -> None:
        """Delete a node."""
        await self._client.delete(f"{_PATH}/{node_id}", cast_to=type(None))
