"""
TypedDicts for tool request parameters.
"""

from __future__ import annotations

from typing import Optional

from typing_extensions import NotRequired, Required, TypedDict

from interactly.types._config_types import ToolConfigOrDict

__all__ = ["ToolCreateParams", "ToolUpdateParams", "ToolListParams"]


class ToolCreateParams(TypedDict, total=False):
    tool_config: Required[ToolConfigOrDict]


class ToolUpdateParams(TypedDict, total=False):
    tool_config: NotRequired[Optional[ToolConfigOrDict]]


class ToolListParams(TypedDict, total=False):
    page: int
    size: int
    search: str
    tool_type: Optional[str]
    workflow_id: Optional[str]
