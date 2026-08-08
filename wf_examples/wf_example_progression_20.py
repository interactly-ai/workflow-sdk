import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 20 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_20.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_20.py
"""

import asyncio
import time
from typing import Optional

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import PromptConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowCommand, WorkflowRunInput
from interactly.runtime.events import (  # Workflow-level events
    AssistantResponseEvent,
    AthenaNodeEvent,
    BusyWaitForUserMessageEvent,
    CompanionEdgeEvent,
    ConditionalEdgeEvent,
    DirectEdgeEvent,
    EndConversationNodeEvent,
    EndRunNodeEvent,
    EndThreadEvent,
    EndWorkflowEvent,
    EndWorkflowIterationEvent,
    ForceTransferToNodeEvent,
    GoogleDocsCreateDocumentNodeEvent,
    GoogleDocsGetDocumentNodeEvent,
    GoogleDocsUpdateDocumentNodeEvent,
    HttpRequestNodeEvent,
    PauseEvent,
    PauseThreadEvent,
    ReverseConditionalEdgeEvent,
    SayLLMNodeEvent,
    SayStaticMessageNodeEvent,
    SelfLoopEdgeEvent,
    SendSMSNodeEvent,
    StartConversationNodeEvent,
    StartRunNodeEvent,
    StartThreadEvent,
    StartWorkflowEvent,
    UserMessagesEvent,
    WorkerLLMNodeEvent,
    WorkflowDebugLogEvent,
    WorkflowErrorEvent,
    WorkflowNavigationEvent,
    WorkflowShowStateEvent,
    WorkflowWarningEvent,
)
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX

# ──────────────────────────────────────────────────────────────────────────────
# COMPLETE EVENT CATALOG
# ──────────────────────────────────────────────────────────────────────────────
#
# All events inherit from BaseEvent which provides:
#   - logical_id: str          — unique UUID for this event
#   - timestamp: float         — UTC timestamp (seconds since epoch)
#   - origin_thread_id: str    — ID of the thread that emitted this event
#   - comments: list           — optional CommentConfig items
#   - interrupted: bool        — True if this event was interrupted during live voice
#
# Node events additionally provide:
#   - origin_node_logical_id: str  — logical ID of the emitting node
#   - origin_node_name: str        — human-readable name of the emitting node
#   - origin_node_run_id: str      — unique ID for this specific node execution
#
# ─── WORKFLOW-LEVEL EVENTS ────────────────────────────────────────────────────
#
# StartWorkflowEvent         — Emitted once when the workflow starts its first turn.
#   type: "start_workflow"
#   (no extra fields beyond BaseEvent)
#
# EndWorkflowEvent           — Emitted once when the workflow reaches a terminal state.
#   type: "end_workflow"
#   llm_token_usage: dict    — Aggregated token counts for the entire run
#   llm_latency_stats: dict  — Aggregated LLM latency stats for the entire run
#
# EndWorkflowIterationEvent  — Emitted at the end of EACH turn (each arun() call).
#   type: "end_workflow_iteration"
#   iteration_number: int    — 1-based counter of the iteration that just completed
#   run_input_output_pair    — WorkflowRunInputOutputPair with input + output for this turn
#
# StartThreadEvent           — Emitted when a new execution thread is created.
#   type: "start_thread"
#
# EndThreadEvent             — Emitted when a thread finishes execution.
#   type: "end_thread"
#   last_node_logical_id     — Logical ID of the last node that ran in this thread
#
# PauseThreadEvent           — Emitted when a thread is paused (after a PauseEvent).
#   type: "pause_thread"
#   last_node_logical_id     — Logical ID of the node that was running when paused
#
# ─── NODE-LEVEL EVENTS ────────────────────────────────────────────────────────
#
# StartRunNodeEvent          — Emitted at the START of every node execution.
#   type: "start_node_run"
#   run_input: NodeRunInput  — The input provided to this node run
#
# EndRunNodeEvent            — Emitted at the END of every node execution.
#   type: "end_node_run"
#   run_output: NodeRunOutput — The output produced by this node run
#                              (type field distinguishes which node type produced it)
#
# UserMessagesEvent          — Emitted when user messages are appended to a thread.
#   type: "user_messages"
#   messages: list[AnyMessage]
#
# BusyWaitForUserMessageEvent — Emitted when a node is waiting for user input.
#   type: "busy_wait_for_user_message"
#   Break your arun() loop here and resume when user sends the next message.
#
# PauseEvent                 — Emitted by a node requesting a programmatic pause.
#   type: "pause_event"
#   (no extra fields; triggers PauseThreadEvent from the runtime)
#
# ForceTransferToNodeEvent   — Emitted to redirect execution to a specific node.
#   type: "force_transfer_to_node"
#   destination_node_logical_id: str
#
# ─── LLM / OUTPUT EVENTS ──────────────────────────────────────────────────────
#
# WorkerLLMNodeEvent         — Emitted by background LLM nodes (workers, evaluators).
#   type: "worker_llm"
#   message: AnyMessage      — The individual LLM step message (may be partial)
#   llm_usage_info: LLMUsageInfo
#
# SayLLMNodeEvent            — Emitted by conversational LLM nodes (SayLLMNodeConfig).
#   type: "say_llm"
#   message: AnyMessage      — The individual LLM step message (may be partial)
#   llm_usage_info: LLMUsageInfo
#
# SayStaticMessageNodeEvent  — Emitted by nodes sending a predefined static response.
#   type: "say_static"
#   message: AIMessage       — The static AI message
#
# AssistantResponseEvent     — Emitted when the assistant's complete response is ready.
#   type: "assistant_response"
#   content: str             — The full text of the assistant's response
#   response_metadata: dict  — Copied from the AI message's response_metadata
#   llm_usage_info: LLMUsageInfo
#   THIS IS THE MAIN EVENT FOR CONVERSATIONAL OUTPUT — use this to drive the UI/voice.
#
# ─── WORKFLOW DIAGNOSTICS ─────────────────────────────────────────────────────
#
# WorkflowNavigationEvent    — Emitted when a navigation message is appended to history.
#   type: "workflow_navigation_message"
#   message: AIMessage       — The artificial navigation memo
#
# WorkflowDebugLogEvent      — Emitted in debug mode with chat history + debug message.
#   type: "workflow_debug_log"
#   chat_history: list[str]
#   debug_message: str
#
# WorkflowWarningEvent       — Emitted for non-fatal warnings.
#   type: "workflow_warning"
#   warning_message: str
#
# WorkflowErrorEvent         — Emitted when an unhandled error occurs.
#   type: "workflow_error"
#   error_message: str
#   stack_trace: str
#   llm_token_usage: dict
#   llm_latency_stats: dict
#
# WorkflowShowStateEvent     — Emitted to expose current runtime variable state.
#   type: "workflow_show_state"
#   thread_id: str
#   runtime_variables: dict  — Thread-scoped runtime variables
#   workflow_runtime_variables: dict — Global workflow runtime variables
#
# ─── CONVERSATION NODE EVENTS ─────────────────────────────────────────────────
#
# StartConversationNodeEvent — Emitted by nodes that start outbound conversations.
#   type: "start_conversation"
#   conversation_status: str  — "initiated" / "in-progress" / "completed" / "failed"
#   conversation_id: str
#
# EndConversationNodeEvent   — Emitted by nodes that end conversations.
#   type: "end_conversation"
#   processed_transcript: str — The final processed transcript
#
# ─── COMMUNICATION NODE EVENTS ────────────────────────────────────────────────
#
# SendSMSNodeEvent           — Emitted by SMS-sending nodes.
#   type: "send_sms"
#   status: str
#   sent_message: str
#   destination_phone_number: str
#
# ─── GOOGLE WORKSPACE EVENTS ──────────────────────────────────────────────────
#
# GoogleDocsCreateDocumentNodeEvent — type: "google_docs_create_document"
#   status, document_id, document_url, document_title
#
# GoogleDocsGetDocumentNodeEvent    — type: "google_docs_get_document"
#   status, document_id, document_content
#
# GoogleDocsUpdateDocumentNodeEvent — type: "google_docs_update_document"
#   status, document_id, document_url, updated_content
#
# ─── REST API EVENTS ──────────────────────────────────────────────────────────
#
# HttpRequestNodeEvent       — Emitted by HttpRequestNodeConfig nodes.
#   type: "http_request"
#   curl_command: str        — The curl equivalent of the request (for debugging)
#   status_code: int
#   response_body: dict
#   error: str
#
# ─── ATHENA INTEGRATION EVENTS ────────────────────────────────────────────────
#
# AthenaNodeEvent            — Emitted by Athena EHR integration nodes.
#   type: "athena"
#   status_code: int
#   response_body: dict
#
# ─── EDGE EVENTS ──────────────────────────────────────────────────────────────
# All edge events inherit from EdgeEvent which has:
#   source_node_logical_id, source_node_name,
#   destination_node_logical_id, destination_node_name, reason
#
# DirectEdgeEvent            — type: "direct_edge"
# SelfLoopEdgeEvent          — type: "self_loop_edge"
# ConditionalEdgeEvent       — type: "conditional_edge"
#   args_filled: dict        — Condition arguments that caused this edge to fire
# ReverseConditionalEdgeEvent — type: "reverse_conditional_edge"
#   global_node_logical_id   — The global node from which reverse navigation came
# CompanionEdgeEvent         — type: "companion_edge"
# ──────────────────────────────────────────────────────────────────────────────


def build_assistant_workflow():
    """Build a minimal workflow to drive the event demonstration."""
    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=100,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 20: Full Event Handling Reference",
        description=f"""
        A minimal workflow designed to demonstrate every possible event type.
        Use this file as your copy-paste template for production service loops.
        See more details at {google_docs_md_link}
        """,
    )

    greeting_node = SayLLMNodeConfig(
        name="Greeting",
        is_start=True,
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(
            prompt=GLOBAL_PROMPT_PREFIX + "Say hello in 5 words or less." + GLOBAL_PROMPT_SUFFIX
        ),
        llms_config=openai_llm_config,
    )

    assistant_node = SayLLMNodeConfig(
        name="Assistant",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(
            prompt=GLOBAL_PROMPT_PREFIX
            + "Reply in 1 sentence, then ask if there is anything else."
            + GLOBAL_PROMPT_SUFFIX
        ),
        llms_config=openai_llm_config,
    )

    return WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[greeting_node, assistant_node],
        edge_configs=[
            DirectEdgeConfig(
                name="G→A",
                source_node_logical_id=greeting_node.logical_id,
                destination_node_logical_id=assistant_node.logical_id,
            ),
        ],
    )


def handle_event_exhaustively(event) -> bool:
    """
    Handle every possible event type.

    Returns True if the caller should break the arun() loop (BusyWaitForUserMessageEvent).

    Copy this function into your service layer and replace each print statement
    with your real handler logic (send to telephony, write to DB, emit metrics, etc.).
    """
    node_name: Optional[str] = getattr(event, "origin_node_name", None) or "runtime"

    # ── CONVERSATIONAL OUTPUT — the most important event ──────────────────────
    if isinstance(event, AssistantResponseEvent):
        # THE primary output event. Send this text to the user (TTS, chat UI, etc.)
        print(f"  🤖 [AssistantResponseEvent] content: {event.content!r}")
        print(f"     llm_usage_info.total_tokens: {event.llm_usage_info.total_tokens}")
        return False

    # ── USER INPUT GATE ────────────────────────────────────────────────────────
    elif isinstance(event, BusyWaitForUserMessageEvent):
        # Stop draining the current arun() and wait for the next user message.
        # Resume by calling arun() again with the user's message.
        print(f"  ⏳ [BusyWaitForUserMessageEvent] [{node_name}] waiting for user input")
        return True

    # ── WORKFLOW LIFECYCLE ─────────────────────────────────────────────────────
    elif isinstance(event, StartWorkflowEvent):
        print(f"  🟢 [StartWorkflowEvent] thread: {event.origin_thread_id}")

    elif isinstance(event, EndWorkflowEvent):
        tokens = (event.llm_token_usage or {}).get("total_tokens", "n/a")
        print(f"  🏁 [EndWorkflowEvent] total_tokens: {tokens}")

    elif isinstance(event, EndWorkflowIterationEvent):
        print(f"  🔚 [EndWorkflowIterationEvent] iteration #{event.iteration_number} done")

    elif isinstance(event, StartThreadEvent):
        print(f"  ➡  [StartThreadEvent] thread: {event.origin_thread_id}")

    elif isinstance(event, EndThreadEvent):
        print(f"  ⏹  [EndThreadEvent] thread: {event.origin_thread_id} last_node: {event.last_node_logical_id}")

    elif isinstance(event, PauseThreadEvent):
        print(f"  ⏸  [PauseThreadEvent] thread: {event.origin_thread_id} last_node: {event.last_node_logical_id}")

    # ── NODE LIFECYCLE ─────────────────────────────────────────────────────────
    elif isinstance(event, StartRunNodeEvent):
        # Fired at the start of every node run. Good for timing / tracing.
        print(f"  ▶  [StartRunNodeEvent] [{node_name}]")

    elif isinstance(event, EndRunNodeEvent):
        # Fired at the end of every node run. run_output contains the node's result.
        out_type = event.run_output.type if event.run_output else "None"
        print(f"  ⏹  [EndRunNodeEvent] [{node_name}] output_type: {out_type}")

    elif isinstance(event, UserMessagesEvent):
        # Fired when user messages are appended to the thread history.
        msg_count = len(event.messages)
        print(f"  👤 [UserMessagesEvent] {msg_count} message(s) appended")

    elif isinstance(event, PauseEvent):
        print(f"  ⏸  [PauseEvent] [{node_name}] node requested pause")

    elif isinstance(event, ForceTransferToNodeEvent):
        print(f"  ↪  [ForceTransferToNodeEvent] → {event.destination_node_logical_id}")

    # ── LLM STREAMING EVENTS ──────────────────────────────────────────────────
    elif isinstance(event, SayLLMNodeEvent):
        # Intermediate streaming message from a SayLLMNodeConfig node.
        # In a voice pipeline, you can start streaming TTS from these partial chunks.
        content = getattr(event.message, "content", "") or ""
        print(f"  💬 [SayLLMNodeEvent] [{node_name}] chunk: {str(content)[:40]!r}")

    elif isinstance(event, WorkerLLMNodeEvent):
        # Intermediate message from a background LLM (worker, evaluator).
        content = getattr(event.message, "content", "") or ""
        print(f"  🔍 [WorkerLLMNodeEvent] [{node_name}] chunk: {str(content)[:40]!r}")

    elif isinstance(event, SayStaticMessageNodeEvent):
        # A static (pre-defined) message was sent to the user.
        content = getattr(event.message, "content", "") if event.message else ""
        print(f"  📢 [SayStaticMessageNodeEvent] [{node_name}]: {content!r}")

    # ── WORKFLOW DIAGNOSTICS ───────────────────────────────────────────────────
    elif isinstance(event, WorkflowNavigationEvent):
        # Artificial AI navigation message appended for LLM context.
        content = getattr(event.message, "content", "") if event.message else ""
        print(f"  🗺  [WorkflowNavigationEvent] [{node_name}]: {str(content)[:80]!r}")

    elif isinstance(event, WorkflowDebugLogEvent):
        print(f"  🐛 [WorkflowDebugLogEvent] {event.debug_message}")

    elif isinstance(event, WorkflowWarningEvent):
        print(f"  ⚠️  [WorkflowWarningEvent] {event.warning_message}")

    elif isinstance(event, WorkflowErrorEvent):
        print(f"  ❌ [WorkflowErrorEvent] {event.error_message}")

    elif isinstance(event, WorkflowShowStateEvent):
        print(f"  📊 [WorkflowShowStateEvent] thread: {event.thread_id}")
        print(f"     runtime_variables: {event.runtime_variables}")

    # ── COMMUNICATION NODE EVENTS ──────────────────────────────────────────────
    elif isinstance(event, SendSMSNodeEvent):
        print(f"  📱 [SendSMSNodeEvent] to: {event.destination_phone_number} status: {event.status}")

    # ── CONVERSATION NODE EVENTS ───────────────────────────────────────────────
    elif isinstance(event, StartConversationNodeEvent):
        print(f"  📞 [StartConversationNodeEvent] id: {event.conversation_id} status: {event.conversation_status}")

    elif isinstance(event, EndConversationNodeEvent):
        print(f"  📵 [EndConversationNodeEvent] transcript: {str(event.processed_transcript or '')[:80]}")

    # ── GOOGLE WORKSPACE EVENTS ────────────────────────────────────────────────
    elif isinstance(event, GoogleDocsCreateDocumentNodeEvent):
        print(f"  📄 [GoogleDocsCreateDocumentNodeEvent] doc_id: {event.document_id} status: {event.status}")

    elif isinstance(event, GoogleDocsGetDocumentNodeEvent):
        print(f"  📄 [GoogleDocsGetDocumentNodeEvent] doc_id: {event.document_id} status: {event.status}")

    elif isinstance(event, GoogleDocsUpdateDocumentNodeEvent):
        print(f"  📄 [GoogleDocsUpdateDocumentNodeEvent] doc_id: {event.document_id} status: {event.status}")

    # ── REST API EVENTS ────────────────────────────────────────────────────────
    elif isinstance(event, HttpRequestNodeEvent):
        print(f"  🌐 [HttpRequestNodeEvent] [{node_name}] status_code: {event.status_code} error: {event.error}")

    # ── ATHENA EVENTS ──────────────────────────────────────────────────────────
    elif isinstance(event, AthenaNodeEvent):
        print(f"  🏥 [AthenaNodeEvent] [{node_name}] status_code: {event.status_code}")

    # ── EDGE EVENTS ────────────────────────────────────────────────────────────
    elif isinstance(event, ReverseConditionalEdgeEvent):
        print(f"  ↩  [ReverseConditionalEdgeEvent] from global node: {event.global_node_logical_id}")

    elif isinstance(event, ConditionalEdgeEvent):
        print(f"  ↪  [ConditionalEdgeEvent] → {event.destination_node_name} args: {event.args_filled}")

    elif isinstance(event, CompanionEdgeEvent):
        print(f"  🔀 [CompanionEdgeEvent] → {event.destination_node_name}")

    elif isinstance(event, DirectEdgeEvent):
        print(f"  →  [DirectEdgeEvent] {event.source_node_name} → {event.destination_node_name}")

    elif isinstance(event, SelfLoopEdgeEvent):
        print(f"  ↺  [SelfLoopEdgeEvent] [{node_name}] loops back")

    # ── CATCH-ALL ──────────────────────────────────────────────────────────────
    else:
        print(f"  ❓ [UNKNOWN EVENT] type: {getattr(event, 'type', type(event).__name__)}")

    return False


async def run():
    """
    Full-verbose event loop demonstrating every event type.
    Run this against a live OpenAI endpoint to see real events flowing through.
    """
    workflow = build_assistant_workflow()
    # The workflow seeds these on upload; read them back so each turn sends the same values.
    dynamic_variables = workflow.workflow_config.miscellaneous.get("default_dynamic_variables", {})
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    inputs_queue = [
        "What's my deductible status?",
        "quit",
    ]
    input_idx = 0

    workflow_input = WorkflowRunInput(
        command=WorkflowCommand.START,
        messages=[],
        dynamic_variables={},
        runtime_variables={},
    )

    start_time = time.time()
    iteration_num = 0

    while True:
        iteration_num += 1
        print(f"\n{'─' * 60}")
        print(f"TURN {iteration_num} | command={workflow_input.command.value}")
        print(f"{'─' * 60}")

        should_break = False
        async for event in workflow_runtime.arun(workflow_input):
            should_break = handle_event_exhaustively(event)
            if should_break:
                break

        if should_break:
            user_input = inputs_queue[input_idx] if input_idx < len(inputs_queue) else "quit"
            input_idx += 1

            if user_input.strip().lower() == "quit":
                print("\n🛑 Conversation ended by user.")
                break

            print(f"\n👤 User sends: {user_input!r}")
            workflow_input = WorkflowRunInput(
                command=WorkflowCommand.DATA,
                messages=[HumanMessage(content=user_input)],
                dynamic_variables={},
                runtime_variables={},
            )
        else:
            print("\n✅ Workflow reached terminal state.")
            break

    elapsed = time.time() - start_time
    print(f"\n⏱️  Total run time: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(run())
