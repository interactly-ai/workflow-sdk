"""
Serialisation bridge between ``interactly-configs`` Pydantic models and plain dicts.

When a caller passes a typed config object (e.g. ``BaseNodeConfig``) to a
resource method, the HTTP layer expects a JSON-serialisable ``dict``.
``serialise_config`` detects Pydantic ``BaseModel`` instances and calls
``.model_dump(mode="json")`` automatically.

``interactly-configs`` (and therefore ``pydantic``) is an optional extra.
When it is absent this function is a no-op passthrough — plain dicts are
returned unchanged and no ``ImportError`` is raised.

Usage::

    from interactly._utils._serialise import serialise_config

    body = serialise_config(node_config)  # dict or BaseNodeConfig -> dict
"""

from __future__ import annotations

from typing import Any


def serialise_config(obj: Any, *, exclude_unset: bool = False) -> Any:
    """
    Convert a Pydantic ``BaseModel`` to a JSON-safe dict via ``model_dump``.

    If *obj* is already a ``dict`` (or any other type) it is returned
    unchanged. If ``pydantic`` is not installed the function is a no-op.

    Args:
        obj: A ``dict``, Pydantic ``BaseModel`` subclass, or any other value.
        exclude_unset: When ``True``, only fields the caller explicitly set are
            serialised (via ``model_dump(exclude_unset=True)``). Use this for
            partial updates (e.g. ``PATCH``) so unspecified fields — including a
            model's ``default_factory`` ``logical_id`` — are omitted and the
            server preserves the existing values instead of overwriting them
            with freshly-generated defaults. Defaults to ``False`` (full dump),
            which is what creates need.

    Returns:
        A JSON-serialisable ``dict`` when *obj* is a Pydantic model;
        otherwise *obj* unchanged.
    """
    try:
        from pydantic import BaseModel

        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json", exclude_unset=exclude_unset)
    except ImportError:
        pass
    return obj


__all__ = ["serialise_config"]
