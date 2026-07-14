"""
Response model for a direct tool execution (``client.tools.execute`` / ``execute_inline``).
"""

from __future__ import annotations

from typing import Any, Optional

from interactly._models import BaseAPIModel

__all__ = ["ToolExecuteResult"]


class ToolExecuteResult(BaseAPIModel):
    """Result of executing a tool directly against supplied argument values.

    Tool-level failures (bad args, thrown exceptions, timeouts) come back as
    ``success=False`` with a clean ``error`` message rather than an HTTP error.
    """

    success: bool
    # The tool's return value on success. Typed ``Any`` because a tool may return
    # any JSON-serialisable value (number, string, dict, list, ...).
    result: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None
