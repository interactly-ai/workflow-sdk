"""
ToolsResource — CRUD for custom LLM tools.

Endpoints:
    GET    /v1/tools/types               → types
    GET    /v1/tools/schema/{tool_type}  → schema
    GET    /v1/tools/inbuilt             → inbuilt
    POST   /v1/tools                     → create
    GET    /v1/tools                     → list (paginated)
    GET    /v1/tools/{id}                → get
    PATCH  /v1/tools/{id}                → update
    DELETE /v1/tools/{id}                → delete
    POST   /v1/tools/{id}/clone          → clone
    POST   /v1/tools/{id}/execute        → execute
    POST   /v1/tools/execute             → execute_inline
    GET    /v1/tools/codebase-functions       → codebase_functions      (staff only)
    GET    /v1/tools/codebase-functions/{id}  → get_codebase_function   (staff only)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import ToolConfigOrDict
from interactly.types.tools.codebase_function import CodebaseFunction, CodebaseFunctionCatalogue
from interactly.types.tools.execute_result import ToolExecuteResult
from interactly.types.tools.tool import Tool

__all__ = ["ToolsResource", "AsyncToolsResource"]

_PATH = "/v1/tools"


class ToolsResource(SyncAPIResource):
    """Synchronous interface to the Tools API."""

    def types(self) -> List[str]:
        """
        Retrieve all available tool type identifiers.

        Returns:
            A list of tool type strings.
        """
        raw: Dict[str, Any] = self._client.get(f"{_PATH}/types", cast_to=dict)
        return cast(List[str], raw.get("tool_types", []))

    def schema(self, tool_type: str) -> Dict[str, Any]:
        """
        Retrieve the JSON Schema for a specific tool type.

        Args:
            tool_type: The tool type string.

        Returns:
            A dict with ``config_schema``.
        """
        return self._client.get(f"{_PATH}/schema/{tool_type}", cast_to=dict)

    def inbuilt(self) -> List[Dict[str, Any]]:
        """
        Retrieve all inbuilt tools from the registry.

        Inbuilt tools are pre-packaged functions (e.g. math utilities) that are
        available without custom configuration.

        Returns:
            A list of dicts with ``tool_id``, ``name``, ``signature``, ``args_schema``, ``category``.
        """
        raw: Dict[str, Any] = self._client.get(f"{_PATH}/inbuilt", cast_to=dict)
        return cast(List[Dict[str, Any]], raw.get("inbuilt_tools", []))

    def configurable_inbuilt(self) -> List[Dict[str, Any]]:
        """
        List configurable inbuilt tools from the catalogue.

        Unlike plain inbuilt tools, these expose a ``config_schema`` so callers
        can supply configuration when attaching them to a workflow.

        Returns:
            A list of dicts with ``key``, ``title``, ``registry_tool_id``, ``config_schema``.
        """
        raw: Dict[str, Any] = self._client.get(f"{_PATH}/configurable-inbuilt", cast_to=dict)
        return cast(List[Dict[str, Any]], raw.get("configurable_inbuilt_tools", []))

    def configurable_inbuilt_schema(self, key: str) -> Dict[str, Any]:
        """
        Retrieve the descriptor + config schema for a single configurable inbuilt tool.

        Args:
            key: The catalogue key of the configurable inbuilt tool.

        Returns:
            A dict with ``key``, ``title``, ``registry_tool_id``, ``config_schema``.
        """
        return self._client.get(f"{_PATH}/configurable-inbuilt/{key}", cast_to=dict)

    def create(self, *, tool_config: ToolConfigOrDict) -> Tool:
        """
        Create a new custom tool.

        Args:
            tool_config: Full ``ToolConfig`` compatible dict or typed ``ToolConfig`` object.

        Returns:
            The created :class:`Tool`.
        """
        return self._client.post(_PATH, body=serialise_config(tool_config), cast_to=Tool)

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        tool_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> SyncPage[Tool]:
        """
        List tools.

        Args:
            page:        Page number (1-indexed, default 1).
            size:        Items per page (default 20).
            search:      Fuzzy name filter.
            tool_type:   Filter by tool type.
            workflow_id: Filter to tools belonging to a workflow.

        Returns:
            A :class:`SyncPage` of :class:`Tool` objects.
        """
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if tool_type is not None:
            params["type"] = tool_type
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, Tool, lambda p: self.list(page=p, size=size, search=search, tool_type=tool_type, workflow_id=workflow_id))

    def get(self, tool_id: str) -> Tool:
        """
        Retrieve a single tool by ID.

        Args:
            tool_id: ObjectId of the tool.

        Returns:
            The :class:`Tool`.

        Raises:
            NotFoundError: If no tool with the given ID exists.
        """
        return self._client.get(f"{_PATH}/{tool_id}", cast_to=Tool)

    def update(
        self,
        tool_id: str,
        *,
        tool_config: NotGivenOr[Optional[ToolConfigOrDict]] = NOT_GIVEN,
    ) -> Tool:
        """
        Update a tool's config.

        Args:
            tool_id:     ObjectId of the tool.
            tool_config: Updated ``ToolConfig`` compatible dict or typed ``ToolConfig`` object.

        Returns:
            The updated :class:`Tool`.
        """
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(tool_config) and tool_config is not None:
            body = serialise_config(tool_config)
        return self._client.patch(f"{_PATH}/{tool_id}", body=body, cast_to=Tool)

    def export(self, tool_id: str) -> Dict[str, Any]:
        """Export a tool as a portable bundle.

        Secrets are **redacted** by the server, not included. The bundle records which fields were
        redacted so :meth:`import_bundle` can tell you what to re-supply via ``secret_overrides``.
        """
        return self._client.get(f"{_PATH}/{tool_id}/export", cast_to=dict)

    def import_bundle(
        self,
        bundle: Dict[str, Any],
        *,
        name_override: Optional[str] = None,
        secret_overrides: Optional[Dict[str, Any]] = None,
        clear_unresolved_refs: bool = True,
        confirm_executable: bool = False,
    ) -> Tool:
        """Import a tool bundle produced by :meth:`export`.

        Args:
            bundle:                The exported bundle.
            name_override:         Name for the imported tool.
            secret_overrides:      Dotted-path → value for each redacted field being re-supplied,
                                   e.g. ``{"api_headers.Authorization": "Bearer ..."}``.
            clear_unresolved_refs: Clear team-scoped references (such as knowledge-base ids) that
                                   cannot resolve in the importing team, rather than importing a
                                   tool that points at another team's resources.
            confirm_executable:    **Required True to import an `inline_python` tool.** Such a bundle
                                   carries executable code that will run in your team's context, so
                                   the server refuses it unless you say so explicitly.
        """
        body: Dict[str, Any] = {
            "bundle": bundle,
            "clear_unresolved_refs": clear_unresolved_refs,
            "confirm_executable": confirm_executable,
        }
        if name_override is not None:
            body["name_override"] = name_override
        if secret_overrides is not None:
            body["secret_overrides"] = secret_overrides
        return self._client.post(f"{_PATH}/import", body=body, cast_to=Tool)

    def delete(self, tool_id: str) -> None:
        """
        Delete a tool.

        Args:
            tool_id: ObjectId of the tool to delete.
        """
        self._client.delete(f"{_PATH}/{tool_id}", cast_to=type(None))

    def clone(self, tool_id: str, *, name: NotGivenOr[Optional[str]] = NOT_GIVEN) -> Tool:
        """Duplicate a saved tool within your team.

        Unlike export/import, the copy is verbatim — secrets included — because both live in the same
        team. It gets a fresh id and ``logical_id``, and is named ``"<source> (Clone)"`` unless ``name``
        is given.

        Raises:
            PermissionDeniedError: For a plain inbuilt tool, which cannot be cloned. A configurable
                inbuilt instance is a real document of your team's and can be.
            NotFoundError: If no such tool exists in your team.
        """
        from interactly._types import is_given

        # Always a body, even with no name: the server declares one, and an empty dict would be dropped
        # before sending, which it answers with a 422. A null name means "<source> (Clone)".
        body: Dict[str, Any] = {"name": name if is_given(name) else None}
        return self._client.post(f"{_PATH}/{tool_id}/clone", body=body, cast_to=Tool)

    def codebase_functions(self) -> CodebaseFunctionCatalogue:
        """List the codebase functions a ``CodebaseFunctionToolConfig`` can call.

        **Interactly-staff only.** For any role below super-admin the server refuses, and this raises
        :class:`PermissionDeniedError`.
        """
        return self._client.get(f"{_PATH}/codebase-functions", cast_to=CodebaseFunctionCatalogue)

    def get_codebase_function(self, function_id: str) -> CodebaseFunction:
        """One codebase function's definition, including the argument schema derived from its signature.

        **Interactly-staff only**: raises :class:`PermissionDeniedError` for any other role.

        Raises:
            NotFoundError: When nothing is registered under ``function_id``. The error body carries a
                ``reason`` that separates "no such function" from "its module could not be imported".
        """
        raw: Dict[str, Any] = self._client.get(f"{_PATH}/codebase-functions/{function_id}", cast_to=dict)
        return CodebaseFunction.model_validate(raw.get("function") or {})

    def execute(self, tool_id: str, *, args: Optional[Dict[str, Any]] = None) -> ToolExecuteResult:
        """
        Execute a saved tool with the given argument values and return its output.

        Args:
            tool_id: ObjectId of the saved tool.
            args:    Argument values keyed by the tool's parameter names (e.g. ``{"x": 21}``).

        Returns:
            A :class:`ToolExecuteResult` with ``success``, ``result`` (the tool's return value),
            ``error`` (set when ``success`` is False), and ``latency_ms``.
        """
        return self._client.post(
            f"{_PATH}/{tool_id}/execute", body={"args": args or {}}, cast_to=ToolExecuteResult
        )

    def execute_inline(
        self, *, tool_config: ToolConfigOrDict, args: Optional[Dict[str, Any]] = None
    ) -> ToolExecuteResult:
        """
        Execute an inline (unsaved) tool config with the given argument values.

        Args:
            tool_config: A typed ``ToolConfig`` object or ``ToolConfig``-compatible dict to run.
            args:        Argument values keyed by the tool's parameter names.

        Returns:
            A :class:`ToolExecuteResult` (see :meth:`execute`).
        """
        return self._client.post(
            f"{_PATH}/execute",
            body={"tool_config": serialise_config(tool_config), "args": args or {}},
            cast_to=ToolExecuteResult,
        )


class AsyncToolsResource(AsyncAPIResource):
    """Asynchronous interface to the Tools API."""

    async def types(self) -> List[str]:
        """Retrieve all available tool type identifiers."""
        raw: Dict[str, Any] = await self._client.get(f"{_PATH}/types", cast_to=dict)
        return cast(List[str], raw.get("tool_types", []))

    async def schema(self, tool_type: str) -> Dict[str, Any]:
        """Retrieve the JSON Schema for a specific tool type."""
        return await self._client.get(f"{_PATH}/schema/{tool_type}", cast_to=dict)

    async def inbuilt(self) -> List[Dict[str, Any]]:
        """Retrieve all inbuilt tools from the registry."""
        raw: Dict[str, Any] = await self._client.get(f"{_PATH}/inbuilt", cast_to=dict)
        return cast(List[Dict[str, Any]], raw.get("inbuilt_tools", []))

    async def configurable_inbuilt(self) -> List[Dict[str, Any]]:
        """List configurable inbuilt tools from the catalogue."""
        raw: Dict[str, Any] = await self._client.get(f"{_PATH}/configurable-inbuilt", cast_to=dict)
        return cast(List[Dict[str, Any]], raw.get("configurable_inbuilt_tools", []))

    async def configurable_inbuilt_schema(self, key: str) -> Dict[str, Any]:
        """Retrieve the descriptor + config schema for a single configurable inbuilt tool."""
        return await self._client.get(f"{_PATH}/configurable-inbuilt/{key}", cast_to=dict)

    async def create(self, *, tool_config: ToolConfigOrDict) -> Tool:
        """Create a new custom tool."""
        return await self._client.post(_PATH, body=serialise_config(tool_config), cast_to=Tool)

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
        tool_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> AsyncPage[Tool]:
        """List tools."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        if tool_type is not None:
            params["type"] = tool_type
        if workflow_id is not None:
            params["workflow_id"] = workflow_id
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, Tool, lambda p: self.list(page=p, size=size, search=search, tool_type=tool_type, workflow_id=workflow_id))

    async def get(self, tool_id: str) -> Tool:
        """Retrieve a single tool by ID."""
        return await self._client.get(f"{_PATH}/{tool_id}", cast_to=Tool)

    async def update(
        self,
        tool_id: str,
        *,
        tool_config: NotGivenOr[Optional[ToolConfigOrDict]] = NOT_GIVEN,
    ) -> Tool:
        """Update a tool's config."""
        from interactly._types import is_given

        body: Dict[str, Any] = {}
        if is_given(tool_config) and tool_config is not None:
            body = serialise_config(tool_config)
        return await self._client.patch(f"{_PATH}/{tool_id}", body=body, cast_to=Tool)

    async def export(self, tool_id: str) -> Dict[str, Any]:
        """Export a tool as a portable bundle. Secrets are redacted by the server."""
        return await self._client.get(f"{_PATH}/{tool_id}/export", cast_to=dict)

    async def import_bundle(
        self,
        bundle: Dict[str, Any],
        *,
        name_override: Optional[str] = None,
        secret_overrides: Optional[Dict[str, Any]] = None,
        clear_unresolved_refs: bool = True,
        confirm_executable: bool = False,
    ) -> Tool:
        """Import a tool bundle produced by :meth:`export`. See the sync counterpart."""
        body: Dict[str, Any] = {
            "bundle": bundle,
            "clear_unresolved_refs": clear_unresolved_refs,
            "confirm_executable": confirm_executable,
        }
        if name_override is not None:
            body["name_override"] = name_override
        if secret_overrides is not None:
            body["secret_overrides"] = secret_overrides
        return await self._client.post(f"{_PATH}/import", body=body, cast_to=Tool)

    async def delete(self, tool_id: str) -> None:
        """Delete a tool."""
        await self._client.delete(f"{_PATH}/{tool_id}", cast_to=type(None))

    async def clone(self, tool_id: str, *, name: NotGivenOr[Optional[str]] = NOT_GIVEN) -> Tool:
        """Duplicate a saved tool within your team. See the sync counterpart."""
        from interactly._types import is_given

        body: Dict[str, Any] = {"name": name if is_given(name) else None}  # always a body; see the sync method
        return await self._client.post(f"{_PATH}/{tool_id}/clone", body=body, cast_to=Tool)

    async def codebase_functions(self) -> CodebaseFunctionCatalogue:
        """List the codebase functions a ``CodebaseFunctionToolConfig`` can call. Interactly-staff only."""
        return await self._client.get(f"{_PATH}/codebase-functions", cast_to=CodebaseFunctionCatalogue)

    async def get_codebase_function(self, function_id: str) -> CodebaseFunction:
        """One codebase function's definition. Interactly-staff only. See the sync counterpart."""
        raw: Dict[str, Any] = await self._client.get(f"{_PATH}/codebase-functions/{function_id}", cast_to=dict)
        return CodebaseFunction.model_validate(raw.get("function") or {})

    async def execute(self, tool_id: str, *, args: Optional[Dict[str, Any]] = None) -> ToolExecuteResult:
        """Execute a saved tool with the given argument values and return its output."""
        return await self._client.post(
            f"{_PATH}/{tool_id}/execute", body={"args": args or {}}, cast_to=ToolExecuteResult
        )

    async def execute_inline(
        self, *, tool_config: ToolConfigOrDict, args: Optional[Dict[str, Any]] = None
    ) -> ToolExecuteResult:
        """Execute an inline (unsaved) tool config with the given argument values."""
        return await self._client.post(
            f"{_PATH}/execute",
            body={"tool_config": serialise_config(tool_config), "args": args or {}},
            cast_to=ToolExecuteResult,
        )
