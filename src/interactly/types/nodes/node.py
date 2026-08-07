"""
Response model for workflow nodes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["Node"]


class Node(BaseAPIModel):
    """A standalone node (used by the workflow editor)."""

    id: Optional[str] = None
    # Type is Dict when interactly_configs is not installed; upgraded to BaseNodeConfig by the validator.
    node_config: Optional[Any] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_node_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"node": {...}}``. Only
        # descend when the wrapper key is present and the inner fields aren't
        # already at top level (list rows / flat payloads pass through).
        inner = data.get("node")
        if isinstance(inner, dict) and "node_config" not in data and "id" not in data and "_id" not in data:
            data = inner
        # Map the server's ``_id`` onto the model's ``id`` field.
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        raw = data.get("node_config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import NodeConfig as _NC
            from pydantic import TypeAdapter

            # Validate through the discriminated union so the concrete subclass
            # (e.g. ``SayLLMNodeConfig``) is returned, preserving its ``type``
            # discriminator and subclass-specific fields.
            data["node_config"] = TypeAdapter(_NC).validate_python(raw)
        except Exception:
            try:
                from interactly_configs import BaseNodeConfig as _BNC

                data["node_config"] = _BNC.model_validate(raw)
            except Exception:
                pass
        return data
