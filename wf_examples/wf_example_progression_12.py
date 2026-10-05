import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 12 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_12.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_12.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

import json

from interactly.configs import CompanionEdgeConfig, ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import ConditionConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig, WorkerLLMNodeConfig
from interactly.configs import (
    BodyContentTypeEnum,
    HttpMethodEnum,
    HttpRequestNodeConfig,
    ResponseFormatEnum,
)
from interactly.configs import PromptConfig
from interactly.configs import GlobalNodeConfig, SayStaticMessageNodeConfig, StaticMessagesConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import (
    AssistantResponseEvent,
    BusyWaitForUserMessageEvent,
    EndRunNodeEvent,
    HttpRequestNodeEvent,
)
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a workflow that demonstrates HttpRequestNodeConfig — a dedicated node that makes an
    HTTP call to an external REST API as a deterministic workflow step.

    Key concepts introduced in this example:
    1. HttpRequestNodeConfig — configure method, URL, headers, body, timeout, and response format
    2. HttpRequestNodeEvent — a specialised event emitted when the HTTP node runs, carrying
       curl_command, status_code, and response_body for observability
    3. Chaining: SayLLM (collect input) → HttpRequestNode (fetch data) → SayLLM (present result)
    4. Dynamic URL construction using {{dynamic_variables}} and [[runtime_variables]]
    5. result_runtime_variable_name — stores the parsed JSON response for downstream nodes
    """

    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=8192,
        temperature=0.2,
        do_not_split_sentences=True,
        # Say nodes stream, so a voice call speaks the first sentence while the rest is written.
        streaming=True,
    )
    worker_openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=8192,
        temperature=0.0,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_description = f"""
    This workflow introduces HttpRequestNodeConfig — a node that sends an HTTP request to an external
    REST API without requiring an LLM to decide. It is the preferred way to integrate external data
    sources when the call should happen unconditionally at a known point in the workflow.

    The example workflow is a simple "drug information lookup" assistant that:
      1. Greets the user and asks for a drug name.
      2. Calls the public Open FDA drug API (no auth required) to look up the drug.
      3. An LLM reads the response (stored in [[fda_drug_result]]) and summarises the key facts.

    HTTP-node features demonstrated:
      - GET request with a query parameter built from a runtime variable
      - JSON response format with result stored in a named runtime variable
      - HttpRequestNodeEvent observation: curl_command, status_code, response_body
      - Timeout configuration to avoid stalling the workflow

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 12: REST API Calls with HttpRequestNodeConfig",
        description=workflow_description,
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the user and ask: "What medication or drug name would you like to look up?"
    Keep the greeting under 20 words.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Greets the user and asks for a drug name to look up",
        is_start=True,
        self_loop=False,
        # Speaks first; the node below waits for the answer and asks again until it has a drug name.
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    # The lookup needs a drug name, so a speaking node asks until there is one while a silent companion
    # (as in Example 6) extracts it; an expression moves on once it is known, and the HTTP node below
    # puts it into its query.
    ASK_DRUG_PROMPT = """
    You are finding out which medication the person wants information about. If they have not named one,
    ask for the name in one short sentence. If they have, say you will look it up now. Do not describe the
    drug yourself.
    """
    ask_drug_node = SayLLMNodeConfig(
        name="Ask Drug Name",
        description="Asks for the drug name until one is given",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASK_DRUG_PROMPT),
        llms_config=openai_llm_config,
    )
    drug_name_extractor_node = WorkerLLMNodeConfig(
        name="Drug Name Extractor",
        description="Silently extracts the drug name the person asked about",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=""),
        structured_output_schema={
            "name": "DrugLookupRequest",
            "description": "The medication the person wants looked up. Leave it empty until they name one.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "drug_name": {
                        "type": "string",
                        "description": "The drug's name as the person said it, brand or generic, lower case, spelling corrected",
                    }
                },
                "required": [],
            },
        },
        llms_config=worker_openai_llm_config,
    )

    # HttpRequestNodeConfig: makes a GET request to the Open FDA drug endpoint.
    #
    # The URL uses the runtime variable [[drug_name_query]] which would typically be
    # populated by a preceding WorkerLLMNode that extracted the drug name from the user's
    # message into a structured field. For this illustration we hard-code a fallback URL.
    #
    # Key fields:
    #   url            — The full URL. Can interpolate {{dynamic}} and [[runtime]] variables.
    #   method         — HttpMethodEnum (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
    #   headers        — Optional dict of HTTP headers (e.g. authorization tokens)
    #   query_parameters — URL query string as a JSON-serialised string (can use [[variables]])
    #   body_parameters  — Request body for POST/PUT/PATCH (JSON-serialised string)
    #   body_content_type — BodyContentTypeEnum (JSON, FORM, MULTIPART, TEXT)
    #   response_format  — ResponseFormatEnum (json, text, binary)
    #   timeout          — seconds; default 30, max 300
    #   result_runtime_variable_name — runtime key where the parsed response is stored
    fda_lookup_node = HttpRequestNodeConfig(
        name="FDA Drug Lookup",
        description="Calls the public Open FDA API to fetch drug information. "
        "No authentication required for public endpoints.",
        url="https://api.fda.gov/drug/label.json",
        method=HttpMethodEnum.GET,
        headers={
            # No auth needed for the public Open FDA API. For protected APIs, add:
            # "Authorization": "Bearer {{api_token}}"  ← dynamic var injected at runtime
        },
        # query_parameters is a JSON string; Interactly will URL-encode and append it.
        # [[drug_name]] is what the companion above extracted. openFDA treats the space between the two
        # clauses as OR, so a brand name ("advil") and a generic one ("ibuprofen") both find a label.
        query_parameters=json.dumps(
            {"search": 'openfda.brand_name:"[[drug_name]]" openfda.generic_name:"[[drug_name]]"', "limit": 1}
        ),
        body_parameters=None,
        body_content_type=BodyContentTypeEnum.JSON,
        response_format=ResponseFormatEnum.JSON,
        timeout=15,
        result_runtime_variable_name="fda_drug_result",
    )

    # SayLLM that reads [[fda_drug_result]] and presents a concise summary.
    DRUG_INFO_PROMPT = """
    The following JSON was returned by the Open FDA drug label API:
        [[fda_drug_result]]

    Summarise the drug information for the user. Include:
    - Brand name and generic name (if available)
    - Main indications (what the drug is used for)
    - Key warnings or contraindications (one or two bullet points maximum)

    Use plain language. Keep the summary under 6 sentences.
    If the JSON is empty or indicates no results, tell the user politely that no information was found for
    [[drug_name]] and suggest they check the spelling.
    """
    drug_info_node = SayLLMNodeConfig(
        name="Drug Information",
        description="Reads the FDA API response from the runtime variable and explains it to the user",
        # Speaks as soon as the lookup returns; a node that waited here would stay silent until the
        # person spoke again.
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + DRUG_INFO_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    FOLLOW_UP_PROMPT = """
    You have summarised this FDA drug label for the person:
        [[fda_drug_result]]

    Answer follow-up questions about it from the label only, in two or three sentences, and suggest a
    pharmacist or doctor for anything the label does not cover. When they say goodbye or have no more
    questions, wish them well briefly.
    When the person says goodbye, or that they have everything they need, do not say goodbye yourself: take the path that ends the conversation, which says the goodbye for you.
    """
    follow_up_node = SayLLMNodeConfig(
        name="Follow-up Questions",
        description="Answers questions about the drug label",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + FOLLOW_UP_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    # A call can only hang up from a node that ends the conversation, and a voice call that cannot hang up
    # answers every goodbye with another goodbye. Global, so the caller can leave from any point.
    end_conversation_node = SayStaticMessageNodeConfig(
        name="End Conversation",
        description="Says goodbye and ends the conversation",
        static_messages_config=StaticMessagesConfig(static_messages=["Thanks for calling. For anything the label does not cover, a pharmacist can help. Goodbye!"]),
        global_node_config=GlobalNodeConfig(
            is_global=True,
            condition=ConditionConfig(
                condition_freeform="Take this path when the person says goodbye or that they have no more questions."
            ),
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    edge_greeting_to_ask = DirectEdgeConfig(
        name="Greeting → Ask Drug Name",
        description="After the greeting, wait for the drug name",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=ask_drug_node.logical_id,
    )

    edge_ask_companion = CompanionEdgeConfig(
        name="Ask Drug Name companion",
        description="Extracts the drug name from every caller turn",
        source_node_logical_id=ask_drug_node.logical_id,
        destination_node_logical_id=drug_name_extractor_node.logical_id,
    )

    edge_ask_to_fda = ConditionalEdgeConfig(
        name="Ask Drug Name → FDA Lookup",
        description="Once a drug name is known, run the HTTP lookup node",
        source_node_logical_id=ask_drug_node.logical_id,
        destination_node_logical_id=fda_lookup_node.logical_id,
        condition=ConditionConfig(condition_expression="isNonEmpty([[drug_name]])"),
    )

    edge_fda_to_drug_info = DirectEdgeConfig(
        name="FDA Lookup → Drug Information",
        description="Once the HTTP call completes, present the result to the user",
        source_node_logical_id=fda_lookup_node.logical_id,
        destination_node_logical_id=drug_info_node.logical_id,
    )

    edge_drug_info_to_follow_up = DirectEdgeConfig(
        name="Drug Information → Follow-up",
        description="After the summary, answer any follow-up questions",
        source_node_logical_id=drug_info_node.logical_id,
        destination_node_logical_id=follow_up_node.logical_id,
    )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            ask_drug_node,
            drug_name_extractor_node,
            fda_lookup_node,
            drug_info_node,
            follow_up_node,
            end_conversation_node,
        ],
        edge_configs=[
            edge_greeting_to_ask,
            edge_ask_companion,
            edge_ask_to_fda,
            edge_fda_to_drug_info,
            edge_drug_info_to_follow_up,
        ],
    )

    return workflow


async def run():
    """
    Minimal REPL for manual testing.

    Conversation flow:
      1. Greeting asks for a drug name.
      2. User replies → workflow proceeds to HttpRequestNode (unconditional GET).
      3. HttpRequestNodeEvent fires with curl_command, status_code, and response_body.
      4. result is stored in [[fda_drug_result]]; LLM node reads and summarises it.
    """
    workflow = build_assistant_workflow()
    # The workflow seeds these on upload; read them back so each turn sends the same values.
    dynamic_variables = workflow.workflow_config.miscellaneous.get("default_dynamic_variables", {})
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    inputs_queue = [
        "aspirin",
        "What are the main side effects I should watch out for?",
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

        elif isinstance(event, HttpRequestNodeEvent):
            # HttpRequestNodeEvent is the dedicated event type for HTTP nodes.
            # It carries observability data without needing to inspect EndRunNodeEvent.
            status = event.status_code or "N/A"
            ok = "✅" if (event.status_code and 200 <= event.status_code < 300) else "❌"
            print(f"\n{ok} [HTTP Node '{event.origin_node_name}'] status={status}")
            if event.curl_command:
                print(f"   curl: {event.curl_command[:120]}...")
            if event.error:
                print(f"   error: {event.error}")

        elif isinstance(event, EndRunNodeEvent):
            # Fallback: inspect any other node completion (e.g. LLM nodes)
            pass

    elapsed = time.time() - start_time
    print(f"\n⏱️  Total run time: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(run())
