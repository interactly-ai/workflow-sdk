import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 11 — Interactly Workflow SDK.

Builds a workflow with ``build_assistant_workflow()``, uploads it to the
Interactly server, and drives it turn-by-turn via :class:`AsyncWorkflowHandle`.
See ``wf_example_progression_11.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_11.py
"""

import asyncio
import time

from langchain_core.messages import HumanMessage

from interactly.configs import DirectEdgeConfig
from interactly.configs import OpenAILLMConfig, OPENAIModel
from interactly.configs import SayLLMNodeConfig
from interactly.configs import ToolNodeConfig
from interactly.configs import PromptConfig
from interactly.configs import InlinePythonToolConfig
from interactly.configs import WorkflowConfig, WorkflowConfigFullyHydrated
from interactly.configs import WorkflowRunInput
from interactly.runtime.events import (
    AssistantResponseEvent,
    BusyWaitForUserMessageEvent,
    EndRunNodeEvent,
)
from interactly import AsyncWorkflowClient, aupload_and_get_handle
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX


def build_assistant_workflow():
    """
    Build a workflow that demonstrates ToolNodeConfig — a dedicated node that executes a tool
    *unconditionally* as a first-class workflow step, rather than letting an LLM decide to call it.

    Key concepts introduced in this example:
    1. ToolNodeConfig — a node that runs exactly one tool and stores its result in a runtime variable
    2. Separating deterministic side effects from LLM reasoning
    3. Chaining: ToolNode → SayLLM that reads the runtime variable with [[...]] interpolation
    4. EndRunNodeEvent inspection to see tool success / tool_result
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

    workflow_description = f"""
    This workflow introduces ToolNodeConfig — a dedicated node type that unconditionally executes a single
    tool as a workflow step. Unlike LLM-driven tool calls (where the model decides *whether* to call a tool),
    a ToolNode always executes its configured tool when the workflow reaches that node.

    Use ToolNodeConfig when you need deterministic, guaranteed execution of a side effect (fetching data,
    running a calculation, calling an external service) regardless of what the user said.

    The example simulates a "health-risk score" calculator: the ToolNode runs an inline Python function
    to compute a risk score, stores the result in the runtime variable `[[health_risk_result]]`, and then
    an LLM node reads that variable to compose a friendly explanation for the user.

    See more details at {google_docs_md_link}
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 11: Standalone Tool Execution with ToolNodeConfig",
        description=workflow_description,
    )

    ############# NODE CONFIGS BELOW #############

    GREETING_PROMPT = """
    Greet the user warmly and ask for three things in a single message:
    1. Their age (in years)
    2. Whether they smoke (yes/no)
    3. Their weekly exercise frequency (days per week, 0–7)

    Keep the message under 30 words.
    """
    greeting_node = SayLLMNodeConfig(
        name="Greeting Node",
        description="Greets the user and collects three inputs needed for risk assessment",
        is_start=True,
        self_loop=False,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + GREETING_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    # ToolNodeConfig: runs unconditionally when the workflow reaches this node.
    # The tool is an InlinePythonToolConfig that computes a simple numeric risk score.
    # The result is stored in runtime variable "health_risk_result", which downstream
    # nodes can read with the [[health_risk_result]] syntax.
    health_risk_tool_node = ToolNodeConfig(
        name="Health Risk Calculator",
        description="Computes a simple health-risk score from conversation context. "
        "Runs unconditionally — no LLM decision required.",
        # tool_arguments can use [[runtime_var]] or {{dynamic_var}} values. Here we
        # intentionally leave it empty so the tool reads from conversation history via
        # its own prompt (this is for illustration; real use would pass extracted values).
        tool_arguments={},
        result_runtime_variable_name="health_risk_result",
        tool_config=InlinePythonToolConfig(
            name="compute_health_risk_score",
            description="Compute a simplified health-risk score (0–100) based on age, smoking status, and exercise",
            signature=(
                "Given a patient's age, smoking status, and weekly exercise days, "
                "returns a dict with 'score' (int 0–100) and 'risk_level' ('low', 'medium', 'high')."
            ),
            args_schema={
                "type": "object",
                "properties": {
                    "age": {"type": "number", "description": "Patient age in years"},
                    "smokes": {"type": "boolean", "description": "True if the patient smokes"},
                    "exercise_days_per_week": {
                        "type": "number",
                        "description": "Number of days per week the patient exercises (0–7)",
                    },
                },
                "required": ["age", "smokes", "exercise_days_per_week"],
            },
            code="""
