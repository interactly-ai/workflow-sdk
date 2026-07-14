import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 17 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_17.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_17.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import SuperNodeConfig
from interactly.configs import PromptConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import AssistantResponseEvent, BusyWaitForUserMessageEvent
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


# ─────────────────────────────────────────────────────────────────────────────
# SUB-WORKFLOW: Insurance Intake
#
# This is the reusable sub-workflow that can be embedded in any parent workflow
# as a SuperNodeConfig. It handles the insurance intake process: collecting the
# member ID and reason for contact.
#
# In production, sub-workflows are stored in the database and referenced by ID.
# For this illustration, we build the sub-workflow as a WorkflowConfigFullyHydrated
# and embed it directly in the SuperNodeConfig.encapsulated_workflow_config field.
# ─────────────────────────────────────────────────────────────────────────────
def build_intake_sub_workflow() -> WorkflowConfigFullyHydrated:
    """
    Build a reusable insurance intake sub-workflow.

    This sub-workflow:
    1. Asks for the member's ID
    2. Asks for the reason for contact
    3. Ends, yielding control back to the parent workflow

    In production this would live in the DB and be referenced by super_workflow_id.
    For illustration purposes it is embedded inline via encapsulated_workflow_config.
    """

    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=200,
        temperature=0.2,
        do_not_split_sentences=True,
    )

    intake_workflow_config = WorkflowConfig(
        category="System Examples",
        name="Insurance Intake Sub-Workflow",
        description=(
            "Reusable sub-workflow that collects member ID and reason for contact. "
            "Designed to be embedded in any parent workflow as a SuperNodeConfig."
        ),
    )

    ASK_MEMBER_ID_PROMPT = """
    Ask the user for their member ID. Explain that it will be used to look up their account.
    Keep the request under 20 words.
    """
    ask_member_id_node = SayLLMNodeConfig(
        name="Ask Member ID",
        description="Asks the member for their member ID",
        is_start=True,
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASK_MEMBER_ID_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    ASK_REASON_PROMPT = """
    The member has provided their member ID. Thank them briefly, then ask for the reason they
    are calling today. Keep the question under 20 words.
    """
    ask_reason_node = SayLLMNodeConfig(
        name="Ask Reason",
        description="Asks why the member is contacting support today",
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASK_REASON_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    edge_ask_member_id_to_ask_reason = DirectEdgeConfig(
        name="Member ID → Reason",
        source_node_logical_id=ask_member_id_node.logical_id,
        destination_node_logical_id=ask_reason_node.logical_id,
    )

    return WorkflowConfigFullyHydrated(
        workflow_config=intake_workflow_config,
        node_configs=[ask_member_id_node, ask_reason_node],
        edge_configs=[edge_ask_member_id_to_ask_reason],
    )


# ─────────────────────────────────────────────────────────────────────────────
# PARENT WORKFLOW
# ─────────────────────────────────────────────────────────────────────────────
def build_assistant_workflow():
    """
    Build a parent workflow that embeds a SuperNodeConfig.

    SuperNodeConfig is the mechanism for workflow composition in the Interactly platform.
    It allows you to:
    - Encapsulate a complete sub-workflow as a single node in a parent workflow
    - Reuse the same sub-workflow across many parent workflows without duplication
    - Maintain sub-workflows independently and update them without touching parent workflows
    - Compose complex multi-stage flows from smaller, tested building blocks

    Key concepts introduced in this example:

    1. SuperNodeConfig — a node whose execution expands into an entire child workflow.
       The child runs to completion, then the parent continues from the next node.

    2. super_workflow_id — the DB ID of the encapsulated workflow (used in production).
       In this illustration we set it to None and use encapsulated_workflow_config instead.

    3. super_workflow_version_number — pin to a specific version for reproducibility.
       If None, the active version is resolved at execution time.

    4. encapsulated_workflow_config — embed the child WorkflowConfigFullyHydrated inline.
       Used for illustration / testing without a live database.

    5. field_values — key-value mapping that lets the parent pass context into the child
       workflow (e.g., which product category the user selected). Left empty here for clarity.

    Production pattern:
        super_node = SuperNodeConfig(
            name="...",
            super_workflow_id="60d21b4667d0d8992e610c85",
            super_workflow_version_number=3,  # pin to a specific version
        )

    Illustration pattern (this file):
        super_node = SuperNodeConfig(
            name="...",
            encapsulated_workflow_config=build_intake_sub_workflow(),
        )
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

    parent_workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 17: Workflow Composition with SuperNodeConfig",
        description=f"""
        This workflow demonstrates SuperNodeConfig — the mechanism for composing workflows
        out of reusable sub-workflows.

        Parent workflow structure:
          [Welcome Node] → [SUPER NODE: Insurance Intake] → [Main Assistant Node]
                                        ↑
              (Expands at runtime into the full intake sub-workflow:
               Ask Member ID → Ask Reason)

        See more details at {google_docs_md_link}
        """,
    )

    # ── Welcome node (parent-owned) ────────────────────────────────────────────
    WELCOME_PROMPT = """
    Give a warm 1-sentence welcome to the Cigna member support line.
    Do not ask any questions yet.
    """
    welcome_node = SayLLMNodeConfig(
        name="Welcome Node",
        description="Welcomes the user before starting the intake sub-workflow",
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + WELCOME_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    # ── Super node: embeds the full intake sub-workflow ────────────────────────
    # In production: set super_workflow_id and optionally super_workflow_version_number.
    # For this illustration: set encapsulated_workflow_config with an inline-built sub-workflow.
    intake_super_node = SuperNodeConfig(
        name="Insurance Intake (Super Node)",
        description=(
            "Encapsulates the entire insurance intake sub-workflow. "
            "When executed, the runtime expands this node into the full child workflow "
            "and runs it to completion before returning control to the parent."
        ),
        self_loop=False,
        # Production usage:
        # super_workflow_id="60d21b4667d0d8992e610c85",
        # super_workflow_version_number=2,
        # Illustration usage (no DB required):
        encapsulated_workflow_config=build_intake_sub_workflow(),
        # field_values: used to pass parent-workflow variables into the child workflow.
        # Keys are SuperNodeInputField.name values declared in the sub-workflow's interface.
        # Left empty in this illustration.
        field_values={},
    )

    # ── Main assistant node (after intake completes) ───────────────────────────
    ASSISTANT_PROMPT = """
    The member has already provided their member ID and reason for contact.
    Acknowledge their reason and ask how you can best assist them today.
    Keep your response under 30 words.
    """
    assistant_node = SayLLMNodeConfig(
        name="Main Assistant",
        description="Post-intake assistant that continues the conversation",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + ASSISTANT_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    ############# EDGE CONFIGS BELOW #############

    edge_welcome_to_intake = DirectEdgeConfig(
        name="Welcome → Intake Super Node",
        description="After welcome, start the intake sub-workflow",
        source_node_logical_id=welcome_node.logical_id,
        destination_node_logical_id=intake_super_node.logical_id,
    )

    edge_intake_to_assistant = DirectEdgeConfig(
        name="Intake Super Node → Main Assistant",
        description="After intake completes, proceed to the main assistant",
        source_node_logical_id=intake_super_node.logical_id,
        destination_node_logical_id=assistant_node.logical_id,
    )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=parent_workflow_config,
        node_configs=[
            welcome_node,
            intake_super_node,
            assistant_node,
        ],
        edge_configs=[
            edge_welcome_to_intake,
            edge_intake_to_assistant,
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
        "CIGN-123456789",  # Member ID
        "I have a billing question",  # Reason for contact
        "Why did my premium go up?",  # Post-intake question
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
