"""
Request body transformation utilities.

Converts caller-provided TypedDict / dict params into a clean JSON-serialisable
dict, stripping NOT_GIVEN values so they are never serialised.
"""

from __future__ import annotations

from typing import Any

from interactly._utils._typing import NotGiven

__all__ = ["strip_not_given", "build_body"]


def _clean_list(seq: list[Any]) -> list[Any]:
    """Drop NotGiven elements from a list and recurse into nested containers."""
    cleaned: list[Any] = []
    for value in seq:
        if isinstance(value, NotGiven):
            continue
        if isinstance(value, dict):
            value = strip_not_given(value)
        elif isinstance(value, list):
            value = _clean_list(value)
        cleaned.append(value)
    return cleaned


def strip_not_given(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively remove entries whose value is a NotGiven sentinel.
    Nested dicts and lists are traversed (NotGiven elements dropped from lists,
    dict elements cleaned); all other values are returned as-is.
    """
    result: dict[str, Any] = {}
    for key, value in obj.items():
        if isinstance(value, NotGiven):
            continue
        if isinstance(value, dict):
            value = strip_not_given(value)
        elif isinstance(value, list):
            value = _clean_list(value)
        result[key] = value
    return result


def build_body(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    Prepare a request body dict for JSON serialisation.
    Returns None if there is nothing to send.
    """
    if params is None:
        return None
    cleaned = strip_not_given(params)
    return cleaned if cleaned else None
