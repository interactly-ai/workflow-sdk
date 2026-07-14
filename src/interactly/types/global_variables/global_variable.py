"""
Response model for global variables.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["GlobalVariable"]


class GlobalVariable(BaseAPIModel):
    """A team-scoped key-value variable accessible within workflow execution."""

    id: Optional[str] = None
    name: str
    value: str = ""
    description: Optional[str] = None
    category: Optional[str] = None
    is_secret: bool = False
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"variable": {...}}``.
        inner = data.get("variable")
        if isinstance(inner, dict) and "name" not in data and "_id" not in data:
            data = inner
        # Map the server's ``_id`` onto the model's ``id`` field.
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        return data
