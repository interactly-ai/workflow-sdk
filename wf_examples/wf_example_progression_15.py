import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 15 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_15.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_15.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import PromptConfig, StaticMessagesConfig
from interactly.configs import ExternalAPIToolConfig, KnowledgeBaseToolConfig, ToolsConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a workflow that demonstrates two LLM-invoked tool types:

    1. ExternalAPIToolConfig — the LLM can call an external REST endpoint when it decides
       the user needs data from that API (e.g. a claims-status lookup).
    2. KnowledgeBaseToolConfig — the LLM can query one or more vector-store knowledge bases
       (RAG) to retrieve relevant document chunks and ground its answer.

    Both tool types are registered on the node's ToolsConfig. The LLM decides at runtime
    which tool to call (or whether to call any) based on the user's query.

    Key concepts introduced in this example:
    - ExternalAPIToolConfig fields: api_endpoint, api_method, api_headers, api_body
    - KnowledgeBaseToolConfig fields: target_knowledge_base_ids, result_runtime_variable_name
    - StaticMessagesConfig on tools: what to say to the user while a tool is executing
    - Combining both tool types in a single ToolsConfig on one LLM node
    """

    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=400,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_description = f"""
    This workflow introduces two LLM-invoked tool types:

    ExternalAPIToolConfig — lets the LLM call an external REST API. Useful for:
      - Real-time data lookups (claims status, member eligibility, appointment slots)
      - CRM / EHR write-back operations
      - Third-party service integrations (payments, scheduling, notifications)

    KnowledgeBaseToolConfig — lets the LLM perform a semantic search over one or more
    Qdrant-backed knowledge bases (RAG). Useful for:
      - Grounding answers in official documentation, policy PDFs, or FAQs
      - Reducing hallucinations by providing verified retrieved context
      - Multi-KB queries (e.g., query both a product KB and a regulatory KB)

    Both tool types are registered on the same LLM node. The LLM decides at runtime
    which tool to invoke based on the user's request and the tool signatures.

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 15: ExternalAPIToolConfig and KnowledgeBaseToolConfig",
        description=workflow_description,
        # Seed the workflow with default values for the dynamic variables it references
        # (e.g. {{cigna_api_token}}). Stored under the "default_dynamic_variables" key in
        # miscellaneous, these are used as defaults when a run does not supply them.
        miscellaneous={
            "default_dynamic_variables": {
                "cigna_api_token": "demo_token_replace_me",
            }
        },
    )

    ############# TOOL CONFIGS BELOW #############

    # ── ExternalAPIToolConfig ─────────────────────────────────────────────────
    # The LLM calls this tool when the user asks about the status of a specific claim.
    # api_endpoint, api_method, api_headers, and api_body are all configurable.
    # The LLM will supply the arguments (claim_id) based on the conversation.
    #
    # IMPORTANT: Replace the placeholder URL and auth header with real values
    # before running against a live system.
    claims_api_tool = ExternalAPIToolConfig(
        name="get_claim_status",
        description="Fetch the status of a health insurance claim from the Cigna claims API",
        signature=(
            "Looks up a claim by claim_id and returns its current status, "
            "amount billed, amount approved, and expected payment date."
        ),
        args_schema={
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "The unique identifier of the claim (e.g. 'CLM-2024-001234')",
                },
            },
            "required": ["claim_id"],
        },
        api_endpoint="https://api.example-cigna-claims.com/v1/claims/{claim_id}",
        api_method="GET",  # type: ignore[arg-type]
        api_headers={
            "Authorization": "Bearer {{cigna_api_token}}",  # ← inject via dynamic_variables
            "Accept": "application/json",
        },
        api_body=None,  # No body needed for GET
        static_messages_config=StaticMessagesConfig(static_messages=["Looking up your claim — one moment please..."]),
        result_runtime_variable_name="claim_status_result",
    )

    # ── KnowledgeBaseToolConfig ───────────────────────────────────────────────
    # The LLM calls this tool when the user asks a question that might be answered
    # by the Cigna policy documentation or FAQs stored in the knowledge base.
    #
    # target_knowledge_base_ids is a list of KB IDs registered in the Interactly platform.
    # Multiple IDs mean the search is run across all of them and results are merged.
    #
    # Replace the placeholder ID with a real KB ID from your Interactly workspace.
    policy_kb_tool = KnowledgeBaseToolConfig(
        name="search_cigna_policy_docs",
        description="Search Cigna's policy documentation and FAQs for relevant information",
        # signature is pre-filled by Interactly with a sensible default, but can be
        # overridden here to tune exactly what the LLM understands about this tool.
        signature=(
            "Performs a semantic search over Cigna's policy documents, benefit guides, and FAQs. "
            "Returns the most relevant excerpts that match the user's query. "
            "Use this tool when the user asks about coverage rules, plan details, or policy terms."
        ),
        target_knowledge_base_ids=[
            "kb_cigna_policy_docs_placeholder",  # ← replace with real KB ID
            "kb_cigna_faqs_placeholder",  # ← replace with real KB ID (optional second KB)
        ],
        static_messages_config=StaticMessagesConfig(
            static_messages=["Searching our policy documentation — one moment..."]
        ),
        result_runtime_variable_name="kb_tool_result",
    )

    # Both tools are registered on the same node via ToolsConfig.
    # The LLM picks the right tool based on the user's query and each tool's signature.
    combined_tools = ToolsConfig(tools=[claims_api_tool, policy_kb_tool])

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the user. Tell them you can:
    1. Look up the status of a specific claim (just provide the claim ID)
    2. Answer questions about Cigna coverage rules and policies

    Keep the greeting under 30 words.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Greets the user and explains available capabilities",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    ASSISTANT_PROMPT = """
    You are a Cigna insurance assistant with access to two tools:
    - get_claim_status: call this when the user provides a claim ID and wants status info
    - search_cigna_policy_docs: call this when the user asks about coverage rules, plan details,
      or any question that may be answered by official Cigna policy documents

    For claim lookups, always confirm the claim ID before calling the tool.
    For policy questions, call the KB tool and synthesise the returned excerpts into a clear answer.
    If no tool is needed (e.g. a simple greeting), answer directly.
    """
    assistant_node = SayLLMNodeConfig(
        name="Insurance Assistant",
        description="Main assistant node with both ExternalAPI and KnowledgeBase tools available",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASSISTANT_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
        tools_config=combined_tools,  # ← Both tools available to this LLM node
    )

    ############# EDGE CONFIGS BELOW #############

    edge_greeting_to_assistant = DirectEdgeConfig(
        name="Greeting → Assistant",
        description="After greeting, move to the main assistant",
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
        "What does my plan cover for mental health therapy?",
        "Can you check on claim CLM-2024-001234?",
        "quit",
    ]
    input_idx = 0

    workflow_input = WorkflowRunInput(
        messages=[],
        dynamic_variables={
            # Inject the API token via dynamic_variables so it's not hardcoded:
            "cigna_api_token": "demo_token_replace_me",
        },
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
