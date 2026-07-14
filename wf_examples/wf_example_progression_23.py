import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 23 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_23.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_23.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import (
    LLMGroupConfig,
    LLMGroupWithBackchannelConfig,
    OperationMode,
    SelectionMode,
)
from interactly.configs import SayLLMNodeConfig, WorkerLLMNodeConfig
from interactly.configs import GlobalConditionEdgeEvaluationMethod, GlobalNodeConfig
from interactly.configs import DynamicMessagesConfig, PromptConfig, StaticMessagesConfig
from interactly.configs import ExternalAPIToolConfig, KnowledgeBaseToolConfig, ToolsConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowCommand, WorkflowRunInput
from interactly.runtime.events import (
    AssistantResponseEvent,
    BusyWaitForUserMessageEvent,
    EndWorkflowEvent,
    EndWorkflowIterationEvent,
    WorkerLLMNodeEvent,
    WorkflowErrorEvent,
    WorkflowNavigationEvent,
    WorkflowWarningEvent,
)
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX

# ─── LLM CONFIGS ──────────────────────────────────────────────────────────────


def _make_fast_llm():
    """Cheap, fast LLM for intake worker and backchannel generation."""
    return OpenAILLMConfig(
        model=OPENAIModel.GPT_4_1_MINI,
        max_tokens=150,
        temperature=0.2,
        do_not_split_sentences=True,
    )


def _make_main_llm_group():
    """
    Primary LLM group for the main assistant.
    Uses LLMGroupConfig so it can be wrapped in LLMGroupWithBackchannelConfig.
    """
    return LLMGroupConfig(
        llms=[
            OpenAILLMConfig(
                model=OPENAIModel.GPT_5_4,
                max_tokens=500,
                temperature=0.3,
                do_not_split_sentences=True,
            )
        ],
        # SEQUENTIAL_WITH_PROACTIVE: try the first LLM; after min_patience_time_ms,
        # kick off any remaining LLMs in parallel as fallback.
        operation_mode=OperationMode.SEQUENTIAL_WITH_PROACTIVE,
        min_patience_time_ms=1500,
    )


def _make_backchannel_config():
    """
    LLMGroupWithBackchannelConfig for voice latency reduction.
    If the main LLM takes >2s, a static filler fires immediately.
    """
    return LLMGroupWithBackchannelConfig(
        main_llm_config=_make_main_llm_group(),
        backchannel_static_responses=[
            "Let me look into that for you...",
            "One moment while I check...",
            "Give me just a second...",
        ],
        backchannel_static_responses_selection_mode=SelectionMode.RANDOM,
        # Only text after this prefix in the main LLM output is sent after a backchannel.
        non_backchannel_response_prefix="[MAIN]",
        backchannel_min_patience_time_ms=2000,
    )


# ─── TOOL CONFIG ──────────────────────────────────────────────────────────────


def _make_tools_config():
    """
    LLM-invoked tools available to the Main Assistant Node.
    The LLM chooses at runtime which tool(s) to call.
    """
    return ToolsConfig(
        tools=[
            # 1. External API tool — looks up a member's benefits via REST
            ExternalAPIToolConfig(
                name="lookup_member_benefits",
                description=(
                    "Look up the member's current benefits, deductible status, and plan details. "
                    "Call this whenever the member asks about their coverage, deductible, or plan."
                ),
                api_endpoint="https://api.cigna-internal.example.com/v1/members/{{member_id}}/benefits",
                api_method="GET",
                api_headers={"Authorization": "Bearer {{api_token}}", "Content-Type": "application/json"},
                # args_schema: JSON Schema for what the LLM should extract before calling this tool.
                args_schema={
                    "type": "object",
                    "properties": {
                        "benefit_category": {
                            "type": "string",
                            "enum": ["medical", "dental", "vision", "pharmacy"],
                            "description": "The benefit category the member asked about",
                        }
                    },
                    "required": ["benefit_category"],
                },
                result_runtime_variable_name="member_benefits_response",
                static_messages_config=StaticMessagesConfig(
                    static_messages=["Looking up your benefits — one moment please..."]
                ),
            ),
            # 2. Knowledge Base tool — RAG over Cigna policy documents
            KnowledgeBaseToolConfig(
                name="search_policy_knowledge_base",
                description=(
                    "Search Cigna's policy and coverage documentation for accurate answers "
                    "about plan rules, exclusions, and procedures. Use this for policy questions."
                ),
                target_knowledge_base_ids=["kb_cigna_policies_001", "kb_cigna_faq_002"],
                result_runtime_variable_name="policy_kb_results",
                static_messages_config=StaticMessagesConfig(
                    static_messages=["Searching our policy documentation — just a moment..."]
                ),
            ),
        ]
    )


# ─── NODE CONFIGS ─────────────────────────────────────────────────────────────


