"""
Union type aliases that broaden every ``*_config`` parameter to accept either a
strongly-typed ``interactly-configs`` Pydantic object or a plain ``dict``.

These aliases are **only** evaluated by static type-checkers (mypy / pyright).
At runtime the ``interactly-configs`` package may not be installed, so all
forward-references inside ``TYPE_CHECKING`` blocks are strings and are never
resolved at import time.

Usage::

    from interactly.types._config_types import NodeConfigOrDict

    class NodeCreateParams(TypedDict, total=False):
        node_config: Required[NodeConfigOrDict]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Union

if TYPE_CHECKING:
    from interactly_configs import (
        BaseNodeConfig,
        BaseRunInput,
        BaseRunOutput,
        EdgeConfig,
        LLMOrGroupConfig,
        SuperNodeInterface,
        ToolConfig,
        WorkflowConfig,
        WorkflowConfigFullyHydrated,
        WorkflowTemplateConfig,
    )

# ---------------------------------------------------------------------------
# Public aliases
# ---------------------------------------------------------------------------

WorkflowConfigOrDict = Union["WorkflowConfig", Dict[str, Any]]
NodeConfigOrDict = Union["BaseNodeConfig", Dict[str, Any]]
EdgeConfigOrDict = Union["EdgeConfig", Dict[str, Any]]
ToolConfigOrDict = Union["ToolConfig", Dict[str, Any]]
RunInputOrDict = Union["BaseRunInput", Dict[str, Any]]
RunOutputOrDict = Union["BaseRunOutput", Dict[str, Any]]
WorkflowConfigFullyHydratedOrDict = Union["WorkflowConfigFullyHydrated", Dict[str, Any]]
LLMConfigOrDict = Union["LLMOrGroupConfig", Dict[str, Any]]
SuperNodeInterfaceOrDict = Union["SuperNodeInterface", Dict[str, Any]]
WorkflowTemplateConfigOrDict = Union["WorkflowTemplateConfig", Dict[str, Any]]

__all__ = [
    "WorkflowConfigOrDict",
    "NodeConfigOrDict",
    "EdgeConfigOrDict",
    "ToolConfigOrDict",
    "RunInputOrDict",
    "RunOutputOrDict",
    "WorkflowConfigFullyHydratedOrDict",
    "LLMConfigOrDict",
    "SuperNodeInterfaceOrDict",
    "WorkflowTemplateConfigOrDict",
]
