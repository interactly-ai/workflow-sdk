"""Condition configuration for conditional edges."""

from typing import Optional

from pydantic import BaseModel, Field

from interactly_configs.prompt import DynamicMessagesConfig, StaticMessagesConfig


class ConditionConfig(BaseModel):
    condition_freeform: Optional[str] = Field(
        default=None,
        description="Condition (expressed in natural language) that determines whether this path is taken",
        title="Freeform condition string",
    )
    condition_expression: Optional[str] = Field(
        default=None,
        description="Condition (expressed in a structured equation with variables) that determines whether this path is taken",
        title="Expression condition string",
    )
    args_schema: Optional[dict] = Field(
        default=None,
        description="JSON Schema describing the arguments that will be passed when condition_freeform is evaluated",
        title="Arguments JSON Schema",
    )
    static_messages_config: Optional[StaticMessagesConfig] = Field(
        default=None,
        description="Static messages that an LLM node should emit while this condition is being evaluated",
        title="Static Messages Configuration",
    )
    dynamic_messages_config: Optional[DynamicMessagesConfig] = Field(
        default=None,
        description=(
            "Dynamic message configuration. When set, the LLM will generate a message to say "
            "when this edge is taken, guided by the provided prompt."
        ),
        title="Dynamic Messages Configuration",
    )
