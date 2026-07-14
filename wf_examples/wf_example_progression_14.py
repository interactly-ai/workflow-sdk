import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 14 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_14.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_14.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import (
    AnthropicLLMConfig,
    ANTHROPICModel,
    GoogleLLMConfig,
    GOOGLEModel,
    OpenAILLMConfig,
    OPENAIModel,
)
from interactly.configs import LLMGroupConfig, OperationMode
from interactly.configs import SayLLMNodeConfig
from interactly.configs import PromptConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a workflow that demonstrates LLMGroupConfig — running multiple LLM providers
    in parallel or sequentially, and using the first response that arrives.

    Key concepts introduced in this example:
    1. LLMGroupConfig — wraps a list of LLMConfig objects; the runtime races them
    2. OperationMode.PARALLEL_SELECT_ONE — queries all LLMs simultaneously, takes
       the first response that arrives within max_patience_time_ms
    3. OperationMode.SEQUENTIAL_WITH_PROACTIVE — starts with the primary LLM;
       if it hasn't responded within min_patience_time_ms, fires the remaining LLMs
       in parallel and still uses whichever responds first
    4. Patience timing: min_patience_time_ms and max_patience_time_ms
    5. Assigning an LLMGroupConfig to llms_config of a SayLLMNodeConfig
    """

    # Primary LLM — fastest, lowest cost (good for most turns)
    openai_nano = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_NANO,
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    # Secondary LLM — fallback if the primary is slow or fails
    google_flash = GoogleLLMConfig(
        model=GOOGLEModel.GEMINI_2_5_FLASH,
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
        thinking_budget=0,
    )

    # Tertiary LLM — second fallback
    claude_haiku = AnthropicLLMConfig(
        model=ANTHROPICModel.CLAUDE_HAIKU_4_5_20251001,
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    # ── LLMGroupConfig with SEQUENTIAL_WITH_PROACTIVE mode ────────────────────
    #
    # The runtime will:
    #   1. Send the prompt to openai_nano immediately.
    #   2. Wait up to min_patience_time_ms (1 500 ms by default) for it to respond.
    #   3. If openai_nano hasn't responded yet, ALSO fire google_flash and claude_haiku
    #      in parallel ("proactive" fallbacks).
    #   4. Whichever LLM responds first wins; the others are cancelled.
    #   5. If no LLM responds within max_patience_time_ms, the node returns None.
    #
    # This gives you the latency guarantees of a fast primary LLM while ensuring you
    # never stall a user conversation due to an upstream outage.
    sequential_with_proactive_group = LLMGroupConfig(
        llms=[openai_nano, google_flash, claude_haiku],
        operation_mode=OperationMode.SEQUENTIAL_WITH_PROACTIVE,
        min_patience_time_ms=1500,  # Wait 1.5 s before firing fallbacks
        max_patience_time_ms=10000,  # Give up after 10 s total
    )

    # ── LLMGroupConfig with PARALLEL_SELECT_ONE mode ──────────────────────────
    #
    # The runtime will:
    #   1. Send the prompt to ALL LLMs simultaneously.
    #   2. Wait unconditionally for min_patience_time_ms (unless all have responded).
    #   3. Pick the first response that arrives after the patience window closes.
    #   4. Cancel the remaining in-flight requests.
    #
    # Use this when you ALWAYS want the absolute fastest response regardless of
    # provider, and you don't mind sending redundant requests (higher cost).
    parallel_select_one_group = LLMGroupConfig(
        llms=[openai_nano, google_flash],
        operation_mode=OperationMode.PARALLEL_SELECT_ONE,
        min_patience_time_ms=800,  # Wait at least 0.8 s before picking a winner
        max_patience_time_ms=8000,  # Hard cap
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_description = f"""
    This workflow demonstrates LLMGroupConfig — a way to run multiple LLM providers in
    parallel or sequentially and return whichever response arrives first.

    There are two operation modes:
    - SEQUENTIAL_WITH_PROACTIVE: Tries the first LLM; fires fallbacks in parallel
      only if the first LLM hasn't responded within min_patience_time_ms. This is the
      recommended default: lowest cost in the happy path, guaranteed latency via fallback.
    - PARALLEL_SELECT_ONE: Fires all LLMs simultaneously and picks the fastest response.
      Higher cost but lowest possible latency.

    Both modes respect max_patience_time_ms as a hard upper bound.

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 14: Multi-Provider Parallelism with LLMGroupConfig",
        description=workflow_description,
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the user and explain this demo uses multi-LLM fallback for resilience.
    Ask what health insurance topic they want to discuss today.
    Keep the greeting under 30 words.
    """
    # Greeting uses SEQUENTIAL_WITH_PROACTIVE: tries OpenAI nano first, falls back to
    # Google Flash and then Claude Haiku if needed.
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Greets the user; uses LLMGroupConfig with sequential-proactive fallback",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=sequential_with_proactive_group,  # ← LLMGroupConfig assigned here
    )

    ASSISTANT_PROMPT = """
    You are a Cigna health insurance assistant. Answer the user's question clearly and concisely.
    For complex topics, break down the answer into short bullet points.
    """
    # Main assistant uses PARALLEL_SELECT_ONE: fires OpenAI nano and Gemini Flash
    # simultaneously and returns whichever responds first.
    assistant_node = SayLLMNodeConfig(
        name="Insurance Assistant",
        description="Main Q&A node; uses LLMGroupConfig with parallel-select-one for lowest latency",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASSISTANT_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=parallel_select_one_group,  # ← Different LLMGroupConfig assigned here
    )

    ############# EDGE CONFIGS BELOW #############

    edge_greeting_to_assistant = DirectEdgeConfig(
        name="Greeting → Assistant",
        description="After greeting, move to the main assistant node",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=assistant_node.logical_id,
    )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            assistant_node,
        ],
        edge_configs=[
            edge_greeting_to_assistant,
        ],
    )

    return workflow


async def run():
    """Minimal REPL for manual testing."""
    workflow = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    inputs_queue = [
        "What is the difference between a deductible and an out-of-pocket maximum?",
        "Can I use my HSA to pay for gym memberships?",
        "quit",
    ]
    input_idx = 0

    workflow_input = WorkflowRunInput(
        messages=[],
        dynamic_variables={},
        runtime_variables={},
    )

    start_time = time.time()

    async for event in workflow_runtime.arun(workflow_input):
        if isinstance(event, BusyWaitForUserMessageEvent):
            node_name = event.origin_node_name or "unknown node"
            print(f"\n🔄 [{node_name}] Waiting for user message ...")

            user_input = inputs_queue[input_idx] if input_idx < len(inputs_queue) else "quit"
            input_idx += 1

            if user_input.strip().lower() == "quit":
                print("🛑 User ended the conversation.")
                break

            print(f"👤 User: {user_input}")
            workflow_input.messages.append(HumanMessage(content=user_input))

        elif isinstance(event, AssistantResponseEvent):
            print(f"🤖 Assistant: {event.content}")

    elapsed = time.time() - start_time
    print(f"\n⏱️  Total run time: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(run())
