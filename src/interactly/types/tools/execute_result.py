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

    #: Coarse failure category, e.g. ``"validation"``.
    error_type: Optional[str] = None

    #: Machine-readable failure reason. ``"unresolved_variables"`` means the tool config still held
    #: ``{{dynamic}}`` / ``[[runtime]]`` placeholders, or its endpoint was not an absolute URL, when
    #: execution was attempted. The team's global variables are merged underneath any
    #: ``dynamic_variables`` you pass — exactly as the live runtime does — so this usually means a
    #: placeholder that no global variable defines. Note a **blank** supplied value does not count as
    #: supplied, so passing ``{"api_base": ""}`` will not shadow the global of that name.
    error_code: Optional[str] = None

    #: True when the tool was validated rather than actually invoked.
    dry_run: Optional[bool] = None

    #: The tool's side-effect classification, which decides whether it can be executed directly or
    #: must be dry-run / confirmation-gated first.
    side_effect: Optional[str] = None
