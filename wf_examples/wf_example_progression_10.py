import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 10 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_10.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_10.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SendSMSNodeConfig
from interactly.configs import EndConversationNodeConfig
from interactly.configs import StartConversationNodeConfig
from interactly.configs import LLMNodeRunInput, SayLLMNodeConfig
from interactly.configs import GlobalNodeConfig
from interactly.configs import NodesRunInputs
from interactly.configs import PromptConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a workflow demonstrating StartConversationNodeConfig, EndConversationNodeConfig, and SendSMSNodeConfig.

    This workflow showcases:
    1. Starting a conversation with voice mode disabled
    2. Multi-path conversation routing based on user intent
    3. Ending a conversation with transcript summary extraction
    4. Sending the conversation summary via SMS to a dynamic phone number
    """

    openai_llm_config_nano = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_NANO,
        max_tokens=30,
        temperature=0.5,
        do_not_split_sentences=True,
    )
    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_MINI,
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.fxxpwy7zor7i"
    )

    workflow_description = f"""

    This workflow introduces conversation lifecycle management through specialized nodes that bookend conversations with explicit start and end actions. 
    It demonstrates Start Conversation Node (which configures conversation parameters like voice mode), End Conversation Node (which processes the entire conversation transcript), and Send SMS Node (which sends conversation summaries via SMS). 
    This example shows a complete healthcare assistant workflow that captures the full conversation, extracts a summary, and delivers it to the patient's phone.

    See more details at {google_docs_md_link}

    Dynamic Variables you can use:
        {{
            "recipient_phone_number": "+1234567890",  # Placeholder - should be provided at runtime
        }}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 10: Conversation with SMS Summary",
        description=workflow_description,
        llms_config=openai_llm_config,
        default_prompt_prefix=GLOBAL_PROMPT_PREFIX,
        default_prompt_suffix=GLOBAL_PROMPT_SUFFIX,
        miscellaneous={
            "default_dynamic_variables": {
                "recipient_phone_number": "+1234567890",  # Placeholder - should be provided at runtime
            }
        },
    )

    ############# NODE CONFIGS BELOW #############

    # START CONVERSATION NODE - Voice mode disabled
    start_conversation_node = StartConversationNodeConfig(
        name="Start Conversation",
        description="Initiates the conversation with voice mode disabled",
        is_start=True,
        is_voice_conversation=False,  # Voice mode is DISABLED
    )

    GREETING_NODE_PROMPT = """
    Welcome the user with a friendly message in less than 15 words. Greet them politely and ask them what they would like to ask or talk about.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Welcome node that greets the user with a friendly message",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GREETING_NODE_PROMPT),
        llms_config=openai_llm_config_nano,
    )

    ROUTER_PROMPT = """
    You are a friendly "routing" agent whose specific role is to route to one of the other agent nodes in the system. 
    Until you are able to ascertain the intent of the user, ask them politely for their intent and continue the conversation to gather more information.

    Take the appropriate path to route to the correct agent when the user's intent matches one of the available paths.
    If the user has clearly specified their intent, but it does not match with any of the paths, just reply politely that their intent is not supported by the system.

    You support only the intents which are related to insurance, scheduling appointments or payments.
    """

    router_node = SayLLMNodeConfig(
        name="Router Node",
        description="Router node that directs user queries to the appropriate assistant nodes",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=ROUTER_PROMPT),
    )

    INSURANCE_CHATBOT_PROMPT = """
    You are a friendly "CignaCare Insurance Agent" whose specific role is to provide compliant, professional, and helpful AI support for Cigna and Evernorth Health Services.

    ==================================================
    1. PURPOSE
    ==================================================
    You assist Cigna members, patients, and caregivers by:
    - Explaining health insurance terms, benefits, coverage, and claims.
    - Guiding users to official Cigna resources and contact channels.
    - Helping users understand plan features (deductibles, copays, prior authorization, in-network vs. out-of-network).
    - Assisting with finding providers, understanding ID cards, and navigating Cigna's website or mobile app.
    - Offering general wellness and preventive-care information that aligns with Cigna's publicly available materials.

    You are **NOT**:
    - A licensed insurance agent or medical professional.
    - A replacement for Cigna customer service or a healthcare provider.
    - A source for topics unrelated to Cigna insurance, healthcare, or wellness.

    Reject all questions about irrelevant or unrelated topics (e.g., sports, politics, entertainment, math problems, celebrity news, general trivia).
    """

    insurance_chatbot_node = SayLLMNodeConfig(
        name="Insurance ChatBot",
        description="Insurance chatbot that answers user queries about insurance policies and claims",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=INSURANCE_CHATBOT_PROMPT),
    )

    SCHEDULING_CHATBOT_PROMPT = """
    You are a friendly "CignaProvider Scheduling Agent" whose specific role is to provide compliant, secure, and concise scheduling support for Cigna Provider Services.

    ==================================================
    1. PURPOSE
    ==================================================
    You help providers and patients manage appointments within Cigna's healthcare network by:
    - Scheduling new appointments.
    - Rescheduling existing appointments.
    - Canceling appointments.
    - Providing appointment confirmation details.
    - Answering questions about scheduling policies and procedures.

    You are **NOT**:
    - A medical professional or insurance claims specialist.
    - A replacement for direct provider communication for urgent matters.
    - Able to access or modify actual appointment systems (you simulate the process).
    """

    scheduling_chatbot_node = SayLLMNodeConfig(
        name="Scheduling ChatBot",
        description="Scheduling chatbot that helps users book, reschedule, or cancel appointments",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=SCHEDULING_CHATBOT_PROMPT),
    )

    PAYMENT_CHATBOT_PROMPT = """
    You are a friendly "CignaCare Payment Agent" whose specific role is to provide compliant, secure, and concise payment support for Cigna Health Services.

    ==================================================
    1. PURPOSE
    ==================================================
    You assist users with payment-related inquiries by:
    - Explaining billing statements and invoices.
    - Guiding users through payment processes.
    - Answering questions about payment plans and options.
    - Helping users understand co-pays, deductibles, and out-of-pocket costs.
    - Directing users to official payment portals and customer service.

    You are **NOT**:
    - Able to process actual payments or access account balances.
    - A replacement for official customer service for disputes or complex billing issues.
    - A source for medical or insurance coverage advice.
    """

    payment_chatbot_node = SayLLMNodeConfig(
        name="Payment ChatBot",
        description="Payment chatbot that assists with billing, payments, and invoices",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=PAYMENT_CHATBOT_PROMPT),
    )

    # END CONVERSATION NODE - With transcript processing and global routing.
    # [[transcript]] is the runtime variable containing the full conversation transcript.
    # It can be dynamically put in the prompt as shown below by enclosing it in double square brackets.
    END_CONVERSATION_SUMMARY_PROMPT = """
    You are a conversation summarization specialist. Your task is to extract a concise, informative summary from the conversation transcript below.

    The summary should:
    1. Capture the main topics discussed
    2. Highlight key information exchanged
    3. Note any actions taken or decisions made
    4. Be clear and professional
    5. Be no longer than 3-4 sentences

    Below is the Raw Conversation Transcript with user and assistant turns.
    [[raw_conversation_transcript]]

    Provide only the summary without any additional commentary or formatting.
    """

    END_CONVERSATION_GLOBAL_EDGE_CONDITION = """
    Trigger this edge when the user says goodbye, farewell, wants to exit the conversation, or indicates they are done with the conversation.
    Examples of such user inputs include:
    - "That's all for now, thank you."
    - "Goodbye!"
    - "I don't have any more questions. Thanks!"
    """

    end_conversation_node = EndConversationNodeConfig(
        name="End Conversation",
        description="Ends the conversation and extracts a summary of the entire conversation",
        process_transcript_prompt=PromptConfig(prompt=END_CONVERSATION_SUMMARY_PROMPT),
        process_transcript_llms_config=openai_llm_config,
        global_node_config=GlobalNodeConfig(
            is_global=True, condition=ConditionConfig(condition_freeform=END_CONVERSATION_GLOBAL_EDGE_CONDITION)
        ),
    )

    # SEND SMS NODE - Sends summary to dynamic phone number
    send_sms_node = SendSMSNodeConfig(
        name="Send Summary via SMS",
        description="Sends the conversation summary to the provided phone number via SMS",
        destination_phone_number="{{recipient_phone_number}}",  # Dynamic variable
        message="Conversation Summary: [[processed_transcript]]",  # Runtime variable from end_conversation_node
        disabled=True,  # Disable SMS sending for testing purposes
    )

    ############# EDGE CONFIGS BELOW #############

    # From Start Conversation to Greeting
    start_to_greeting_edge = DirectEdgeConfig(
        source_node_logical_id=start_conversation_node.logical_id,
        destination_node_logical_id=greeting_node.logical_id,
        name="Start to Greeting",
        description="After starting the conversation, proceed to the greeting node.",
    )

    # From Greeting to Router
    greeting_to_router_edge = DirectEdgeConfig(
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=router_node.logical_id,
        name="Go to Router Node",
        description="After greeting the user, go to the router node to determine user intent.",
    )

    # Router to Insurance
    ROUTER_TO_INSURANCE_CONDITION = """
    Take this path to route to an internal insurance agent. Take this path only when it is clear that the user wants help with insurance.
    """
    router_to_insurance_chatbot_edge = ConditionalEdgeConfig(
        source_node_logical_id=router_node.logical_id,
        destination_node_logical_id=insurance_chatbot_node.logical_id,
        name="Insurance ChatBot",
        description="Routes the call from the router node to the insurance chatbot.",
        condition=ConditionConfig(condition_freeform=ROUTER_TO_INSURANCE_CONDITION),
    )

    # Router to Scheduling
    ROUTER_TO_SCHEDULING_CONDITION = """
    Take this path to route to an internal scheduling agent. Take this path only when it is clear that the user wants help with scheduling appointments.
    """
    router_to_scheduling_chatbot_edge = ConditionalEdgeConfig(
        source_node_logical_id=router_node.logical_id,
        destination_node_logical_id=scheduling_chatbot_node.logical_id,
        name="Scheduling ChatBot",
        description="Routes the call from the router node to the scheduling chatbot.",
        condition=ConditionConfig(condition_freeform=ROUTER_TO_SCHEDULING_CONDITION),
    )

    # Router to Payment
    ROUTER_TO_PAYMENT_CONDITION = """
    Take this path to route to an internal payment agent. Take this path only when it is clear that the user wants help with billing, payments or invoices.
    """
    router_to_payment_chatbot_edge = ConditionalEdgeConfig(
        source_node_logical_id=router_node.logical_id,
        destination_node_logical_id=payment_chatbot_node.logical_id,
        name="Payment ChatBot",
        description="Routes the call from the router node to the payment chatbot.",
        condition=ConditionConfig(condition_freeform=ROUTER_TO_PAYMENT_CONDITION),
    )

    # From End Conversation to Send SMS
    end_to_sms_edge = DirectEdgeConfig(
        source_node_logical_id=end_conversation_node.logical_id,
        destination_node_logical_id=send_sms_node.logical_id,
        name="Send Summary SMS",
        description="After ending the conversation and extracting summary, send it via SMS.",
    )

    ############# WORKFLOW ASSEMBLY BELOW #############

    workflow_config_full = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            start_conversation_node,
            greeting_node,
            router_node,
            insurance_chatbot_node,
            scheduling_chatbot_node,
            payment_chatbot_node,
            end_conversation_node,
            send_sms_node,
        ],
        edge_configs=[
            start_to_greeting_edge,
            greeting_to_router_edge,
            router_to_insurance_chatbot_edge,
            router_to_scheduling_chatbot_edge,
            router_to_payment_chatbot_edge,
            end_to_sms_edge,
        ],
    )

    return workflow_config_full


async def main():
    """
    Main function to test the workflow.

    This demonstrates:
    1. Starting a conversation with voice mode disabled
    2. Routing between different specialized chatbots
    3. Ending the conversation when user says goodbye
    4. Extracting a conversation summary
    5. Sending the summary via SMS to a dynamic phone number
    """
    workflow_config_full = build_assistant_workflow()
    # The workflow seeds these on upload; read them back so each turn sends the same values.
    dynamic_variables = workflow_config_full.workflow_config.miscellaneous.get(
        "default_dynamic_variables", {}
    )
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow_config_full, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    prev_time = time.time()
    elapseds = []
    chat_history = []

    print("\n" + "=" * 120)
    print("EXAMPLE 10: Conversation with SMS Summary")
    print("=" * 120)
    print("\nThis workflow demonstrates:")
    print("1. StartConversationNodeConfig with voice mode DISABLED")
    print("2. Multi-path routing (Insurance, Scheduling, Payment)")
    print("3. EndConversationNodeConfig that extracts a conversation summary")
    print("4. SendSMSNodeConfig that sends the summary to a dynamic phone number")
    print("\nTo exit and trigger SMS summary, type: goodbye")
    print("=" * 120 + "\n")

    while True:
        print("=" * 120)
        print("\n======================================= Chat History =======================================")
        print("=" * 120)

        for msg in chat_history:
            print(msg)
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
            print(f"\nEvent received: {type(event).__name__}\n{event.model_dump_json(indent=2)}\n")

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
        print(f"\n{'='*120}")
        print("PERFORMANCE STATISTICS")
        print(f"{'='*120}")
        print(f"Total samples: {n}")
        print(f"All samples (sorted): {elapseds}")
        print(
            f"Response Time (sec): Median: {median_first_token_time:.2f}, Average: {average_first_token_time:.2f}, "
            f"90th Percentile: {percentile_90_first_token_time:.2f}, 99th Percentile: {percentile_99_first_token_time:.2f}"
        )
        print(f"{'='*120}\n")


if __name__ == "__main__":
    asyncio.run(main())
