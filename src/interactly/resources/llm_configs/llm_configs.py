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
    POST   /v1/llm-configs/export          → export
    POST   /v1/llm-configs/import          → import_bundle
    GET    /v1/llm-configs/{id}/usage      → usage
    POST   /v1/llm-configs/{id}/test       → test
    POST   /v1/llm-configs/test            → test_inline
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from interactly._pagination import AsyncPage, SyncPage
from interactly._resource import AsyncAPIResource, SyncAPIResource
from interactly._types import NOT_GIVEN, NotGivenOr, is_given
from interactly._utils._credentials import CREDENTIAL_FIELDS, CREDENTIAL_HEADER_MAPS, is_credential_header
from interactly._utils._serialise import serialise_config
from interactly.types._config_types import LLMConfigOrDict
from interactly.types.llm_configs.llm_config import LLMConfig, LLMConfigImportResult, LLMConfigTestResult
from interactly.types.usage import UsageReport

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


def _stored_config(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The ``config`` dict inside a ``GET /llm-configs/{id}`` response, envelope or not."""
    record = raw.get("llm_config") if isinstance(raw.get("llm_config"), dict) else raw
    config = record.get("config") if isinstance(record, dict) else None
    return config if isinstance(config, dict) else None


def _pair_group_members(new_members: List[Any], old_members: List[Any]) -> List[Any]:
    """Pair each outgoing group member with the stored member holding its key, as the server does.

    By ``logical_id``, so a reordered group never carries one provider's key onto another. A member with
    an id but no stored match gets no pairing. Only members with no ``logical_id`` at all fall back to
    positional pairing among themselves.
    """
    old_by_id: Dict[Any, List[Any]] = {}
    for member in old_members:
        if isinstance(member, dict) and member.get("logical_id") is not None:
            old_by_id.setdefault(member["logical_id"], []).append(member)
    idless_old = [m for m in old_members if isinstance(m, dict) and m.get("logical_id") is None]

    pairs = []
    idless_new = []
    for member in new_members:
        if not isinstance(member, dict):
            continue
        logical_id = member.get("logical_id")
        if logical_id is None:
            idless_new.append(member)
        elif old_by_id.get(logical_id):
            pairs.append((member, old_by_id[logical_id].pop(0)))
    pairs.extend(zip(idless_new, idless_old))
    return pairs


def _carry_stored_credentials(new_config: Any, old_config: Any) -> None:
    """Copy each stored credential into the outgoing config wherever the outgoing one leaves it blank.

    The client-side twin of the server's own preservation, which it applies only to non-admin callers: an admin is
    shown the credentials on read, so for an admin a blank one means "delete it". Without this, an admin-token SDK
    user who sends a freshly built config deletes the provider credentials without being told. Carried:

    - each credential field (``api_key``, Bedrock's ``aws_access_key_id`` and ``aws_secret_access_key``) that the
      outgoing config leaves unset;
    - each credential header of a header map (the custom gateway's ``default_headers``: ``Authorization``,
      ``x-api-key`` and the like) that the outgoing map sends empty, matched by name exactly and then ignoring
      case, as the server matches it. A header the caller filled in keeps its value. If the outgoing config has no
      header map at all, the stored credential headers are carried into a new one; the other headers are not.

    Recurses into group members (paired by ``logical_id``) and backchannel sub-configs, as the server does. Mutates
    ``new_config`` in place.

    One deliberate difference from the server: credentials are carried only onto a config of the same ``type``.
    Switching a saved config from one provider to another must not hand the old provider's credentials to the new
    one; the caller supplies the new provider's, or the server's team credentials apply.
    """
    if not isinstance(new_config, dict) or not isinstance(old_config, dict):
        return
    if new_config.get("type") == old_config.get("type"):
        for field in CREDENTIAL_FIELDS:
            if new_config.get(field) is None and old_config.get(field) is not None:
                new_config[field] = old_config[field]
        for field in CREDENTIAL_HEADER_MAPS:
            if isinstance(old_config.get(field), dict):
                carried = _carry_stored_headers(new_config.get(field), old_config[field])
                if carried is not None:
                    new_config[field] = carried
    for new_member, old_member in _pair_group_members(new_config.get("llms") or [], old_config.get("llms") or []):
        _carry_stored_credentials(new_member, old_member)
    for key in ("main_llm_config", "backchannel_llm_config"):
        _carry_stored_credentials(new_config.get(key), old_config.get(key))


def _carry_stored_headers(new_headers: Any, old_headers: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The outgoing headers with each blank credential header given its stored value, or ``None`` to leave them."""
    stored = {name: value for name, value in old_headers.items() if value and is_credential_header(name)}
    if new_headers is None:
        return dict(stored) or None
    if not isinstance(new_headers, dict):
        return None
    stored_by_lower = {str(name).lower(): value for name, value in stored.items()}
    restored = dict(new_headers)
    for name, value in new_headers.items():
        if value in (None, "") and is_credential_header(name):
            value = stored.get(name, stored_by_lower.get(str(name).lower()))
            if value:
                restored[name] = value
    return restored


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
        return SyncPage._from_response(raw, LLMConfig, lambda p: self.list(page=p, size=size, search=search), page=page, size=size)

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
        preserve_credentials: bool = True,
    ) -> LLMConfig:
        """Update a saved LLM config; only supplied fields are sent.

        ``config`` replaces the stored config **wholesale**. For a caller with an admin or super-admin token, the
        server treats a credential the config leaves blank as "remove it", because an admin is shown the real
        credentials on read and so could only have cleared one on purpose. A config built fresh in code has none, so
        that would silently delete the provider's ``api_key``, Bedrock's AWS key pair, or a custom gateway's
        ``Authorization`` header.

        ``preserve_credentials`` (the default) guards against that. The stored config is read first, and each
        credential ``config`` leaves blank is carried over from it, in group members (paired by ``logical_id``) and
        backchannel configs too, and only onto a config of the same provider type. That costs one extra GET. For a
        non-admin the read returns no credentials and nothing changes, since the server keeps them for them anyway.

        Args:
            preserve_credentials: Pass ``False`` to send ``config`` exactly as given. With an admin token, that is
                                  how stored credentials are deliberately removed.
        """
        body = _build_update_body(
            name=name,
            description=description,
            config=config,
            is_default=is_default,
            override_default=override_default,
        )
        if preserve_credentials and "config" in body:
            stored = _stored_config(self._client.get(f"{_PATH}/{llm_config_id}", cast_to=dict))
            _carry_stored_credentials(body["config"], stored)
        return self._client.patch(f"{_PATH}/{llm_config_id}", body=body, cast_to=LLMConfig)

    def delete(self, llm_config_id: str) -> None:
        """Delete a saved LLM config."""
        self._client.delete(f"{_PATH}/{llm_config_id}", cast_to=type(None))

    def usage(self, llm_config_id: str) -> UsageReport:
        """The team's workflows that use this saved LLM config, in any version.

        A delete doesn't consult this: deleting the config still succeeds, and leaves these with a reference that no
        longer resolves.

        Raises:
            NotFoundError: no saved LLM config with this id in the team.
        """
        return self._client.get(f"{_PATH}/{llm_config_id}/usage", cast_to=UsageReport)

    def export(self, *, llm_config_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Export saved LLM configs as a portable bundle dict, for :meth:`import_bundle` here or on another server.

        Every secret is replaced with ``"<REDACTED>"`` and listed in ``bundle["redactions"]`` as
        ``{"path", "config_name", "reason"}``, whatever the caller's role: the file is meant to be passed around.

        Args:
            llm_config_ids: The configs to export; every config of the team when omitted.

        Raises:
            NotFoundError: one of ``llm_config_ids`` names no config of the team.
        """
        return self._client.post(f"{_PATH}/export", body=_export_body(llm_config_ids), cast_to=dict)

    def import_bundle(
        self, bundle: Dict[str, Any], *, secret_overrides: Optional[Dict[str, str]] = None
    ) -> LLMConfigImportResult:
        """Create LLM configs from an exported bundle, all or nothing.

        Every redacted secret must come back in ``secret_overrides``, keyed by its ``path`` in
        ``bundle["redactions"]``: ``{r["path"]: value for r in bundle["redactions"]}``. An id the team already uses is
        replaced by a new one (``ids_reminted``), and a name it already uses gets an ``(imported)`` suffix
        (``renamed_from``). Imported configs never become the team default.

        Raises:
            UnprocessableEntityError: a redacted secret was not supplied, or the bundle is malformed; the paths are
                in ``err.body``.
            ConflictError: the import collides with the team's configs.
        """
        return self._client.post(
            f"{_PATH}/import", body=_import_body(bundle, secret_overrides), cast_to=LLMConfigImportResult
        )

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
        return AsyncPage._from_response(raw, LLMConfig, lambda p: self.list(page=p, size=size, search=search), page=page, size=size)

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
        preserve_credentials: bool = True,
    ) -> LLMConfig:
        """Update a saved LLM config; only supplied fields are sent. See the sync counterpart, in
        particular for ``preserve_credentials``."""
        body = _build_update_body(
            name=name,
            description=description,
            config=config,
            is_default=is_default,
            override_default=override_default,
        )
        if preserve_credentials and "config" in body:
            stored = _stored_config(await self._client.get(f"{_PATH}/{llm_config_id}", cast_to=dict))
            _carry_stored_credentials(body["config"], stored)
        return await self._client.patch(f"{_PATH}/{llm_config_id}", body=body, cast_to=LLMConfig)

    async def delete(self, llm_config_id: str) -> None:
        """Delete a saved LLM config."""
        await self._client.delete(f"{_PATH}/{llm_config_id}", cast_to=type(None))

    async def usage(self, llm_config_id: str) -> UsageReport:
        """The team's workflows that use this saved LLM config; see :meth:`LLMConfigsResource.usage`."""
        return await self._client.get(f"{_PATH}/{llm_config_id}/usage", cast_to=UsageReport)

    async def export(self, *, llm_config_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Export saved LLM configs as a portable bundle dict; see :meth:`LLMConfigsResource.export`."""
        return await self._client.post(f"{_PATH}/export", body=_export_body(llm_config_ids), cast_to=dict)

    async def import_bundle(
        self, bundle: Dict[str, Any], *, secret_overrides: Optional[Dict[str, str]] = None
    ) -> LLMConfigImportResult:
        """Create LLM configs from an exported bundle, all or nothing; see :meth:`LLMConfigsResource.import_bundle`."""
        return await self._client.post(
            f"{_PATH}/import", body=_import_body(bundle, secret_overrides), cast_to=LLMConfigImportResult
        )

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


def _export_body(llm_config_ids: Optional[List[str]]) -> Dict[str, Any]:
    # Always a body: the route requires one, and a null list of ids is how it is asked for every config.
    return {"llm_config_ids": llm_config_ids}


def _import_body(bundle: Dict[str, Any], secret_overrides: Optional[Dict[str, str]]) -> Dict[str, Any]:
    body: Dict[str, Any] = {"bundle": bundle}
    if secret_overrides:
        body["secret_overrides"] = secret_overrides
    return body
