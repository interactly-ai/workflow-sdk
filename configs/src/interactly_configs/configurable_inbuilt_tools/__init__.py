"""
CONFIGURABLE_INBUILT_TOOL_CATALOGUE

Central registry of inbuilt tools that expose user-configurable fields. Each entry maps a stable
``configurable_key`` to a descriptor containing:

- ``registry_tool_id``: the key the server uses to look up the callable in its tool registry.
- ``extra_config_model``: a ``pydantic.BaseModel`` subclass whose JSON schema describes the extra
  user-configurable fields for this tool. The same schema is returned by
  ``GET /v1/tools/configurable-inbuilt/{key}``.
- ``title``: human-readable display name shown in a picker.

This mirrors the server's catalogue so a client can render or validate the same forms offline. The
server remains the source of truth: call ``client.tools.configurable_inbuilt()`` to see what a given
deployment actually offers.
"""

from typing import Dict, Type, TypedDict

from pydantic import BaseModel

from interactly_configs.configurable_inbuilt_tools.call_forward import (
    CALL_FORWARD_CONFIGURABLE_KEY,
    CALL_FORWARD_REGISTRY_TOOL_ID,
    CallForwardExtraConfig,
)


class ConfigurableInbuiltToolEntry(TypedDict):
    """Shape of each entry in ``CONFIGURABLE_INBUILT_TOOL_CATALOGUE``."""

    registry_tool_id: str
    extra_config_model: Type[BaseModel]
    title: str


CONFIGURABLE_INBUILT_TOOL_CATALOGUE: Dict[str, ConfigurableInbuiltToolEntry] = {
    CALL_FORWARD_CONFIGURABLE_KEY: {
        "registry_tool_id": CALL_FORWARD_REGISTRY_TOOL_ID,
        "extra_config_model": CallForwardExtraConfig,
        "title": "Call Forward",
    },
}

__all__ = [
    "CALL_FORWARD_CONFIGURABLE_KEY",
    "CALL_FORWARD_REGISTRY_TOOL_ID",
    "CONFIGURABLE_INBUILT_TOOL_CATALOGUE",
    "CallForwardExtraConfig",
    "ConfigurableInbuiltToolEntry",
]
