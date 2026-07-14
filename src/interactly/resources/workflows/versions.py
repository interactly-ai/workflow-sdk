"""
WorkflowVersionsResource — sub-resource of WorkflowsResource.

Provides CRUD + activation for a specific workflow's versions:
    client.workflows.versions.create(workflow_id, ...)
    client.workflows.versions.list(workflow_id)
    client.workflows.versions.activate(workflow_id, version_number)
    client.workflows.versions.update(workflow_id, version_number, ...)
    client.workflows.versions.update_config(workflow_id, version_number, config=...)
    client.workflows.versions.delete(workflow_id, version_number)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._utils._serialise import serialise_config
from interactly._utils._transform import build_body
from interactly.types._config_types import WorkflowConfigOrDict
from interactly.types.workflows.params import VersionConfigUpdateParams, VersionCreateParams, VersionUpdateParams
from interactly.types.workflows.version_diff import VersionDiff
from interactly.types.workflows.workflow import Workflow, WorkflowVersion

__all__ = ["WorkflowVersionsResource", "AsyncWorkflowVersionsResource"]

_ACTIVE_PATH = "/v1/workflows/versions/active"


def _build_active_params(
    *,
    page: int,
    size: int,
    favorites: Optional[bool],
    created_by_me: Optional[bool],
    category: Optional[str],
    categories: Optional[List[str]],
    logical_id: Optional[str],
) -> Dict[str, Any]:
    params: Dict[str, Any] = {"page": page, "size": size}
    if favorites is not None:
        params["favorites"] = favorites
    if created_by_me is not None:
        params["created_by_me"] = created_by_me
    if category is not None:
        params["category"] = category
    if categories is not None:
        params["categories"] = categories
    if logical_id is not None:
        params["logical_id"] = logical_id
    return params


class WorkflowVersionsResource(SyncAPIResource):
    """Synchronous interface to workflow version endpoints."""

    def _path(self, workflow_id: str, version_number: Optional[int] = None) -> str:
        base = f"/v1/workflows/{workflow_id}/versions"
        return f"{base}/{version_number}" if version_number is not None else base

    def create(
        self,
        workflow_id: str,
        *,
        version_name: Optional[str] = None,
        mark_as_active: bool = False,
        source_version_number: Optional[int] = None,
    ) -> WorkflowVersion:
        """
        Create a new version of the workflow.

        Args:
            workflow_id:           The workflow to version.
            version_name:          Optional human-readable label.
            mark_as_active:        Immediately activate this version.
            source_version_number: Clone from this version (default: current active).
        """
        body: dict[str, Any] = {"mark_as_active": mark_as_active}
        if version_name is not None:
            body["version_name"] = version_name
        if source_version_number is not None:
            body["source_version_number"] = source_version_number

        version = self._client.post(
            self._path(workflow_id),
            body=body,
            cast_to=WorkflowVersion,
        )
        if mark_as_active:
            version.is_active = True
        return version

    def list(self, workflow_id: str) -> List[WorkflowVersion]:
        """Return all versions for the given workflow.

        Returns a full ``List[WorkflowVersion]`` (not a paginated ``SyncPage``)
        because the underlying endpoint is not paginated.
        """
        result = self._client.get(
            self._path(workflow_id),
            cast_to=dict,
        )
        items = result.get("versions", []) if isinstance(result, dict) else []
        return [WorkflowVersion.model_validate(v) for v in items]

    def activate(self, workflow_id: str, version_number: int) -> Workflow:
        """Mark a specific version as the active version.

        Returns the updated :class:`Workflow` (the activate endpoint responds
        with the full workflow, whose ``active_version_number`` now points at
        ``version_number``).
        """
        return self._client.post(
            f"{self._path(workflow_id, version_number)}/activate",
            cast_to=Workflow,
        )

    def update(
        self,
        workflow_id: str,
        version_number: int,
        *,
        version_name: str,
    ) -> WorkflowVersion:
        """Rename a workflow version."""
        return self._client.patch(
            self._path(workflow_id, version_number),
            body={"version_name": version_name},
            cast_to=WorkflowVersion,
        )

    def update_config(
        self,
        workflow_id: str,
        version_number: int,
        *,
        config: WorkflowConfigOrDict,
    ) -> WorkflowVersion:
        """Replace the graph config (nodes + edges) for a version."""
        return self._client.patch(
            f"{self._path(workflow_id, version_number)}/config",
            body={"config": serialise_config(config)},
            cast_to=WorkflowVersion,
        )

    def delete(self, workflow_id: str, version_number: int) -> None:
        """Permanently delete a workflow version."""
        self._client.delete(
            self._path(workflow_id, version_number),
            cast_to=type(None),
        )

    def diff(self, workflow_id: str, version1: int, version2: int) -> VersionDiff:
        """
        Compare two workflow versions and return a structured diff.

        Args:
            workflow_id: ObjectId of the workflow.
            version1:    First version number (typically the older version).
            version2:    Second version number (typically the newer version).

        Returns:
            A :class:`VersionDiff` with ``workflow_config_changes``, ``nodes``,
            ``edges``, and ``summary``. Each ``NodeDiff``/``EdgeDiff`` carries a
            ``status`` (``added``/``removed``/``modified``); for modified entries,
            ``changes`` lists the field-level ``FieldDiff``s (e.g. a
            ``main_response_config.prompt`` change with its old and new values).
        """
        return self._client.get(
            f"/v1/workflows/{workflow_id}/versions/{version1}/diff/{version2}",
            cast_to=VersionDiff,
        )

    def list_active(
        self,
        *,
        page: int = 1,
        size: int = 20,
        favorites: Optional[bool] = None,
        created_by_me: Optional[bool] = None,
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        logical_id: Optional[str] = None,
    ) -> SyncPage[WorkflowVersion]:
        """
        List every workflow's active version across the team (paginated).

        This is not scoped to a single workflow — it returns one active version
        per workflow, honouring the same filters as the workflow list.

        Args:
            page:          Page number (1-indexed, default 1).
            size:          Items per page (default 20).
            favorites:     Restrict to the user's favorited workflows.
            created_by_me: Restrict to workflows created by the requesting user.
            category:      Filter by a single category name.
            categories:    Filter by multiple category names.
            logical_id:    Filter by workflow logical ID.

        Returns:
            A :class:`SyncPage` of :class:`WorkflowVersion` objects.
        """
        params = _build_active_params(
            page=page,
            size=size,
            favorites=favorites,
            created_by_me=created_by_me,
            category=category,
            categories=categories,
            logical_id=logical_id,
        )
        raw = self._client.get(_ACTIVE_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(
            raw,
            WorkflowVersion,
            lambda p: self.list_active(
                page=p,
                size=size,
                favorites=favorites,
                created_by_me=created_by_me,
                category=category,
                categories=categories,
                logical_id=logical_id,
            ),
        )


class AsyncWorkflowVersionsResource(AsyncAPIResource):
    """Async interface to workflow version endpoints."""

    def _path(self, workflow_id: str, version_number: Optional[int] = None) -> str:
        base = f"/v1/workflows/{workflow_id}/versions"
        return f"{base}/{version_number}" if version_number is not None else base

    async def create(
        self,
        workflow_id: str,
        *,
        version_name: Optional[str] = None,
        mark_as_active: bool = False,
        source_version_number: Optional[int] = None,
    ) -> WorkflowVersion:
        body: dict[str, Any] = {"mark_as_active": mark_as_active}
        if version_name is not None:
            body["version_name"] = version_name
        if source_version_number is not None:
            body["source_version_number"] = source_version_number

        version = await self._client.post(
            self._path(workflow_id),
            body=body,
            cast_to=WorkflowVersion,
        )
        if mark_as_active:
            version.is_active = True
        return version

    async def list(self, workflow_id: str) -> List[WorkflowVersion]:
        """Return all versions for the given workflow.

        Returns a full ``List[WorkflowVersion]`` (not a paginated ``AsyncPage``)
        because the underlying endpoint is not paginated.
        """
        result = await self._client.get(
            self._path(workflow_id),
            cast_to=dict,
        )
        items = result.get("versions", []) if isinstance(result, dict) else []
        return [WorkflowVersion.model_validate(v) for v in items]

    async def activate(self, workflow_id: str, version_number: int) -> Workflow:
        """Mark a specific version as the active version.

        Returns the updated :class:`Workflow` (the activate endpoint responds
        with the full workflow, whose ``active_version_number`` now points at
        ``version_number``).
        """
        return await self._client.post(
            f"{self._path(workflow_id, version_number)}/activate",
            cast_to=Workflow,
        )

    async def update(
        self,
        workflow_id: str,
        version_number: int,
        *,
        version_name: str,
    ) -> WorkflowVersion:
        return await self._client.patch(
            self._path(workflow_id, version_number),
            body={"version_name": version_name},
            cast_to=WorkflowVersion,
        )

    async def update_config(
        self,
        workflow_id: str,
        version_number: int,
        *,
        config: WorkflowConfigOrDict,
    ) -> WorkflowVersion:
        return await self._client.patch(
            f"{self._path(workflow_id, version_number)}/config",
            body={"config": serialise_config(config)},
            cast_to=WorkflowVersion,
        )

    async def delete(self, workflow_id: str, version_number: int) -> None:
        await self._client.delete(
            self._path(workflow_id, version_number),
            cast_to=type(None),
        )

    async def diff(self, workflow_id: str, version1: int, version2: int) -> VersionDiff:
        """
        Compare two workflow versions and return a structured diff.

        Args:
            workflow_id: ObjectId of the workflow.
            version1:    First version number (typically the older version).
            version2:    Second version number (typically the newer version).

        Returns:
            A :class:`VersionDiff` with ``workflow_config_changes``, ``nodes``,
            ``edges``, and ``summary``. Each ``NodeDiff``/``EdgeDiff`` carries a
            ``status`` (``added``/``removed``/``modified``); for modified entries,
            ``changes`` lists the field-level ``FieldDiff``s (e.g. a
            ``main_response_config.prompt`` change with its old and new values).
        """
        return await self._client.get(
            f"/v1/workflows/{workflow_id}/versions/{version1}/diff/{version2}",
            cast_to=VersionDiff,
        )

    async def list_active(
        self,
        *,
        page: int = 1,
        size: int = 20,
        favorites: Optional[bool] = None,
        created_by_me: Optional[bool] = None,
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        logical_id: Optional[str] = None,
    ) -> AsyncPage[WorkflowVersion]:
        """List every workflow's active version across the team (paginated)."""
        params = _build_active_params(
            page=page,
            size=size,
            favorites=favorites,
            created_by_me=created_by_me,
            category=category,
            categories=categories,
            logical_id=logical_id,
        )
        raw = await self._client.get(_ACTIVE_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(
            raw,
            WorkflowVersion,
            lambda p: self.list_active(
                page=p,
                size=size,
                favorites=favorites,
                created_by_me=created_by_me,
                category=category,
                categories=categories,
                logical_id=logical_id,
            ),
        )
