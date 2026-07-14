"""
SuperNodesResource — manage workflows published as super nodes.

Super nodes allow embedding one workflow inside another. Callers publish a
workflow as a super node, which records a versioned hydrated snapshot of its
config. Other workflows can then reference it via a SuperNodeConfig node.

Endpoints:
    GET    /v1/super-nodes                               → list
    GET    /v1/super-nodes/{workflow_id}                 → get
    GET    /v1/super-nodes/{workflow_id}/schema          → schema
    PUT    /v1/workflows/{workflow_id}/super-node-interface → publish
    DELETE /v1/workflows/{workflow_id}/super-node-interface → unpublish
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import SuperNodeInterfaceOrDict
from interactly.types.super_nodes.super_node import (
    SuperNodeDependent,
    SuperNodeDetail,
    SuperNodeExpandPreview,
    SuperNodeSummary,
)

__all__ = ["SuperNodesResource", "AsyncSuperNodesResource"]

_PATH = "/v1/super-nodes"
_WORKFLOWS_PATH = "/v1/workflows"


class SuperNodesResource(SyncAPIResource):
    """Synchronous interface to the Super Nodes API."""

    def list(self) -> List[SuperNodeSummary]:
        """
        List all super nodes published for the team.

        Returns a full ``List[SuperNodeSummary]`` (not a paginated ``SyncPage``)
        because the underlying endpoint is not paginated.

        Returns:
            A list of :class:`SuperNodeSummary` objects.
        """
        raw = self._client.get(_PATH, cast_to=list)
        return [SuperNodeSummary.model_validate(item) for item in (raw or [])]

    def get(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> SuperNodeDetail:
        """
        Retrieve the full super node definition for a workflow version.

        Args:
            workflow_id:     ObjectId of the encapsulated workflow.
            version_number:  Specific version (defaults to the workflow's active version).

        Returns:
            The :class:`SuperNodeDetail` including interface and hydrated config snapshot.

        Raises:
            NotFoundError: If the workflow has not been published as a super node.
        """
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return self._client.get(f"{_PATH}/{workflow_id}", cast_to=SuperNodeDetail, params=params)

    def schema(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve the JSON Schema for a super node's input fields.

        Useful for rendering input forms in workflow editors.

        Args:
            workflow_id:    ObjectId of the workflow.
            version_number: Specific version (defaults to the workflow's active version).

        Returns:
            A JSON Schema dict describing the ``field_values`` shape.
        """
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return self._client.get(f"{_PATH}/{workflow_id}/schema", cast_to=dict, params=params)

    def publish(
        self,
        workflow_id: str,
        *,
        interface: SuperNodeInterfaceOrDict,
    ) -> Dict[str, Any]:
        """
        Publish a workflow as a super node.

        Creates a new version of the workflow with a recorded ``SuperNodeInterface``
        and a hydrated snapshot of the workflow config.

        Args:
            workflow_id: ObjectId of the workflow to publish.
            interface:   A typed ``SuperNodeInterface`` (preferred) or an equivalent
                         ``dict`` describing input fields and their mappings into
                         the sub-workflow.

        Returns:
            A dict with ``workflow_id``, ``workflow_version_number``, ``message``,
            ``num_input_fields``.
        """
        return self._client.put(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-interface",
            body={"interface": serialise_config(interface)},
            cast_to=dict,
        )

    def unpublish(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Unpublish a workflow version as a super node.

        Sets ``is_active=False`` on the super node interface for the given
        (workflow, version) pair.  If ``version_number`` is omitted, the
        workflow's current active version is used.

        Args:
            workflow_id:    ObjectId of the workflow to unpublish.
            version_number: Specific version to unpublish (defaults to the
                            workflow's active version).

        Returns:
            A dict with ``workflow_id``, ``workflow_version_number``,
            ``message``, and ``workflows_referencing`` (list of workflow IDs
            that still reference this super node interface).

        Raises:
            NotFoundError: If the workflow has not been published as a super node.
        """
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return self._client.delete(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-interface",
            params=params,
            cast_to=dict,
        )

    def dependents(
        self,
        workflow_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> SyncPage[SuperNodeDependent]:
        """
        List workflows that embed this workflow as a super node (paginated).

        Useful before unpublishing to see what would break.

        Args:
            workflow_id: ObjectId of the published super-node workflow.
            page:        Page number (1-indexed, default 1).
            size:        Items per page (default 20).

        Returns:
            A :class:`SyncPage` of :class:`SuperNodeDependent` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = self._client.get(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-dependents", cast_to=dict, params=params
        )
        return SyncPage._from_response(
            raw, SuperNodeDependent, lambda p: self.dependents(workflow_id, page=p, size=size)
        )

    def expand_preview(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> SuperNodeExpandPreview:
        """
        Preview a workflow with all super nodes inlined as flat nodes/edges.

        Does not mutate the workflow; returns the expanded config plus a
        diagnostic expansion report.

        Args:
            workflow_id:    ObjectId of the workflow to expand.
            version_number: Specific version (defaults to the workflow's active version).
        """
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return self._client.post(
            f"{_WORKFLOWS_PATH}/{workflow_id}/expand-preview",
            params=params,
            cast_to=SuperNodeExpandPreview,
        )

    def snapshot_status(self, workflow_id: str) -> Dict[str, Any]:
        """
        Report whether the workflow's super-node snapshot is current.

        Args:
            workflow_id: ObjectId of the workflow.

        Returns:
            A status dict describing snapshot freshness.
        """
        return self._client.get(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-snapshot-status", cast_to=dict
        )


class AsyncSuperNodesResource(AsyncAPIResource):
    """Asynchronous interface to the Super Nodes API."""

    async def list(self) -> List[SuperNodeSummary]:
        """List all super nodes published for the team.

        Returns a full ``List[SuperNodeSummary]`` (not a paginated ``AsyncPage``)
        because the underlying endpoint is not paginated.
        """
        raw = await self._client.get(_PATH, cast_to=list)
        return [SuperNodeSummary.model_validate(item) for item in (raw or [])]

    async def get(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> SuperNodeDetail:
        """Retrieve the full super node definition for a workflow version."""
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return await self._client.get(f"{_PATH}/{workflow_id}", cast_to=SuperNodeDetail, params=params)

    async def schema(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Retrieve the JSON Schema for a super node's input fields."""
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return await self._client.get(f"{_PATH}/{workflow_id}/schema", cast_to=dict, params=params)

    async def publish(
        self,
        workflow_id: str,
        *,
        interface: SuperNodeInterfaceOrDict,
    ) -> Dict[str, Any]:
        """Publish a workflow as a super node (typed ``SuperNodeInterface`` preferred; dict accepted)."""
        return await self._client.put(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-interface",
            body={"interface": serialise_config(interface)},
            cast_to=dict,
        )

    async def unpublish(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Unpublish a workflow version as a super node."""
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return await self._client.delete(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-interface",
            params=params,
            cast_to=dict,
        )

    async def dependents(
        self,
        workflow_id: str,
        *,
        page: int = 1,
        size: int = 20,
    ) -> AsyncPage[SuperNodeDependent]:
        """List workflows that embed this workflow as a super node (paginated)."""
        params: Dict[str, Any] = {"page": page, "size": size}
        raw = await self._client.get(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-dependents", cast_to=dict, params=params
        )
        return AsyncPage._from_response(
            raw, SuperNodeDependent, lambda p: self.dependents(workflow_id, page=p, size=size)
        )

    async def expand_preview(
        self,
        workflow_id: str,
        *,
        version_number: Optional[int] = None,
    ) -> SuperNodeExpandPreview:
        """Preview a workflow with all super nodes inlined as flat nodes/edges."""
        params: Dict[str, Any] = {}
        if version_number is not None:
            params["version_number"] = version_number
        return await self._client.post(
            f"{_WORKFLOWS_PATH}/{workflow_id}/expand-preview",
            params=params,
            cast_to=SuperNodeExpandPreview,
        )

    async def snapshot_status(self, workflow_id: str) -> Dict[str, Any]:
        """Report whether the workflow's super-node snapshot is current."""
        return await self._client.get(
            f"{_WORKFLOWS_PATH}/{workflow_id}/super-node-snapshot-status", cast_to=dict
        )
