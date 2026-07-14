"""
Response model for node libraries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["NodeLibrary"]


class NodeLibrary(BaseAPIModel):
    """A library of reusable nodes shareable within a team."""

    id: Optional[str] = None
    # Type is Dict when interactly_configs is not installed; upgraded to BaseNodeConfig by the validator.
    node_library_config: Optional[Any] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_node_library_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"node_library": {...}}``.
        # Only descend when the wrapper key is present and the inner fields aren't
        # already at top level (list rows / flat payloads pass through).
        inner = data.get("node_library")
        if isinstance(inner, dict) and "node_library_config" not in data and "id" not in data and "_id" not in data:
            data = inner
        # Map the server's ``_id`` onto the model's ``id`` field.
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        raw = data.get("node_library_config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from pydantic import TypeAdapter

            from interactly_configs import NodeConfig as _NC

            data["node_library_config"] = TypeAdapter(_NC).validate_python(raw)
        except Exception:
            try:
                from interactly_configs import BaseNodeConfig as _BNC

                data["node_library_config"] = _BNC.model_validate(raw)
            except Exception:
                pass
        return data
