import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 24 — Interactly Workflow SDK.

Background work: a **companion thread** polls for a lab result while the caller
keeps talking, and an **evaluate-while-waiting** edge moves the conversation on
the moment the result lands — with no user message.

Unlike examples 1–23 this one is driven over the **WebSocket** (``client.runs.stream()``)
rather than an ``AsyncWorkflowHandle``. That is not a stylistic choice: the REST
driver does not advance background work on its own, so a companion thread would
never make progress unless you pumped it yourself. See ``run_over_rest()`` at the
bottom for how to do exactly that when WebSocket is not an option.

See ``wf_example_progression_24.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_24.py
"""

import asyncio

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import CompanionThreadConfig, EvaluateWhileWaitingConfig, SelfLoopConfig
from interactly.configs import InlinePythonToolConfig
from interactly.configs import LLMGroupConfig, OpenAILLMConfig, OPENAIModel
from interactly.configs import NoOpNodeConfig, SayLLMNodeConfig, SayStaticMessageNodeConfig, ToolNodeConfig
from interactly.configs import PromptConfig, StaticMessagesConfig
from interactly.configs import WorkflowCommand, WorkflowConfig, WorkflowConfigFullyHydrated
from interactly import AsyncWorkflowClient
from _shared_sdk import get_async_client
from _shared_constants import GLOBAL_PROMPT_PREFIX, GLOBAL_PROMPT_SUFFIX

# ─── THE SIMULATED EXTERNAL SYSTEM ────────────────────────────────────────────

# A stand-in for "call the lab's API and see whether the result is back yet".
# It returns a **flat integer**, not a dict, and that matters — see the note in
# the accompanying .md about dotted access into a dict-valued runtime variable.
POLL_LAB_RESULTS_CODE = '''
def poll_lab_results(attempts_so_far):
    """Simulated poll of an external lab system.

    Returns the new attempt count. The caller's graph treats >= 3 as "the result
    has landed", so this stands in for a real endpoint that returns 202 twice and
    then 200.
    """
    try:
        n = int(attempts_so_far)
    except (TypeError, ValueError):
        n = 0
    return n + 1
'''

RESULT_READY_AFTER_ATTEMPTS = 3


def _make_llm():
    """One small, cheap model — this example is about control flow, not prompting."""
    return LLMGroupConfig(
        llms=[
            OpenAILLMConfig(
                model=OPENAIModel.GPT_4_1_MINI,
                max_tokens=120,
                temperature=0.2,
                do_not_split_sentences=True,
            )
        ]
    )


def build_assistant_workflow():
    """
    Build a workflow where background work and the conversation genuinely run at once.

    Key concepts introduced in this example:
    1. CompanionThreadConfig — fork a background thread off a direct edge
    2. SelfLoopConfig — bound that thread's polling so it cannot run forever
    3. Cross-thread variables — ``[[thread_labpoll.lab_attempts]]``
    4. EvaluateWhileWaitingConfig — advance the conversation with no user message
    5. NoOpNodeConfig — a fan-out point that does nothing but be a fork point
    """

    llm = _make_llm()

    workflow_description = """
    A caller has had blood work done and rings in to ask whether the results are back.
    Rather than making them hold in silence, this workflow forks a companion thread that
    polls the lab system in the background while the main thread carries on the conversation.

    The moment the poll succeeds, an evaluate-while-waiting edge fires — the workflow speaks
    the result without waiting for the caller to say anything else.

    This is the pairing the two features were built for: the companion thread produces the
    fact, and the waiting edge is what lets that fact interrupt a conversation.
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 24: Companion thread + evaluate-while-waiting",
        description=workflow_description,
    )

    ############# NODE CONFIGS BELOW #############

    # The fork point. A no-op node is ideal here: it does no work, but it gives the graph
    # somewhere to fan out from. That matters because of the rule below — the node carrying
    # the waiting edge must NOT also have outgoing direct edges, so the fork cannot live on
    # the chat node itself.
    entry_node = NoOpNodeConfig(
        name="Entry",
        description="Fan-out point: one direct edge continues the conversation, one forks the poller.",
        is_start=True,
        note="Exists only to fork the companion thread upstream of the node that waits.",
    )

    # The companion thread's only node. `self_loop_config` re-executes it until either its
    # exit edge matches or a bound is hit — a bound is REQUIRED, and the SDK refuses to
    # construct a SelfLoopConfig without one.
    poll_node = ToolNodeConfig(
        name="Poll Lab Results",
        description="Polls the lab system every few seconds until the result lands or the budget runs out.",
        tool_arguments={"attempts_so_far": "[[lab_attempts]]"},
        result_runtime_variable_name="lab_attempts",
        self_loop_config=SelfLoopConfig(
            enabled=True,
            max_retries=8,  # up to 9 executions in total
            expiry_time=60,  # ...and never longer than a minute, whichever comes first
            time_between_retries=3,
        ),
        tool_config=InlinePythonToolConfig(
            name="poll_lab_results",
            description="Check whether the caller's lab result is available yet",
            signature="Given the number of attempts so far, returns the new attempt count.",
            args_schema={
                "type": "object",
                "properties": {
                    "attempts_so_far": {
                        "type": "number",
                        "description": "How many times this poll has already run in this thread",
                    }
                },
                "required": ["attempts_so_far"],
            },
            code=POLL_LAB_RESULTS_CODE,
        ),
    )

    # The companion thread's terminal node. A companion must terminate within its turn —
    # it can never wait for a user message — so it needs somewhere to land.
    landed_node = NoOpNodeConfig(
        name="Result Landed",
        description="Terminal node for the companion thread once the poll succeeds.",
        output_runtime_variable_name="lab_result_ready",
    )

    CHAT_PROMPT = """
    You are keeping a patient company on the phone while their lab results are still
    being fetched. Reply in ONE short sentence. Answer whatever they ask, be warm, and
    NEVER claim the results have arrived — a different part of the workflow does that.
    """
    chat_node = SayLLMNodeConfig(
        name="Chat While Waiting",
        description="The main thread: talks to the caller and parks waiting for their next message.",
        wait_for_user_message=True,
        self_loop=True,  # NOTE: unrelated to SelfLoopConfig above — see the .md
        main_response_config=PromptConfig(prompt=GLOBAL_PROMPT_PREFIX + CHAT_PROMPT + GLOBAL_PROMPT_SUFFIX),
        llms_config=llm,
    )

    deliver_node = SayStaticMessageNodeConfig(
        name="Deliver Result",
        description="Speaks the result. Reached with no user message when the waiting condition matches.",
        static_messages_config=StaticMessagesConfig(
            static_messages=["Good news — your lab results just came through: A1C 5.4%, within range."]
        ),
    )

    ############# EDGE CONFIGS BELOW #############

    edges = [
        # The MAIN thread. Exactly one outgoing direct edge per node may be the main one;
        # this is it, and it is not flagged as a companion.
        DirectEdgeConfig(
            source_node_logical_id=entry_node.logical_id,
            destination_node_logical_id=chat_node.logical_id,
        ),
        # The COMPANION fork. `thread_id` is what makes the thread addressable: without it
        # the thread still runs, but no other thread can read its variables.
        DirectEdgeConfig(
            source_node_logical_id=entry_node.logical_id,
            destination_node_logical_id=poll_node.logical_id,
            companion_thread_config=CompanionThreadConfig(
                is_companion_thread=True,
                thread_id="labpoll",
            ),
        ),
        # The self-loop's exit. Without this the poller would keep going until it hit
        # `max_retries` or `expiry_time` — correct, but slower and noisier.
        ConditionalEdgeConfig(
            source_node_logical_id=poll_node.logical_id,
            destination_node_logical_id=landed_node.logical_id,
            condition=ConditionConfig(
                condition_expression=f"[[lab_attempts]] >= {RESULT_READY_AFTER_ATTEMPTS}",
            ),
        ),
        # The point of the whole example: this edge is evaluated while `chat_node` is
        # parked waiting for the caller, so it can fire with no user message at all.
        # Note it reads the COMPANION's variable, via the thread_<id> prefix.
        ConditionalEdgeConfig(
            source_node_logical_id=chat_node.logical_id,
            destination_node_logical_id=deliver_node.logical_id,
            condition=ConditionConfig(
                condition_expression=f"[[thread_labpoll.lab_attempts]] >= {RESULT_READY_AFTER_ATTEMPTS}",
            ),
            evaluate_while_waiting_config=EvaluateWhileWaitingConfig(
                enabled=True,
                # ON_NODE_COMPLETION (the default): only re-evaluate when the node that can
                # actually change the answer has run again. The alternative is blind polling.
                trigger_node_logical_ids=[poll_node.logical_id],
            ),
        ),
    ]

    return WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[entry_node, poll_node, landed_node, chat_node, deliver_node],
        edge_configs=edges,
    )


