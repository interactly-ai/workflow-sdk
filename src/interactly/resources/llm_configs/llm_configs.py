"""
LLMConfigsResource — manage saved (named) team LLM configurations.

Saved LLM configs let a team register named provider/group configurations once
and reference them from node/workflow configs via
``BaseLLMConfig.named_llm_config_id`` / ``named_llm_config_name`` rather than
inlining provider settings (and API keys) into every node.

Endpoints:
    GET    /v1/schemas/llm-config          → schema
    POST   /v1/llm-configs                 → create
    GET    /v1/llm-configs                 → list (paginated)
    GET    /v1/llm-configs/default         → get_default
    GET    /v1/llm-configs/{id}            → get
    PATCH  /v1/llm-configs/{id}            → update
    DELETE /v1/llm-configs/{id}            → delete
    POST   /v1/llm-configs/{id}/test       → test
    POST   /v1/llm-configs/test            → test_inline
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr, is_given
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import LLMConfigOrDict
from interactly.types.llm_configs.llm_config import LLMConfig, LLMConfigTestResult

__all__ = ["LLMConfigsResource", "AsyncLLMConfigsResource"]

_PATH = "/v1/llm-configs"
_SCHEMA_PATH = "/v1/schemas/llm-config"


def _build_create_body(
    *,
    name: str,
    config: LLMConfigOrDict,
    description: Optional[str],
    is_default: bool,
    override_default: bool,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "name": name,
        "config": serialise_config(config),
        "is_default": is_default,
        "override_default": override_default,
    }
    if description is not None:
        body["description"] = description
    return body


def _build_update_body(
    *,
    name: NotGivenOr[Optional[str]],
    description: NotGivenOr[Optional[str]],
    config: NotGivenOr[Optional[LLMConfigOrDict]],
    is_default: NotGivenOr[Optional[bool]],
    override_default: bool,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"override_default": override_default}
    if is_given(name):
        body["name"] = name
    if is_given(description):
        body["description"] = description
    if is_given(config) and config is not None:
        body["config"] = serialise_config(config)
    if is_given(is_default):
        body["is_default"] = is_default
    return body


def _build_test_body(
    *,
    system_prompt: str,
    messages: Optional[List[Dict[str, Any]]],
    config: NotGivenOr[Optional[LLMConfigOrDict]],
) -> Dict[str, Any]:
    body: Dict[str, Any] = {"system_prompt": system_prompt, "messages": messages or []}
    if is_given(config) and config is not None:
        body["config"] = serialise_config(config)
    return body


class LLMConfigsResource(SyncAPIResource):
    """Synchronous interface to the saved LLM configs API."""

    def schema(self) -> Dict[str, Any]:
        """Return the JSON schema for a saved LLM config (``LLMOrGroupConfig``)."""
        return self._client.get(_SCHEMA_PATH, cast_to=dict)

    def create(
        self,
        *,
        name: str,
        config: LLMConfigOrDict,
        description: Optional[str] = None,
        is_default: bool = False,
        override_default: bool = False,
    ) -> LLMConfig:
        """Create a saved LLM config (single provider or group).

        Args:
            name:             Human-readable name for the config.
            config:           A typed ``LLMOrGroupConfig`` or compatible dict.
            description:      Optional description.
            is_default:       Mark this config as the team default.
            override_default: Allow replacing an existing default when ``is_default`` is set.
        """
        body = _build_create_body(
            name=name,
            config=config,
            description=description,
            is_default=is_default,
            override_default=override_default,
        )
        return self._client.post(_PATH, body=body, cast_to=LLMConfig)

    def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
    ) -> SyncPage[LLMConfig]:
        """List the team's saved LLM configs (paginated)."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        raw = self._client.get(_PATH, cast_to=dict, params=params)
        return SyncPage._from_response(raw, LLMConfig, lambda p: self.list(page=p, size=size, search=search))

    def get_default(self) -> LLMConfig:
        """Return the team's default saved LLM config.

        Raises:
            NotFoundError: If the team has no default configured.
        """
        return self._client.get(f"{_PATH}/default", cast_to=LLMConfig)

    def get(self, llm_config_id: str) -> LLMConfig:
        """Retrieve a single saved LLM config by ID."""
        return self._client.get(f"{_PATH}/{llm_config_id}", cast_to=LLMConfig)

    def update(
        self,
        llm_config_id: str,
        *,
        name: NotGivenOr[Optional[str]] = NOT_GIVEN,
        description: NotGivenOr[Optional[str]] = NOT_GIVEN,
        config: NotGivenOr[Optional[LLMConfigOrDict]] = NOT_GIVEN,
        is_default: NotGivenOr[Optional[bool]] = NOT_GIVEN,
        override_default: bool = False,
    ) -> LLMConfig:
        """Update a saved LLM config; only supplied fields are sent."""
        body = _build_update_body(
            name=name,
            description=description,
            config=config,
            is_default=is_default,
            override_default=override_default,
        )
        return self._client.patch(f"{_PATH}/{llm_config_id}", body=body, cast_to=LLMConfig)

    def delete(self, llm_config_id: str) -> None:
        """Delete a saved LLM config."""
        self._client.delete(f"{_PATH}/{llm_config_id}", cast_to=type(None))

    def test(
        self,
        llm_config_id: str,
        *,
        system_prompt: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        config: NotGivenOr[Optional[LLMConfigOrDict]] = NOT_GIVEN,
    ) -> LLMConfigTestResult:
        """Exercise a saved LLM config against a system prompt + optional messages.

        Args:
            llm_config_id: The saved config to test.
            system_prompt: Required non-empty system prompt.
            messages:      Optional ordered conversation history
                           (each ``{"role": ..., "content": ...}``).
            config:        Optional inline override (a redacted override reuses the stored secret).
        """
        body = _build_test_body(system_prompt=system_prompt, messages=messages, config=config)
        return self._client.post(f"{_PATH}/{llm_config_id}/test", body=body, cast_to=LLMConfigTestResult)

    def test_inline(
        self,
        *,
        system_prompt: str,
        config: LLMConfigOrDict,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMConfigTestResult:
        """Exercise an unsaved (inline) LLM config before persisting it.

        Unlike :meth:`test`, there is no stored record, so ``config`` must carry
        its own ``api_key`` (or omit it to fall back to the team's stored vendor
        credentials).
        """
        body: Dict[str, Any] = {
            "system_prompt": system_prompt,
            "messages": messages or [],
            "config": serialise_config(config),
        }
        return self._client.post(f"{_PATH}/test", body=body, cast_to=LLMConfigTestResult)


class AsyncLLMConfigsResource(AsyncAPIResource):
    """Asynchronous interface to the saved LLM configs API."""

    async def schema(self) -> Dict[str, Any]:
        """Return the JSON schema for a saved LLM config (``LLMOrGroupConfig``)."""
        return await self._client.get(_SCHEMA_PATH, cast_to=dict)

    async def create(
        self,
        *,
        name: str,
        config: LLMConfigOrDict,
        description: Optional[str] = None,
        is_default: bool = False,
        override_default: bool = False,
    ) -> LLMConfig:
        """Create a saved LLM config (single provider or group)."""
        body = _build_create_body(
            name=name,
            config=config,
            description=description,
            is_default=is_default,
            override_default=override_default,
        )
        return await self._client.post(_PATH, body=body, cast_to=LLMConfig)

    async def list(
        self,
        *,
        page: int = 1,
        size: int = 20,
        search: Optional[str] = None,
    ) -> AsyncPage[LLMConfig]:
        """List the team's saved LLM configs (paginated)."""
        params: Dict[str, Any] = {"page": page, "size": size}
        if search is not None:
            params["search"] = search
        raw = await self._client.get(_PATH, cast_to=dict, params=params)
        return AsyncPage._from_response(raw, LLMConfig, lambda p: self.list(page=p, size=size, search=search))

    async def get_default(self) -> LLMConfig:
        """Return the team's default saved LLM config."""
        return await self._client.get(f"{_PATH}/default", cast_to=LLMConfig)

    async def get(self, llm_config_id: str) -> LLMConfig:
        """Retrieve a single saved LLM config by ID."""
        return await self._client.get(f"{_PATH}/{llm_config_id}", cast_to=LLMConfig)

    async def update(
        self,
        llm_config_id: str,
        *,
        name: NotGivenOr[Optional[str]] = NOT_GIVEN,
        description: NotGivenOr[Optional[str]] = NOT_GIVEN,
        config: NotGivenOr[Optional[LLMConfigOrDict]] = NOT_GIVEN,
        is_default: NotGivenOr[Optional[bool]] = NOT_GIVEN,
        override_default: bool = False,
    ) -> LLMConfig:
        """Update a saved LLM config; only supplied fields are sent."""
        body = _build_update_body(
            name=name,
            description=description,
            config=config,
            is_default=is_default,
            override_default=override_default,
        )
        return await self._client.patch(f"{_PATH}/{llm_config_id}", body=body, cast_to=LLMConfig)

    async def delete(self, llm_config_id: str) -> None:
        """Delete a saved LLM config."""
        await self._client.delete(f"{_PATH}/{llm_config_id}", cast_to=type(None))

    async def test(
        self,
        llm_config_id: str,
        *,
        system_prompt: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        config: NotGivenOr[Optional[LLMConfigOrDict]] = NOT_GIVEN,
    ) -> LLMConfigTestResult:
        """Exercise a saved LLM config against a system prompt + optional messages."""
        body = _build_test_body(system_prompt=system_prompt, messages=messages, config=config)
        return await self._client.post(f"{_PATH}/{llm_config_id}/test", body=body, cast_to=LLMConfigTestResult)

    async def test_inline(
        self,
        *,
        system_prompt: str,
        config: LLMConfigOrDict,
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMConfigTestResult:
        """Exercise an unsaved (inline) LLM config before persisting it."""
        body: Dict[str, Any] = {
            "system_prompt": system_prompt,
            "messages": messages or [],
            "config": serialise_config(config),
        }
        return await self._client.post(f"{_PATH}/test", body=body, cast_to=LLMConfigTestResult)
