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
        description=(
            "Name of the runtime variable to store the result of the tool execution. Leaving this at "
            "'tool_result' means inherit: if the attached tool names its own result variable, that name "
            "is used. Any OTHER name set here overrides the tool. 'tool_result' cannot be used to "
            "override a tool that names something else — it is indistinguishable from not having chosen. "
            "The success flag and error message follow whichever name wins, as <name>_success and "
            "<name>_error."
        ),
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
        ``result_runtime_variable_name``, but the tool node writes under whichever of the two wins —
        see :func:`effective_result_variable_name`; the older reading, that the node's field always won,
        and the two are independent (both default to ``"tool_result"``). So a node named ``"scoring"``
        holding a tool config left at the default reserves ``tool_result_success`` while actually writing
        ``scoring_success`` — and a mapping onto that name passes tool-level validation. This class is the
        only object that sees both fields.

        **It raises rather than warns, and the reason is not that the field is new.** It is not:
        ``result_variable_mappings`` ships with a dashboard editor and the copilot writes it, so stored
        configs do contain mappings. What makes raising safe is that this validator has been rejecting the
        colliding shape since before the field was authorable anywhere, so no config that would trip it
        can ever have been stored — the population it rejects is empty by construction, and it gates every
        write into that population, so it cannot grow.

        That matters more here than for a save-time check, because ``model_validator(mode="after")`` fires
        on *parse*, which includes reading a stored node. A collision that had been stored would make the
        workflow unloadable rather than merely unsavable. ``configs/tool.py`` keeps its equivalent raise on
        the same reasoning.

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

        result_name = effective_result_variable_name(self, self.tool_config)
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


def effective_result_variable_name(node_config: Any, tool_config: Any = None) -> str:
    """Where a tool node actually writes its outcome: the node's name if the author chose one, else the
    tool's.

    Mirrors the upstream rule exactly, and mirroring it is not optional — this is what the validator above
    reserves ``<name>_success`` / ``<name>_error`` against, so a mirror using the older "the node always
    wins" reading would **accept configs the server rejects and reject configs the server accepts**. That
    divergence is invisible to ``make parity-check``: it compares a validator as
    ``"{decorator}:{mode}"`` and does not look at module-level functions at all.

    **"Chose one" is decided by VALUE, not by ``model_fields_set``.** Every config reaches a server
    runtime through a Mongo round-trip, and Beanie persists all fields with ``keep_nulls=True``, so
    ``model_validate`` marks every field as explicitly set — a set-based rule adopts the tool's name never
    in production while passing every in-memory test. Compared against the field's declared default rather
    than a literal, so changing that default cannot silently invert the rule.

    The one ambiguity is unresolvable: an author who explicitly wants ``tool_result`` on a node whose tool
    names something else cannot be told apart from one who left the field alone, so the tool wins.
    """
    declared_default = ToolNodeConfig.model_fields["result_runtime_variable_name"].default
    chosen = getattr(node_config, "result_runtime_variable_name", None)
    if chosen and chosen != declared_default:
        return chosen
    from_tool = getattr(tool_config, "result_runtime_variable_name", None)
    return from_tool or chosen or declared_default


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
