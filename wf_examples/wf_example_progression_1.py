import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 1 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_1.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_1.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly import AsyncWorkflowClient, aupload_and_get_handle
from interactly.configs import (
    ConditionConfig,
    ConditionalEdgeConfig,
    DirectEdgeConfig,
    LLMNodeRunInput,
    NodesRunInputs,
    OPENAIModel,
    OpenAILLMConfig,
    PromptConfig,
    SayLLMNodeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
    WorkflowRunInput,
)
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent

from _shared_sdk import get_async_client


def build_assistant_workflow():
    openai_llm_config_nano = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4_NANO,
        max_tokens=30,
        temperature=0.5,
        do_not_split_sentences=True,
    )
    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=300,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_description = f"""
    This workflow demonstrates a simple insurance chatbot that greets the user and provides helpful information about Cigna health insurance services. 
    It represents the foundational building block of conversational AI workflows, showcasing a basic structure with a greeting, a conversational assistant, and a natural conversation ending.

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 1: Insurance ChatBot",
        description=workflow_description,
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_NODE_PROMPT = """
    Welcome the user with a friendly message in less than 15 words. Greet them politely and ask them what they would like to ask or talk about.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Welcome node that greets the user with a friendly message",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GREETING_NODE_PROMPT),
        llms_config=openai_llm_config_nano,
    )

    INSURANCE_CHATBOT_PROMPT = """
        You are "CignaCare Assistant," a compliant, professional, and helpful AI support chatbot for Cigna and Evernorth Health Services.

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

    ==================================================
    GLOBAL REMINDER (APPLIES TO EVERY RESPONSE)
    ==================================================
    You are an AI assistant for **Cigna/Evernorth**.
    - Stay strictly within healthcare insurance and wellness support topics.
    - Follow all safety, privacy, and compliance rules.
    - Encourage professional medical or customer service contact for personal, urgent, or complex matters.
    - Refuse to answer questions unrelated to Cigna or healthcare.
    - Keep your responses concise, clear, and professional.
    - Never output more than 3 sentences at a time.
    - Always ask if the user has any other questions after answering.
    """

    insurance_chatbot_node = SayLLMNodeConfig(
        name="Insurance ChatBot",
        description="Insurance chatbot that answers user queries about insurance policies and claims",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=INSURANCE_CHATBOT_PROMPT),
        llms_config=openai_llm_config,
    )

    end_conversation_node = SayStaticMessageNodeConfig(
        name="End Conversation",
        description="Ends the conversation with a thank you message",
        static_messages_config=StaticMessagesConfig(
            static_messages=["Thank you for chatting with CignaCare Assistant. Have a great day!"]
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    greeting_to_insurance_chatbot_edge = DirectEdgeConfig(
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=insurance_chatbot_node.logical_id,
        name="Go to Insurance ChatBot",
        description="After starting the conversation, route to the insurance chatbot for assistance.",
    )

    INSURANCE_CHATBOT_TO_END_CONVERSATION_EDGE_CONDITION = """
    Take this path if the user indicates they want to end the conversation or says goodbye.
    Examples of such user inputs include:
    - "That's all for now, thank you."
    - "Goodbye!"
    - "I don't have any more questions. Thanks!"
    """

    insurance_chatbot_to_end_conversation_edge = ConditionalEdgeConfig(
        source_node_logical_id=insurance_chatbot_node.logical_id,
        destination_node_logical_id=end_conversation_node.logical_id,
        name="End Conversation",
        description="Routes the call from the insurance chatbot to the end conversation node.",
        condition=ConditionConfig(condition_freeform=INSURANCE_CHATBOT_TO_END_CONVERSATION_EDGE_CONDITION),
    )

    ############# WORKFLOW ASSEMBLY BELOW #############

    workflow_config_full = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            insurance_chatbot_node,
            end_conversation_node,
        ],
        edge_configs=[
            greeting_to_insurance_chatbot_edge,
            insurance_chatbot_to_end_conversation_edge,
        ],
    )

    return workflow_config_full


async def main():
    workflow_config_full = build_assistant_workflow()
    # The workflow seeds these on upload; read them back so each turn sends the same values.
    dynamic_variables = workflow_config_full.workflow_config.miscellaneous.get(
        "default_dynamic_variables", {}
    )

    client: AsyncWorkflowClient = get_async_client()
    handle = await aupload_and_get_handle(
        client,
        workflow_config_full,
        dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={handle.workflow_id}")

    prev_time = time.time()
    elapseds: list[float] = []
    chat_history: list[str] = []
    while True:
        print("=" * 141)
        print("\n\n======================================= Chat History " + "=" * 87)
        print("=" * 141)

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
        async for event in handle.arun(workflow_input):
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

            if loop_count > 100:
                print("Quitting because of potential infinite loop")
                break

    if elapseds:
        elapseds.sort()
        n = len(elapseds)
        median_first_token_time = elapseds[n // 2] if n % 2 == 1 else (elapseds[n // 2 - 1] + elapseds[n // 2]) / 2
        average_first_token_time = sum(elapseds) / n
        percentile_90_first_token_time = elapseds[int(n * 0.9)]
        percentile_99_first_token_time = elapseds[int(n * 0.99)]
        print(f"Total samples: {n}")
        print(f"All samples (sorted): {elapseds}")
        print(
            f"Elapsed First Token Time (ms): Median: {median_first_token_time:.2f}, "
            f"Average: {average_first_token_time:.2f}, "
            f"90th Percentile: {percentile_90_first_token_time:.2f}, "
            f"99th Percentile: {percentile_99_first_token_time:.2f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
