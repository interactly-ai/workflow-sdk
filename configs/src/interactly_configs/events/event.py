"""Runtime event models for the Interactly workflow engine.

This module mirrors the event hierarchy emitted by the server-side workflow
runtime.  Message-carrying fields use ``Any`` instead of langchain types so
this package has no runtime dependency on ``langchain_core``; events arrive
as plain dicts and round-trip cleanly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, List, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter

from interactly_configs.comment import CommentConfig
from interactly_configs.nodes.node_unions import NodeRunInput, NodeRunOutput
from interactly_configs.workflow_run import WorkflowRunInputOutputPair


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


class LLMUsageInfo(BaseModel):
    """Information about an LLM call's usage and latency."""

    response_model: Optional[str] = Field(default=None)
    provider: Optional[str] = Field(default=None)
    ai_message_turn_id: Optional[str] = Field(default=None)
    llm_response_id: Optional[str] = Field(default=None)
    used_user_api_key: bool = Field(default=False)
    finish_reason: Optional[list[str]] = Field(default=None)
    response_latency_milliseconds: Optional[int] = Field(default=None)
    prompt_tokens: Optional[int] = Field(default=None)
    completion_tokens: Optional[int] = Field(default=None)
    total_tokens: Optional[int] = Field(default=None)
    was_streamed: Optional[bool] = Field(default=None)
    was_estimated: bool = Field(default=False)


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
    messages: list[Any] = Field(default_factory=list)


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
    type: Literal["condition_evaluator_llm"] = Field(default="condition_evaluator_llm")  # type: ignore[assignment]


class DiscardedMainLLMNodeEvent(BaseLLMNodeEvent):
    type: Literal["discarded_main_llm"] = Field(default="discarded_main_llm")  # type: ignore[assignment]


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


class ConditionalEdgeEvent(EdgeEvent):
    type: Literal["conditional_edge"] = Field(default="conditional_edge")
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
    Union[
        StartWorkflowEvent,
        EndWorkflowEvent,
        EndWorkflowIterationEvent,
        StartThreadEvent,
        PauseThreadEvent,
        EndThreadEvent,
        StartRunNodeEvent,
        EndRunNodeEvent,
        UserMessagesEvent,
        BusyWaitForUserMessageEvent,
        PauseEvent,
        ForceTransferToNodeEvent,
        WorkerLLMNodeEvent,
        SayLLMNodeEvent,
        ConditionEvaluatorLLMNodeEvent,
        DiscardedMainLLMNodeEvent,
        SayStaticMessageNodeEvent,
        AssistantResponseEvent,
        WorkflowDebugLogEvent,
        WorkflowNavigationEvent,
        WorkflowWarningEvent,
        WorkflowErrorEvent,
        WorkflowShowStateEvent,
        StartConversationNodeEvent,
        EndConversationNodeEvent,
        SendSMSNodeEvent,
        GoogleDocsCreateDocumentNodeEvent,
        GoogleDocsGetDocumentNodeEvent,
        GoogleDocsUpdateDocumentNodeEvent,
        HttpRequestNodeEvent,
        AthenaNodeEvent,
        DirectEdgeEvent,
        SelfLoopEdgeEvent,
        ReverseConditionalEdgeEvent,
        ConditionalEdgeEvent,
        CompanionEdgeEvent,
    ],
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


class WorkflowEventsArray(BaseModel):
    """A simple container for an array of workflow events."""

    events: list[Event] = Field(default_factory=list)
