from typing import Any, Dict, Literal, Optional

from pydantic import Field

from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
)
from interactly_configs.tool import ToolConfig

class ToolNodeConfig(BaseNodeConfig):
    type: Literal["tool_node"] = Field(
        default="tool_node",
        description="Type of the node. Must be 'tool_node'",
    )
    primary_category: Optional[str] = Field(
        default="System",
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default="Tool",
        description="Secondary category of the node",
        title="Secondary Category",
    )
    tool_config: Optional[ToolConfig] = Field(
        default=None,
        description="Configuration for the tool to be executed",
        title="Tool Configuration",
    )
    tool_arguments: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Arguments to pass to the tool. Can contain dynamic/runtime variables as strings or inside nested structures.",
        title="Tool Arguments",
    )
    result_runtime_variable_name: Optional[str] = Field(
        default="tool_result",
        description="Name of the runtime variable to store the result of the tool execution",
        title="Result Runtime Variable Name",
    )

class ToolNodeRunInput(BaseNodeRunInput):
    type: Literal["tool_node"] = Field(
        default="tool_node",
        description="Discriminator field which must always be 'tool_node'",
    )

class ToolNodeRunOutput(BaseNodeRunOutput):
    type: Literal["tool_node"] = Field(
        default="tool_node",
        description="Discriminator field which must always be 'tool_node'",
    )
    success: bool = Field(
        default=False,
        description="Indicates whether the tool execution was successful",
    )
    tool_result: Optional[Any] = Field(
        default=None,
        description="The resulting output of the tool execution",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the tool execution failed",
    )
