"""
GlobalVariablesResource — manage team-scoped global variables.

Variables can be plain values or secrets (stored encrypted). They are
injected into workflow state under ``{{global.<name>}}`` at runtime.

Endpoints:
    POST   /v1/global-variables/bulk         → bulk_create
    POST   /v1/global-variables              → create
    GET    /v1/global-variables              → list (paginated)
    GET    /v1/global-variables/{id}         → get
    PATCH  /v1/global-variables/{id}         → update
    DELETE /v1/global-variables/{id}         → delete
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr
from interactly.types.global_variables.global_variable import GlobalVariable

__all__ = ["GlobalVariablesResource", "AsyncGlobalVariablesResource"]

_PATH = "/v1/global-variables"


class GlobalVariablesResource(SyncAPIResource):
    """Synchronous interface to the Global Variables API."""

    def create(
        self,
        *,
        name: str,
        value: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_secret: bool = False,
    ) -> GlobalVariable:
        """
        Create a single global variable.

        Args:
            name:        Unique variable name (used in ``{{global.<name>}}`` syntax).
            value:       Variable value (will be encrypted if ``is_secret=True``).
            description: Human-readable description.
            category:    Freeform category label for grouping.
            is_secret:   When ``True``, the value is encrypted at rest and redacted in API responses.

        Returns:
            The created :class:`GlobalVariable`.
        """
        body: Dict[str, Any] = {"name": name, "is_secret": is_secret}
        if value is not None:
            body["value"] = value
        if description is not None:
            body["description"] = description
        if category is not None:
            body["category"] = category
        return self._client.post(_PATH, body=body, cast_to=GlobalVariable)

    def bulk_create(self, *, variables: List[Dict[str, Any]]) -> List[GlobalVariable]:
        """
        Create multiple global variables in one request.

        Args:
            variables: List of variable dicts, each with ``name`` and optionally
                       ``value``, ``description``, ``category``, ``is_secret``.

        Returns:
            A list of successfully created :class:`GlobalVariable` objects.

        Raises:
            ValueError: If the server reports per-item ``errors`` (the message
                        includes the reported failures).
        """
        body: Dict[str, Any] = {"variables": variables}
        raw = self._client.post(f"{_PATH}/bulk", body=body, cast_to=dict)
        errors = raw.get("errors") or []
        if errors:
            raise ValueError(f"bulk_create reported {len(errors)} error(s): {errors}")
        return [GlobalVariable.model_validate(item) for item in raw.get("created", [])]

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        category: Optional[str] = None,
    ) -> SyncPage[GlobalVariable]:
        """
        List global variables.

        Args:
            page:     Page number (1-indexed, default 1).
            size:     Items per page (default 20).
            search:   Fuzzy name filter.
            category: Filter by category label.

        Returns:
            A :class:`SyncPage` of :class:`GlobalVariable` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if category is not None:
            params["category"] = category
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, GlobalVariable, lambda p: self.list(page=p, size=size, search=search, category=category))

    def get(self, variable_id: str) -> GlobalVariable:
        """
        Retrieve a single global variable by ID.

        Args:
            variable_id: ObjectId of the variable.

        Returns:
            The :class:`GlobalVariable`.

        Raises:
            NotFoundError: If no variable with the given ID exists.
        """
        return self._client.get(f"{_PATH}/{variable_id}", cast_to=GlobalVariable)

    def update(
        self,
        variable_id: str,
        *,
        name: NotGivenOr[Optional[str]] = NOT_GIVEN,
        value: NotGivenOr[Optional[str]] = NOT_GIVEN,
        description: NotGivenOr[Optional[str]] = NOT_GIVEN,
        category: NotGivenOr[Optional[str]] = NOT_GIVEN,
        is_secret: NotGivenOr[Optional[bool]] = NOT_GIVEN,
    ) -> GlobalVariable:
        """
        Update a global variable.

        Only provided (non-``NOT_GIVEN``) fields are sent to the server.

        Args:
            variable_id: ObjectId of the variable.
            name:        New unique name.
            value:       New value.
            description: New description.
            category:    New category label.
            is_secret:   Toggle encryption.

        Returns:
            The updated :class:`GlobalVariable`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(name):
            body["name"] = name
        if is_given(value):
            body["value"] = value
        if is_given(description):
            body["description"] = description
        if is_given(category):
            body["category"] = category
        if is_given(is_secret):
            body["is_secret"] = is_secret
        return self._client.patch(f"{_PATH}/{variable_id}", body=body, cast_to=GlobalVariable)

    def delete(self, variable_id: str) -> None:
        """
        Delete a global variable.

        Args:
            variable_id: ObjectId of the variable to delete.
        """
        self._client.delete(f"{_PATH}/{variable_id}", cast_to=type(None))

    def resolve(self) -> Dict[str, Any]:
        """
        Resolve all global variables for the team into a ``{name: value}`` dict.

        Secret values are decrypted server-side; this endpoint is intended for
        execution services that need to inject variables into workflow state.

        Returns:
            A plain dict mapping each variable name to its resolved value.
        """
        raw = self._client.get(f"{_PATH}/resolve", cast_to=dict)
        return cast(Dict[str, Any], raw.get("variables", raw))


class AsyncGlobalVariablesResource(AsyncAPIResource):
    """Asynchronous interface to the Global Variables API."""

    async def create(
        self,
        *,
        name: str,
        value: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        is_secret: bool = False,
    ) -> GlobalVariable:
        """Create a single global variable."""
        body: Dict[str, Any] = {"name": name, "is_secret": is_secret}
        if value is not None:
            body["value"] = value
        if description is not None:
            body["description"] = description
        if category is not None:
            body["category"] = category
        return await self._client.post(_PATH, body=body, cast_to=GlobalVariable)

    async def bulk_create(self, *, variables: List[Dict[str, Any]]) -> List[GlobalVariable]:
        """Create multiple global variables in one request.

        Returns the successfully created variables; raises ``ValueError`` if the
        server reports per-item ``errors``.
        """
        body: Dict[str, Any] = {"variables": variables}
        raw = await self._client.post(f"{_PATH}/bulk", body=body, cast_to=dict)
        errors = raw.get("errors") or []
        if errors:
            raise ValueError(f"bulk_create reported {len(errors)} error(s): {errors}")
        return [GlobalVariable.model_validate(item) for item in raw.get("created", [])]

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        category: Optional[str] = None,
    ) -> AsyncPage[GlobalVariable]:
        """List global variables."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if category is not None:
            params["category"] = category
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, GlobalVariable, lambda p: self.list(page=p, size=size, search=search, category=category))

    async def get(self, variable_id: str) -> GlobalVariable:
        """Retrieve a single global variable by ID."""
        return await self._client.get(f"{_PATH}/{variable_id}", cast_to=GlobalVariable)

    async def update(
        self,
        variable_id: str,
        *,
        name: NotGivenOr[Optional[str]] = NOT_GIVEN,
        value: NotGivenOr[Optional[str]] = NOT_GIVEN,
        description: NotGivenOr[Optional[str]] = NOT_GIVEN,
        category: NotGivenOr[Optional[str]] = NOT_GIVEN,
        is_secret: NotGivenOr[Optional[bool]] = NOT_GIVEN,
    ) -> GlobalVariable:
        """Update a global variable."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(name):
            body["name"] = name
        if is_given(value):
            body["value"] = value
        if is_given(description):
            body["description"] = description
        if is_given(category):
            body["category"] = category
        if is_given(is_secret):
            body["is_secret"] = is_secret
        return await self._client.patch(f"{_PATH}/{variable_id}", body=body, cast_to=GlobalVariable)

    async def delete(self, variable_id: str) -> None:
        """Delete a global variable."""
        await self._client.delete(f"{_PATH}/{variable_id}", cast_to=type(None))

    async def resolve(self) -> Dict[str, Any]:
        """
        Resolve all global variables for the team into a ``{name: value}`` dict.

        Returns:
            A plain dict mapping each variable name to its resolved value.
        """
        raw = await self._client.get(f"{_PATH}/resolve", cast_to=dict)
        return cast(Dict[str, Any], raw.get("variables", raw))
