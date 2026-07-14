"""
TypedDicts for global variable request parameters.
"""

from __future__ import annotations

from typing import List, Optional

from typing_extensions import NotRequired, Required, TypedDict

__all__ = [
    "GlobalVariableCreateParams",
    "GlobalVariableUpdateParams",
    "GlobalVariableListParams",
    "GlobalVariableBulkCreateParams",
]


class GlobalVariableCreateParams(TypedDict, total=False):
    name: Required[str]
    value: str
    description: Optional[str]
    category: Optional[str]
    is_secret: bool


class GlobalVariableUpdateParams(TypedDict, total=False):
    name: NotRequired[Optional[str]]
    value: NotRequired[Optional[str]]
    description: NotRequired[Optional[str]]
    category: NotRequired[Optional[str]]
    is_secret: NotRequired[Optional[bool]]


class _BulkItem(TypedDict, total=False):
    name: Required[str]
    value: str
    description: Optional[str]
    category: Optional[str]
    is_secret: bool


class GlobalVariableBulkCreateParams(TypedDict):
    variables: List[_BulkItem]


class GlobalVariableListParams(TypedDict, total=False):
    page: int
    size: int
    search: str
    category: Optional[str]
