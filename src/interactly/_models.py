"""
Base Pydantic model for all SDK response objects.

All response models (WorkflowResponse, RunResponse, etc.) inherit from
BaseAPIModel instead of pydantic.BaseModel directly. This gives us a single
place to configure shared settings (e.g. forbid extra fields, alias handling).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = ["BaseAPIModel"]


class BaseAPIModel(BaseModel):
    """
    Shared base for every SDK response model.

    Configuration:
        - Extra fields in the response JSON are stored and accessible via
          model.model_extra, so the SDK does not break on server-side additions.
        - Field aliases are populated from either the field name or the alias,
          whichever the server sends.
    """

    model_config = ConfigDict(
        # Keep unknown server fields rather than raising.
        extra="allow",
        # Allow population using either the field name or the alias.
        populate_by_name=True,
        # Automatically strip leading/trailing whitespace from str fields.
        str_strip_whitespace=True,
    )

    def model_dump_api(self, **kwargs: Any) -> dict[str, Any]:
        """
        Dump the model to a dict suitable for sending back to the server.
        Excludes unset fields and strips NOT_GIVEN values automatically.
        """
        return self.model_dump(exclude_unset=True, exclude_none=False, **kwargs)
