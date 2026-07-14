"""
Response models for workflow scheduled runs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["ScheduleStatus", "Schedule"]


class ScheduleStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Schedule(BaseAPIModel):
    """A scheduled execution of a workflow."""

    id: str
    workflow_id: str
    team_id: str
    created_by: Optional[str] = None
    status: ScheduleStatus
    scheduled_time: datetime
    run_input: Optional[Dict[str, Any]] = None
    version: Optional[int] = None
    scheduled_by_name: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"schedule": {...}}``.
        inner = data.get("schedule")
        if isinstance(inner, dict) and "id" not in data and "_id" not in data:
            data = inner
        # Map the server's ``_id`` onto the model's ``id`` field.
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        return data
