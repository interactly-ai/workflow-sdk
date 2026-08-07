"""Edge configuration models."""

from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, Type
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from interactly_configs.base_defs import BaseEntityConfig
from interactly_configs.condition import ConditionConfig

# Delimiter joining a fork companion's internal thread id: ``"<parent>_companion_<configured_id>"``.
# This substring is load-bearing — companion detection and the author-facing thread_reference_id
# derivation both key off it. Defined here (a leaf config module) so every producer/consumer
# references one canonical value instead of a repeated literal.
COMPANION_THREAD_DELIMITER = "_companion_"


class EdgeType(str, Enum):
    DIRECT = "direct"
    CONDITIONAL = "conditional"
    COMPANION = "companion"

    @classmethod
    def get_type_to_config_map(cls) -> Dict["EdgeType", Type["BaseEdgeConfig"]]:
        """Returns a mapping of edge types to their respective configuration classes."""
        return {
            cls.DIRECT: DirectEdgeConfig,
            cls.CONDITIONAL: ConditionalEdgeConfig,
            cls.COMPANION: CompanionEdgeConfig,
        }

    @classmethod
    def get_type_to_run_input_map(cls) -> Dict["EdgeType", Type["BaseEdgeRunInput"]]:
        """Returns a mapping of edge types to their respective run-input classes."""
        return {
            cls.DIRECT: BaseEdgeRunInput,
            cls.CONDITIONAL: BaseEdgeRunInput,
            cls.COMPANION: BaseEdgeRunInput,
        }


class BaseEdgeConfig(BaseEntityConfig):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "edge_" + str(uuid4()),
        description="Unique identifier for the edge",
        title="Edge Logical ID",
    )
    name: Optional[str] = Field(default=None, description="Name of the edge", title="Edge Name")
    description: Optional[str] = Field(default=None, description="Description of the edge", title="Edge Description")
    source_node_logical_id: Optional[str] = Field(
        default=None,
        description="Logical ID of the source node for this edge",
        title="Source Node Logical ID",
    )
    destination_node_logical_id: Optional[str] = Field(
        default=None,
        description="Logical ID of the target node for this edge",
        title="Destination Node Logical ID",
    )


class CompanionThreadConfig(BaseModel):
    """
    Compound companion-thread settings for a direct edge, grouping the two related fields so their
    relationship is explicit in the authoring UI and the stored config.
    """

    is_companion_thread: bool = Field(
        default=False,
        description=(
            "When a node has multiple outgoing direct edges, edges with this flag set to True spawn "
            "companion threads that run alongside the single main thread (the one edge with this flag "
            "False). Companion threads keep executing and emitting events while the main thread waits "
            "for user input, and never receive UI user messages. A lone direct edge always continues "
            "the main thread regardless of this flag."
        ),
        title="Is Companion Thread",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description=(
            "Author-chosen id for the forked companion thread. Other threads read this companion's "
            "runtime variables via [[thread_<thread_id>.<var>]], and the companion reads the main "
            "thread via [[thread_0.<var>]]. Must be unique across the workflow's companion edges, "
            "non-empty, and use only [A-Za-z0-9_-] (no '.', no '_companion_', and not the reserved "
            "id '0'). Optional: if omitted, a uuid is generated at fork time and the companion is not "
            "addressable via a cross-thread reference."
        ),
        title="Thread ID",
    )

    model_config = ConfigDict(title="Companion Thread")


class DirectEdgeConfig(BaseEdgeConfig):
    type: Literal["direct"] = Field(
        default=EdgeType.DIRECT.value,
        description="Type of the edge. Always 'direct' for this config.",
        title="Edge Type",
    )
    companion_thread_config: Optional[CompanionThreadConfig] = Field(
        default=None,
        description=(
            "Companion-thread settings (is_companion_thread + thread_id). None means the edge continues "
            "the main thread. See CompanionThreadConfig."
        ),
        title="Companion Thread",
    )

    model_config = ConfigDict(title="Direct Edge")


class WaitingEvaluationTriggerMode(str, Enum):
    """What arms an evaluation of a conditional edge while its source node waits for user input."""

    # Armed by a nominated node completing another execution (in any thread). The recommended mode:
    # it does no work until the node that can actually change the expression's inputs has run.
    ON_NODE_COMPLETION = "on_node_completion"
    # Armed on every background pump pass. Blind polling — only for authors who cannot name a
    # trigger node; pair with ``min_seconds_between_evaluations`` to bound the cost.
    ON_EVERY_BACKGROUND_TICK = "on_every_background_tick"


