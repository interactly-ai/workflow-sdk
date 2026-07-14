import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 6 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_6.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_6.py
"""

import asyncio
import json
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import CompanionEdgeConfig, ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import LLMNodeRunInput, SayLLMNodeConfig, WorkerLLMNodeConfig
from interactly.configs import GlobalNodeConfig
from interactly.configs import NodesRunInputs
from interactly.configs import SayStaticMessageNodeConfig
from interactly.configs import PromptConfig, StaticMessagesConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import (
    AssistantResponseEvent,
    BusyWaitForUserMessageEvent,
    EndRunNodeEvent,
    WorkerLLMNodeEvent,
    WorkflowDebugLogEvent,
    WorkflowWarningEvent,
)
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    openai_llm_config_nano = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_NANO,
        max_tokens=100,
        temperature=0.5,
        do_not_split_sentences=True,
    )
    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=1000,
        temperature=0.2,
        do_not_split_sentences=True,
    )
    worker_openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=1000,
        temperature=0.0,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.1ytnn7qz0ft6"
    )

    workflow_description = f"""
    This workflow introduces Companion Edges - a powerful pattern that links a conversational Say LLM agent with a Worker LLM agent for parallel structured data extraction. 
    While the Say agent engages naturally with users, its companion Worker silently extracts structured data that can then drive sophisticated multi-path conditional routing. 
    This example demonstrates an insurance risk assessment workflow that collects applicant information and routes to three different care paths (Standard Risk, Premium Client, or Elevated Risk) based on complex expression-based conditions.

    See more details at {google_docs_md_link}

    Dynamic Variables you can use:
        {{
            "greeting_phrase": "Welcome to our Insurance Risk Assessment Portal!",
            "company_name": "Premier Insurance Group",
            "standard_quote_time": "24 hours",
            "standard_approval_time": "3-5 business days",
            "discount_program": "wellness",
            "premium_approval_time": "48 hours",
            "premium_contact_time": "4 business hours",
            "elevated_contact_time": "48 hours",
            "elevated_approval_time": "2-3 weeks",
            "farewell_message": "Thank you for your interest in our insurance services. We look forward to serving you. Have a great day!"
        }}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 6: Insurance Risk Assessment with Advanced Conditional Branching",
        description=workflow_description,
        llms_config=openai_llm_config,
        default_prompt_prefix=GLOBAL_PROMPT_PREFIX,
        default_prompt_suffix=GLOBAL_PROMPT_SUFFIX,
        # miscellaneous={"debug_mode": "true"},
        miscellaneous={
            "default_dynamic_variables": {
                "greeting_phrase": "Welcome to our Insurance Risk Assessment Portal!",
                "company_name": "Premier Insurance Group",
                "standard_quote_time": "24 hours",
                "standard_approval_time": "3-5 business days",
                "discount_program": "wellness",
                "premium_approval_time": "48 hours",
                "premium_contact_time": "4 business hours",
                "elevated_contact_time": "48 hours",
                "elevated_approval_time": "2-3 weeks",
                "farewell_message": "Thank you for your interest in our insurance services. We look forward to serving you. Have a great day!",
            }
        },
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_NODE_PROMPT = """
    Welcome the user to the insurance risk assessment portal in less than 20 words. 
    Ask them to provide information about their insurance application.
    Use the greeting: {{greeting_phrase}}
    Mention that we are from {{company_name}}.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Welcome node that greets the user and asks for insurance application information",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GREETING_NODE_PROMPT),
        llms_config=openai_llm_config_nano,
    )

    ASSESSMENT_SAY_NODE_PROMPT = """
    You are an internal agent specialized in insurance risk assessment. Your specific job is to collect and evaluate insurance application information.

    Engage in a natural conversation with the applicant and try to gather the following information in a friendly, conversational manner:
    - Full name
    - Age (must be a number)
    - Desired coverage amount in dollars (must be a number)
    - Whether they have pre-existing medical conditions (yes/no)
    - If yes, the severity level: none, mild, moderate, or severe
    - Their occupation
    - Any risk factors: smoking, high-risk occupation (police, firefighter, pilot, etc.), dangerous hobbies (skydiving, racing, etc.)
    - Lifestyle health score (1-100) based on their exercise habits, diet quality, and sleep patterns
    """

    assessment_say_node = SayLLMNodeConfig(
        name="Insurance Risk Assessor",
        description="Say LLM node that conducts risk assessment interview and extracts structured data",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=ASSESSMENT_SAY_NODE_PROMPT),
    )

    ASSESSMENT_WORKER_NODE_COMPANION_PROMPT = """
    """

    # Define the structured output schema for insurance risk assessment
    INSURANCE_ASSESSMENT_SCHEMA_AS_DICT = {
        "name": "InsuranceRiskAssessment",
        "description": "Extract and assess insurance application information of the user based on the chat history so far. If any information is missing, do not populate that field. Do not make assumptions. Only fill in what has been explicitly provided by the user.",
        "input_schema": {
            "title": "InsuranceApplicationData",
            "type": "object",
            "properties": {
                "applicant_name": {
                    "title": "Applicant Name",
                    "type": "string",
                    "description": "Full name of the insurance applicant",
                },
                "age": {"title": "Age", "type": "integer", "description": "Applicant's age in years"},
                "coverage_amount": {
                    "title": "Coverage Amount",
                    "type": "integer",
                    "description": "Requested coverage amount in dollars",
                },
                "has_preexisting_conditions": {
                    "title": "Has Pre-existing Conditions",
                    "type": "boolean",
                    "description": "Whether the applicant has any pre-existing medical conditions",
                },
                "condition_severity": {
                    "title": "Condition Severity",
                    "type": "string",
                    "enum": ["none", "mild", "moderate", "severe"],
                    "description": "Severity level of pre-existing conditions if any",
                },
                "occupation": {
                    "title": "Occupation",
                    "type": "string",
                    "description": "Applicant's occupation or job type",
                },
                "risk_factors": {
                    "title": "Risk Factors",
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of identified risk factors (e.g., smoking, high-risk occupation, dangerous hobbies). Return as an empty list [] if no risk factors are identified.",
                },
                "lifestyle_score": {
                    "title": "Lifestyle Score",
                    "type": "integer",
                    "description": "Lifestyle health score from 1-100 based on exercise, diet, sleep habits",
                },
            },
            "required": ["risk_factors"],
        },
    }

    assessment_worker_llm_companion_node = WorkerLLMNodeConfig(
        name="Assessment Companion LLM",
        description="Companion LLM node to assist the main assessment node in extracting structured data",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=ASSESSMENT_WORKER_NODE_COMPANION_PROMPT),
        structured_output_schema=INSURANCE_ASSESSMENT_SCHEMA_AS_DICT,
        llms_config=worker_openai_llm_config,
    )

    # Path 1: Standard Risk - for younger, healthy applicants with low coverage
    STANDARD_RISK_PROMPT = """
    You are a friendly internal agent specialized in handling standard risk insurance applicants.

    You are speaking with a client who qualifies for the Standard Risk tier with preferred rates.

    Their profile indicates:
    - Good health status
    - Low-risk lifestyle
    - Age and coverage within standard parameters

    Next steps:
    1. Tell them that you will send them a personalized quote within {{standard_quote_time}}
    2. Tell them that the standard approval process takes {{standard_approval_time}}
    3. Tell them that they may be eligible for {{discount_program}} discounts

    End with: Thank you for choosing {{company_name}} and check if they have any other questions.
    """

    standard_risk_node = SayLLMNodeConfig(
        name="Standard Risk Path",
        description="Handles standard risk applicants with straightforward approval",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=STANDARD_RISK_PROMPT),
        llms_config=openai_llm_config,
    )

    # Path 2: Premium Client - high coverage, low risk, gets concierge service
    PREMIUM_CLIENT_PROMPT = """
    You are a specialized internal agent providing concierge underwriting services for premium insurance clients.
    You are speaking with a client who qualifies for premium concierge service.


    Their profile indicates:
    - Excellent health and lifestyle factors
    - Substantial coverage request
    - Premium tier eligibility

    Tell them about their Premium Benefits:
    1. Dedicated underwriter assigned immediately
    2. Expedited approval within {{premium_approval_time}}
    3. Access to premium rates and exclusive riders
    4. Concierge service for all your insurance needs
    5. Priority customer support
    6. Complimentary annual policy reviews

    And finally tell them:
    A premium services representative will contact you within {{premium_contact_time}} to discuss your customized coverage options.

    Finish by asking how you may further assist them today.
    """

    premium_client_node = SayLLMNodeConfig(
        name="Premium Client Path",
        description="VIP path for high-value, low-risk clients with concierge service",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=PREMIUM_CLIENT_PROMPT),
    )

    # Path 3: Elevated Risk - needs medical underwriting
    ELEVATED_RISK_PROMPT = """
    You are an internal agent specialized in handling elevated risk insurance applicants requiring medical underwriting.
    You are speaking with a client whose application requires additional medical underwriting review.

    Based on the assessment of the client, you know that
    - Some health considerations need evaluation
    - Additional documentation may be required
    - Coverage may be offered with adjusted premiums

    Next steps would be to tell them the following:
    1. Our underwriting team will contact you within {{elevated_contact_time}}
    2. You may need to provide medical records or schedule a health exam
    3. Approval process typically takes {{elevated_approval_time}}
    4. We'll work with you to find the best coverage options

    Tell them that you appreciate their patience. And finish by asking if they have any questions about the underwriting process.
    """

    elevated_risk_node = SayLLMNodeConfig(
        name="Elevated Risk Path",
        description="Handles elevated risk cases requiring medical underwriting",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=ELEVATED_RISK_PROMPT),
    )

    END_CONVERSATION_GLOBAL_EDGE_CONDITION = """
    Trigger this to route to the conversation ending agent when the patient clearly indicates they want to end the conversation, such as by saying "no", "that's all", "thank you", or similar phrases.
    """

    end_conversation_node = SayStaticMessageNodeConfig(
        name="End Conversation",
        description="Ends the conversation with a thank you message",
        static_messages_config=StaticMessagesConfig(static_messages=["{{farewell_message}}"]),
        global_node_config=GlobalNodeConfig(
            is_global=True, condition=ConditionConfig(condition_freeform=END_CONVERSATION_GLOBAL_EDGE_CONDITION)
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    greeting_to_assessment_edge = DirectEdgeConfig(
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=assessment_say_node.logical_id,
        name="Go to Risk Assessment",
        description="After greeting, route to the risk assessment interview.",
    )

    assessment_companion_edge = CompanionEdgeConfig(
        source_node_logical_id=assessment_say_node.logical_id,
        destination_node_logical_id=assessment_worker_llm_companion_node.logical_id,
        name="Assessment Companion Edge",
        description="Companion edge to link the assessment SayLLM node with its structured data extraction companion LLM node.",
    )

    # Condition 2: Standard Risk Path
    # Young (< 50), healthy (no severe conditions), low coverage (< $500k), good lifestyle (>= 70),
    # and no known risk factors. Risk-factor applicants are always routed to Elevated.
    # isPresent guard ensures routing waits until the companion has extracted risk_factors.
    STANDARD_RISK_CONDITION = (
        "isPresent([[risk_factors]])"
        " AND ([[age]] < 50)"
        " AND ([[coverage_amount]] < 500000)"
        " AND ([[condition_severity]] == 'none' OR [[condition_severity]] == 'mild')"
        " AND ([[lifestyle_score]] >= 70)"
        " AND NOT isNonEmpty([[risk_factors]])"
    )

    assessment_to_standard_edge = ConditionalEdgeConfig(
        source_node_logical_id=assessment_say_node.logical_id,
        destination_node_logical_id=standard_risk_node.logical_id,
        name="Route to Standard Risk",
        description="Routes to standard risk path for low-risk applicants with modest coverage needs.",
        condition=ConditionConfig(condition_expression=STANDARD_RISK_CONDITION.strip()),
    )

    # Condition 1: Premium Client Path
    # High coverage (>= $1M), excellent health (no conditions or mild only), good lifestyle, age < 65,
    # and no known risk factors. Risk-factor applicants are always routed to Elevated.
    # isPresent guard ensures routing waits until the companion has extracted risk_factors.
    PREMIUM_CLIENT_CONDITION = (
        "isPresent([[risk_factors]])"
        " AND ([[coverage_amount]] >= 1000000)"
        " AND ([[age]] < 65)"
        " AND ([[condition_severity]] == 'none' OR [[condition_severity]] == 'mild')"
        " AND ([[lifestyle_score]] >= 75)"
        " AND NOT isNonEmpty([[risk_factors]])"
    )

    assessment_to_premium_edge = ConditionalEdgeConfig(
        source_node_logical_id=assessment_say_node.logical_id,
        destination_node_logical_id=premium_client_node.logical_id,
        name="Route to Premium Client",
        description="Routes high-value, low-risk clients to premium concierge service.",
        condition=ConditionConfig(condition_expression=PREMIUM_CLIENT_CONDITION.strip()),
    )

    # Condition 3: Elevated Risk Path (true catch-all)
    # Fires when all key routing fields are present AND the profile does not qualify
    # for either Standard or Premium. This guarantees exactly-one routing:
    #   Elevated = data_complete AND NOT Premium AND NOT Standard
    # The completeness guard (isPresent checks) prevents premature firing before
    # the companion has extracted all fields the routing logic depends on.
    ELEVATED_RISK_CONDITION = (
        "isPresent([[lifestyle_score]])"
        " AND isPresent([[coverage_amount]])"
        " AND isPresent([[age]])"
        " AND isPresent([[condition_severity]])"
        " AND isPresent([[risk_factors]])"
        # Does not qualify for Premium (mirrors PREMIUM_CLIENT_CONDITION exactly):
        " AND NOT ("
        "   isPresent([[risk_factors]])"
        "   AND ([[coverage_amount]] >= 1000000)"
        "   AND ([[age]] < 65)"
        "   AND ([[condition_severity]] == 'none' OR [[condition_severity]] == 'mild')"
        "   AND ([[lifestyle_score]] >= 75)"
        "   AND NOT isNonEmpty([[risk_factors]])"
        " )"
        # Does not qualify for Standard (mirrors STANDARD_RISK_CONDITION exactly):
        " AND NOT ("
        "   isPresent([[risk_factors]])"
        "   AND ([[age]] < 50)"
        "   AND ([[coverage_amount]] < 500000)"
        "   AND ([[condition_severity]] == 'none' OR [[condition_severity]] == 'mild')"
        "   AND ([[lifestyle_score]] >= 70)"
        "   AND NOT isNonEmpty([[risk_factors]])"
        " )"
    )

    assessment_to_elevated_edge = ConditionalEdgeConfig(
        source_node_logical_id=assessment_say_node.logical_id,
        destination_node_logical_id=elevated_risk_node.logical_id,
        name="Route to Elevated Risk",
        description="Routes to elevated risk path for cases needing additional underwriting review.",
        condition=ConditionConfig(condition_expression=ELEVATED_RISK_CONDITION.strip()),
    )

    ############# WORKFLOW ASSEMBLY BELOW #############

    workflow_config_full = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            assessment_say_node,
            assessment_worker_llm_companion_node,
            standard_risk_node,
            elevated_risk_node,
            premium_client_node,
            end_conversation_node,
        ],
        edge_configs=[
            greeting_to_assessment_edge,
            assessment_companion_edge,
            # Evaluation order: Premium (1) → Standard (2) → Elevated (3).
            # After the mutual exclusivity fix, order is no longer correctness-critical —
            # exactly one condition fires regardless of which is checked first.
            # Order is retained here for readability (most exclusive first, catch-all last).
            assessment_to_premium_edge,  # Condition 1: most exclusive
            assessment_to_standard_edge,  # Condition 2
            assessment_to_elevated_edge,  # Condition 3: catch-all
        ],
    )

    dynamic_variables = {
        "greeting_phrase": "Welcome to our Insurance Risk Assessment Portal!",
        "company_name": "Premier Insurance Group",
        "standard_quote_time": "24 hours",
        "standard_approval_time": "3-5 business days",
        "discount_program": "wellness",
        "premium_approval_time": "48 hours",
        "premium_contact_time": "4 business hours",
        "elevated_contact_time": "48 hours",
        "elevated_approval_time": "2-3 weeks",
        "farewell_message": "Thank you for your interest in our insurance services. We look forward to serving you. Have a great day!",
    }
    print(f"Built workflow config: \n\n{workflow_config_full.model_dump_json(indent=2)}\n\n")
    print(f"Dynamic variables: \n\n{json.dumps(dynamic_variables, indent=2)}\n\n")
    return workflow_config_full, dynamic_variables


async def main():
    workflow_config_full, dynamic_variables = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow_config_full, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    prev_time = time.time()
    elapseds = []
    chat_history = []
    structured_outputs = []  # To collect structured outputs from nodes

    while True:
        print(
            "============================================================================================================================================="
        )
        print(
            "\n\n======================================= Chat History ==================================================================================="
        )
        print(
            "============================================================================================================================================="
        )

        for msg in chat_history:
            print(msg)

        # Display collected structured outputs
        if structured_outputs:
            print("\n" + "=" * 50 + " STRUCTURED OUTPUTS " + "=" * 50)
            for i, output in enumerate(structured_outputs):
                print(f"\nStructured Output #{i+1}:")
                print(json.dumps(output, indent=2))
            print("=" * 120)

        user_input = input("User Input: ")
        chat_history.append(f"\n USER: {user_input} \n")
        prev_time = time.time()
        if user_input.strip() == "<exit>":
            break
        user_message = HumanMessage(content=user_input)
        workflow_input = WorkflowRunInput(
            thread_to_node_inputs={"0": NodesRunInputs(node_run_inputs=[LLMNodeRunInput(messages=[user_message])])},
            dynamic_variables=dynamic_variables,
        )

        loop_count = 0
        async for event in workflow_runtime.arun(workflow_input):
            loop_count += 1
            print(f"\nEvent received: {type(event)}\n{event.model_dump_json(indent=2)}\n")

            if isinstance(event, BusyWaitForUserMessageEvent):
                node_name = event.origin_node_name
                msg = f"\n NODE: {node_name} .. is waiting for user input... \n"
                chat_history.append(msg)

            if isinstance(event, AssistantResponseEvent):
                node_name = event.origin_node_name
                elapsed = time.time() - prev_time
                msg = f"\n ASSISTANT (in {elapsed:.2f} sec) ({node_name}): {event.content} \n"
                chat_history.append(msg)
                elapseds.append(elapsed)
                prev_time = time.time()

            # WorkerLLMNodeEvent fires each time a Worker LLM node runs.
            # Log it so that learners can see when the companion worker is active.
            if isinstance(event, WorkerLLMNodeEvent):
                node_name = event.origin_node_name
                print(f"\n\U0001f916 WORKER LLM NODE EVENT from {node_name}")

            # Surface routing warnings and debug info so expression evaluation failures are visible.
            if isinstance(event, WorkflowWarningEvent):
                print(f"\n⚠️  ROUTING WARNING: {event.warning_message or event.debug_message}")

            if isinstance(event, WorkflowDebugLogEvent):
                print(f"\n🔍 ROUTING DEBUG: {event.debug_message}")

            # Capture structured output from Say LLM nodes
            if (
                isinstance(event, EndRunNodeEvent)
                and hasattr(event.run_output, "structured_output")
                and event.run_output.structured_output
            ):
                node_name = event.origin_node_name
                structured_output = event.run_output.structured_output
                structured_outputs.append(structured_output)
                print(f"\n📋 STRUCTURED OUTPUT CAPTURED from {node_name}:")
                print(json.dumps(structured_output, indent=2))

            if loop_count > 100:  # Add a limit to avoid runaway loops
                print("Quitting because of potential infinite loop")
                break

    # Print performance statistics
    if elapseds:
        elapseds.sort()
        n = len(elapseds)
        median_first_token_time = elapseds[n // 2] if n % 2 == 1 else (elapseds[n // 2 - 1] + elapseds[n // 2]) / 2
        average_first_token_time = sum(elapseds) / n
        percentile_90_first_token_time = elapseds[int(n * 0.9)]
        percentile_99_first_token_time = elapseds[int(n * 0.99)]
        print(f"\nTotal samples: {n}")
        print(f"All samples (sorted): {elapseds}")
        print(
            f"Elapsed First Token Time (ms): Median: {median_first_token_time:.2f}, Average: {average_first_token_time:.2f}, 90th Percentile: {percentile_90_first_token_time:.2f}, 99th Percentile: {percentile_99_first_token_time:.2f}"
        )

    # Print final structured outputs summary
    if structured_outputs:
        print("\n" + "=" * 50 + " FINAL STRUCTURED OUTPUTS SUMMARY " + "=" * 50)
        for i, output in enumerate(structured_outputs):
            print(f"\nStructured Output #{i+1}:")
            print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
