"""Runtime event models for the Interactly workflow engine.

This module mirrors the event hierarchy emitted by the server-side workflow
runtime.  Message-carrying fields use ``Any`` instead of langchain types so
this package has no runtime dependency on ``langchain_core``; events arrive
as plain dicts and round-trip cleanly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter, computed_field

from interactly_configs.comment import CommentConfig
from interactly_configs.edge import COMPANION_THREAD_DELIMITER
from interactly_configs.nodes.node_unions import NodeRunInput, NodeRunOutput
from interactly_configs.workflow_run import WorkflowRunInputOutputPair


def _thread_reference_id(thread_id: str | None) -> Optional[str]:
    """
    Author-facing display id for a thread: the main thread stays ``"0"``; a fork companion whose
    internal id is ``"<parent>_companion_<configured>"`` displays as its configured id.
    """
    if thread_id is None:
        return None
    if COMPANION_THREAD_DELIMITER in thread_id:
        return thread_id.rsplit(COMPANION_THREAD_DELIMITER, 1)[-1]
    return thread_id


# The set of terminal reasons a bounded self-loop can stop on. Kept as a single named contract so
# producers and event consumers agree on the allowed values instead of relying on free-form strings.
SelfLoopOutcome = Literal["max_retries", "expiry_time"]


class BaseEvent(BaseModel):
    logical_id: Optional[str] = Field(
        default_factory=lambda: "event_" + str(uuid4()),
        description="Unique ID associated with this event. If not provided, a new ID will be generated.",
    )
    timestamp: float = Field(
        default_factory=lambda: datetime.now(timezone.utc).timestamp(),
        description="Timestamp of when the event was created, in UTC.",
        title="Event Timestamp",
    )
    origin_thread_id: Optional[str] = Field(default=None, description="ID of the thread to which this event belongs")
    comments: List[CommentConfig] = Field(
        default_factory=list,
        description="List of comments associated with the workflow run",
        title="Workflow Run Comments",
    )
    interrupted: bool = Field(
        default=False,
        description="Indicates whether this event was generated but interrupted during a live voice session.",
        title="Event Interrupted Flag",
    )

    @computed_field(  # type: ignore[prop-decorator]
        description=(
            "Author-facing display id for the event's thread: '0' for the main thread, or a fork "
            "companion's configured thread_id (derived from the internal '<parent>_companion_<id>')."
        )
    )
    @property
    def thread_reference_id(self) -> Optional[str]:
        return _thread_reference_id(self.origin_thread_id)


class StructuredOutputRetryAttempt(BaseModel):
    attempt_number: int = Field(description="The attempt number that failed.")
    error_message: str = Field(description="The error message received when trying to parse the invalid JSON.")
    latency_milliseconds: int = Field(description="The latency of the LLM response for this failed attempt.")


class StructuredOutputRetryMetadata(BaseModel):
    retry_count: int = Field(description="Number of retry attempts made to get a valid JSON output from the LLM.")
    failed_attempts: List[StructuredOutputRetryAttempt] = Field(
        default_factory=list, description="Details of the failed attempts to parse the structured output."
    )


class IterationCallLatencyStats(BaseModel):
    """
    Latency distribution statistics for a category of calls (LLM or tool) within one iteration.
    All values are in milliseconds.
    """

    average_milliseconds: Optional[float] = Field(
        default=None,
        description="Mean latency across all calls of this type. None if no calls were made.",
    )
    min_milliseconds: Optional[float] = Field(
        default=None,
        description="Minimum (fastest) individual call latency. None if no calls were made.",
    )
    max_milliseconds: Optional[float] = Field(
        default=None,
        description="Maximum (slowest) individual call latency. None if no calls were made.",
    )
    median_milliseconds: Optional[float] = Field(
        default=None,
        description="Median call latency (middle value, or mean of two middle values for even "
        "counts). None if no calls were made.",
    )


class WorkflowIterationMetrics(BaseModel):
    """
    Operational metrics captured at the end of each workflow iteration (turn).
    Attached to EndWorkflowIterationEvent.
    """

    e2e_latency_milliseconds: Optional[int] = Field(
        default=None,
        description="End-to-end wall-clock latency of the iteration in milliseconds, "
        "from when arun() was entered to when EndWorkflowIterationEvent was produced.",
    )
    nodes_executed_count: int = Field(
        default=0,
        description="Number of node runs started during this iteration (counted via StartRunNodeEvent emissions).",
    )
    llm_call_count: int = Field(
        default=0,
        description="Number of distinct LLM model invocations during this iteration. "
        "Includes say_llm, worker_llm, and condition_evaluator_llm events. "
        "Multiple events that share the same llm_response_id "
        "(i.e., streaming chunks of one response) are counted as a single call.",
    )
    tool_call_count: int = Field(
        default=0,
        description="Number of external tool-node invocations during this iteration "
        "(e.g. HTTP request nodes, Athena nodes, SMS nodes, Google Docs nodes). "
        "Does not include in-LLM-node react-loop tool calls.",
    )
    llm_call_latency_stats: Optional[IterationCallLatencyStats] = Field(
        default=None,
        description="Latency distribution (average, min, max, median) for LLM calls in milliseconds. "
        "None if no LLM calls were made.",
    )
    tool_call_latency_stats: Optional[IterationCallLatencyStats] = Field(
        default=None,
        description="Latency distribution (average, min, max, median) for external tool-node calls in "
        "milliseconds. None if no tool calls were made.",
    )


class LLMUsageInfo(BaseModel):
    """Information about an LLM call's usage and latency."""

    response_model: Optional[str] = Field(default=None)
    named_llm_config_id: Optional[str] = Field(
        default=None, description="The ID of the named LLM configuration used for the response"
    )
    named_llm_config_name: Optional[str] = Field(
        default=None, description="The name of the named LLM configuration used for the response"
    )
    provider: Optional[str] = Field(default=None)
    ai_message_turn_id: Optional[str] = Field(default=None)
    llm_response_id: Optional[str] = Field(default=None)
    used_user_api_key: bool = Field(default=False)
    finish_reason: Optional[List[str]] = Field(default=None)
    response_latency_milliseconds: Optional[int] = Field(default=None)
    prompt_tokens: Optional[int] = Field(default=None)
    completion_tokens: Optional[int] = Field(default=None)
    total_tokens: Optional[int] = Field(default=None)
    was_streamed: Optional[bool] = Field(default=None)
    was_estimated: bool = Field(default=False)
    structured_output_retry_metadata: Optional[StructuredOutputRetryMetadata] = Field(
        default=None,
        description="Metadata about retries made to get a valid JSON output from the LLM.",
    )


