"""
Response models for the codebase-function catalogue (``client.tools.codebase_functions``).

**Interactly-staff only.** These describe functions in the platform's own codebase that a
``CodebaseFunctionToolConfig`` can call. The server refuses every route for a role below super-admin, so
for any other credential the methods that return these raise ``PermissionDeniedError``.

Shapes captured from the dev server.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from interactly._models import BaseAPIModel

__all__ = ["CodebaseFunction", "CodebaseFunctionCatalogue"]


class CodebaseFunction(BaseAPIModel):
    """One registered codebase function, as a ``CodebaseFunctionToolConfig.function_id`` can name it."""

    #: The stable id a tool config names, e.g. ``benefits.estimate_member_cost_share``.
    id: Optional[str] = None
    #: Its location, ``package.module:function`` — also accepted as a ``function_id``.
    qualified_name: Optional[str] = None
    name: Optional[str] = None
    summary: Optional[str] = None
    #: The docstring the model is given when the function is offered as a tool.
    signature: Optional[str] = None
    #: JSON Schema of the arguments, derived from the function's signature.
    args_schema: Optional[Dict[str, Any]] = None
    #: JSON Schema of the ``extra_config`` a tool config may carry for this function.
    extra_config_schema: Optional[Dict[str, Any]] = None
    #: ``none``, ``reads``, ``writes``, ``sends`` or ``unknown``.
    side_effect: Optional[str] = None
    category: Optional[str] = None
    tenancy: Optional[str] = None
    is_async: Optional[bool] = None
    source_ref: Optional[str] = None
    #: The id of the function that replaces this one, when it is deprecated.
    deprecated_by: Optional[str] = None


class CodebaseFunctionCatalogue(BaseAPIModel):
    """Every codebase function registered in the serving process."""

    codebase_functions: List[CodebaseFunction] = Field(default_factory=list)
    total_count: Optional[int] = None
    #: Catalogued modules that could not be imported in the serving process, keyed by module. Expected
    #: when a function depends on a package that service does not carry; the quickest way to tell that
    #: apart from a misspelled id.
    unavailable_modules: Dict[str, Any] = Field(default_factory=dict)
