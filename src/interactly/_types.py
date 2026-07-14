"""
Shared type aliases used across the SDK.

All public-facing param types (TypedDict) are in `interactly.types.*`.
This module contains lower-level internal aliases and the NOT_GIVEN sentinel.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import httpx
from typing_extensions import TypeAlias

# --------------------------------------------------------------------------- #
# NOT_GIVEN sentinel                                                           #
# --------------------------------------------------------------------------- #
# Imported from _utils._typing to keep this module thin, but re-exported here
# so that `from interactly._types import NOT_GIVEN, NotGivenOr` works.
from interactly._utils._typing import NOT_GIVEN, NotGiven, NotGivenOr, is_given

__all__ = [
    "NOT_GIVEN",
    "NotGiven",
    "NotGivenOr",
    "is_given",
    "Headers",
    "HeadersLike",
    "Query",
    "Body",
    "ResponseT",
    "AnyMapping",
]

# --------------------------------------------------------------------------- #
# HTTP building-block aliases                                                  #
# --------------------------------------------------------------------------- #

Headers: TypeAlias = Dict[str, str]
HeadersLike: TypeAlias = Union[Dict[str, str], httpx.Headers]
Query: TypeAlias = Optional[Dict[str, Any]]
Body: TypeAlias = Optional[Dict[str, Any]]
AnyMapping: TypeAlias = Dict[str, Any]

# --------------------------------------------------------------------------- #
# Generic return-type placeholder used in method signatures                   #
# --------------------------------------------------------------------------- #
from typing import TypeVar

ResponseT = TypeVar("ResponseT")
ModelT = TypeVar("ModelT")