class WorkflowEvent(BaseEvent):
    pass


class StartWorkflowEvent(WorkflowEvent):
    type: Literal["start_workflow"] = Field(default="start_workflow")


class EndWorkflowEvent(WorkflowEvent):
    type: Literal["end_workflow"] = Field(default="end_workflow")
    llm_token_usage: Optional[dict] = Field(default=None)
    llm_latency_stats: Optional[dict] = Field(default=None)


class EndWorkflowIterationEvent(WorkflowEvent):
    type: Literal["end_workflow_iteration"] = Field(default="end_workflow_iteration")
    iteration_number: Optional[int] = Field(default=None)
    run_input_output_pair: Optional[WorkflowRunInputOutputPair] = Field(default=None)
    iteration_metrics: Optional[WorkflowIterationMetrics] = Field(
        default=None,
        description="Operational metrics for this iteration: e2e latency, node count, LLM/tool "
        "call counts, and LLM/tool latency distribution statistics.",
    )


class WorkflowReadyForInputEvent(WorkflowEvent):
    """
    Emitted when every non-companion thread has settled (ended / busy-waiting / paused) and the
    workflow is ready to accept the next human input, EVEN IF companion threads are still running in
    the background. This is the explicit "accept input now" signal, decoupled from
    EndWorkflowIterationEvent (a per-turn accounting marker) and EndWorkflowEvent (true completion:
    all threads, companions included, have ended).
    """

    type: Literal["workflow_ready_for_input"] = Field(default="workflow_ready_for_input")
    active_companion_thread_ids: List[str] = Field(
        default_factory=list,
        description="Companion thread ids still running in the background at the moment the workflow "
        "became ready for the next user input.",
    )


