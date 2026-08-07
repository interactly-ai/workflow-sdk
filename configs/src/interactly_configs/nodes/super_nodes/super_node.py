from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

from pydantic import ConfigDict, Field, field_serializer

from interactly_configs.llm_group import LLMOrGroupConfig
from interactly_configs.nodes.node import (
    BaseNodeConfig,
    BaseNodeRunInput,
    BaseNodeRunOutput,
    NodeType,
)
from interactly_configs.super_node_interface import SuperNodeInterface

if TYPE_CHECKING:
    from interactly_configs.workflow import WorkflowConfigFullyHydrated


class SuperNodeReverseEdgeScope(str, Enum):
    """Controls which inlined sub-workflow nodes receive the super node placeholder's
    ``global_node_config.reverse_conditional_edge`` when the super node is expanded.

    The reverse edge is surfaced to the model as a per-turn LLM tool, so in BOTH modes
    only LLM-capable nodes are targeted — a static / HTTP / EndConversation node could
    never fire it.
    """

    # Stamp the reverse onto EVERY interior LLM node, so the "back to caller" tool is
    # available wherever the user converses: a middle specialist, an in-sub-workflow
    # escalation node, or a terminal. This is the default.
    ALL_INTERIOR_LLM_NODES = "all_interior_llm_nodes"

    # Stamp the reverse only onto the sub-workflow's terminal LLM nodes — for
    # sub-workflows where the user should only be able to reverse from the final step.
    TERMINAL_NODES = "terminal_nodes"


class SuperNodeConfig(BaseNodeConfig):
    type: Literal["super_node"] = Field(
        default=NodeType.SUPER_NODE.value,
        description="Type of the node. Must be 'super_node'",
        title="Node Type",
    )
    primary_category: Optional[str] = Field(
        default="Super Node",
        description="Primary category of the node",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default="Super Node",
        description="Secondary category of the node",
        title="Secondary Category",
    )
    super_workflow_id: Optional[str] = Field(
        default=None,
        description="The ID of the workflow encapsulated by this super node",
        title="Super Workflow ID",
    )
    super_workflow_version_number: Optional[int] = Field(
        default=None,
        description="Specific version of the encapsulated workflow. If None, the active version is used at execution time.",
        title="Super Workflow Version Number",
    )
    field_values: Dict[str, Any] = Field(
        default_factory=dict,
        description="Values provided by the calling workflow for each of the super node's declared input fields. Keyed by SuperNodeInputField.name.",
        title="Field Values",
    )
    override_llm_config: bool = Field(
        default=False,
        description=(
            "When true, LLM-based nodes inside this super node use the LLM configuration specified here "
            "(attachable_llm_config_id or llms_config) instead of their own authored config. When false "
            "(the default), interior nodes keep their authored LLM configuration."
        ),
        title="Override LLM Configuration",
    )
    override_only_workflow_default_nodes: bool = Field(
        default=False,
        description=(
            "Scopes the LLM override. When false (the default), every interior LLM node is overridden. "
            "When true, only interior LLM nodes that are themselves set to 'Workflow Default LLM' (i.e. had "
            "no explicit config of their own) are overridden; nodes with an explicit inline/named config are "
            "left untouched. Only relevant when override_llm_config is true."
        ),
        title="Only Override Workflow-Default Nodes",
    )
    attachable_llm_config_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of the named LLM Configuration to apply to the targeted interior LLM nodes. If provided, "
            "overrides the inline llms_config. Only relevant when override_llm_config is true."
        ),
    )
    llms_config: Optional[LLMOrGroupConfig] = Field(
        default=None,
        description=(
            "Inline LLM configuration applied to the targeted interior LLM nodes. Use 'Workflow Default LLM' "
            "to fall back to the base workflow's workflow-level config. Only relevant when override_llm_config "
            "is true."
        ),
        title="LLM Configuration",
    )
    reverse_edge_scope: Optional[SuperNodeReverseEdgeScope] = Field(
        default=None,
        description=(
            "Controls which inlined sub-workflow nodes receive this super node's "
            "global_node_config.reverse_conditional_edge during expansion. When None (the "
            "default), behaves as 'all_interior_llm_nodes': the reverse is stamped onto every "
            "interior LLM node so the user can return to the caller from anywhere inside the "
            "super node. 'terminal_nodes' restricts it to the sub-workflow's terminal LLM nodes "
            "only. Only relevant when global_node_config.reverse_conditional_edge is set. Kept "
            "Optional (None == default behaviour) so the field can be removed later without "
            "breaking existing configs."
        ),
        title="Reverse Edge Scope",
    )
    super_node_interface: Optional[SuperNodeInterface] = Field(
        default=None,
        description=(
            "Interface definition for this super node. Copied from the super node entity at embedding time. "
            "Used by the expander at runtime to resolve field_values mappings. Not user-editable."
        ),
        title="Super Node Interface",
    )
    encapsulated_workflow_config: Optional[WorkflowConfigFullyHydrated] = Field(
        default=None,
        description=(
            "Snapshot of the fully-hydrated sub-workflow config at the time this super node was embedded. "
            "Used by the expander at runtime instead of a DB fetch. Not user-editable."
        ),
        title="Encapsulated Workflow Config",
    )

    @field_serializer("super_workflow_id", when_used="json")
    def _ser_super_workflow_id(self, v: str | None) -> Optional[str]:
        # Need this to serialize str to string for JSON output
        return str(v) if v else None

    model_config = ConfigDict(
        title="Super Node",
    )


class SuperNodeRunInput(BaseNodeRunInput):
    type: Literal["super_node"] = Field(
        default="super_node", description="Discriminator field which must always be 'super_node'"
    )


class SuperNodeRunOutput(BaseNodeRunOutput):
    type: Literal["super_node"] = Field(
        default="super_node", description="Discriminator field which must always be 'super_node'"
    )
