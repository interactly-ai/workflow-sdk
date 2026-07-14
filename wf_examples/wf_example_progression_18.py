import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 18 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_18.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_18.py
"""

import asyncio
import time

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import WorkflowRunEvalLLMNodeConfig
from interactly.configs import WorkflowRunFetchNodeConfig
from interactly.configs import PromptConfig
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
    """
    Build an evaluation workflow that demonstrates WorkflowRunFetchNodeConfig and
    WorkflowRunEvalLLMNodeConfig.

    Evaluation workflows are a special class of workflows designed to assess the quality
    of conversations that happened in a DIFFERENT (production) workflow run. They are
    invoked AFTER a call completes, receiving the workflow_run_id as a dynamic variable.

    Typical pipeline:
        Production call completes
            → evaluation workflow triggered (async, post-call)
                → WorkflowRunFetchNodeConfig: loads the transcript + metadata from DB
                → WorkflowRunEvalLLMNodeConfig: LLM reads the transcript and scores it
                → (optional) SayLLMNodeConfig: synthesizes a human-readable report

    Key concepts introduced in this example:

    1. WorkflowRunFetchNodeConfig
       - workflow_run_id: which run to evaluate (default: "{{workflow_run_id}}" — injected
         via dynamic_variables when the eval workflow is triggered)
       - result_runtime_variable_name: the runtime variable that receives the fetched run
         (as a stringified JSON object)

    2. WorkflowRunEvalLLMNodeConfig
       - Inherits from WorkerLLMNodeConfig — it is a background LLM node, not a Say node,
         so it does NOT produce assistant speech. It processes internally.
       - input_runtime_variable_name: which runtime variable holds the workflow run to evaluate
         (default: "workflow_run_object" — should match result_runtime_variable_name above)
       - output_runtime_variable_name: where the evaluation result is stored
       - structured_output_schema: optional JSON Schema for the evaluation output fields
         (e.g., scores, categories, flags). If None, the evaluator outputs free-form text.
       - is_turn_by_turn_evaluator: if True, the evaluator scores each individual turn
         rather than the entire conversation as a whole.

    3. WorkerLLMNodeEvent: the evaluator emits WorkerLLMNodeEvent (not AssistantResponseEvent)
       because it is a background worker, not a conversational speaker.

    4. EndRunNodeEvent: the fetch node emits EndRunNodeEvent with a
       WorkflowRunFetchNodeRunOutput in run_output, containing fetched_workflow_run (JSON str).
    """

    openai_llm_config = OpenAILLMConfig(
        model=OPENAIModel.GPT_5_4,
        max_tokens=800,
        temperature=0.0,  # Deterministic for scoring
        do_not_split_sentences=True,
    )

    google_docs_md_link = (
        "https://docs.google.com/document/d/1nYFTeDCnDPS5z91yKzgaYNlL2Ew_sl2TXb5QYc0Zjfg/edit?tab=t.ymmopdx5ykkl"
    )

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 18: Evaluation Workflow (WorkflowRunFetchNodeConfig + WorkflowRunEvalLLMNodeConfig)",
        description=f"""
        Demonstrates how to build a post-call quality evaluation workflow.

        Evaluation workflows run asynchronously AFTER a production call completes.
        They use:
        - WorkflowRunFetchNodeConfig to load the completed call's transcript from the DB
        - WorkflowRunEvalLLMNodeConfig to score it using an LLM against defined criteria
        - An optional SayLLMNodeConfig to format a human-readable evaluation report

        The workflow_run_id of the target call is injected via dynamic_variables.

        See more details at {google_docs_md_link}
        """,
        # Seed the workflow with a default value for the dynamic variable it references
        # ({{workflow_run_id}}). Stored under the "default_dynamic_variables" key in
        # miscellaneous, this is used as a default when a run does not supply it.
        miscellaneous={
            "default_dynamic_variables": {
                "workflow_run_id": "6789abcdef1234567890abcd",  # placeholder — replace with a real run id
            }
        },
    )

    # ── Node 1: WorkflowRunFetchNodeConfig ─────────────────────────────────────
    # Fetches the completed workflow run from the database.
    # workflow_run_id is injected via dynamic_variables (double-brace template syntax).
    # The fetched run (transcript + metadata) is stored in "workflow_run_object" as a
    # stringified JSON object, ready for the evaluator node to read.
    fetch_node = WorkflowRunFetchNodeConfig(
        name="Fetch Workflow Run",
        description=(
            "Loads the target production call's transcript and metadata from the database. "
            "workflow_run_id is provided via dynamic_variables at evaluation trigger time."
        ),
        is_start=True,
        self_loop=False,
        wait_for_user_message=False,
        # Template syntax: {{workflow_run_id}} is resolved at runtime from dynamic_variables.
        workflow_run_id="{{workflow_run_id}}",
        # The fetched run is stored here and read by the evaluator node below.
        result_runtime_variable_name="workflow_run_object",
    )

    # ── Node 2: WorkflowRunEvalLLMNodeConfig ───────────────────────────────────
    # Evaluates the fetched workflow run using an LLM.
    # The evaluator reads from input_runtime_variable_name and writes a structured
    # evaluation to output_runtime_variable_name.
    #
    # structured_output_schema defines the fields the LLM must fill in (like a rubric).
    # If None, the evaluator produces free-form text evaluation.
    EVALUATOR_PROMPT = """
    You are a quality assurance evaluator for Cigna member support calls.

    You will receive the full transcript of a call as a JSON object in your context.
    Evaluate the call on the following dimensions and return structured scores:

    1. Greeting Quality (0-10): Was the agent's greeting warm, professional, and brand-aligned?
    2. Issue Resolution (0-10): Was the member's issue fully resolved by the end of the call?
    3. Empathy Score (0-10): Did the agent demonstrate empathy and understanding?
    4. Compliance (pass/fail): Were all required disclosures made (e.g. call recording notice)?
    5. Call Summary: A 2-sentence summary of what the call was about and how it ended.
    6. Improvement Suggestions: Up to 3 bullet points on how the agent could improve.

    Return your evaluation in the exact structured format defined by the output schema.
    """
    evaluator_node = WorkflowRunEvalLLMNodeConfig(
        name="Quality Evaluator",
        description=(
            "LLM node that reads the fetched workflow run transcript and evaluates the call "
            "against Cigna quality rubrics. Produces structured scores and a summary."
        ),
        self_loop=False,  # Always False for evaluator nodes
        wait_for_user_message=False,  # Always False for evaluator nodes
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + EVALUATOR_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
        # Reads from the variable populated by fetch_node above
        input_runtime_variable_name="workflow_run_object",
        # Writes evaluation results here
        output_runtime_variable_name="evaluation_result",
        # Whether to evaluate each turn individually vs. the whole conversation
        is_turn_by_turn_evaluator=False,
        # JSON Schema defining the fields the LLM must output.
        # If None, output is free-form text.
        structured_output_schema={
            "type": "object",
            "properties": {
                "greeting_quality": {"type": "integer", "minimum": 0, "maximum": 10},
                "issue_resolution": {"type": "integer", "minimum": 0, "maximum": 10},
                "empathy_score": {"type": "integer", "minimum": 0, "maximum": 10},
                "compliance": {"type": "string", "enum": ["pass", "fail"]},
                "call_summary": {"type": "string"},
                "improvement_suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 3,
                },
            },
            "required": [
                "greeting_quality",
                "issue_resolution",
                "empathy_score",
                "compliance",
                "call_summary",
            ],
        },
    )

    # ── Node 3: SayLLMNodeConfig — optional summary report (for human review) ──
    # This node is optional. It reads the structured evaluation from
    # [[evaluation_result]] and formats it into a readable summary.
    # In a fully automated pipeline this node would be removed.
    REPORT_PROMPT = """
    Based on the structured evaluation stored in [[evaluation_result]], write a concise
    quality report that a supervisor could quickly read. Include the scores and the
    top improvement suggestion. Format it as 3-4 short sentences.
    """
    report_node = SayLLMNodeConfig(
        name="Evaluation Report",
        description="Formats the structured evaluation into a human-readable summary",
        self_loop=False,
        wait_for_user_message=False,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + REPORT_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    ############# EDGE CONFIGS BELOW #############

    edge_fetch_to_eval = DirectEdgeConfig(
        name="Fetch → Evaluator",
        description="After loading the workflow run, run the evaluator",
        source_node_logical_id=fetch_node.logical_id,
        destination_node_logical_id=evaluator_node.logical_id,
    )

    edge_eval_to_report = DirectEdgeConfig(
        name="Evaluator → Report",
        description="After scoring, generate the formatted report",
        source_node_logical_id=evaluator_node.logical_id,
        destination_node_logical_id=report_node.logical_id,
    )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            fetch_node,
            evaluator_node,
            report_node,
        ],
        edge_configs=[
            edge_fetch_to_eval,
            edge_eval_to_report,
        ],
    )

    return workflow


async def run():
    """
    Demonstration run for an evaluation workflow.

    NOTE: WorkflowRunFetchNodeConfig requires a live database connection and a real
    workflow_run_id to fetch data from the database. Without these, the fetch node will
    fail or return empty data.

    For local testing, either:
    a) Use a real workflow_run_id from a completed call in your dev environment, or
    b) Mock the fetch node at the service layer to return a fixture transcript.

    The event loop below shows how to observe WorkerLLMNodeEvent (from the evaluator)
    and EndRunNodeEvent (from the fetch node).
    """
    workflow = build_assistant_workflow()
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    workflow_input = WorkflowRunInput(
        messages=[],
        dynamic_variables={
            # In production, this is set to the ID of the completed call to evaluate.
            # Replace with a real workflow_run_id from your dev environment.
            "workflow_run_id": "6789abcdef1234567890abcd",  # ← placeholder
        },
        runtime_variables={},
    )

    start_time = time.time()

    async for event in workflow_runtime.arun(workflow_input):
        if isinstance(event, BusyWaitForUserMessageEvent):
            # Evaluation workflows should never wait for user messages.
            # If this fires, it indicates a misconfiguration.
            print(f"⚠️  Unexpected BusyWaitForUserMessageEvent from [{event.origin_node_name}]")

        elif isinstance(event, EndRunNodeEvent):
            # Fired by WorkflowRunFetchNodeConfig after loading the call data.
            # run_output is a WorkflowRunFetchNodeRunOutput with .fetched_workflow_run
            node_name = event.origin_node_name or "unknown node"
            print(f"\n📦 [{node_name}] EndRunNodeEvent received")
            if event.run_output:
                print(f"   run_output type: {event.run_output.type}")
                # event.run_output.fetched_workflow_run is a stringified JSON string
                fetched = getattr(event.run_output, "fetched_workflow_run", None)
                if fetched:
                    print(f"   fetched_workflow_run (first 200 chars): {str(fetched)[:200]}")
                else:
                    print("   fetched_workflow_run: None (no real DB in this demo)")

        elif isinstance(event, WorkerLLMNodeEvent):
            # Fired by WorkflowRunEvalLLMNodeConfig as it processes internally.
            # WorkerLLMNodeEvent carries individual LLM message steps (not final output).
            node_name = event.origin_node_name or "unknown node"
            print(f"\n🔍 [{node_name}] WorkerLLMNodeEvent: {event.type}")
            if event.message:
                content = getattr(event.message, "content", "") or ""
                print(f"   message content (first 200 chars): {str(content)[:200]}")

        elif isinstance(event, AssistantResponseEvent):
            # Fired by the final SayLLMNodeConfig (Evaluation Report node).
            print(f"\n📋 Evaluation Report:\n{event.content}")

    elapsed = time.time() - start_time
    print(f"\n⏱️  Total run time: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(run())