class CompanionStepBoundaryEvent(WorkflowEvent):
    """
    Emitted by the background companion stepper after each discrete self-loop step for a companion
    thread. Marks a safe point at which runtime state is fully consistent and can be checkpointed.
    """

    type: Literal["companion_step_boundary"] = Field(default="companion_step_boundary")
    companion_thread_id: str = Field(description="The companion thread id that was just advanced one step.")
    attempts_completed: Optional[int] = Field(
        default=None, description="Number of self-loop attempts completed so far for this companion's current node."
    )
    deadline_epoch: Optional[float] = Field(
        default=None,
        description="Absolute wall-clock expiry deadline (epoch seconds) for the bounded self-loop, if set.",
    )
    still_active: bool = Field(
        default=True, description="Whether this companion thread still has pending background work after this step."
    )


class WaitingEvaluationBoundaryEvent(WorkflowEvent):
    """
    Emitted by the background pump after evaluating the waiting-eligible conditional edges of one
    parked thread. Marks a safe checkpoint point, mirroring ``CompanionStepBoundaryEvent``.
    """

    type: Literal["waiting_evaluation_boundary"] = Field(default="waiting_evaluation_boundary")
    parked_node_logical_id: Optional[str] = Field(
        default=None, description="The node the thread was parked at when its edges were evaluated"
    )
    edges_evaluated: int = Field(default=0, description="Number of waiting-eligible edges evaluated in this pass")
    transitioned: bool = Field(
        default=False, description="Whether an edge matched and a transition was performed in this pass"
    )
    still_waiting: bool = Field(
        default=True, description="Whether this thread is still parked waiting for user input after this pass"
    )


class StartThreadEvent(WorkflowEvent):
    type: Literal["start_thread"] = Field(default="start_thread")


class PauseThreadEvent(WorkflowEvent):
    type: Literal["pause_thread"] = Field(default="pause_thread")
    last_node_logical_id: Optional[str] = Field(default=None)


class EndThreadEvent(WorkflowEvent):
    type: Literal["end_thread"] = Field(default="end_thread")
    last_node_logical_id: Optional[str] = Field(default=None)


class NodeEvent(BaseEvent):
    origin_node_logical_id: Optional[str] = Field(default=None)
    origin_node_name: Optional[str] = Field(default=None)
    origin_node_run_id: Optional[str] = Field(default=None)


class StartRunNodeEvent(NodeEvent):
    type: Literal["start_node_run"] = Field(default="start_node_run")
    run_input: Optional[NodeRunInput] = Field(default=None)


class EndRunNodeEvent(NodeEvent):
    type: Literal["end_node_run"] = Field(default="end_node_run")
    run_output: Optional[NodeRunOutput] = Field(default=None)


class UserMessagesEvent(NodeEvent):
    type: Literal["user_messages"] = Field(default="user_messages")
    messages: List[Any] = Field(default_factory=list)


class BaseLLMNodeEvent(NodeEvent):
    type: Literal["llm"] = Field(default="llm")
    message: Optional[Any] = Field(default=None)
    llm_usage_info: LLMUsageInfo = Field(default_factory=LLMUsageInfo)


class WorkerLLMNodeEvent(BaseLLMNodeEvent):
    type: Literal["worker_llm"] = Field(default="worker_llm")  # type: ignore[assignment]


class SayLLMNodeEvent(BaseLLMNodeEvent):
    type: Literal["say_llm"] = Field(default="say_llm")  # type: ignore[assignment]


class SayStaticMessageNodeEvent(NodeEvent):
    type: Literal["say_static"] = Field(default="say_static")
    message: Optional[Any] = Field(default=None)


class ConditionEvaluatorLLMNodeEvent(BaseLLMNodeEvent):
    type: Literal["condition_evaluator_llm"] = Field(default="condition_evaluator_llm")
    destination_node_logical_id: Optional[str] = Field(
        default=None, description="The candidate destination node whose condition was evaluated."
    )
    is_condition_met: Optional[bool] = Field(
        default=None, description="Whether the evaluated condition resolved to true for this evaluator call."
    )  # type: ignore[assignment]


class DiscardedMainLLMNodeEvent(BaseLLMNodeEvent):
    type: Literal["discarded_main_llm"] = Field(default="discarded_main_llm")
    reason: Literal["global_condition_matched"] = Field(
        default="global_condition_matched",
        description="Why the main LLM response was discarded.",
    )  # type: ignore[assignment]


