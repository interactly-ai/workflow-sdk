import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 4 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_4.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_4.py
"""

import asyncio
import json
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import LLMNodeRunInput, SayLLMNodeConfig, WorkerLLMNodeConfig
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
        temperature=0.0,
        do_not_split_sentences=True,
    )
    worker_openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=1000,
        temperature=0.0,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.cozmsi1dywfp"
    )

    workflow_description = f"""
    This workflow introduces Worker LLM agents - AI agents that perform tasks in the background without directly communicating with the user.
    Unlike conversational "Say LLM" agents, the output of Worker LLM agents is not sent directly to the user. 
    In this example, we demonstrate how Worker LLM agents can be used to extract structured information from user interactions.
    This workflow demonstrates a healthcare patient intake process that collects structured information.

    See more details at {google_docs_md_link}

    Dynamic Variables you can use:
        {{
            "greeting_phrase": "Hello and welcome!",
            "organization_name": "HealthFirst Medical Center",
            "emergency_number": "911",
            "high_urgency_response_time": "2 hours",
            "medium_urgency_response_time": "24 hours",
            "low_urgency_response_time": "48 hours",
            "closing_message": "Your health is our priority, and we're here to help.",
            "farewell_message": "Thank you for providing your information. We'll be in touch soon. Have a great day!"
        }}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 4: Structured Output with Worker LLM",
        description=workflow_description,
        default_prompt_prefix=GLOBAL_PROMPT_PREFIX,
        default_prompt_suffix=GLOBAL_PROMPT_SUFFIX,
        # miscellaneous={"debug_mode": "true"},
        miscellaneous={
            "default_dynamic_variables": {
                "greeting_phrase": "Hello and welcome!",
                "organization_name": "HealthFirst Medical Center",
                "emergency_number": "911",
                "high_urgency_response_time": "2 hours",
                "medium_urgency_response_time": "24 hours",
                "low_urgency_response_time": "48 hours",
                "closing_message": "Your health is our priority, and we're here to help.",
                "farewell_message": "Thank you for providing your information. We'll be in touch soon. Have a great day!",
            }
        },
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_NODE_PROMPT = """
    Welcome the user with a friendly message in less than 15 words. Ask them to provide their basic information for a healthcare intake form.
    Use the greeting phrase: {{greeting_phrase}}
    Mention that we are from {{organization_name}}.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Welcome node that greets the user and asks for healthcare intake information",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GREETING_NODE_PROMPT),
        llms_config=openai_llm_config_nano,
    )

    # Define the structured output schema for patient intake information
    PATIENT_INTAKE_SCHEMA_AS_DICT = {
        "name": "PatientIntakeForm",
        "description": "Extract structured patient information based on the chat history so far. If any information is missing, do not populate that field. Do not make assumptions. Only fill in what has been explicitly provided by the patient.",
        "input_schema": {
            "title": "PatientIntakeData",
            "type": "object",
            "properties": {
                "full_name": {
                    "title": "Full Name",
                    "type": "string",
                    "description": "Patient's complete name (first and last)",
                },
                "age": {"title": "Age", "type": "integer", "description": "Patient's age in years"},
                "primary_complaint": {
                    "title": "Primary Complaint",
                    "type": "string",
                    "description": "Main health concern or reason for visit",
                },
                "urgency_level": {
                    "title": "Urgency Level",
                    "type": "string",
                    "enum": ["low", "medium", "high", "emergency"],
                    "description": "Assessed urgency level based on symptoms",
                },
                "has_insurance": {
                    "title": "Has Insurance",
                    "type": "boolean",
                    "description": "Whether the patient has health insurance",
                },
                "preferred_contact": {
                    "title": "Preferred Contact Method",
                    "type": "string",
                    "enum": ["phone", "email", "text", "portal"],
                    "description": "Patient's preferred method of communication",
                },
            },
            "required": [],
        },
    }

    # INTAKE_WORKER_PROMPT is intentionally left empty here.
    # When a WorkerLLMNodeConfig has a structured_output_schema, the model uses
    # the schema's field names, types, and descriptions as its implicit instructions.
    # The schema itself tells the model what data to extract from the conversation.
    # In production you may add explicit instructions here (e.g. "Extract the following
    # fields from the conversation...") to improve accuracy for complex extraction tasks.
    INTAKE_WORKER_PROMPT = """
    """

    intake_worker_node = WorkerLLMNodeConfig(
        name="Patient Intake Worker",
        description="Worker LLM node that extracts structured patient information from user input",
        self_loop=True,  # Can loop to ask follow-up questions
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=INTAKE_WORKER_PROMPT),
        llms_config=worker_openai_llm_config,
        structured_output_schema=PATIENT_INTAKE_SCHEMA_AS_DICT,
    )

    SUMMARY_NODE_PROMPT = """
    You are a summarization agent whose specific role is to provide a concise and friendly summary of the patient intake information collected.

    Based on the patient intake information that was just collected, provide a friendly summary of what was captured.
    Thank the patient and let them know what the next steps will be based on their urgency level.

    For emergency cases: Direct them to call {{emergency_number}} or go to the nearest emergency room immediately.
    For high urgency: Let them know they'll be contacted within {{high_urgency_response_time}}.
    For medium urgency: Let them know they'll be contacted within {{medium_urgency_response_time}}.
    For low urgency: Let them know they'll be contacted within {{low_urgency_response_time}}.

    Keep the response warm, professional, and reassuring.
    End with: {{closing_message}}
    """

    summary_node = SayLLMNodeConfig(
        name="Intake Summary",
        description="Provides a summary of the collected intake information and next steps",
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=SUMMARY_NODE_PROMPT),
        llms_config=openai_llm_config,
    )

    end_conversation_node = SayStaticMessageNodeConfig(
        name="End Conversation",
        description="Ends the conversation with a thank you message",
        static_messages_config=StaticMessagesConfig(static_messages=["{{farewell_message}}"]),
    )

    ############# EDGE CONFIGS BELOW #############

    greeting_to_intake_edge = DirectEdgeConfig(
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=intake_worker_node.logical_id,
        name="Go to Patient Intake",
        description="After greeting, route to the intake worker to collect patient information.",
    )

    INTAKE_TO_SUMMARY_CONDITION_FREEFORM = """
    Trigger this to route to the internal summary agent right after you have collected sufficient information to fill out the patient intake form.
    Specifically, trigger when the fields 'full_name' and 'primary_complaint' have been filled in the structured output.
    """

    intake_to_summary_edge = ConditionalEdgeConfig(
        source_node_logical_id=intake_worker_node.logical_id,
        destination_node_logical_id=summary_node.logical_id,
        name="Go to Summary",
        description="Routes from intake worker to summary when information is complete.",
        condition=ConditionConfig(condition_freeform=INTAKE_TO_SUMMARY_CONDITION_FREEFORM),
    )

    summary_to_end_edge = DirectEdgeConfig(
        source_node_logical_id=summary_node.logical_id,
        destination_node_logical_id=end_conversation_node.logical_id,
        name="End Conversation",
        description="After providing summary, end the conversation.",
    )

    ############# WORKFLOW ASSEMBLY BELOW #############

    workflow_config_full = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            intake_worker_node,
            summary_node,
            end_conversation_node,
        ],
        edge_configs=[
            greeting_to_intake_edge,
            intake_to_summary_edge,
            summary_to_end_edge,
        ],
    )

    dynamic_variables = {
        "greeting_phrase": "Hello and welcome!",
        "organization_name": "HealthFirst Medical Center",
        "emergency_number": "911",
        "high_urgency_response_time": "2 hours",
        "medium_urgency_response_time": "24 hours",
        "low_urgency_response_time": "48 hours",
        "closing_message": "Your health is our priority, and we're here to help.",
        "farewell_message": "Thank you for providing your information. We'll be in touch soon. Have a great day!",
    }
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
    structured_outputs = []  # To collect structured outputs from worker nodes

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

            # Capture structured output from Worker LLM nodes
            if isinstance(event, WorkerLLMNodeEvent):
                node_name = event.origin_node_name
                print(f"\n🤖 WORKER LLM NODE EVENT from {node_name}")

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
        print(f"\n" + "=" * 50 + " FINAL STRUCTURED OUTPUTS SUMMARY " + "=" * 50)
        for i, output in enumerate(structured_outputs):
            print(f"\nStructured Output #{i+1}:")
            print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
