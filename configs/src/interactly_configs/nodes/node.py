from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from interactly_configs.base_defs import BaseEntityConfig
from interactly_configs.condition import ConditionConfig
from interactly_configs.run_input import BaseRunInput
from interactly_configs.run_output import BaseRunOutput


class NodeType(str, Enum):
    # System nodes
    SAY_LLM = "say_llm"
    WORKER_LLM = "worker_llm"
    SUPER_NODE = "super_node"
    SAY_STATIC = "say_static"
    TOOL_NODE = "tool_node"

    # internal system nodes
    WORKFLOW_RUN_FETCH = "workflow_run_fetch"
    WORKFLOW_RUN_EVALUATOR = "workflow_run_evaluator"

    # Conversation nodes
    START_CONVERSATION = "start_conversation"
    END_CONVERSATION = "end_conversation"

    # Communication nodes
    SEND_SMS = "send_sms"

    # Google Workspace nodes
    GOOGLE_DOCS = "google_docs"

    # API nodes
    HTTP_REQUEST = "http_request"

    # Athena nodes
    ATHENA_PATIENTS_SEARCH = "athena_patients_search"
    ATHENA_PATIENTS_UPDATE = "athena_patients_update"
    ATHENA_PATIENTS_CREATE = "athena_patients_create"
    ATHENA_APPOINTMENTS_CREATE = "athena_appointments_create"

    # Data Transformation nodes
    DEDUPLICATE = "deduplicate"
    FIELD_EXTRACTOR = "field_extractor"

    # Utility nodes
    NO_OP = "no_op"

class NodeCategory(str, Enum):
    """
    Enum representing different categories of nodes.
    """

    # Primary categories
    SYSTEM = "System"
    SUPER_NODE = "Super Node"
    CUSTOM = "Custom"
    COMMUNICATIONS = "Communications"
    GOOGLE_WORKSPACE = "Google Workspace"
    REST_API = "REST API"
    EHR = "EHR"
    ATHENA = "Athena"
    DATA_TRANSFORMATION = "Data Transformation"

    # Secondary categories
    CONVERSATION = "Conversation"
    LLM = "LLM"
    SMS = "SMS"
    GOOGLE_DOCS = "Google Docs"
    HTTP_REQUEST = "HTTP Request"
    EHR_INTEGRATIONS = "EHR Integrations"
    EVALUATION = "Evaluation"
    UTILITY = "Utility"
    TOOL = "Tool"
    DEDUPLICATION = "Deduplication"
    EXTRACTION = "Extraction"

class GlobalConditionEdgeEvaluationMethod(str, Enum):
    WORKFLOW_DEFAULT = "workflow_default"
    TOOL_CALL = "tool_call"
    INDEPENDENT_LLM_EVALUATIONS = "independent_llm_evaluations"

class GlobalNodeConfig(BaseModel):
    is_global: bool = Field(
        default=False,
        description="Whether this node is a global node available as a conditional pathway to all nodes in the workflow",
        title="Is Global Node",
    )
    condition: Optional[ConditionConfig] = Field(
        default=None,
        description="Condition that determines whether this global node is navigated to",
        title="Global Node Condition",
    )
    global_condition_edge_evaluation_method: Optional[GlobalConditionEdgeEvaluationMethod] = Field(
        default=GlobalConditionEdgeEvaluationMethod.WORKFLOW_DEFAULT,
        description="Method used to evaluate global condition edges going into this node.",
        title="Global Condition Edge Evaluation Method",
    )
    reverse_conditional_edge: Optional[ConditionConfig] = Field(
        default=None,
        description=(
            "Condition and message configuration for navigating back to the node that preceded this global node. "
            "When the condition is satisfied while this global node is executing, the workflow returns control to "
            "whichever node originally transitioned into this global node. Supports freeform condition, args schema, "
            "static messages, and dynamic messages — identical to a regular conditional edge."
        ),
        title="Reverse Conditional Edge",
    )