class EdgeEvent(BaseEvent):
    edge_name: Optional[str] = Field(default=None)
    edge_logical_id: Optional[str] = Field(default=None)
    edge_run_id: Optional[str] = Field(default=None)
    source_node_logical_id: Optional[str] = Field(default=None)
    source_node_name: Optional[str] = Field(default=None)
    destination_node_logical_id: Optional[str] = Field(default=None)
    destination_node_name: Optional[str] = Field(default=None)
    reason: Optional[str] = Field(default=None)


class DirectEdgeEvent(EdgeEvent):
    type: Literal["direct_edge"] = Field(default="direct_edge")


class SelfLoopEdgeEvent(EdgeEvent):
    type: Literal["self_loop_edge"] = Field(default="self_loop_edge")


class SelfLoopDelayEvent(EdgeEvent):
    """Emitted before waiting ``time_between_retries`` seconds ahead of a bounded self-loop retry."""

    type: Literal["self_loop_delay"] = Field(default="self_loop_delay")
    delay_seconds: float = Field(
        default=0.0, description="Number of seconds the runtime will wait before the next self-loop iteration"
    )
    attempt_number: int = Field(
        default=0, description="The upcoming self-loop attempt number (1-based, counting the first execution)"
    )


class SelfLoopExhaustedEvent(EdgeEvent):
    """
    Emitted when a bounded self-loop stops without a matching exit edge because its ``max_retries``
    or ``expiry_time`` bound was reached.
    """

    type: Literal["self_loop_exhausted"] = Field(default="self_loop_exhausted")
    outcome: Optional[SelfLoopOutcome] = Field(
        default=None, description="Why the loop stopped: 'max_retries' or 'expiry_time'"
    )
    total_attempts: int = Field(default=0, description="Total number of executions performed across the self-loop")


class NodeExpiredEvent(NodeEvent):
    """
    Emitted when an in-flight self-loop node execution is terminated because the ``expiry_time``
    wall-clock budget elapsed while it was still running.
    """

    type: Literal["node_expired"] = Field(default="node_expired")
    attempt_number: int = Field(default=0, description="The self-loop attempt number whose execution was terminated")
    reason: Optional[str] = Field(default=None, description="Human-readable reason the node execution was terminated")


class WaitingConditionMatchedEvent(EdgeEvent):
    """
    Emitted when a conditional edge's ``condition_expression`` evaluated to True *while the source
    node was parked waiting for user input* (see EvaluateWhileWaitingConfig), causing the edge to be
    taken with no user message.

    Emitted immediately before the ``ConditionalEdgeEvent`` for the same transition, so the run record
    shows both that the hop happened and why it was evaluated at that moment at all.
    """

    type: Literal["waiting_condition_matched"] = Field(default="waiting_condition_matched")
    condition_expression: Optional[str] = Field(
        default=None, description="The edge's authored condition expression, before variable substitution"
    )
    hydrated_condition_expression: Optional[str] = Field(
        default=None, description="The condition expression after all variable substitution, as actually evaluated"
    )
    trigger_mode: Optional[str] = Field(
        default=None, description="Which trigger mode armed this evaluation ('on_node_completion' | ...)"
    )
    trigger_node_logical_id: Optional[str] = Field(
        default=None,
        description="For 'on_node_completion', the trigger node whose completion armed this evaluation.",
    )
    trigger_node_completion_count: Optional[int] = Field(
        default=None,
        description="The trigger node's total completion count at the moment this evaluation was armed",
    )
    transitions_this_wait: int = Field(
        default=0, description="How many times this edge has now fired during the current uninterrupted wait"
    )
    guardrail_redirected_from_logical_id: Optional[str] = Field(
        default=None,
        description="Set only when a guardrail escalation redirected this hop: the edge's CONFIGURED "
        "destination, while destination_node_logical_id carries the escalation node actually entered.",
    )


class GuardrailEscalationEdgeEvent(EdgeEvent):
    """
    Emitted when the guardrail-strikes threshold is reached and the workflow escalates.

    On the redirect path, ``destination_node_logical_id`` is the configured escalation node. On the
    finish path (no valid escalation node configured), it is None and the workflow finishes after
    this event.
    """

    type: Literal["guardrail_escalation_edge"] = Field(default="guardrail_escalation_edge")
    num_guardrail_nodes_entered: int = Field(
        default=0,
        description="The value of the guardrail-entry counter at the point escalation was triggered",
    )