class EvaluateWhileWaitingConfig(BaseModel):
    """
    Opt-in: evaluate this conditional edge's ``condition_expression`` while the SOURCE node is parked
    waiting for a user message, and take the edge if it becomes True — with no user message required.

    Without this config a conditional edge is evaluated at exactly one moment: immediately after each
    execution of its source node. A ``say_llm`` node with ``self_loop`` + ``wait_for_user_message``
    therefore parks indefinitely, and a runtime variable that flips in the background (e.g. written by
    a polling node in a companion thread) cannot move the conversation forward on its own.

    Only valid on an edge whose condition uses ``condition_expression``; ``condition_freeform``
    conditions need an LLM call per evaluation and are rejected rather than silently ignored.
    """

    enabled: bool = Field(
        default=False,
        description=(
            "When True, this edge is also evaluated while its source node is parked waiting for user "
            "input, and is taken if the expression becomes True."
        ),
        title="Evaluate While Waiting For User Input",
    )
    trigger_mode: WaitingEvaluationTriggerMode = Field(
        default=WaitingEvaluationTriggerMode.ON_NODE_COMPLETION,
        description=(
            "What arms an evaluation. 'on_node_completion' (recommended) evaluates only once a node "
            "named in trigger_node_logical_ids has completed another execution; "
            "'on_every_background_tick' evaluates on every background pass."
        ),
        title="Evaluation Trigger",
    )
    trigger_node_logical_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Node logical ids whose completion arms one evaluation of this edge. Required when "
            "trigger_mode is 'on_node_completion'. Nodes may live in any thread — typically a "
            "companion-thread node that updates the runtime variable this expression reads."
        ),
        title="Trigger Nodes",
    )
    min_seconds_between_evaluations: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Debounce: an armed evaluation waits until this many seconds after the previous one. "
            "REQUIRED (and must be > 0) when trigger_mode is 'on_every_background_tick', because that "
            "mode is always armed — without a debounce it would evaluate on every background pass, "
            "spinning the driver loop and flooding the run record. Optional for 'on_node_completion', "
            "which is already bounded by how often the trigger node completes. 0 means no debounce and "
            "is only meaningful for 'on_node_completion'."
        ),
        title="Minimum Seconds Between Evaluations",
    )
    max_transitions_per_wait: int = Field(
        default=3,
        ge=1,
        description=(
            "Hard bound on how many times this edge may fire during a single uninterrupted wait "
            "(reset when a user message is received). Guards against background hop loops in which no "
            "user is ever given a turn."
        ),
        title="Max Transitions Per Wait",
    )

    model_config = ConfigDict(title="Evaluate While Waiting For User Input")


class ConditionalEdgeConfig(BaseEdgeConfig):
    type: Literal["conditional"] = Field(
        default=EdgeType.CONDITIONAL.value,
        description="Type of the edge. Always 'conditional' for this config.",
        title="Edge Type",
    )
    condition: Optional[ConditionConfig] = Field(
        default=None,
        description="Condition that determines whether this edge is taken",
        title="Edge Condition",
    )
    evaluate_while_waiting_config: Optional[EvaluateWhileWaitingConfig] = Field(
        default=None,
        description=(
            "Settings for evaluating this edge while its source node waits for user input. None (the "
            "default) preserves the classic behavior exactly: the edge is evaluated only after each "
            "source-node execution. See EvaluateWhileWaitingConfig."
        ),
        title="Evaluate While Waiting For User Input",
    )

    model_config = ConfigDict(title="Conditional Edge")


class CompanionEdgeConfig(BaseEdgeConfig):
    type: Literal["companion"] = Field(
        default=EdgeType.COMPANION.value,
        description="Type of the edge. Always 'companion' for this config.",
        title="Edge Type",
    )

    model_config = ConfigDict(title="Companion Edge")


EdgeConfig = Annotated[
    DirectEdgeConfig | ConditionalEdgeConfig | CompanionEdgeConfig,
    Field(discriminator="type"),
]


def edge_is_companion(edge: Any) -> bool:
    """
    True when a direct edge is flagged as a companion-thread fork. Reads the nested
    ``companion_thread_config`` defensively so it works on any edge type (non-direct edges have no
    companion config and return False).
    """
    cfg = getattr(edge, "companion_thread_config", None)
    return bool(cfg and cfg.is_companion_thread)


def edge_companion_thread_id(edge: Any) -> Optional[str]:
    """Author-chosen companion ``thread_id`` for a direct edge, or None if unset / not a companion edge."""
    cfg = getattr(edge, "companion_thread_config", None)
    return cfg.thread_id if cfg else None


def edge_evaluates_while_waiting(edge: Any) -> bool:
    """
    True when a conditional edge opts into being evaluated while its source node waits for user input.
    Reads the nested ``evaluate_while_waiting_config`` defensively so it works on any edge type (a
    non-conditional edge has no such config and returns False), and so a config persisted before this
    feature existed reads as False.
    """
    cfg = getattr(edge, "evaluate_while_waiting_config", None)
    return bool(cfg and cfg.enabled)


def edge_waiting_evaluation_config(edge: Any) -> Optional[EvaluateWhileWaitingConfig]:
    """The edge's ``EvaluateWhileWaitingConfig`` if it is enabled, else None."""
    cfg = getattr(edge, "evaluate_while_waiting_config", None)
    return cfg if (cfg and cfg.enabled) else None


class BaseEdgeRunInput(BaseModel):
    miscellaneous: dict = Field(
        default_factory=dict,
        description="Miscellaneous run-input data that can be used by the edge",
        title="Miscellaneous Edge Run Input",
    )
