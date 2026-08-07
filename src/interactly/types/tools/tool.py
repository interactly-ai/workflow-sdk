"""
Response model for tools.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import model_validator

from interactly._models import BaseAPIModel

__all__ = ["Tool"]


class Tool(BaseAPIModel):
    """A custom tool registered for LLM function calling."""

    id: Optional[str] = None
    # Type is Dict when interactly_configs is not installed; upgraded to ToolConfig by the validator.
    tool_config: Optional[Any] = None
    team_id: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def name(self) -> Optional[str]:
        """The tool's name, read from its ``tool_config``."""
        return self._config_attr("name")

    @property
    def description(self) -> Optional[str]:
        """The tool's description, read from its ``tool_config``."""
        return self._config_attr("description")

    def _config_attr(self, key: str) -> Optional[Any]:
        cfg = self.tool_config
        if cfg is None:
            return None
        if isinstance(cfg, dict):
            return cfg.get(key)
        return getattr(cfg, key, None)

    @model_validator(mode="before")
    @classmethod
    def _coerce_tool_config(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # Unwrap the server's single-object envelope: ``{"tool": {...}}``. Only
        # descend when the wrapper key is present and the inner fields aren't
        # already at top level (list rows / flat payloads pass through).
        inner = data.get("tool")
        if isinstance(inner, dict) and "tool_config" not in data and "id" not in data and "_id" not in data:
            data = inner
        # Map the server's ``_id`` onto the model's ``id`` field.
        if "_id" in data and "id" not in data:
            data["id"] = str(data["_id"])
        raw = data.get("tool_config")
        if raw is None or not isinstance(raw, dict):
            return data
        try:
            from interactly_configs import ToolConfig as _TC
            from pydantic import TypeAdapter

            data["tool_config"] = TypeAdapter(_TC).validate_python(raw)
        except Exception:
            pass
        return data
