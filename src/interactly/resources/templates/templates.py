"""
TemplatesResource — CRUD for workflow templates.

Endpoints:
    GET    /v1/templates/schema          → schema
    POST   /v1/templates                 → create
    GET    /v1/templates                 → list (paginated)
    GET    /v1/templates/{id}            → get
    PATCH  /v1/templates/{id}            → update
    DELETE /v1/templates/{id}            → delete
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import WorkflowTemplateConfigOrDict
from interactly.types.templates.template import Template

__all__ = ["TemplatesResource", "AsyncTemplatesResource"]

_PATH = "/v1/templates"


class TemplatesResource(SyncAPIResource):
    """Synchronous interface to the Workflow Templates API."""

    def schema(self) -> Dict[str, Any]:
        """
        Retrieve the JSON Schema for workflow template configs.

        Returns:
            A dict containing ``config_schema``.
        """
        return self._client.get(f"{_PATH}/schema", cast_to=dict)

    def create(
        self,
        *,
        config: WorkflowTemplateConfigOrDict,
    ) -> Template:
        """
        Create a new workflow template.

        Args:
            config: A typed ``WorkflowTemplateConfig`` (preferred) or an
                    equivalent plain ``dict``.

        Returns:
            The created :class:`Template`.
        """
        return self._client.post(_PATH, body=serialise_config(config), cast_to=Template)

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        access_level: Optional[str] = None,
    ) -> SyncPage[Template]:
        """
        List workflow templates.

        Args:
            page:         Page number (1-indexed, default 1).
            size:         Items per page (default 20).
            search:       Fuzzy name filter.
            access_level: Filter by access level (e.g. ``"public"``, ``"private"``).

        Returns:
            A :class:`SyncPage` of :class:`Template` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if access_level is not None:
            params["access_level"] = access_level
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, Template, lambda p: self.list(page=p, size=size, search=search, access_level=access_level))

    def get(self, template_id: str) -> Template:
        """
        Retrieve a single workflow template by ID.

        Args:
            template_id: ObjectId of the template.

        Returns:
            The :class:`Template`.

        Raises:
            NotFoundError: If no template with the given ID exists.
        """
        return self._client.get(f"{_PATH}/{template_id}", cast_to=Template)

    def update(
        self,
        template_id: str,
        *,
        config: NotGivenOr[Optional[WorkflowTemplateConfigOrDict]] = NOT_GIVEN,
    ) -> Template:
        """
        Update a workflow template's config.

        Args:
            template_id: ObjectId of the template.
            config:      New typed ``WorkflowTemplateConfig`` (preferred) or dict.

        Returns:
            The updated :class:`Template`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(config):
            body = serialise_config(config) or {}
        return self._client.patch(f"{_PATH}/{template_id}", body=body, cast_to=Template)

    def delete(self, template_id: str) -> None:
        """
        Delete a workflow template.

        Args:
            template_id: ObjectId of the template to delete.
        """
        self._client.delete(f"{_PATH}/{template_id}", cast_to=type(None))


class AsyncTemplatesResource(AsyncAPIResource):
    """Asynchronous interface to the Workflow Templates API."""

    async def schema(self) -> Dict[str, Any]:
        """Retrieve the JSON Schema for workflow template configs."""
        return await self._client.get(f"{_PATH}/schema", cast_to=dict)

    async def create(self, *, config: WorkflowTemplateConfigOrDict) -> Template:
        """Create a new workflow template (typed config preferred; dict accepted)."""
        return await self._client.post(_PATH, body=serialise_config(config), cast_to=Template)

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        access_level: Optional[str] = None,
    ) -> AsyncPage[Template]:
        """List workflow templates."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if access_level is not None:
            params["access_level"] = access_level
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, Template, lambda p: self.list(page=p, size=size, search=search, access_level=access_level))

    async def get(self, template_id: str) -> Template:
        """Retrieve a single workflow template by ID."""
        return await self._client.get(f"{_PATH}/{template_id}", cast_to=Template)

    async def update(
        self,
        template_id: str,
        *,
        config: NotGivenOr[Optional[WorkflowTemplateConfigOrDict]] = NOT_GIVEN,
    ) -> Template:
        """Update a workflow template's config (typed config preferred; dict accepted)."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(config):
            body = serialise_config(config) or {}
        return await self._client.patch(f"{_PATH}/{template_id}", body=body, cast_to=Template)

    async def delete(self, template_id: str) -> None:
        """Delete a workflow template."""
        await self._client.delete(f"{_PATH}/{template_id}", cast_to=type(None))
