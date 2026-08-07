"""Workflow-level configuration models.

Note: ``node_configs`` in ``WorkflowConfigFullyHydrated`` is typed as
``SerializeAsAny[BaseNodeConfig]`` (the client-visible base). ``SerializeAsAny``
is essential: it makes each node serialise with its **actual** subclass fields —
including the ``type`` discriminator — so the server can retag it on import.
Without it, Pydantic would dump each node using only the ``BaseNodeConfig``
fields, dropping ``type`` and the subclass payload, which makes the server
silently create an empty workflow.
"""

from enum import Enum
from typing import Any, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, SerializeAsAny

from interactly_configs.acls import AccessControlLevel
from interactly_configs.edge import EdgeConfig
from interactly_configs.evaluation import EvaluationConfig
from interactly_configs.llm import NoLLMConfig
from interactly_configs.llm_group import LLMOrGroupConfig
from interactly_configs.nodes import BaseNodeConfig
from interactly_configs.prompt import PromptConfig
from interactly_configs.tool import MCPServerConfig, ToolsConfig


class GlobalConditionEdgeEvaluationMethod(str, Enum):
    TOOL_CALL = "tool_call"
    INDEPENDENT_LLM_EVALUATIONS = "independent_llm_evaluations"


class GuardrailStrikesConfig(BaseModel):
    max_guardrail_nodes_before_escalation: Optional[int] = Field(
        default=None,
        description=(
            "Maximum number of times guardrail nodes may be entered (from a non-guardrail node) "
            "before the workflow escalates. None disables the feature."
        ),
        title="Max Guardrail Nodes Before Escalation",
    )
    escalation_node_logical_id: Optional[str] = Field(
        default=None,
        description=(
            "Logical ID of the node to transition to when the escalation threshold is reached. "
            "If None (or it does not resolve to a node), the workflow finishes instead."
        ),
        title="Escalation Node Logical ID",
    )
    escalation_message: Optional[str] = Field(
        default=None,
        description=(
            "Message sent to the user just before the workflow finishes when the escalation "
            "threshold is reached and no escalation node is configured. Supports dynamic/runtime "
            "variable templating. If None, the workflow finishes silently."
        ),
        title="Escalation Message",
    )


