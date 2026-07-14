import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 19 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_19.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_19.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import PromptConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowCommand, WorkflowRunInput
from interactly.runtime.events import (
    AssistantResponseEvent,
    BusyWaitForUserMessageEvent,
    EndRunNodeEvent,
    EndWorkflowEvent,
    EndWorkflowIterationEvent,
    PauseEvent,
    PauseThreadEvent,
    StartRunNodeEvent,
    WorkerLLMNodeEvent,
    WorkflowErrorEvent,
)
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX

# ──────────────────────────────────────────────────────────────────────────────
# WORKFLOWCOMMAND — Complete Reference
# ──────────────────────────────────────────────────────────────────────────────
#
# WorkflowCommand controls the operation mode for each WorkflowRunInput call.
# It is set on WorkflowRunInput.command (default: WorkflowCommand.START).
#
# WorkflowCommand.START  — Start a fresh workflow run (first call only).
#                          The runtime initialises thread state and runs from
#                          the start node.
#
# WorkflowCommand.DATA   — Send a new user message to a running workflow.
#                          Used on every subsequent turn after START.
#                          The runtime appends the message and resumes from the
#                          last waiting position.
#
# WorkflowCommand.RESUME — Explicitly resume a PAUSED workflow.
#                          Similar to DATA but semantically signals intent to
#                          resume after a programmatic pause (not just waiting
#                          for user input).
#
# WorkflowCommand.PAUSE  — Signal the runtime to pause the workflow after the
#                          current node completes. The runtime emits PauseEvent
#                          + PauseThreadEvent and stops execution. The state is
#                          preserved in the WorkflowRuntime instance so it can
#                          be resumed later.
#
# WorkflowCommand.STOP   — Cancel the workflow run. The runtime cancels any
#                          in-flight async tasks and terminates the generator.
#                          Typically implemented by cancelling the asyncio Task
#                          that drives the arun() generator.
#
# Service-layer pseudo-code pattern:
#
#   runtime = WorkflowRuntime.from_config(workflow)
#
#   # Turn 1: Start
#   async for event in runtime.arun(WorkflowRunInput(command=WorkflowCommand.START, ...)):
#       handle(event)  # breaks at BusyWaitForUserMessageEvent
#
#   # Turn 2: Send user message
#   async for event in runtime.arun(WorkflowRunInput(command=WorkflowCommand.DATA, messages=[user_msg], ...)):
#       handle(event)
#
#   # Programmatic pause (e.g. supervisor review required):
#   async for event in runtime.arun(WorkflowRunInput(command=WorkflowCommand.PAUSE, ...)):
#       handle(event)  # will emit PauseEvent + PauseThreadEvent then stop
#
#   # Later: resume
#   async for event in runtime.arun(WorkflowRunInput(command=WorkflowCommand.RESUME, ...)):
#       handle(event)
#
#   # Cancel the run entirely (e.g. caller hung up):
#   arun_task.cancel()  # STOP is implemented by cancelling the asyncio Task
# ──────────────────────────────────────────────────────────────────────────────


