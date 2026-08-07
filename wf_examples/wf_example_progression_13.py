import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 13 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_13.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_13.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import (
    AnthropicLLMConfig,
    ANTHROPICModel,
    AzureOpenAILLMConfig,
    AZUREOPENAIModel,
    WorkflowDefaultLLMConfig,
    GoogleLLMConfig,
    GOOGLEModel,
    OpenAILLMConfig,
    OPENAIModel,
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
    Build a workflow that demonstrates all four LLM providers supported by Interactly,
    plus the WorkflowDefaultLLMConfig fallback.

    Key concepts introduced in this example:
    1. OpenAILLMConfig        — direct OpenAI API (GPT-5 / GPT-4.x)
    2. AzureOpenAILLMConfig   — Azure-hosted OpenAI (same models, enterprise auth)
    3. GoogleLLMConfig        — Google Gemini models
    4. AnthropicLLMConfig     — Anthropic Claude models
    5. WorkflowDefaultLLMConfig — defers to the platform-level default; no provider lock-in
    6. Assigning per-node llms_config to choose the best model for each task
    """

    # ── OpenAI ────────────────────────────────────────────────────────────────
    # Uses the OpenAI API directly (OPENAI_API_KEY env var).
    # reasoning_effort controls how much reasoning GPT-5 models spend before responding.
    openai_nano = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_NANO,
        max_tokens=60,
        temperature=0.3,
        do_not_split_sentences=True,
        reasoning_effort="low",  # 'minimal' | 'low' | 'medium' | 'high'
    )

    # ── Azure OpenAI ───────────────────────────────────────────────────────────
    # Same models as OpenAI, but served through an Azure deployment.
    # endpoint and api_version fall back to AZURE_OPENAI_ENDPOINT / OPENAI_API_VERSION env vars.
    azure_mini = AzureOpenAILLMConfig(
        model=AZUREOPENAIModel.GPT_5_MINI,
        max_tokens=200,
        temperature=0.2,
        do_not_split_sentences=True,
        reasoning_effort="medium",
        # endpoint="https://my-org.openai.azure.com/",  # ← omit to read from env
        # api_version="2025-01-01-preview",             # ← omit to read from env
        # api_key=SecretStr("..."),                     # ← prefer env var AZURE_OPENAI_API_KEY
    )

    # ── Google Gemini ──────────────────────────────────────────────────────────
    # Uses GOOGLE_API_KEY env var.
    # thinking_budget=0 disables the extended-thinking / reasoning chain (faster, cheaper).
    google_flash = GoogleLLMConfig(
        model=GOOGLEModel.GEMINI_2_5_FLASH,
        max_tokens=400,
        temperature=0.2,
        do_not_split_sentences=True,
        thinking_budget=0,  # 0 = no thinking; set > 0 for deeper reasoning
    )

    # ── Anthropic Claude ──────────────────────────────────────────────────────
    # Uses ANTHROPIC_API_KEY env var.
    # thinking_budget=0 disables Claude's extended thinking feature.
    claude_haiku = AnthropicLLMConfig(
        model=ANTHROPICModel.CLAUDE_HAIKU_4_5_20251001,
        max_tokens=300,
        temperature=0.3,
        do_not_split_sentences=True,
        thinking_budget=0,
    )

    # ── GlobalDefault ─────────────────────────────────────────────────────────
    # Inherits whatever LLM the Interactly platform is configured to use by default.
    # This is the most portable option: no provider lock-in, picks up platform upgrades.
    global_default = WorkflowDefaultLLMConfig(
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_description = f"""
    This workflow illustrates how to configure different LLM providers on a per-node basis.
    Interactly supports OpenAI, Azure OpenAI, Google Gemini, Anthropic Claude, and a
    WorkflowDefaultLLMConfig that delegates to the platform-level default.

    Each provider has its own model enum and provider-specific optional fields (e.g.
    reasoning_effort for GPT-5, thinking_budget for Gemini and Claude).
    All providers share a common set of base fields: max_tokens, temperature,
    do_not_split_sentences, truncated_max_recent_messages, streaming, max_retries, etc.

    Choosing the right provider per node lets you:
    - Use a cheap nano/flash model for routing / classification nodes (low latency)
    - Use a powerful model for complex reasoning nodes (high accuracy)
    - Use Azure endpoints for data-residency / enterprise compliance requirements
    - Use GlobalDefault so the same workflow config works across different deployments

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 13: Alternative LLM Providers",
        description=workflow_description,
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the user. Tell them this demo uses different LLM providers for different nodes.
    Ask which health insurance topic they want help with today.
    Keep the greeting under 25 words.
    """
    # Uses OpenAI nano — fast and cheap for greetings.
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node (OpenAI nano)",
        description="Greeting using a lightweight OpenAI nano model",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_nano,
    )

    CLAIMS_PROMPT = """
    You are a claims assistant. Answer the user's question about health insurance claims clearly
    and concisely. Reference Cigna's publicly available claims process when applicable.
    """
    # Uses Azure OpenAI mini — enterprise deployment with data residency control.
    claims_node = SayLLMNodeConfig(
        name="Claims Assistant (Azure OpenAI mini)",
        description="Claims questions answered by an Azure-hosted GPT model",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + CLAIMS_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=azure_mini,
    )

    WELLNESS_PROMPT = """
    You are a wellness advisor. Answer the user's question about preventive care,
    nutrition, fitness, or mental wellbeing in a warm, supportive tone.
    """
    # Uses Google Gemini Flash — good balance of speed and quality for conversational tasks.
    wellness_node = SayLLMNodeConfig(
        name="Wellness Advisor (Google Gemini Flash)",
        description="Wellness questions answered by a Google Gemini model",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + WELLNESS_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=google_flash,
    )

    BENEFITS_PROMPT = """
    You are a benefits specialist. Explain insurance plan features (deductibles, copays,
    in/out-of-network), help the user compare plans, and clarify coverage terminology.
    """
    # Uses Anthropic Claude Haiku — efficient for structured explanations.
    benefits_node = SayLLMNodeConfig(
        name="Benefits Specialist (Anthropic Claude Haiku)",
        description="Benefits questions answered by an Anthropic Claude model",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + BENEFITS_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=claude_haiku,
    )

    GENERAL_PROMPT = """
    You are a general Cigna assistant. Answer any health insurance question the user has.
    If the topic is claims, benefits, or wellness, let them know they can ask more specific questions.
    """
    # Uses WorkflowDefaultLLMConfig — no provider lock-in; picks up whatever the platform default is.
    general_node = SayLLMNodeConfig(
        name="General Assistant (Platform Default)",
        description="Catch-all node using the platform's global default LLM",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GENERAL_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=global_default,
    )

    ############# EDGE CONFIGS BELOW #############

    # For brevity this example uses DirectEdges to a single general node.
    # In production you would add ConditionalEdges to route to the right specialist.

    edge_greeting_to_general = DirectEdgeConfig(
        name="Greeting → General",
        description="Route all users to the general assistant after greeting",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=general_node.logical_id,
    )

    # NOTE: In a real workflow you would add ConditionalEdges from greeting_node to
    # claims_node, wellness_node, and benefits_node based on topic classification.
    # The three specialist nodes are configured above for reference but are only
    # wired in via commented edges below.
    #
    # edge_greeting_to_claims = ConditionalEdgeConfig(
    #     name="Greeting → Claims",
    #     source_node_logical_id=greeting_node.logical_id,
    #     destination_node_logical_id=claims_node.logical_id,
    #     condition=ConditionConfig(condition_freeform="User's question is about claims or billing"),
    # )
    # edge_greeting_to_wellness = ConditionalEdgeConfig(
    #     name="Greeting → Wellness",
    #     source_node_logical_id=greeting_node.logical_id,
    #     destination_node_logical_id=wellness_node.logical_id,
    #     condition=ConditionConfig(condition_freeform="User's question is about wellness, fitness, or mental health"),
    # )
    # edge_greeting_to_benefits = ConditionalEdgeConfig(
    #     name="Greeting → Benefits",
    #     source_node_logical_id=greeting_node.logical_id,
    #     destination_node_logical_id=benefits_node.logical_id,
    #     condition=ConditionConfig(condition_freeform="User's question is about plan benefits or coverage details"),
    # )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            claims_node,
            wellness_node,
            benefits_node,
            general_node,
        ],
        edge_configs=[
            edge_greeting_to_general,
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
        "How do I submit a claim for an out-of-network doctor visit?",
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