class SelfLoopConfig(BaseModel):
    """
    Bounded self-loop / retry policy for a node.

    When ``enabled``, the node re-executes its functionality repeatedly until ONE of the following
    happens, whichever comes first:
      1. an outgoing conditional edge matches (the loop's exit), or
      2. ``max_retries`` re-executions have been performed, or
      3. the ``expiry_time`` wall-clock budget for the whole loop elapses.

    Outgoing conditional edges are re-evaluated after every execution to decide whether to exit
    (take a matching edge) or run again. When the loop stops without a matching exit edge, the
    runtime publishes a ``self_loop_outcome`` runtime variable (``"max_retries"`` | ``"expiry_time"``)
    that authors can branch on with a dedicated "exhausted"/"timeout" conditional edge.

    This is distinct from the LLM-node ``self_loop: bool`` flag, which governs loop-back while
    waiting for the next user message and is unaffected by this config.
    """

    enabled: bool = Field(
        default=False,
        description=(
            "Re-execute this node until a conditional edge matches, max_retries is reached, or "
            "expiry_time elapses (whichever comes first)."
        ),
        title="Self Loop",
    )
    max_retries: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Maximum number of re-executions after the first attempt (total attempts = "
            "max_retries + 1). Leave empty for no bound by count."
        ),
        title="Max Retries",
    )
    expiry_time: Optional[int] = Field(
        default=None,
        ge=1,
        le=3600,
        description=(
            "Overall wall-clock budget in seconds for the whole self-loop. An execution still "
            "running when this elapses is terminated. Leave empty for no time bound. "
            "Note: a CPU-bound inline-Python body with no await points cannot be interrupted "
            "mid-execution; expiry reliably bounds I/O-bound work."
        ),
        title="Expiry Time (seconds)",
    )
    time_between_retries: int = Field(
        default=0,
        ge=0,
        le=300,
        description="Seconds to wait between the end of one execution and the start of the next.",
        title="Time Between Retries (seconds)",
    )

    @model_validator(mode="after")
    def _validate_bounds(self) -> "SelfLoopConfig":
        if self.enabled and self.max_retries is None and self.expiry_time is None:
            raise ValueError("self_loop_config requires at least one of max_retries or expiry_time when enabled.")
        return self


class BaseNodeConfig(BaseEntityConfig):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "node_" + str(uuid4()),
        description="Unique identifier for the node",
        title="Node Logical ID",
    )
    name: Optional[str] = Field(
        default=None,
        description="Name of the node",
        title="Node Name",
    )
    primary_category: Optional[str] = Field(
        default=None,
        description="Primary category of the node. E.g. System, Super Node, Custom, etc",
        title="Primary Category",
    )
    secondary_category: Optional[str] = Field(
        default=None,
        description="Secondary category of the node. E.g. LLM, API Call, etc",
        title="Secondary Category",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the node",
        title="Node Description",
    )
    is_start: bool = Field(
        default=False,
        description="Whether this node is the starting node of the workflow",
        title="Is Start Node",
    )
    global_node_config: Optional[GlobalNodeConfig] = Field(
        default=None,
        description="Configuration for when this node is a global node",
        title="Global Node Configuration",
    )
    is_guardrail_node: bool = Field(
        default=False,
        description=(
            "Whether this node is a guardrail node. When the workflow-level "
            "`miscellaneous.no_hopping_between_guardrail_nodes` setting is enabled (the default), the runtime "
            "blocks conditional transitions from this guardrail node to any other guardrail node — including "
            "regular freeform/expression conditional edges and synthesized global-node edges. Self-edges and "
            "self-loops on the same guardrail node remain allowed."
        ),
        title="Is Guardrail Node",
    )
    self_loop_config: Optional[SelfLoopConfig] = Field(
        default=None,
        description="Bounded self-loop / retry policy for this node.",
        title="Self Loop",
    )


class BaseNodeRunInput(BaseRunInput):
    type: Literal["base_node"] = Field(
        default="base_node",
        description="Discriminator field which must always be 'base_node'",
    )
    node_logical_id: Optional[str] = Field(
        default=None,
        description="Logical ID of the node this run input is for",
        title="Node Logical ID",
    )

class BaseNodeRunOutput(BaseRunOutput):
    type: Literal["base_node"] = Field(
        default="base_node",
        description="Discriminator field which must always be 'base_node'",
    )
    node_logical_id: Optional[str] = Field(
        default=None,
        description="Logical ID of the node this run output belongs to",
        title="Node Logical ID",
    )
    node_run_id: Optional[str] = Field(
        default=None,
        description="Unique identifier for the run of this node",
        title="Node Run ID",
    )