def build_assistant_workflow():
    """
    Build a simple multi-turn workflow for demonstrating lifecycle events.

    Key concepts introduced in this example:

    1. WorkflowCommand enum — START, DATA, RESUME, PAUSE, STOP and when to use each.

    2. Lifecycle events — the full set of non-conversational events the runtime emits:
       - StartRunNodeEvent: fired at the start of each node run
       - EndRunNodeEvent: fired at the end of each node run
       - EndWorkflowIterationEvent: fired after each user-turn's iteration completes
       - EndWorkflowEvent: fired when the entire workflow ends (terminal state)
       - PauseEvent: fired by a node when it requests a pause
       - PauseThreadEvent: fired by the runtime when a thread is actually paused
       - WorkflowErrorEvent: fired when an unhandled error occurs

    3. WorkflowRunInput.command — set the command for each arun() call to control flow.

    4. Service-layer pattern — the same WorkflowRuntime instance is kept alive across
       multiple arun() calls; state is preserved in the runtime between turns.
    """

    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=200,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 19: Advanced WorkflowCommands and Lifecycle Events",
        description=f"""
        Demonstrates WorkflowCommand (START, DATA, RESUME, PAUSE, STOP) and the full set
        of workflow lifecycle events (PauseEvent, PauseThreadEvent, EndWorkflowEvent,
        EndWorkflowIterationEvent, StartRunNodeEvent, EndRunNodeEvent, WorkflowErrorEvent).

        See more details at {google_docs_md_link}
        """,
    )

    GREETING_PROMPT = """
    Greet the user briefly. Ask one question: what brings them to Cigna support today?
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Greets and asks for the reason",
        is_start=True,
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    ASSISTANT_PROMPT = """
    You are a Cigna member support assistant. Continue the conversation with the member.
    Be concise — respond in 1-2 sentences. After responding, ask if there is anything else.
    """
    assistant_node = SayLLMNodeConfig(
        name="Assistant Node",
        description="Main support assistant with self-loop",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASSISTANT_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    edge_greeting_to_assistant = DirectEdgeConfig(
        name="Greeting → Assistant",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=assistant_node.logical_id,
    )

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[greeting_node, assistant_node],
        edge_configs=[edge_greeting_to_assistant],
    )

    return workflow


def handle_all_events(event, _iteration_num: int) -> bool:
    """
    Handle every event type the runtime can emit.

    Returns True if the loop should break (end of this iteration's turn).

    This function is a reference for building a production service loop.
    In a real service, each branch would call the appropriate handler
    (e.g., send audio to the telephony bridge, update DB, emit metrics).
    """
    node_name = getattr(event, "origin_node_name", None) or "runtime"

    # ── Conversational events ──────────────────────────────────────────────────
    if isinstance(event, BusyWaitForUserMessageEvent):
        print(f"  ⏳ BusyWaitForUserMessageEvent — [{node_name}] waiting for user input")
        return True  # Signal caller to collect user input and re-invoke arun()

    elif isinstance(event, AssistantResponseEvent):
        print(f"  🤖 AssistantResponseEvent — [{node_name}]: {event.content}")

    # ── Worker LLM events (background reasoning, evaluators) ──────────────────
    elif isinstance(event, WorkerLLMNodeEvent):
        content = getattr(event.message, "content", "") if event.message else ""
        print(f"  🔍 WorkerLLMNodeEvent — [{node_name}]: {str(content)[:80]}")

    # ── Node lifecycle events ──────────────────────────────────────────────────
    elif isinstance(event, StartRunNodeEvent):
        # Fired at the START of every node run.
        # Useful for: timing node execution, logging node entry, UI "thinking" indicator.
        print(f"  ▶  StartRunNodeEvent — [{node_name}]")

    elif isinstance(event, EndRunNodeEvent):
        # Fired at the END of every node run.
        # Useful for: timing node execution, auditing node outputs, debugging.
        output_type = event.run_output.type if event.run_output else "None"
        print(f"  ⏹  EndRunNodeEvent — [{node_name}] output type: {output_type}")

    # ── Pause events ───────────────────────────────────────────────────────────
    elif isinstance(event, PauseEvent):
        # Fired by a NODE when it requests a pause (e.g. for human review).
        # Note: most nodes do NOT emit this — it's a deliberate programmatic pause.
        print(f"  ⏸  PauseEvent — [{node_name}] node requested pause")

    elif isinstance(event, PauseThreadEvent):
        # Fired by the RUNTIME after it honours a pause request.
        # The thread is now paused; state is preserved in the WorkflowRuntime instance.
        # To resume: call arun(WorkflowRunInput(command=WorkflowCommand.RESUME, ...))
        thread_id = event.origin_thread_id if hasattr(event, "origin_thread_id") else "?"
        last_node = event.last_node_logical_id or "?"
        print(f"  ⏸  PauseThreadEvent — thread {thread_id} paused after node {last_node}")

    # ── Workflow-level lifecycle events ────────────────────────────────────────
    elif isinstance(event, EndWorkflowIterationEvent):
        # Fired at the end of EACH TURN (each arun() call).
        # Contains a WorkflowRunInputOutputPair with the full input + output for this turn.
        # Useful for: persisting turn data to DB, incrementing iteration counters.
        itr = event.iteration_number
        print(f"  🔚 EndWorkflowIterationEvent — iteration #{itr} complete")
        # event.run_input_output_pair contains run_input + run_output for this turn

    elif isinstance(event, EndWorkflowEvent):
        # Fired ONCE when the workflow reaches a terminal state (all threads ended).
        # Contains aggregated LLM token usage and latency stats for the entire run.
        token_info = event.llm_token_usage or {}
        total_tokens = token_info.get("total_tokens", "unknown")
        print(f"  🏁 EndWorkflowEvent — workflow complete. Total tokens used: {total_tokens}")

    # ── Error events ───────────────────────────────────────────────────────────
    elif isinstance(event, WorkflowErrorEvent):
        # Fired when an unhandled error occurs.
        print(f"  ❌ WorkflowErrorEvent — {event.error_message}")

    return False  # Continue the loop


async def run():
    """
    Demonstrates a full multi-turn conversation with verbose lifecycle event logging.

    Unlike previous examples that only handled BusyWaitForUserMessageEvent and
    AssistantResponseEvent, this loop handles EVERY event the runtime can emit.
    """
    workflow = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    inputs_queue = [
        "I have a question about my deductible",
        "How much have I met so far this year?",
        "quit",
    ]
    input_idx = 0

    # ── WorkflowCommand.START — first invocation ────────────────────────────
    # Use WorkflowCommand.START on the very first arun() call.
    # For all subsequent turns, use WorkflowCommand.DATA.
    workflow_input = WorkflowRunInput(
        command=WorkflowCommand.START,  # ← explicit START (this is also the default)
        messages=[],
        dynamic_variables={},
        runtime_variables={},
    )

    start_time = time.time()
    iteration_num = 0

    while True:
        iteration_num += 1
        print(f"\n{'=' * 60}")
        print(f"TURN {iteration_num} — command: {workflow_input.command.value}")
        print(f"{'=' * 60}")

        should_break = False

        async for event in workflow_runtime.arun(workflow_input):
            should_break = handle_all_events(event, iteration_num)
            if should_break:
                break

        if should_break:
            # BusyWaitForUserMessageEvent was received — collect user input for next turn
            user_input = inputs_queue[input_idx] if input_idx < len(inputs_queue) else "quit"
            input_idx += 1

            if user_input.strip().lower() == "quit":
                print("\n🛑 User ended the conversation.")
                # ── WorkflowCommand.STOP pattern ──────────────────────────────
                # In a real service, STOP is implemented by cancelling the asyncio Task
                # driving arun(). For local illustration, we simply break.
                #
                # Production pattern:
                #   arun_task = asyncio.create_task(drain_events(runtime, workflow_input))
                #   arun_task.cancel()  # This triggers WorkflowCommand.STOP semantics
                break

            print(f"👤 User: {user_input}")

            # ── WorkflowCommand.DATA — all subsequent turns ─────────────────
            # After the first turn, always use DATA to send the next user message.
            # The same WorkflowRuntime instance handles the state continuity.
            workflow_input = WorkflowRunInput(
                command=WorkflowCommand.DATA,  # ← DATA for all non-first turns
                messages=[HumanMessage(content=user_input)],
                dynamic_variables={},
                runtime_variables={},
            )
        else:
            # No BusyWaitForUserMessageEvent — workflow has reached a terminal state
            print("\n✅ Workflow reached terminal state (no more waiting for input).")
            break

    elapsed = time.time() - start_time
    print(f"\n⏱️  Total run time: {elapsed:.2f}s")

    # ──────────────────────────────────────────────────────────────────────────
    # WORKFLOWCOMMAND.PAUSE / RESUME — conceptual example
    # ──────────────────────────────────────────────────────────────────────────
    #
    # Imagine you want to pause mid-conversation for supervisor review:
    #
    #   pause_input = WorkflowRunInput(
    #       command=WorkflowCommand.PAUSE,
    #       messages=[],        # No user message needed for PAUSE
    #       dynamic_variables={},
    #       runtime_variables={},
    #   )
    #   async for event in runtime.arun(pause_input):
    #       if isinstance(event, PauseThreadEvent):
    #           print("Workflow paused — supervisor review in progress")
    #           break
    #
    #   # ... supervisor reviews the conversation ...
    #
    #   resume_input = WorkflowRunInput(
    #       command=WorkflowCommand.RESUME,
    #       messages=[HumanMessage(content="Supervisor approved. Please continue.")],
    #       dynamic_variables={},
    #       runtime_variables={},
    #   )
    #   async for event in runtime.arun(resume_input):
    #       handle(event)
    # ──────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    asyncio.run(run())
