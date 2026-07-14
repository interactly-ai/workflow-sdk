"""
Response model for workflow templates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["Template"]


class Template(BaseAPIModel):
    """A reusable workflow template."""

    id: Optional[str] = None
    workflow_template_config: Optional[Dict[str, Any]] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap_envelope(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"workflow_template": {...}}``.
        # Only descend when the wrapper key is present and the inner fields aren't
        # already at top level (list rows / flat payloads pass through).
        inner = data.get("workflow_template")
        if (
            isinstance(inner, dict)
            and "workflow_template_config" not in data
            and "id" not in data
            and "_id" not in data
        ):
            data = inner
        # Map the server's ``_id`` onto the model's ``id`` field.
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        return data
