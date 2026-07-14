"""
Request parameter types for the saved LLM-config endpoints.
"""

from __future__ import annotations

from typing import List, Optional

from typing_extensions import NotRequired, TypedDict

from interactly.types._config_types import LLMConfigOrDict

__all__ = [
    "LLMConfigCreateParams",
    "LLMConfigUpdateParams",
    "LLMConfigListParams",
    "LLMTestMessageParam",
    "LLMConfigTestParams",
    "LLMConfigTestInlineParams",
]


class LLMTestMessageParam(TypedDict):
    """A single conversation message sent to a test endpoint."""

    role: NotRequired[str]  # "human" | "ai" | "system" (server default: "human")
    content: str


class LLMConfigCreateParams(TypedDict):
    """Parameters for ``client.llm_configs.create()``."""

    name: str
    config: LLMConfigOrDict
    description: NotRequired[Optional[str]]
    is_default: NotRequired[bool]
    override_default: NotRequired[bool]


class LLMConfigUpdateParams(TypedDict, total=False):
    """Parameters for ``client.llm_configs.update()`` (only supplied keys are sent)."""

    name: Optional[str]
    description: Optional[str]
    config: Optional[LLMConfigOrDict]
    is_default: Optional[bool]
    override_default: bool


class LLMConfigListParams(TypedDict):
    """Query parameters for ``client.llm_configs.list()``."""

    page: NotRequired[int]
    size: NotRequired[int]
    search: NotRequired[Optional[str]]


class LLMConfigTestParams(TypedDict):
    """Parameters for ``client.llm_configs.test()`` (saved config)."""

    system_prompt: str
    messages: NotRequired[List[LLMTestMessageParam]]
    # Optional inline override; a redacted (api_key=None) override reuses the stored secret.
    config: NotRequired[Optional[LLMConfigOrDict]]


class LLMConfigTestInlineParams(TypedDict):
    """Parameters for ``client.llm_configs.test_inline()`` (unsaved config)."""

    system_prompt: str
    config: LLMConfigOrDict
    messages: NotRequired[List[LLMTestMessageParam]]
