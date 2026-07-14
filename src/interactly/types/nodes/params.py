"""
TypedDicts for node request parameters.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from typing_extensions import NotRequired, Required, TypedDict

from interactly.types._config_types import NodeConfigOrDict

__all__ = ["NodeCreateParams", "NodeUpdateParams", "NodeListParams"]


class NodeCreateParams(TypedDict, total=False):
    node_config: Required[NodeConfigOrDict]


class NodeUpdateParams(TypedDict, total=False):
    node_config: NotRequired[Optional[NodeConfigOrDict]]


class NodeListParams(TypedDict, total=False):
    page: int
    size: int
    search: str
    node_type: Optional[str]
    workflow_id: Optional[str]