def _parse_workflow_bool(raw: Any, *, default: bool) -> bool:
    """Read a ``miscellaneous`` flag that may have been stored as a bool or as a string.

    ``miscellaneous`` is an untyped dict, so a flag set through the dashboard can arrive as the
    string "true" while the same flag set programmatically arrives as a real bool. Both must mean
    the same thing.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        lowered = raw.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    return default


class WorkflowAccessConfig(BaseModel):
    """Access control for a workflow."""

    access_level: Optional[AccessControlLevel] = Field(
        default=None,
        description="Access level for the workflow",
        title="Access Level",
    )
    access_list: Optional[List[str]] = Field(
        default=None,
        description="List of user IDs that have access to this workflow",
        title="Access List",
    )


class WorkflowConfig(BaseModel):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "workflow_" + str(uuid4()),
        description="Unique identifier for the workflow",
        title="Workflow Logical ID",
    )
    name: Optional[str] = Field(
        default=None,
        description="Name of the workflow",
        title="Workflow Name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the workflow",
        title="Workflow Description",
    )
    category: Optional[str] = Field(
        default="User Created",
        description="Category of the workflow (e.g. 'User Created', 'System Examples', 'System Internal')",
        title="Workflow Category",
    )
    attachable_llm_config_id: Optional[str] = Field(
        default=None,
        description="ID of the named LLM Configuration to use. If provided, overrides inline configuration.",
    )
    llms_config: Optional[LLMOrGroupConfig] = Field(
        default_factory=NoLLMConfig,
        description=(
            "Global configuration for LLM based nodes. "
            "Used if no specific LLM configuration is provided for a node."
        ),
        title="Global LLM Configuration",
    )
    main_response_config: Optional[PromptConfig] = Field(
        default=None,
        description=(
            "Global main response configuration. "
            "Used if no specific prompt config is provided for a node."
        ),
        title="Global Main Response Configuration",
    )
    backchannel_response_config: Optional[PromptConfig] = Field(
        default=None,
        description=(
            "Global backchannel response configuration. "
            "Used if no specific backchannel prompt config is provided for a node."
        ),
        title="Global Backchannel Response Configuration",
    )
    default_prompt_prefix: Optional[str] = Field(
        default=None,
        description="If present, this string will be added as prefix to every node's system prompt",
        title="Global Default Prompt Prefix",
    )
    default_prompt_suffix: Optional[str] = Field(
        default=None,
        description="If present, this string will be added as suffix to every node's system prompt",
        title="Global Default Prompt Suffix",
    )
    ignore_content_received_during_llm_tool_call_specification: bool = Field(
        default=False,
        description=(
            "If true, every LLM node in this workflow behaves as if "
            "ignore_content_received_during_llm_tool_call_specification is true, and every tool behaves "
            "as if ignore_content_received_during_llm_tool_call_specification is true: free-text "
            "content the LLM returns in the same response as one or more tool calls is ignored "
            "and treated as empty."
        ),
        title="Ignore content received during LLM tool call specification",
    )
    tools_config: Optional[ToolsConfig] = Field(
        default=None,
        description="Global list of tools available to all LLM based nodes in the workflow",
        title="Global Tools Configuration",
    )
    mcp_servers: Optional[List[MCPServerConfig]] = Field(
        default=None,
        description=(
            "List of MCP server connections. "
            "Tools discovered from these servers are available to nodes with use_mcp_tools enabled."
        ),
        title="MCP Server Configurations",
    )
    global_condition_evaluation_method: Optional[GlobalConditionEdgeEvaluationMethod] = Field(
        default=GlobalConditionEdgeEvaluationMethod.TOOL_CALL,
        description="Method used to evaluate global conditions for all nodes in this workflow.",
        title="Global Condition Evaluation Method",
    )
    nodes: List[str] = Field(
        default_factory=list,
        description="List of node DB IDs in the workflow",
        title="Node IDs",
    )
    edges: List[str] = Field(
        default_factory=list,
        description="List of edge DB IDs in the workflow",
        title="Edge IDs",
    )
    miscellaneous: dict = Field(
        default_factory=dict,
        description=(
            "Miscellaneous workflow-level config passed to the runtime.\n\n"
            "Known keys (all optional):\n"
            "  ``consecutive_conditional_edges_max_limit`` (int as str, default ``'3'``) — "
            "Maximum number of consecutive conditional edge hops before the next LLM call "
            "is forced to skip tool calls, breaking potential infinite-loop chains.\n"
            "  ``no_consecutive_conditional_edge_after_reverse_conditional_edge_taken`` "
            "(``'true'``/``'false'``, default ``'true'``) — When ``'true'``, taking any "
            "reverse conditional edge always triggers the no-tool-call enforcement on the "
            "immediately following LLM invocation."
        ),
        title="Miscellaneous Config",
    )
    access_config: Optional[WorkflowAccessConfig] = Field(
        default_factory=WorkflowAccessConfig,
        description="Access control configuration for the workflow",
        title="Access Config",
    )
    evaluation_config: Optional[EvaluationConfig] = Field(
        default=None,
        description="Configuration for automatic evaluation of workflow runs",
        title="Evaluation Configuration",
    )
    guardrail_strikes_config: Optional[GuardrailStrikesConfig] = Field(
        default=None,
        description="Configuration for guardrail-node strike counting and escalation.",
        title="Guardrail Strikes Configuration",
    )


class WorkflowConfigFullyHydrated(BaseModel):
    """A fully resolved workflow config with embedded node and edge objects.

    On the server side, ``node_configs`` is typed as the discriminated
    ``NodeConfig`` union. On the client side, ``BaseNodeConfig`` is used
    since the full node hierarchy is not published.
    """

    workflow_config: Optional[WorkflowConfig] = Field(
        default=None,
        description="Workflow configuration for runtime",
    )
    node_configs: List[SerializeAsAny[BaseNodeConfig]] = Field(
        default_factory=list,
        description="List of node configurations for runtime",
    )
    edge_configs: List[EdgeConfig] = Field(
        default_factory=list,
        description="List of edge configurations for runtime",
    )
    dynamic_variables: dict = Field(
        default_factory=dict,
        description="Dynamic variables that can be used across nodes and edges",
    )
    runtime_variables: dict = Field(
        default_factory=dict,
        description="Runtime variables that can be used across nodes and edges",
    )

    def is_keep_skipped_messages_enabled(self) -> bool:
        """Read the ``keep_skipped_messages_in_history`` miscellaneous flag; default False.

        When True, assistant fragments the caller barged over are RETAINED in the chat history
        instead of being pruned.

        Operational tradeoff: retained fragments were generated *before* the barge-in and may
        include content the caller did not fully hear. Once retained, that content stays visible to
        subsequent workflow / LLM turns, which will treat it as already spoken. Enable only when that
        is the desired behavior.
        """
        if self.workflow_config is None:
            return False
        raw = self.workflow_config.miscellaneous.get("keep_skipped_messages_in_history", False)
        return _parse_workflow_bool(raw, default=False)