class ConditionalEdgeEvent(EdgeEvent):
    type: Literal["conditional_edge"] = Field(default="conditional_edge")
    super_node_exit_origin: Optional[str] = Field(
        default=None,
        description=(
            "If this conditional edge was projected onto an interior LLM node of an inlined "
            "super-node sub-workflow as part of a parent-authored outgoing conditional edge, this "
            "field carries the original super-node placeholder logical_id."
        ),
    )
    args_filled: dict = Field(default_factory=dict)


class ReverseConditionalEdgeEvent(ConditionalEdgeEvent):
    type: Literal["reverse_conditional_edge"] = Field(default="reverse_conditional_edge")  # type: ignore[assignment]
    global_node_logical_id: Optional[str] = Field(default=None)


class CompanionEdgeEvent(EdgeEvent):
    type: Literal["companion_edge"] = Field(default="companion_edge")


class BusyWaitEvent(BaseEvent):
    pass


class BusyWaitForUserMessageEvent(BusyWaitEvent, NodeEvent):
    type: Literal["busy_wait_for_user_message"] = Field(default="busy_wait_for_user_message")


class PauseEvent(NodeEvent):
    type: Literal["pause_event"] = Field(default="pause_event")


class ForceTransferToNodeEvent(NodeEvent):
    type: Literal["force_transfer_to_node"] = Field(default="force_transfer_to_node")
    destination_node_logical_id: Optional[str] = Field(default=None)


class AssistantResponseEvent(NodeEvent):
    type: Literal["assistant_response"] = Field(default="assistant_response")
    content: Optional[str] = Field(default=None)
    response_metadata: dict = Field(default_factory=dict)
    llm_usage_info: LLMUsageInfo = Field(default_factory=LLMUsageInfo)


class WorkflowDebugLogEvent(BaseEvent):
    type: Literal["workflow_debug_log"] = Field(default="workflow_debug_log")
    chat_history: List[str] = Field(default_factory=list)
    debug_message: Optional[str] = Field(default=None)


class WorkflowNavigationEvent(NodeEvent):
    type: Literal["workflow_navigation_message"] = Field(default="workflow_navigation_message")
    message: Optional[Any] = Field(default=None)


class WorkflowWarningEvent(BaseEvent):
    type: Literal["workflow_warning"] = Field(default="workflow_warning")
    warning_message: Optional[str] = Field(default=None)


class WorkflowErrorEvent(BaseEvent):
    type: Literal["workflow_error"] = Field(default="workflow_error")
    error_message: Optional[str] = Field(default=None)
    stack_trace: Optional[str] = Field(default=None)
    llm_token_usage: Optional[dict] = Field(default=None)
    llm_latency_stats: Optional[dict] = Field(default=None)


class WorkflowShowStateEvent(BaseEvent):
    type: Literal["workflow_show_state"] = Field(default="workflow_show_state")
    thread_id: Optional[str] = Field(default=None)
    runtime_variables: dict = Field(default_factory=dict)
    workflow_runtime_variables: dict = Field(default_factory=dict)

    @computed_field(  # type: ignore[prop-decorator]
        description=(
            "Author-facing display id for this state's thread: '0' for main, or the companion's "
            "configured thread_id. This state event carries identity in `thread_id`, so derive from "
            "it (not origin)."
        )
    )
    @property
    def thread_reference_id(self) -> Optional[str]:
        return _thread_reference_id(self.thread_id or self.origin_thread_id)


class SendSMSNodeEvent(NodeEvent):
    type: Literal["send_sms"] = Field(default="send_sms")
    status: Optional[str] = Field(default=None)
    sent_message: Optional[str] = Field(default=None)
    destination_phone_number: Optional[str] = Field(default=None)


class GoogleDocsCreateDocumentNodeEvent(NodeEvent):
    type: Literal["google_docs_create_document"] = Field(default="google_docs_create_document")
    status: Optional[str] = Field(default=None)
    document_id: Optional[str] = Field(default=None)
    document_url: Optional[str] = Field(default=None)
    document_title: Optional[str] = Field(default=None)


class GoogleDocsGetDocumentNodeEvent(NodeEvent):
    type: Literal["google_docs_get_document"] = Field(default="google_docs_get_document")
    status: Optional[str] = Field(default=None)
    document_id: Optional[str] = Field(default=None)
    document_content: Optional[str] = Field(default=None)


