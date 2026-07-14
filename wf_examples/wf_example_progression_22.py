import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 22 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_22.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_22.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import (
    LLMGroupConfig,
    LLMGroupWithBackchannelConfig,
    OperationMode,
    SelectionMode,
)
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
    Build a workflow that demonstrates LLMGroupWithBackchannelConfig.

    In voice-based AI conversations, real-time responsiveness is critical. When a
    complex question takes 3–5 seconds for the LLM to answer, the silence feels
    unnatural. The backchannel pattern solves this:

    CONCEPT — How backchannel works:
    ─────────────────────────────────
    1. User sends a message.
    2. The main LLM starts generating immediately.
    3. A timer starts. If the main LLM responds within `backchannel_min_patience_time_ms`
       (default: 2000 ms), the backchannel is NEVER triggered — the main response is
       delivered directly.
    4. If the main LLM takes LONGER than that patience window:
       a. A backchannel response fires immediately (either a static phrase or a
          backchannel LLM response).
       b. The client hears the backchannel filler immediately (e.g. "Let me check
          that for you...").
       c. When the main LLM finishes, its response follows the backchannel.
       d. `non_backchannel_response_prefix`: if set, only the text AFTER this exact
          prefix in the main LLM output is sent following the backchannel. This lets
          the LLM know it should skip the acknowledgment it would normally include.

    FIELD REFERENCE:
    ─────────────────────────────────────────────────────────────────────────────────
    LLMGroupWithBackchannelConfig
      main_llm_config                       → LLMGroupConfig (not a raw LLMConfig)
                                              Wraps the primary LLM(s) — can be a
                                              parallel group for speed.
      non_backchannel_response_prefix       → Optional[str]
                                              Prefix string in the main LLM's prompt
                                              output. If the backchannel fires, only
                                              text after this prefix is appended to the
                                              backchannel. Lets the main LLM drop its
                                              own filler acknowledgment.
      backchannel_llm_config                → Optional[LLMGroupConfig]
                                              LLM that generates a dynamic filler.
                                              Use a fast/cheap model here.
                                              Mutually exclusive with static responses
                                              (prefer static for speed).
      backchannel_static_responses          → list[str]
                                              Pre-written filler phrases. One is
                                              chosen at runtime (no LLM cost, lowest
                                              latency). Set this OR backchannel_llm_config.
      backchannel_static_responses_selection_mode → SelectionMode (RANDOM | SEQUENCE)
                                              How to pick from the static list.
      backchannel_min_patience_time_ms      → Optional[int] (default: 2000)
                                              How many ms to wait for the main LLM
                                              before firing the backchannel.

    USAGE:
    ─────────────────────────────────────────────────────────────────────────────────
    Pass LLMGroupWithBackchannelConfig as the `llms_config` on a SayLLMNodeConfig.
    The field type is `LLMOrGroupConfig` (discriminated union on "type"):
      Union[LLMConfig, LLMGroupConfig, LLMGroupWithBackchannelConfig]

    DESIGN NOTES:
    ─────────────────────────────────────────────────────────────────────────────────
    - For fastest backchannel latency, use backchannel_static_responses (no LLM call).
    - For smarter fillers, use backchannel_llm_config with a fast model like GPT-4o-mini.
    - Lower backchannel_min_patience_time_ms for tighter conversations (try 1500 ms).
    - The main_llm_config is itself a LLMGroupConfig, so you can list multiple fallback
      or parallel LLMs for the primary response.
    - non_backchannel_response_prefix must match exactly what you instruct the LLM to
      output; use a distinctive delimiter to avoid false matches.
    """

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 22: LLMGroupWithBackchannelConfig",
        description=f"""
        Demonstrates LLMGroupWithBackchannelConfig for low-latency voice conversations.
        When the main LLM is slow, a backchannel filler fires immediately to avoid silence.

        See more details at {google_docs_md_link}
        """,
    )

    ############# LLM CONFIG BELOW #############

    # Main LLM: GPT-4.1 for high-quality answers.
    # Wrapped in LLMGroupConfig (required by LLMGroupWithBackchannelConfig).
    main_llm_group = LLMGroupConfig(
        llms=[
            OpenAILLMConfig(
                model=OPENAIModel.GPT_5_4,
                max_tokens=400,
                temperature=0.3,
                do_not_split_sentences=True,
            )
        ],
        # SEQUENTIAL_WITH_PROACTIVE: try the first LLM; if it doesn't respond within
        # min_patience_time_ms, kick off remaining LLMs in parallel.
        operation_mode=OperationMode.SEQUENTIAL_WITH_PROACTIVE,
        min_patience_time_ms=1500,
    )

    # Backchannel LLM: GPT-4o-mini for fast, cheap filler generation.
    # Only used when backchannel_static_responses is NOT set.
    backchannel_llm_group = LLMGroupConfig(
        llms=[
            OpenAILLMConfig(
                model=OPENAIModel.GPT_4_1_MINI,
                max_tokens=30,  # Filler should be very short
                temperature=0.7,
                do_not_split_sentences=True,
            )
        ],
        operation_mode=OperationMode.SEQUENTIAL_WITH_PROACTIVE,
    )

    # ── Approach A: LLM-generated backchannel ─────────────────────────────────
    # Use this when you want context-aware filler phrases (e.g. "Let me look that up...").
    # The backchannel_llm_config gets its own prompt from the node's backchannel prompt field.
    # NOTE: This adds LLM latency to the backchannel itself — prefer static responses
    # when lowest latency is needed.
    backchannel_with_llm = LLMGroupWithBackchannelConfig(
        main_llm_config=main_llm_group,
        backchannel_llm_config=backchannel_llm_group,
        # The main LLM's output will start with this prefix when a backchannel was sent.
        # Only text AFTER this prefix is appended to the backchannel response.
        # Instruct the main LLM to output this prefix in its system prompt.
        non_backchannel_response_prefix="[MAIN]",
        backchannel_min_patience_time_ms=2000,  # 2 seconds of patience before filler fires
    )

    # ── Approach B: Static backchannel responses ───────────────────────────────
    # Use this for lowest latency — no LLM call needed for the filler.
    # One phrase is chosen according to backchannel_static_responses_selection_mode.
    backchannel_with_static = LLMGroupWithBackchannelConfig(
        main_llm_config=main_llm_group,
        # Exclusive with backchannel_llm_config: use static OR llm, not both.
        backchannel_static_responses=[
            "Let me pull that up for you...",
            "Give me just a moment...",
            "One moment while I look into that...",
            "Looking that up now...",
        ],
        backchannel_static_responses_selection_mode=SelectionMode.RANDOM,
        non_backchannel_response_prefix="[MAIN]",
        backchannel_min_patience_time_ms=1800,
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the member warmly. Ask how you can help today.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting",
        description="Greet the member",
        is_start=True,
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        # Simple single LLM for the greeting (no backchannel needed here — it's fast)
        llms_config=OpenAILLMConfig(
            model=OPENAIModel.GPT_4_1_MINI,
            max_tokens=100,
            temperature=0.3,
            do_not_split_sentences=True,
        ),
    )

    BENEFITS_PROMPT = """
    You are the Cigna benefits specialist. Answer the member's benefits question thoroughly
    and accurately. This may require looking up complex plan details, so take time to be precise.

    IMPORTANT: When a backchannel response has already been sent to the member (i.e. they
    heard a filler phrase), start your response with the EXACT token "[MAIN]" followed by
    your answer WITHOUT any introductory filler (e.g. do NOT say "Of course!" or "Sure!").
    The backchannel already acknowledged you heard them.

    Example with backchannel: "[MAIN] Your annual deductible for in-network services is $500."
    Example without backchannel (fast response): "Your annual deductible for in-network services is $500."
    """
    benefits_node = SayLLMNodeConfig(
        name="Benefits Q&A",
        description="Answers complex benefits questions with backchannel for slow responses",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + BENEFITS_PROMPT + GLOBAL_PROMPT_SUFFIX),
        # ── LLMGroupWithBackchannelConfig (static variant) ─────────────────────
        # Pass `backchannel_with_static` OR `backchannel_with_llm` here.
        # Using static for this node (lowest latency filler).
        llms_config=backchannel_with_static,
    )

    CLAIMS_PROMPT = """
    You are the Cigna claims specialist. Answer the member's claims question.
    When a backchannel response was already sent, start with "[MAIN]" and skip fillers.
    """
    claims_node = SayLLMNodeConfig(
        name="Claims Q&A",
        description="Answers claims questions — demonstrates LLM-generated backchannel",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + CLAIMS_PROMPT + GLOBAL_PROMPT_SUFFIX),
        # ── LLMGroupWithBackchannelConfig (LLM variant) ─────────────────────────
        # The backchannel here is generated by GPT-4o-mini (context-aware filler).
        llms_config=backchannel_with_llm,
    )

    ############# EDGE CONFIGS BELOW #############

    edge_greeting_to_benefits = DirectEdgeConfig(
        name="Greeting → Benefits",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=benefits_node.logical_id,
    )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[greeting_node, benefits_node, claims_node],
        edge_configs=[edge_greeting_to_benefits],
    )

    return workflow


async def run():
    """Minimal REPL demonstrating backchannel behavior."""
    workflow = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    inputs_queue = [
        "Can you explain how my deductible applies when I see a specialist out of network?",
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