def compute_health_risk_score(age: float, smokes: bool, exercise_days_per_week: float) -> dict:
    '''Simplified health-risk scorer. Returns score (0-100) and risk_level.'''
    score = 0

    # Age contribution (0-40 points)
    if age < 30:
        score += 0
    elif age < 45:
        score += 10
    elif age < 60:
        score += 25
    else:
        score += 40

    # Smoking contribution (0-40 points)
    if smokes:
        score += 40

    # Lack-of-exercise contribution (0-20 points)
    exercise_score = max(0, 20 - int(exercise_days_per_week * 20 / 7))
    score += exercise_score

    score = min(score, 100)

    if score < 30:
        risk_level = "low"
    elif score < 60:
        risk_level = "medium"
    else:
        risk_level = "high"

    return {"score": score, "risk_level": risk_level}
""",
        ),
    )

    # The LLM node reads [[health_risk_result]] which was set by the ToolNode above.
    RISK_EXPLANATION_PROMPT = """
    You have just computed the following health-risk assessment result:
        [[health_risk_result]]

    Explain this result to the user in plain language:
    - State the risk level (low / medium / high).
    - Give two or three actionable lifestyle tips appropriate for their risk level.
    - Be empathetic and encouraging.

    Keep your response under 5 sentences.
    """
    risk_explanation_node = SayLLMNodeConfig(
        name="Risk Explanation",
        description="Reads the computed risk score from the runtime variable and explains it to the user",
        self_loop=True,
        wait_for_user_message=True,
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + RISK_EXPLANATION_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=openai_llm_config,
    )

    ############# EDGE CONFIGS BELOW #############

    edge_greeting_to_tool = DirectEdgeConfig(
        name="Greeting → Risk Calculator",
        description="After collecting user inputs, immediately run the risk-scoring tool",
        source_node_logical_id=greeting_node.logical_id,
        destination_node_logical_id=health_risk_tool_node.logical_id,
    )

    edge_tool_to_explanation = DirectEdgeConfig(
        name="Risk Calculator → Explanation",
        description="After the tool finishes, pass control to the LLM that explains the result",
        source_node_logical_id=health_risk_tool_node.logical_id,
        destination_node_logical_id=risk_explanation_node.logical_id,
    )

    ############# WORKFLOW HYDRATION BELOW #############

    workflow = WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            health_risk_tool_node,
            risk_explanation_node,
        ],
        edge_configs=[
            edge_greeting_to_tool,
            edge_tool_to_explanation,
        ],
    )

    return workflow


async def run():
    """
    Minimal REPL for manual testing.

    Conversation flow:
      1. Workflow greets the user and asks for age, smoking status, exercise days.
      2. User replies → workflow routes to ToolNode (unconditional tool execution).
      3. ToolNode runs compute_health_risk_score, stores result in [[health_risk_result]].
         → EndRunNodeEvent carries the run_output with tool_result and success flag.
      4. LLM node reads [[health_risk_result]] and explains the result to the user.
    """
    workflow = build_assistant_workflow()
    # The workflow seeds these on upload; read them back so each turn sends the same values.
    dynamic_variables = workflow.workflow_config.miscellaneous.get("default_dynamic_variables", {})
    client: AsyncWorkflowClient = get_async_client()
    workflow_runtime = await aupload_and_get_handle(
        client, workflow, dynamic_variables=dynamic_variables,
    )
    print(f"Uploaded workflow id={workflow_runtime.workflow_id}")
    # Simulate a user conversation with pre-supplied answers for automated testing.
    inputs_queue = [
        "Hi! I'm 52, I used to smoke but quit 2 years ago — so no. I exercise about 3 days a week.",
        "What should I focus on first to lower my risk?",
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

        elif isinstance(event, EndRunNodeEvent):
            node_name = event.origin_node_name or "unknown"
            run_output = event.run_output

            # ToolNodeConfig produces a ToolNodeRunOutput with .success and .tool_result
            if run_output and hasattr(run_output, "tool_result"):
                status = "✅" if getattr(run_output, "success", False) else "❌"
                print(f"\n{status} [ToolNode '{node_name}'] tool_result = {run_output.tool_result}")
                if not getattr(run_output, "success", True):
                    print(f"   Error: {getattr(run_output, 'error_message', 'unknown')}")

    elapsed = time.time() - start_time
    print(f"\n⏱️  Total run time: {elapsed:.2f}s")


if __name__ == "__main__":
    asyncio.run(run())
