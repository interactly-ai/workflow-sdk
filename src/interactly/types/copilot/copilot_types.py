"""Response models for the Copilot API."""

from __future__ import annotations

from typing import Any, Dict, Optional

from interactly._models import BaseAPIModel

__all__ = ["CopilotSchema"]


class CopilotSchema(BaseAPIModel):
    """Schema shapes returned by the copilot schema endpoints."""

    copilot_input_schema: Optional[Dict[str, Any]] = None
    copilot_event_schema: Optional[Dict[str, Any]] = None
