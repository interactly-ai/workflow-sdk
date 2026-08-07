"""
TypedDicts for node library request parameters.
"""

from __future__ import annotations

from typing import Optional

from typing_extensions import Required, TypedDict

from interactly.types._config_types import NodeConfigOrDict

__all__ = ["NodeLibraryCreateParams", "NodeLibraryListParams"]


class NodeLibraryCreateParams(TypedDict, total=False):
    node_library_config: Required[NodeConfigOrDict]


class NodeLibraryListParams(TypedDict, total=False):
    page: int
    size: int
    search: str
    access_level: Optional[str]
