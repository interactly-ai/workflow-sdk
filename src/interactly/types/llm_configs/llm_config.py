"""
Response models for saved (named) LLM configurations.

A saved LLM config is a team-scoped, named record wrapping either a single
provider config or an LLM group. Node/workflow configs may reference one via
``BaseLLMConfig.named_llm_config_id`` / ``named_llm_config_name`` instead of
inlining the provider settings.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import Field, model_validator

from interactly._models import BaseAPIModel

__all__ = ["LLMConfig", "LLMTestMemberInfo", "LLMConfigTestResult", "ImportedLLMConfig", "LLMConfigImportResult"]


class LLMConfig(BaseAPIModel):
    """A saved, named LLM configuration (single provider or group).

    For a caller below admin, the server clears the credentials on read: ``api_key``, Bedrock's AWS key pair, and
    the values of credential headers such as a custom gateway's ``Authorization``.
    ``config`` is a plain ``dict`` unless the ``[configs]`` extra is installed,
    in which case it is upgraded to a typed ``LLMOrGroupConfig`` (mirrors the
    coercion used by :class:`Node` / :class:`Tool`).
    """

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    # Type is Dict when interactly_configs is not installed; upgraded to LLMOrGroupConfig by the validator.
    config: Optional[Any] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"llm_config": {...}}``.
        inner = data.get("llm_config")
        if isinstance(inner, dict) and "config" not in data and "id" not in data and "_id" not in data:
            data = inner
        # The LLM-config endpoints address records by their logical
        # ``llm_config_id`` (a UUID), not the Mongo ``_id`` — map that onto
        # ``id`` so ``get``/``update``/``delete`` round-trip correctly.
        if "id" not in data:
            if data.get("llm_config_id") is not None:
                data["id"] = str(data["llm_config_id"])
            elif "_id" in data:
                data["id"] = str(data["_id"])
        raw = data.get("config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import LLMOrGroupConfig as _LLM
            from pydantic import TypeAdapter

            data["config"] = TypeAdapter(_LLM).validate_python(raw)
        except Exception:
            pass
        return data


class LLMTestMemberInfo(BaseAPIModel):
    """Identity of the group member that produced a given response (null for single configs)."""

    index: Optional[int] = None
    logical_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class LLMConfigTestResult(BaseAPIModel):
    """Outcome of exercising an LLM config against a system prompt + messages."""

    success: bool
    response: Optional[str] = None
    error: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    #: Whether the call used the team's own saved provider key rather than the deployment's. ``None`` for a group,
    #: whose members decide separately, and when the call never reached a provider client.
    used_user_api_key: Optional[bool] = None
    #: On failure, what kind it was, read from the provider's error: ``auth``, ``permission``, ``quota``,
    #: ``rate_limit``, ``model``, ``timeout``, ``unavailable`` or ``other``. ``error`` holds the provider's own
    #: message.
    error_category: Optional[str] = None
    # Group-config extras (all null for single-provider configs).
    winning_member: Optional[LLMTestMemberInfo] = None
    backchannel_response: Optional[str] = None
    backchannel_member: Optional[LLMTestMemberInfo] = None
    backchannel_prompt_tokens: Optional[int] = None
    backchannel_completion_tokens: Optional[int] = None
    backchannel_total_tokens: Optional[int] = None


class ImportedLLMConfig(BaseAPIModel):
    """One LLM config an import created."""

    llm_config: LLMConfig
    #: The config's id in the exporting team.
    source_llm_config_id: Optional[str] = None
    #: The bundle's name for the config, when the team already used it and the copy was renamed.
    renamed_from: Optional[str] = None
    #: True when the team already used the config's id or logical id, so new ones were made: workflows that attach
    #: the config by its old id don't reach this copy.
    ids_reminted: bool = False


class LLMConfigImportResult(BaseAPIModel):
    """What an LLM-config import created."""

    imported: List[ImportedLLMConfig] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
