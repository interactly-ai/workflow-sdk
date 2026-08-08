import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 21 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_21.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_21.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import GlobalConditionEdgeEvaluationMethod, GlobalNodeConfig
from interactly.configs import DynamicMessagesConfig, PromptConfig, StaticMessagesConfig
from interactly.configs import GlobalConditionEdgeEvaluationMethod as WorkflowGlobalMethod
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a workflow that demonstrates advanced condition features.

    This example goes beyond the simple ConditionalEdgeConfig from earlier examples
    and shows all four advanced features of the condition system:

    1. condition_freeform vs condition_expression
       - condition_freeform: natural language ("the user said they want to cancel")
       - condition_expression: a structured expression using [[variables]] and operators
         e.g. "[[intent]] == 'cancel' && [[satisfaction_score]] < 3"
       - Both can be set — the runtime uses freeform if expression is absent

    2. args_schema on ConditionConfig
       - Defines the JSON Schema of arguments the LLM should fill when evaluating
         the freeform condition. The LLM extracts these from conversation context.
       - Example: { "type": "object", "properties": { "intent": { "type": "string" } } }
       - These filled args appear in ConditionalEdgeEvent.args_filled

    3. static_messages_config and dynamic_messages_config on ConditionConfig
       - static_messages_config: a pre-written message the LLM emits when this
         conditional edge fires (e.g. "Let me transfer you to billing.")
       - dynamic_messages_config: a PROMPT guiding the LLM to generate a contextual
         message on the fly when this edge fires (more flexible than static)
       - At most one of these should be set per condition

    4. GlobalNodeConfig and reverse_conditional_edge
       - A "global" node is reachable from ANY node in the workflow via its condition.
       - reverse_conditional_edge: a ConditionConfig that, when met while the global
         node is executing, returns control to the node that last navigated into the
         global node (e.g. "handle emergency then return to where we were").
       - global_condition_edge_evaluation_method: TOOL_CALL (default), WORKFLOW_DEFAULT,
         or INDEPENDENT_LLM_EVALUATIONS — controls how the global condition is evaluated.

    Also demonstrates:
    - WorkflowConfig.global_condition_evaluation_method: the workflow-level default method
    """

    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 21: Advanced Condition Features",
        description=f"""
        Demonstrates the full condition system:
        - condition_freeform vs condition_expression on ConditionConfig
        - args_schema for structured LLM argument extraction
        - static_messages_config and dynamic_messages_config when edges fire
        - GlobalNodeConfig: is_global, condition, reverse_conditional_edge
        - global_condition_evaluation_method at workflow and node levels

        See more details at {google_docs_md_link}
        """,
        # Workflow-level default method for evaluating global condition edges.
        # TOOL_CALL (default): LLM uses a tool call to set the condition arguments.
        # INDEPENDENT_LLM_EVALUATIONS: each conditional edge is evaluated independently.
        global_condition_evaluation_method=WorkflowGlobalMethod.TOOL_CALL,
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the member warmly. Ask why they are calling today.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Greets and collects initial intent",
        is_start=True,
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    BILLING_PROMPT = """
    You are the Cigna billing specialist. Help the member with billing inquiries.
    Answer their question and ask if there is anything else.
    """
    billing_node = SayLLMNodeConfig(
        name="Billing Support",
        description="Handles billing questions",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + BILLING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    CLAIMS_PROMPT = """
    You are the Cigna claims specialist. Help the member with claims status and submissions.
    Answer their question and ask if there is anything else.
    """
    claims_node = SayLLMNodeConfig(
        name="Claims Support",
        description="Handles claims questions",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + CLAIMS_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    # ── GLOBAL NODE: Medical Emergency ────────────────────────────────────────
    # A global node is reachable from ANY other node if its condition fires.
    # Use case: the member mentions a medical emergency mid-conversation — the
    # workflow must respond immediately, regardless of which node is currently active.
    EMERGENCY_PROMPT = """
    URGENT: The member has indicated a potential medical emergency.
    Calmly advise them to call 911 immediately or go to the nearest emergency room.
    Ask if they need you to stay on the line.
    """
    emergency_node = SayLLMNodeConfig(
        name="Emergency Node",
        description="Handles medical emergency mentions — reachable from any node",
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + EMERGENCY_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
        # ── GlobalNodeConfig ───────────────────────────────────────────────────
        global_node_config=GlobalNodeConfig(
            is_global=True,  # ← Makes this node reachable from ANY node in the workflow
            # The condition that causes navigation to this global node.
            # condition_freeform: natural language description of when to navigate here.
            # condition_expression: structured expression (takes precedence when set).
            # args_schema: JSON Schema defining what the LLM should extract.
            condition=ConditionConfig(
                condition_freeform=(
                    "The member uses urgent language suggesting a medical emergency "
                    "(e.g. 'chest pain', 'can't breathe', 'emergency', 'call 911')."
                ),
                # No condition_expression here — freeform is used.
                # args_schema lets the LLM extract structured arguments from the conversation.
                # These appear in ConditionalEdgeEvent.args_filled.
                args_schema={
                    "type": "object",
                    "properties": {
                        "emergency_keywords_detected": {
                            "type": "string",
                            "description": "The exact urgent phrase the member used",
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["high", "medium"],
                            "description": "Estimated severity based on the member's language",
                        },
                    },
                    "required": ["emergency_keywords_detected"],
                },
                # static_messages_config: a pre-written message emitted AS the edge fires.
                # The LLM says this immediately when it decides to take this path.
                # Use this when the message is always the same.
                static_messages_config=StaticMessagesConfig(
                    static_messages=[
                        "I hear that this may be urgent — let me help you right away.",
                        "Please hold on — I'm connecting you with emergency guidance immediately.",
                    ]
                    # static_messages_selection_mode defaults to RANDOM
                ),
                # NOTE: do NOT set dynamic_messages_config if static_messages_config is set.
                # dynamic_messages_config is preferred when you want context-aware transitions.
            ),
            # global_condition_edge_evaluation_method: overrides the workflow-level default
            # for THIS specific global node's condition.
            # TOOL_CALL: (default) LLM uses a structured tool call to fill args_schema fields.
            global_condition_edge_evaluation_method=GlobalConditionEdgeEvaluationMethod.TOOL_CALL,
            # ── reverse_conditional_edge ─────────────────────────────────────────
            # After handling the emergency, we may want to return to the node that
            # was active before the emergency was detected (e.g. Billing or Claims).
            # The reverse_conditional_edge fires if its condition is met while this
            # global node is running.
            reverse_conditional_edge=ConditionConfig(
                condition_freeform=(
                    "The emergency situation has been addressed and the member is calm again, "
                    "indicating they would like to continue with the original inquiry."
                ),
                # dynamic_messages_config: instead of a static message, provide a prompt
                # that guides the LLM to generate a contextual bridging message.
                # Use this when the appropriate message depends on conversation context.
                dynamic_messages_config=DynamicMessagesConfig(
                    dynamic_message_prompt=(
                        "Generate a brief, reassuring transition message (1 sentence) that "
                        "acknowledges the member is okay and returns to their original inquiry. "
                        "Be warm but concise."
                    )
                ),
            ),
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    # ── ConditionalEdgeConfig with condition_freeform + args_schema ───────────
    # From the greeting, navigate to Billing or Claims based on stated intent.

    edge_greeting_to_billing = ConditionalEdgeConfig(
        name="Greeting → Billing",
        description="Navigate to billing when the member mentions billing or payments",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=billing_node.logical_id,
        condition=ConditionConfig(
            condition_freeform=("The member mentioned billing, invoices, payment, premium, or deductible inquiry."),
            # args_schema: the LLM will extract these values as it evaluates the condition.
            # They appear in ConditionalEdgeEvent.args_filled for auditing.
            args_schema={
                "type": "object",
                "properties": {
                    "billing_topic": {
                        "type": "string",
                        "description": "The specific billing topic mentioned by the member",
                    },
                },
                "required": ["billing_topic"],
            },
            # dynamic_messages_config: LLM generates a contextual routing message.
            # e.g. "I'll connect you with our billing team to help with your premium question."
            dynamic_messages_config=DynamicMessagesConfig(
                dynamic_message_prompt=(
                    "Generate a 1-sentence transition message that confirms you heard the member's "
                    "billing inquiry and are connecting them to the billing specialist."
                )
            ),
        ),
    )

    edge_greeting_to_claims = ConditionalEdgeConfig(
        name="Greeting → Claims",
        description="Navigate to claims when the member mentions a claim",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=claims_node.logical_id,
        condition=ConditionConfig(
            condition_freeform=("The member mentioned a claim, claim status, claim submission, or reimbursement."),
            # condition_expression: a structured alternative to condition_freeform.
            # Use [[variable]] syntax to reference runtime variables.
            # When both freeform and expression are set, expression takes precedence
            # if the runtime variable exists; otherwise freeform is used.
            # Here we show the expression syntax for documentation purposes:
            # condition_expression="[[intent]] == 'claims'",
            args_schema={
                "type": "object",
                "properties": {
                    "claim_id_mentioned": {
                        "type": "string",
                        "description": "Claim ID if the member mentioned one, or 'none'",
                    },
                },
                "required": ["claim_id_mentioned"],
            },
            # static_messages_config: always says the same message when this edge fires.
            static_messages_config=StaticMessagesConfig(
                static_messages=["I'll connect you to our claims team — they'll be able to help you right away."]
            ),
        ),
    )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            billing_node,
            claims_node,
            emergency_node,  # Global node — no explicit source edge needed
        ],
        edge_configs=[
            edge_greeting_to_billing,
            edge_greeting_to_claims,
        ],
    )

    return workflow


async def run():
    """Minimal REPL demonstrating condition-based routing."""
    workflow = build_assistant_workflow()
    # The workflow seeds these on upload; read them back so each turn sends the same values.
    dynamic_variables = workflow.workflow_config.miscellaneous.get("default_dynamic_variables", {})
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    inputs_queue = [
        "I have a question about my last bill",
        "Actually, I'm having chest pain right now",  # ← triggers Emergency global node
        "I'm fine now, thank you. Can we get back to my billing question?",  # ← reverse edge
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
