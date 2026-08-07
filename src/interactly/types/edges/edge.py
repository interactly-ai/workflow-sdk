"""
Response model for workflow edges.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["Edge"]


class Edge(BaseAPIModel):
    """A standalone edge (used by the workflow editor)."""

    id: Optional[str] = None
    # Type is Dict when interactly_configs is not installed; upgraded to EdgeConfig by the validator.
    edge_config: Optional[Any] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_edge_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"edge": {...}}``. Only
        # descend when the wrapper key is present and the inner fields aren't
        # already at top level (list rows / flat payloads pass through).
        inner = data.get("edge")
        if isinstance(inner, dict) and "edge_config" not in data and "id" not in data and "_id" not in data:
            data = inner
        # Map the server's ``_id`` onto the model's ``id`` field.
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        raw = data.get("edge_config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import EdgeConfig as _EC
            from pydantic import TypeAdapter

            data["edge_config"] = TypeAdapter(_EC).validate_python(raw)
        except Exception:
            pass
        return data
