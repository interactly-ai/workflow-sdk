import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 16 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_16.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_16.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import PromptConfig
from interactly.configs import MCPServerConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a workflow that demonstrates MCPServerConfig and use_mcp_tools.

    MCP (Model Context Protocol) is an open standard that lets you expose tools from any
    server to any LLM. Instead of writing ExternalAPIToolConfig or InlinePythonToolConfig
    by hand, you point the workflow at an MCP server URL, and Interactly automatically
    discovers and registers all the tools that server exposes.

    Key concepts introduced in this example:
    1. MCPServerConfig — defined on WorkflowConfig.mcp_servers (workflow-level, shared)
    2. use_mcp_tools=True on a SayLLMNodeConfig — opts that node in to use MCP-discovered tools
    3. Multiple MCP servers can be registered simultaneously; all their tools are merged
    4. api_headers — for MCP servers that require authentication tokens
    5. Comparison with explicit tool configs (ExternalAPIToolConfig / KnowledgeBaseToolConfig)
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
    This workflow demonstrates MCPServerConfig — the Model Context Protocol integration.

    MCP (modelcontextprotocol.io) is an open standard that decouples tool definitions from
    workflow code. Instead of hardcoding ExternalAPIToolConfig objects, you register one or
    more MCP server URLs at the workflow level. Interactly connects to each server,
    discovers its tool catalog, and makes those tools available to any node that sets
    use_mcp_tools=True.

    When to use MCP vs. explicit tool configs:
    - Use MCPServerConfig when you have an existing MCP-compatible tool server (e.g. a
      company-internal MCP gateway that already wraps your APIs).
    - Use ExternalAPIToolConfig / InlinePythonToolConfig for quick, self-contained tool
      definitions that don't need a separate server process.

    Setup requirements for running this example:
    - You need a running MCP server at the configured server_url.
    - The server must implement the MCP spec (listTools + callTool endpoints).
    - Set the Authorization header with a valid token (or remove it for public servers).
    - A minimal test MCP server can be started with: https://github.com/modelcontextprotocol

    See more details at {google_docs_md_link}
    """

    # ── MCP Server definitions (workflow-level) ────────────────────────────────
    # Define one or more MCP servers. The runtime will connect to each and discover tools.
    # Replace the placeholder URLs and headers with your real MCP server details.
    internal_tools_mcp = MCPServerConfig(
        name="Internal Cigna Tools MCP Server",
        server_url="https://mcp.internal.cigna-example.com/mcp",  # ← replace with real URL
        api_headers={
            # Add authentication headers required by your MCP server, e.g.:
            "Authorization": "Bearer {{mcp_api_token}}",  # ← inject via dynamic_variables
            "X-Tenant-ID": "{{tenant_id}}",
        },
    )

    # A second MCP server (e.g. a public one for demonstration):
    # Interactly merges tool catalogs from all registered servers.
    public_demo_mcp = MCPServerConfig(
        name="Public Demo MCP Server",
        server_url="https://demo-mcp.example.com/mcp",  # ← replace with real URL
        api_headers=None,  # No auth needed for public demo servers
    )

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 16: MCP Server Integration with MCPServerConfig",
        description=workflow_description,
        # Register MCP servers at the workflow level. All their tools become available
        # to any node that sets use_mcp_tools=True.
        mcp_servers=[
            internal_tools_mcp,
            public_demo_mcp,
        ],
        # Seed the workflow with default values for the dynamic variables it references
        # (e.g. {{mcp_api_token}}, {{tenant_id}}). Stored under the "default_dynamic_variables"
        # key in miscellaneous, these are used as defaults when a run does not supply them.
        miscellaneous={
            "default_dynamic_variables": {
                "mcp_api_token": "demo_token_replace_me",
                "tenant_id": "cigna-demo",
            }
        },
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the user. Tell them you have access to a set of tools via MCP servers and can
    help with claims, eligibility checks, and policy questions.
    Ask what they need help with today. Keep the greeting under 30 words.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Greets the user; no MCP tools needed for a greeting",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
        # use_mcp_tools=False (default) — this node does not need MCP tools
        use_mcp_tools=False,
    )

    ASSISTANT_PROMPT = """
    You are a Cigna insurance assistant with access to a set of tools discovered from
    MCP servers. Use them when appropriate to answer the user's query.

    Available capabilities (discovered automatically from MCP servers at runtime):
    - Internal Cigna tools: claims lookup, eligibility check, benefit details
    - Public demo tools: general information retrieval

    Always confirm your understanding of the user's request before calling a tool.
    After receiving a tool result, synthesise the information into a clear, concise answer.
    """
    assistant_node = SayLLMNodeConfig(
        name="MCP-Powered Assistant",
        description="Main assistant with access to all tools from registered MCP servers",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASSISTANT_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
        # use_mcp_tools=True opts this node in to use all tools discovered from the
        # MCP servers registered in workflow_config.mcp_servers.
        use_mcp_tools=True,
    )

    ############# EDGE CONFIGS BELOW #############

    edge_greeting_to_assistant = DirectEdgeConfig(
        name="Greeting → MCP Assistant",
        description="Route to the MCP-powered assistant after greeting",
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
    """
    Minimal REPL for manual testing.

    NOTE: This example requires a live MCP server at the configured server_url.
    Without one, the workflow will start but the assistant node will have no MCP tools
    available (or will fail to connect). To test locally, run a demo MCP server first.
    """
    workflow = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    inputs_queue = [
        "Can you check my eligibility for physical therapy?",
        "quit",
    ]
    input_idx = 0

    workflow_input = WorkflowRunInput(
        messages=[],
        dynamic_variables={
            "mcp_api_token": "demo_token_replace_me",
            "tenant_id": "cigna-demo",
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
