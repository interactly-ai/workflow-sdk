from typing import Any, Dict, Literal, Optional

from pydantic import Field, model_validator

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

    preserve_argument_types: bool = Field(
        default=False,
        description=(
            "When true, a tool_arguments value that is exactly one placeholder (e.g. '[[patient]]' with "
            "nothing around it) resolves to the variable's native value — dict, list, int, bool, None — "
            "instead of its string form, and an unresolved one becomes None rather than the literal "
            "placeholder text. Mixed strings such as 'Hello {{name}}' are interpolated as before. Off by "
            "default because it changes the type an existing tool receives."
        ),
        title="Preserve Argument Types",
    )

    @model_validator(mode="after")
    def _check_mappings_avoid_this_nodes_outcome_keys(self) -> "ToolNodeConfig":
        """Reject a result mapping that would land on this node's own success/error variables.

        ``BaseToolConfig`` already reserves the keys derived from *its own*
        ``result_runtime_variable_name``, but the tool node writes its outcome under the **node's** field,
        and the two are independent (both default to ``"tool_result"``). So a node named ``"scoring"``
        holding a tool config left at the default reserves ``tool_result_success`` while actually writing
        ``scoring_success`` — and a mapping onto that name passes tool-level validation. This class is the
        only object that sees both fields.

        It raises rather than warns because the window is open: ``result_variable_mappings`` is unreleased,
        so no stored config can contain one and nothing existing can be invalidated.

        Three limits, stated so the partial coverage is not mistaken for the whole guarantee — the runtime
        write order is what actually guarantees it:

        * a *saved* tool's mappings are invisible here, and reachable at runtime after the by-reference
          merge;
        * ``expand_result_into_runtime_variables`` cannot be checked at all, since the colliding name comes
          from the tool's return value rather than its config;
        * the same tool config is valid on an LLM node and invalid here. That is correct in substance —
          only the tool node owns these keys — but it does mean a saved tool cannot be validated alone.
        """
        if not self.tool_config or not self.tool_config.result_variable_mappings:
            return self

        result_name = self.result_runtime_variable_name or "tool_result"
        reserved = {f"{result_name}_success", f"{result_name}_error"}
        offenders = sorted({m.target_variable_name for m in self.tool_config.result_variable_mappings} & reserved)
        if offenders:
            raise ValueError(
                f"result_variable_mappings writes {offenders}, which this tool node already writes as the "
                f"outcome of the call (derived from the node's result_runtime_variable_name="
                f"'{result_name}'). Mapping onto them would replace the success flag or the error message "
                f"with tool data, and conditional edges branch on those. Choose another target name."
            )
        return self


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
