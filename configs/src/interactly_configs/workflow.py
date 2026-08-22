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
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    SerializeAsAny,
    TypeAdapter,
    ValidationError,
    field_validator,
)

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


#: Built once — constructing a TypeAdapter per node would dominate the cost of parsing a workflow.
#: Imported lazily inside the module body to avoid a cycle: node_unions imports config modules that
#: (indirectly) import this one.
from interactly_configs.nodes.node_unions import NodeConfig as _NodeConfigUnion  # noqa: E402

_NODE_CONFIG_ADAPTER = TypeAdapter(_NodeConfigUnion)


class UnknownNodeConfig(BaseNodeConfig):
    """Fallback for a node whose ``type`` this package does not know yet.

    A client necessarily lags the server, so a workflow can legitimately contain a node type added
    after this package was released. Rather than failing the whole workflow, such a node lands here
    with ``extra="allow"`` so its fields survive validation and a later ``model_dump()`` — which means
    a fetch/modify/upload round trip does not quietly delete parts of someone's workflow.
    """

    model_config = ConfigDict(extra="allow")


def _coerce_node_config(value: Any) -> Any:
    """Validate one node through the discriminated union, falling back for unknown types.

    ``List[SerializeAsAny[BaseNodeConfig]]`` alone is NOT enough: ``SerializeAsAny`` governs
    serialization, so it preserves subclass fields only for an object that is already the subclass.
    Validating a plain dict against that annotation coerces it straight to ``BaseNodeConfig`` and
    **silently discards every subclass field** — a `say_llm` node came back with no ``type``, no
    ``prompt_config`` and no ``wait_for_user_message``. Upgrading through the union here is what makes
    a server round trip lossless.
    """
    if isinstance(value, BaseNodeConfig):
        return value
    if isinstance(value, dict):
        try:
            return _NODE_CONFIG_ADAPTER.validate_python(value)
        except ValidationError:
            return UnknownNodeConfig.model_validate(value)
    return value


class WorkflowConfigFullyHydrated(BaseModel):
    """A fully resolved workflow config with embedded node and edge objects.

    ``node_configs`` is annotated ``SerializeAsAny[BaseNodeConfig]`` rather than the server's
    discriminated ``NodeConfig`` union so an unknown node type cannot fail the whole workflow, and a
    ``mode="before"`` validator upgrades each entry through that union so known types keep full
    fidelity. See ``_coerce_node_config``.
    """

    workflow_config: Optional[WorkflowConfig] = Field(
        default=None,
        description="Workflow configuration for runtime",
    )
    node_configs: List[SerializeAsAny[BaseNodeConfig]] = Field(
        default_factory=list,
        description="List of node configurations for runtime",
    )

    @field_validator("node_configs", mode="before")
    @classmethod
    def _upgrade_node_configs(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [_coerce_node_config(item) for item in value]
        return value
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
    secret_variables: Dict[str, SecretStr] = Field(
        default_factory=dict,
        exclude=True,
        repr=False,
        description=(
            "Credential-valued variables, carried apart from dynamic_variables so this config can be "
            "serialized, logged and cached without emitting them. Copied onto the run input, which "
            "documents the rule; see BaseRunInput.secret_variables."
        ),
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
