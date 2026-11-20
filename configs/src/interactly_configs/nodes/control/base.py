"""Shared base for the control nodes, which pause the run or end it rather than doing work of their own."""

from typing import Optional

from pydantic import Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunOutput,
    NodeCategory,
    SelfLoopConfig,
)

#: What marks a value as a template, filled in from the variables when the node runs: ``{{dynamic}}``,
#: ``[[runtime]]`` and Liquid tags.
_TEMPLATE_MARKERS = ("{{", "[[", "{%")


class BaseControlNodeConfig(BaseNodeConfig):
    """Files the node under System › Control, and hides settings a control node never uses."""

    primary_category: Optional[str] = Field(
        default=NodeCategory.SYSTEM.value,
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=NodeCategory.CONTROL.value,
        description="Secondary category of the node",
        title="Secondary Category",
    )
    self_loop_config: Optional[SelfLoopConfig] = Field(
        default=None,
        description="A control node runs once each time it is entered.",
        title="Self Loop",
    )


class BaseControlNodeRunOutput(BaseNodeRunOutput):
    success: bool = Field(default=False, description="Whether the node did what it was asked")
    error_message: Optional[str] = Field(default=None, description="Why it did not, when it did not")


def is_template(value: str) -> bool:
    """Whether ``value`` holds a placeholder that is filled in from the variables when the node runs."""
    return any(marker in value for marker in _TEMPLATE_MARKERS)