# ─── DRIVING IT ───────────────────────────────────────────────────────────────


async def run_over_websocket(client: AsyncWorkflowClient, workflow_id: str) -> None:
    """Drive the run over the WebSocket, which pumps background work for you.

    The one thing that changes once companions are in play: ``end_workflow_iteration``
    no longer means "your turn". It means one turn's accounting is done — companions may
    still be running. Break on ``is_ready_for_input()`` instead.
    """
    # Canned replies, so the example runs unattended. The caller is chatting about
    # nothing in particular; the interesting event arrives without their help.
    replies = ["Sure, I'll hold.", "No rush.", "Thanks for checking."]
    reply_idx = 0

    print("=" * 70)
    print("  Driving over WebSocket — the server pumps background work itself")
    print("=" * 70)

    async with client.runs.stream(workflow_id=workflow_id, command=WorkflowCommand.START) as stream:
        async for event in stream:
            thread = event.thread_reference_id

            if event.type == "assistant_response":
                who = "🤖 Assistant" if thread == "0" else f"🤖 [{thread}]"
                print(f"{who}: {event.output}")

            elif event.type == "companion_step_boundary":
                print("   ⏳ [labpoll] one poll step finished")

            elif event.type == "waiting_condition_matched":
                # The headline: the workflow moved on with no user message.
                print("\n   ⚡ waiting condition matched — advancing with NO user message\n")

            elif event.type == "self_loop_exhausted":
                # Event-specific fields are TOP-LEVEL attributes (RunEvent is
                # extra="allow"), not under `event.data` — the server never fills that in.
                print(f"   ⛔ [labpoll] gave up on '{event.outcome}' after {event.total_attempts} attempts")

            if event.is_ready_for_input():
                # `active_companion_thread_ids` holds INTERNAL ids ("0_companion_labpoll"),
                # not the `thread_id` you configured. Match on the suffix, not equality.
                active = getattr(event, "active_companion_thread_ids", None) or []
                print(f"   … still running in the background: {active or 'nothing'}")

                if reply_idx >= len(replies):
                    print("\n   (out of canned replies — waiting for the poll to land)")
                    continue
                print(f"👤 Caller: {replies[reply_idx]}")
                reply_idx += 1
                # A real client would send the next turn here. This example lets the
                # background work finish instead, which is the behaviour being shown.

            if event.is_terminal():
                print(f"\n✅ Run finished ({event.type}).")
                break