def build_assistant_workflow():
    """
    Build the full Cigna Member Services AI workflow — the synthesis capstone.

    This demonstrates the complete composition of all workflow concepts into a
    single production-grade workflow for inbound member support calls.
    """

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 23: Synthesis Capstone — Cigna Member Services",
        description=f"""
        Full-featured inbound member services AI agent combining:
        WorkerLLMNodeConfig, SayLLMNodeConfig, LLMGroupWithBackchannelConfig,
        ExternalAPIToolConfig, KnowledgeBaseToolConfig, ConditionalEdgeConfig with
        ConditionConfig (args_schema, dynamic/static messages), GlobalNodeConfig with
        reverse_conditional_edge, WorkflowCommand lifecycle, and comprehensive events.

        See more details at {google_docs_md_link}
        """,
        # Seed the workflow with default values for the dynamic variables it references
        # (e.g. {{member_id}}, {{api_token}}). Stored under the "default_dynamic_variables"
        # key in miscellaneous, these are used as defaults when a run does not supply them.
        miscellaneous={
            "default_dynamic_variables": {
                "member_id": "MBR-987654",
                "api_token": "mock-token-abc123",
            }
        },
    )

    # ── 1. Intake Worker Node (Ex 4–5) ────────────────────────────────────────
    # Runs first, silently. Structured output fields are written into runtime variables.
    # Does NOT wait for user input and does NOT say anything aloud.
    INTAKE_PROMPT = """
    You are a silent intake AI. Extract the following from the conversation context:
    - member_intent: one of "billing", "claims", "benefits", "general", "farewell"
    - caller_tone: one of "calm", "frustrated", "urgent"

    Return only the structured output. Do not say anything to the user.
    """
    intake_node = WorkerLLMNodeConfig(
        name="Intake Worker",
        description="Silent intent classification before the greeting",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,  # Does NOT block for user input
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + INTAKE_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=_make_fast_llm(),
        structured_output_schema={
            "name": "CignaMemberIntake",
            "description": "Initial intent and tone classification for a member services call",
            "input_schema": {
                "type": "object",
                "properties": {
                    "member_intent": {
                        "type": "string",
                        "enum": ["billing", "claims", "benefits", "general", "farewell"],
                    },
                    "caller_tone": {
                        "type": "string",
                        "enum": ["calm", "frustrated", "urgent"],
                    },
                },
                "required": ["member_intent", "caller_tone"],
            },
        },
    )

    # ── 2. Greeting Node (Ex 1–3) ─────────────────────────────────────────────
    GREETING_PROMPT = """
    Greet the member warmly by name if available. Introduce yourself as Cigna's virtual assistant.
    Ask how you can help them today.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting",
        description="Initial warm greeting",
        is_start=False,
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=_make_fast_llm(),
    )

    # ── 3. Main Assistant Node (Ex 15, 22) ────────────────────────────────────
    # Core conversational loop with:
    # - LLMGroupWithBackchannelConfig for voice responsiveness
    # - ExternalAPIToolConfig + KnowledgeBaseToolConfig for grounded answers
    MAIN_PROMPT = """
    You are Cigna's primary member services AI assistant. Help members with benefits,
    coverage, claims status, and general insurance questions. Use the available tools
    to look up real member data or search policy documentation before answering.

    When a backchannel filler has already been sent to the member, start your response
    with the exact token "[MAIN]" and skip any introductory filler acknowledgments.

    Always be empathetic, clear, and concise.
    """
    main_assistant_node = SayLLMNodeConfig(
        name="Main Assistant",
        description="Primary conversational AI with backchannel and tool support",
        self_loop=True,  # Default: stay in this node after each turn
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + MAIN_PROMPT + GLOBAL_PROMPT_SUFFIX),
        # LLMGroupWithBackchannelConfig: voice-optimized with static filler (Ex 22)
        llms_config=_make_backchannel_config(),
        # LLM-invoked tools: ExternalAPIToolConfig + KnowledgeBaseToolConfig (Ex 15)
        tools_config=_make_tools_config(),
    )

    # ── 4. Billing Node (Ex 6–7) ──────────────────────────────────────────────
    BILLING_PROMPT = """
    You are Cigna's billing specialist. Help the member resolve billing disputes,
    understand their EOB, or set up payment plans.
    Ask if you've fully resolved their billing question before returning to the main menu.
    """
    billing_node = SayLLMNodeConfig(
        name="Billing Specialist",
        description="Dedicated billing support node",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + BILLING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=_make_main_llm_group(),
    )

    # ── 5. Farewell Node (terminal) (Ex 1–3) ──────────────────────────────────
    FAREWELL_PROMPT = """
    Thank the member sincerely for calling Cigna. Wish them well and let them know
    a satisfaction survey will follow. Do not ask any further questions.
    """
    farewell_node = SayLLMNodeConfig(
        name="Farewell",
        description="Closing node — ends the conversation gracefully",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + FAREWELL_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=_make_fast_llm(),
    )

    # ── 6. Escalation Node (GLOBAL) (Ex 21) ──────────────────────────────────
    # Reachable from ANY node when the member requests a human agent.
    ESCALATION_PROMPT = """
    The member has requested to speak with a human agent. Acknowledge their request warmly,
    let them know you are transferring the call, and reassure them that an agent will assist
    them shortly. Do not attempt to resolve the issue yourself.
    """
    escalation_node = SayLLMNodeConfig(
        name="Escalation",
        description="Human escalation — global node reachable from any point in the conversation",
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ESCALATION_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=_make_fast_llm(),
        global_node_config=GlobalNodeConfig(
            is_global=True,  # Reachable from ANY node
            # Condition that triggers navigation to this global node (Ex 21)
            condition=ConditionConfig(
                condition_freeform=(
                    "The member explicitly requests to speak with a human agent, supervisor, "
                    "or representative — e.g. 'talk to a person', 'transfer me', 'human please'."
                ),
                # args_schema: structured data the LLM extracts when deciding to escalate
                args_schema={
                    "type": "object",
                    "properties": {
                        "escalation_reason": {
                            "type": "string",
                            "description": "Why the member wants to escalate",
                        },
                        "urgency": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                    },
                    "required": ["escalation_reason"],
                },
                # static_messages_config: immediate verbal acknowledgment as the edge fires
                static_messages_config=StaticMessagesConfig(
                    static_messages=[
                        "Of course — let me connect you with one of our agents right away.",
                        "Absolutely — I'll transfer you to a specialist now.",
                    ]
                ),
            ),
            global_condition_edge_evaluation_method=GlobalConditionEdgeEvaluationMethod.TOOL_CALL,
            # reverse_conditional_edge: return to the previous node if the member changes
            # their mind while still on the escalation node (Ex 21)
            reverse_conditional_edge=ConditionConfig(
                condition_freeform=(
                    "The member changed their mind and no longer wants to speak with a human agent — "
                    "e.g. 'never mind', 'I'll stay with you', 'forget it'."
                ),
                dynamic_messages_config=DynamicMessagesConfig(
                    dynamic_message_prompt=(
                        "Generate a brief (1-sentence) warm transition message acknowledging the member's "
                        "decision to continue with the virtual assistant and returning to their inquiry."
                    )
                ),
            ),
        ),
    )

    # ─── EDGE CONFIGS ─────────────────────────────────────────────────────────

    # Intake → Greeting (always)
    edge_intake_to_greeting = DirectEdgeConfig(
        name="Intake → Greeting",
        source_node_logical_id=intake_node.logical_id,
        destination_node_logical_id=greeting_node.logical_id,
    )

    # Greeting → Main Assistant (always)
    edge_greeting_to_main = DirectEdgeConfig(
        name="Greeting → Main Assistant",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=main_assistant_node.logical_id,
    )

    # Main Assistant → Billing (conditional — billing intent detected)
    edge_main_to_billing = ConditionalEdgeConfig(
        name="Main → Billing",
        description="Navigate to billing specialist when member signals a billing topic",
        source_node_logical_id=main_assistant_node.logical_id,
        destination_node_logical_id=billing_node.logical_id,
        condition=ConditionConfig(
            condition_freeform=(
                "The member is asking specifically about a bill, invoice, payment, premium charge, "
                "or EOB explanation and would benefit from the dedicated billing specialist."
            ),
            args_schema={
                "type": "object",
                "properties": {
                    "billing_subtopic": {
                        "type": "string",
                        "description": "Specific billing subtopic mentioned (e.g. 'EOB', 'payment plan')",
                    }
                },
                "required": ["billing_subtopic"],
            },
            dynamic_messages_config=DynamicMessagesConfig(
                dynamic_message_prompt=(
                    "Generate a 1-sentence transition message confirming you heard the member's "
                    "billing question and are connecting them with the billing specialist."
                )
            ),
        ),
    )

    # Main Assistant → Farewell (conditional — member is done)
    edge_main_to_farewell = ConditionalEdgeConfig(
        name="Main → Farewell",
        description="End conversation when member says goodbye",
        source_node_logical_id=main_assistant_node.logical_id,
        destination_node_logical_id=farewell_node.logical_id,
        condition=ConditionConfig(
            condition_freeform=(
                "The member has indicated they are done and are ending the call — "
                "e.g. 'goodbye', 'that's all', 'thanks, bye', 'I'm good now'."
            ),
            static_messages_config=StaticMessagesConfig(
                static_messages=["Thank you so much for calling Cigna — have a wonderful day!"]
            ),
        ),
    )

    # Billing → Main (conditional — billing issue resolved, return to main)
    edge_billing_to_main = ConditionalEdgeConfig(
        name="Billing → Main Assistant",
        source_node_logical_id=billing_node.logical_id,
        destination_node_logical_id=main_assistant_node.logical_id,
        condition=ConditionConfig(
            condition_freeform="The billing question is resolved and the member wants to ask something else.",
            static_messages_config=StaticMessagesConfig(
                static_messages=["Great — let me take you back to our main assistant."]
            ),
        ),
    )

    # ─── WORKFLOW HYDRATION ───────────────────────────────────────────────────

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            intake_node,
            greeting_node,
            main_assistant_node,
            billing_node,
            farewell_node,
            escalation_node,
        ],
        edge_configs=[
            edge_intake_to_greeting,
            edge_greeting_to_main,
            edge_main_to_billing,
            edge_main_to_farewell,
            edge_billing_to_main,
        ],
    )

    return workflow


# ─── MULTI-TURN REPL (Ex 19, 20) ─────────────────────────────────────────────


async def run():
    """
    Full multi-turn REPL demonstrating WorkflowCommand lifecycle and event handling.

    Turn 1  — command=WorkflowCommand.START  (no user message; intake runs first)
    Turn 2+ — command=WorkflowCommand.DATA   (user messages drive subsequent turns)

    Events handled:
    - BusyWaitForUserMessageEvent  → inject next user message
    - AssistantResponseEvent       → print assistant reply
    - WorkerLLMNodeEvent           → print silent intake result
    - WorkflowNavigationEvent      → print routing decisions (debug)
    - WorkflowWarningEvent         → print warnings
    - WorkflowErrorEvent           → print errors and abort
    - EndWorkflowIterationEvent    → print per-iteration stats
    - EndWorkflowEvent             → print final token usage
    """
    workflow = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    # Simulated conversation turns
    inputs_queue = [
        "I have a question about my deductible",
        "Can you tell me how much I've paid toward my deductible this year?",
        "Actually, I also got a confusing bill — can you help with that?",
        "The bill says I owe $350 — but my EOB shows $0 patient responsibility",
        "That's all cleared up, thanks. Goodbye!",
        "quit",
    ]
    input_idx = 0
    is_first_turn = True

    print("=" * 65)
    print("  Cigna Member Services AI — Synthesis Capstone (Example 23)")
    print("=" * 65)

    while True:
        # First turn uses WorkflowCommand.START; all subsequent turns use DATA
        command = WorkflowCommand.START if is_first_turn else WorkflowCommand.DATA
        is_first_turn = False

        workflow_input = WorkflowRunInput(
            messages=[],
            command=command,
            dynamic_variables={
                "member_id": "MBR-987654",
                "api_token": "mock-token-abc123",
            },
            runtime_variables={},
        )

        start = time.time()
        done = False

        async for event in workflow_runtime.arun(workflow_input):

            if isinstance(event, BusyWaitForUserMessageEvent):
                node_name = event.origin_node_name or "unknown"
                print(f"\n🔄 [{node_name}] Ready for input...")

                user_input = inputs_queue[input_idx] if input_idx < len(inputs_queue) else "quit"
                input_idx += 1

                if user_input.strip().lower() == "quit":
                    print("🛑 Conversation ended by user.")
                    done = True
                    break

                print(f"👤 Member: {user_input}")
                workflow_input.messages.append(HumanMessage(content=user_input))

            elif isinstance(event, AssistantResponseEvent):
                # Strip the [MAIN] backchannel prefix if present before displaying
                content = event.content
                if content.startswith("[MAIN]"):
                    content = content[len("[MAIN]") :].lstrip()
                print(f"🤖 Cigna AI: {content}")

            elif isinstance(event, WorkerLLMNodeEvent):
                # Silent intake result — logged but not spoken
                print(f"📋 [Intake] {event.message}")

            elif isinstance(event, WorkflowNavigationEvent):
                # Routing decisions — useful for debugging
                print(f"🗺️  [Navigation] {event.message}")

            elif isinstance(event, WorkflowWarningEvent):
                print(f"⚠️  [Warning] {event.warning_message}")

            elif isinstance(event, WorkflowErrorEvent):
                print(f"❌ [Error] {event.error_message}")
                done = True
                break

            elif isinstance(event, EndWorkflowIterationEvent):
                elapsed = time.time() - start
                print(f"\n📊 [Iteration {event.iteration_number}] Completed in {elapsed:.2f}s")
                # Break the inner event loop — the REPL outer loop drives next turns
                break

            elif isinstance(event, EndWorkflowEvent):
                usage = event.llm_token_usage
                print(
                    f"\n✅ Workflow complete. Tokens — Prompt: {usage.prompt_tokens}, Completion: {usage.completion_tokens}"
                )
                done = True
                break

        if done:
            break

    print("\n" + "=" * 65)
    print("  Session ended.")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run())
