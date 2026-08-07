"""
TypedDicts for edge request parameters.
"""

from __future__ import annotations

from typing import Optional

from typing_extensions import NotRequired, Required, TypedDict

from interactly.types._config_types import EdgeConfigOrDict

__all__ = ["EdgeCreateParams", "EdgeUpdateParams", "EdgeListParams"]


class EdgeCreateParams(TypedDict, total=False):
    edge_config: Required[EdgeConfigOrDict]


class EdgeUpdateParams(TypedDict, total=False):
    edge_config: NotRequired[Optional[EdgeConfigOrDict]]


class EdgeListParams(TypedDict, total=False):
    page: int
    size: int
    search: str
    edge_type: Optional[str]
    workflow_id: Optional[str]