class GoogleDocsUpdateDocumentNodeEvent(NodeEvent):
    type: Literal["google_docs_update_document"] = Field(default="google_docs_update_document")
    status: Optional[str] = Field(default=None)
    document_id: Optional[str] = Field(default=None)
    document_url: Optional[str] = Field(default=None)
    updated_content: Optional[str] = Field(default=None)


class StartConversationNodeEvent(NodeEvent):
    type: Literal["start_conversation"] = Field(default="start_conversation")
    conversation_status: Optional[str] = Field(default=None)
    conversation_id: Optional[str] = Field(default=None)


class EndConversationNodeEvent(NodeEvent):
    type: Literal["end_conversation"] = Field(default="end_conversation")
    processed_transcript: Optional[str] = Field(default=None)


class HttpRequestNodeEvent(NodeEvent):
    type: Literal["http_request"] = Field(default="http_request")
    curl_command: Optional[str] = Field(default=None)
    status_code: Optional[int] = Field(default=None)
    response_body: Optional[dict] = Field(default=None)
    error: Optional[str] = Field(default=None)


class AthenaNodeEvent(NodeEvent):
    type: Literal["athena"] = Field(default="athena")
    status_code: Optional[int] = Field(default=None)
    response_body: Optional[dict] = Field(default=None)


Event = Annotated[
    StartWorkflowEvent | EndWorkflowEvent | EndWorkflowIterationEvent | WorkflowReadyForInputEvent | CompanionStepBoundaryEvent | WaitingEvaluationBoundaryEvent | StartThreadEvent | PauseThreadEvent | EndThreadEvent | StartRunNodeEvent | EndRunNodeEvent | UserMessagesEvent | BusyWaitForUserMessageEvent | PauseEvent | ForceTransferToNodeEvent | WorkerLLMNodeEvent | SayLLMNodeEvent | ConditionEvaluatorLLMNodeEvent | DiscardedMainLLMNodeEvent | SayStaticMessageNodeEvent | AssistantResponseEvent | WorkflowDebugLogEvent | WorkflowNavigationEvent | WorkflowWarningEvent | WorkflowErrorEvent | WorkflowShowStateEvent | StartConversationNodeEvent | EndConversationNodeEvent | SendSMSNodeEvent | GoogleDocsCreateDocumentNodeEvent | GoogleDocsGetDocumentNodeEvent | GoogleDocsUpdateDocumentNodeEvent | HttpRequestNodeEvent | AthenaNodeEvent | DirectEdgeEvent | SelfLoopEdgeEvent | SelfLoopDelayEvent | SelfLoopExhaustedEvent | NodeExpiredEvent | ReverseConditionalEdgeEvent | ConditionalEdgeEvent | WaitingConditionMatchedEvent | CompanionEdgeEvent | GuardrailEscalationEdgeEvent,
    Field(discriminator="type"),
]


_EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(payload: Any) -> BaseEvent:
    """Parse a raw event dict into the appropriate typed event class.

    Unknown discriminator values fall back to a generic :class:`BaseEvent`
    with ``extra="allow"`` semantics so forward compatibility is preserved.
    """
    if isinstance(payload, BaseEvent):
        return payload
    try:
        return _EVENT_ADAPTER.validate_python(payload)
    except Exception:  # noqa: BLE001 - forward-compat fallback for unknown discriminator values
        return BaseEvent.model_validate(payload)


def should_persist_background_event(event: Any) -> bool:
    """
    Whether an event produced by a background pump is worth keeping in the persisted run record.

    A ``WaitingEvaluationBoundaryEvent`` that produced no transition is pure per-tick bookkeeping:
    while a thread is parked with a pending evaluation it recurs on EVERY background pass, so keeping
    it would grow the run record without bound. Drivers should still forward it on the wire -- it is
    the "state advanced, safe to re-checkpoint" signal -- but it does not belong in run history. A
    boundary event that DID transition is kept, because it records a real hop.
    """
    if isinstance(event, WaitingEvaluationBoundaryEvent):
        return event.transitioned
    return True


class WorkflowEventsArray(BaseModel):
    """A simple container for an array of workflow events."""

    events: List[Event] = Field(default_factory=list)