async def run_over_rest(client: AsyncWorkflowClient, workflow_id: str) -> None:
    """The same run over plain HTTP — where **you** must pump, or nothing happens.

    Not called by ``main()``; it is here because "my companion thread never runs" is
    almost always this. ``execute()`` returns as soon as the main thread parks, and the
    companion sits there until something advances it.
    """
    response = await client.runs.execute(workflow_id, command=WorkflowCommand.START)
    print(f"turn {response.turn_number}: background work pending = {response.has_background_work}")

    if response.has_background_work:
        # Polls `pump_companions()` until nothing is left, bounded so a long-running
        # companion cannot block forever. Returns EVERY response, so no events are lost.
        responses = await client.runs.drive_background_work(
            workflow_id,
            response.run_id,
            interval_seconds=1.0,
            max_iterations=60,
        )
        for pumped in responses:
            for event in pumped.events:
                # A pump can produce MAIN-thread output: if the waiting condition matched
                # during the pump, the assistant speaks even though no user message was sent.
                print("   pumped:", event)

        # `has_background_work` on the last response distinguishes "finished" from
        # "ran out of iterations".
        if responses and responses[-1].has_background_work:
            print("   ⚠️  still pumping when max_iterations ran out")


async def main() -> None:
    client = get_async_client()

    config = build_assistant_workflow()
    workflow = await client.workflows.create_from_config(config, name=config.workflow_config.name)
    print(f"Created workflow {workflow.id}\n")

    try:
        await run_over_websocket(client, workflow.id)
    finally:
        await client.workflows.delete(workflow.id)
        print(f"\nDeleted workflow {workflow.id}")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
