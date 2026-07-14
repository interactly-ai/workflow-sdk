"""
NodeLibrariesResource — manage reusable node library packages.

Node libraries bundle sets of nodes and edges that can be imported into
workflows. They support versioned packages with access controls.

Endpoints:
    GET    /v1/node-libraries/schema     → schema
    POST   /v1/node-libraries            → create
    GET    /v1/node-libraries            → list (paginated)
    GET    /v1/node-libraries/{id}       → get
    PATCH  /v1/node-libraries/{id}       → update
    DELETE /v1/node-libraries/{id}       → delete
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import NodeConfigOrDict
from interactly.types.node_libraries.node_library import NodeLibrary

__all__ = ["NodeLibrariesResource", "AsyncNodeLibrariesResource"]

_PATH = "/v1/node-libraries"


class NodeLibrariesResource(SyncAPIResource):
    """Synchronous interface to the Node Libraries API."""

    def schema(self) -> Dict[str, Any]:
        """
        Retrieve the JSON Schema for node library configs.

        Returns:
            A dict containing ``config_schema``.
        """
        return self._client.get(f"{_PATH}/schema", cast_to=dict)

    def create(self, *, node_library_config: NodeConfigOrDict) -> NodeLibrary:
        """
        Create a new node library.

        Args:
            node_library_config: Full ``NodeLibraryConfig`` compatible dict or typed ``BaseNodeConfig`` object.

        Returns:
            The created :class:`NodeLibrary`.
        """
        return self._client.post(_PATH, body=serialise_config(node_library_config), cast_to=NodeLibrary)

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        access_level: Optional[str] = None,
    ) -> SyncPage[NodeLibrary]:
        """
        List node libraries.

        Args:
            page:         Page number (1-indexed, default 1).
            size:         Items per page (default 20).
            search:       Fuzzy name filter.
            access_level: Filter by access level (e.g. ``"public"``, ``"private"``).

        Returns:
            A :class:`SyncPage` of :class:`NodeLibrary` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if access_level is not None:
            params["access_level"] = access_level
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, NodeLibrary, lambda p: self.list(page=p, size=size, search=search, access_level=access_level))

    def get(self, library_id: str) -> NodeLibrary:
        """
        Retrieve a single node library by ID.

        Args:
            library_id: ObjectId of the node library.

        Returns:
            The :class:`NodeLibrary`.

        Raises:
            NotFoundError: If no node library with the given ID exists.
        """
        return self._client.get(f"{_PATH}/{library_id}", cast_to=NodeLibrary)

    def update(
        self,
        library_id: str,
        *,
        node_library_config: NotGivenOr[Optional[NodeConfigOrDict]] = NOT_GIVEN,
    ) -> NodeLibrary:
        """
        Update a node library's config.

        Args:
            library_id:          ObjectId of the node library.
            node_library_config: Updated config dict or typed ``BaseNodeConfig`` object.

        Returns:
            The updated :class:`NodeLibrary`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(node_library_config) and node_library_config is not None:
            body = serialise_config(node_library_config)
        return self._client.patch(f"{_PATH}/{library_id}", body=body, cast_to=NodeLibrary)

    def delete(self, library_id: str) -> None:
        """
        Delete a node library.

        Args:
            library_id: ObjectId of the node library to delete.
        """
        self._client.delete(f"{_PATH}/{library_id}", cast_to=type(None))


class AsyncNodeLibrariesResource(AsyncAPIResource):
    """Asynchronous interface to the Node Libraries API."""

    async def schema(self) -> Dict[str, Any]:
        """Retrieve the JSON Schema for node library configs."""
        return await self._client.get(f"{_PATH}/schema", cast_to=dict)

    async def create(self, *, node_library_config: NodeConfigOrDict) -> NodeLibrary:
        """Create a new node library."""
        return await self._client.post(_PATH, body=serialise_config(node_library_config), cast_to=NodeLibrary)

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        access_level: Optional[str] = None,
    ) -> AsyncPage[NodeLibrary]:
        """List node libraries."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if access_level is not None:
            params["access_level"] = access_level
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, NodeLibrary, lambda p: self.list(page=p, size=size, search=search, access_level=access_level))

    async def get(self, library_id: str) -> NodeLibrary:
        """Retrieve a single node library by ID."""
        return await self._client.get(f"{_PATH}/{library_id}", cast_to=NodeLibrary)

    async def update(
        self,
        library_id: str,
        *,
        node_library_config: NotGivenOr[Optional[NodeConfigOrDict]] = NOT_GIVEN,
    ) -> NodeLibrary:
        """Update a node library's config."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(node_library_config) and node_library_config is not None:
            body = serialise_config(node_library_config)
        return await self._client.patch(f"{_PATH}/{library_id}", body=body, cast_to=NodeLibrary)

    async def delete(self, library_id: str) -> None:
        """Delete a node library."""
        await self._client.delete(f"{_PATH}/{library_id}", cast_to=type(None))
