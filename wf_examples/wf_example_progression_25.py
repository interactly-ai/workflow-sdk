import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 25 — Interactly Workflow SDK.

Bounded retries: re-execute a flaky node until it succeeds, then branch on **how the
loop ended** — and converge every branch back through a single no-op junction.

The same workflow is run twice, changing only a dynamic variable:

* run 1 — the check succeeds on its second attempt (the happy exit)
* run 2 — it never succeeds, the loop exhausts, and ``self_loop_outcome`` routes to
  the apology branch

That second run is the one worth studying. A retry loop that gives up and has nowhere
to go simply stops, and from the outside a stalled workflow and a finished one look
identical.

See ``wf_example_progression_25.md`` for an illustrated walkthrough — a schematic
diagram, node/edge tables, key details, and a sample conversation.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_25.py
"""

import asyncio

from interactly.configs import ConditionConfig
from interactly.configs import ConditionalEdgeConfig, DirectEdgeConfig
from interactly.configs import InlinePythonToolConfig, SelfLoopConfig
from interactly.configs import NoOpNodeConfig, SayStaticMessageNodeConfig, ToolNodeConfig
from interactly.configs import StaticMessagesConfig
from interactly.configs import WorkflowCommand, WorkflowConfig, WorkflowConfigFullyHydrated
from interactly import AsyncWorkflowClient
from _shared_sdk import get_async_client

# ─── THE FLAKY EXTERNAL SYSTEM ────────────────────────────────────────────────

# Stands in for an eligibility service that answers "still checking" before it answers
# properly. It is deliberately stateless: the node feeds its OWN previous result back in
# as an argument, which is how a self-looping node carries state between attempts.
#
# `mode` comes from a dynamic variable, so the same graph takes a different exit on each
# of the two runs below without the workflow being edited.
CHECK_ELIGIBILITY_CODE = '''
def check_eligibility(previous_status, mode):
    """Simulated flaky eligibility check.

    Answers "pending" first and "approved" on the next attempt — the shape a real
    polling endpoint has when it returns 202 before 200. In "always_pending" mode it
    never answers, so the retry loop runs out instead.
    """
    if mode == "always_pending":
        return "pending"
    return "approved" if previous_status == "pending" else "pending"
'''


def build_assistant_workflow():
    """
    Build a workflow around a bounded retry loop with three distinct exits.

    Key concepts introduced in this example:
    1. SelfLoopConfig on a node — bounded re-execution, with the bound enforced by the runtime
    2. The happy exit — an outgoing conditional edge, re-evaluated after every execution
    3. ``[[self_loop_outcome]]`` — branching on *why* the loop stopped
    4. NoOpNodeConfig as a fan-in junction — three branches, one outgoing edge
    """

    workflow_description = """
    A caller asks whether they are covered for a procedure. The eligibility service is slow
    and sometimes does not answer at all, so the check node retries on a bound rather than
    blocking or failing outright.

    Three edges leave the check node, and exactly one of them will be taken:
      * the check came back approved  — the happy exit
      * the loop ran out of attempts  — [[self_loop_outcome]] == 'max_retries'
      * the loop ran out of time      — [[self_loop_outcome]] == 'expiry_time'

    All three converge on a single no-op junction, so the farewell exists once in the graph
    instead of three times.
    """

    workflow_config = WorkflowConfig(
        category="System Examples",
        name="Example 25: Bounded retries and self-loop outcomes",
        description=workflow_description,
        default_dynamic_variables={"mode": "normal"},
    )

    ############# NODE CONFIGS BELOW #############

    greeting_node = SayStaticMessageNodeConfig(
        name="Greeting",
        description="Opens the call while the eligibility check runs.",
        is_start=True,
        static_messages_config=StaticMessagesConfig(
            static_messages=["Let me check your coverage — one moment please."]
        ),
    )

    # `enabled=True` with NO bound raises at construction, in the SDK, before any request
    # is sent. A loop that can never terminate is a bug worth catching at authoring time.
    check_node = ToolNodeConfig(
        name="Check Eligibility",
        description="Retries the eligibility service on a bound; exits early if it answers.",
        # The node reads its own previous result. On the first execution the variable is
        # unset, so the tool sees no "pending" and answers "pending" — which is the point.
        tool_arguments={
            "previous_status": "[[eligibility_status]]",
            "mode": "{{mode}}",
        },
        result_runtime_variable_name="eligibility_status",
        self_loop_config=SelfLoopConfig(
            enabled=True,
            max_retries=3,  # 3 retries => up to 4 executions in total
            expiry_time=45,  # ...and never longer than 45s, whichever lands first
            time_between_retries=2,
        ),
        tool_config=InlinePythonToolConfig(
            name="check_eligibility",
            description="Ask the eligibility service whether this member is covered",
            signature="Given the previous status and a mode, returns 'approved' or 'pending'.",
            args_schema={
                "type": "object",
                "properties": {
                    "previous_status": {"type": "string", "description": "This node's result from the last attempt"},
                    "mode": {"type": "string", "description": "'normal', or 'always_pending' to never answer"},
                },
                "required": ["previous_status", "mode"],
            },
            code=CHECK_ELIGIBILITY_CODE,
        ),
    )

    approved_node = SayStaticMessageNodeConfig(
        name="Approved",
        description="The happy exit: the check answered before any bound was hit.",
        static_messages_config=StaticMessagesConfig(
            static_messages=["Good news — you're covered for this procedure."]
        ),
    )

    apologise_node = SayStaticMessageNodeConfig(
        name="Out Of Attempts",
        description="Reached when the loop stopped on max_retries.",
        static_messages_config=StaticMessagesConfig(
            static_messages=["I couldn't get an answer from our eligibility system just now — I'll email you today."]
        ),
    )

    escalate_node = SayStaticMessageNodeConfig(
        name="Out Of Time",
        description="Reached when the loop stopped on expiry_time.",
        static_messages_config=StaticMessagesConfig(
            static_messages=["Our eligibility system is taking too long — let me put you through to a specialist."]
        ),
    )

    # The fan-in junction. It does nothing, which is the point: without it the farewell
    # would have to be duplicated on all three branches, or the graph would need three
    # near-identical terminal nodes.
    #
    # This is NOT the same as `disabled=True`. A disabled node is skipped entirely and
    # emits no events, so a downstream conditional edge would have nothing to branch on.
    # A no-op node runs, and writes `junction_success` to thread state.
    junction_node = NoOpNodeConfig(
        name="Junction",
        description="Fan-in point for all three outcomes.",
        output_runtime_variable_name="junction",
    )

    farewell_node = SayStaticMessageNodeConfig(
        name="Farewell",
        description="One farewell, reachable from every branch.",
        static_messages_config=StaticMessagesConfig(static_messages=["Thanks for calling — goodbye."]),
    )

    ############# EDGE CONFIGS BELOW #############

    edges = [
        DirectEdgeConfig(
            source_node_logical_id=greeting_node.logical_id,
            destination_node_logical_id=check_node.logical_id,
        ),
        # 1. The happy exit. Outgoing conditional edges are re-evaluated after EVERY
        #    execution of the node, which is what decides "leave" vs. "go round again".
        ConditionalEdgeConfig(
            source_node_logical_id=check_node.logical_id,
            destination_node_logical_id=approved_node.logical_id,
            # The expression language has ==, !=, <, <=, >, >=, AND/OR/NOT and the
            # isPresent/isAbsent/isEmpty/isNonEmpty unary forms. There is no contains().
            condition=ConditionConfig(condition_expression="[[eligibility_status]] == 'approved'"),
        ),
        # 2. Gave up after N attempts. The runtime publishes `self_loop_outcome` only when
        #    the loop stops WITHOUT a matching exit edge.
        ConditionalEdgeConfig(
            source_node_logical_id=check_node.logical_id,
            destination_node_logical_id=apologise_node.logical_id,
            condition=ConditionConfig(condition_expression="[[self_loop_outcome]] == 'max_retries'"),
        ),
        # 3. Ran out of wall-clock time.
        ConditionalEdgeConfig(
            source_node_logical_id=check_node.logical_id,
            destination_node_logical_id=escalate_node.logical_id,
            condition=ConditionConfig(condition_expression="[[self_loop_outcome]] == 'expiry_time'"),
        ),
        # All three converge here.
        DirectEdgeConfig(
            source_node_logical_id=approved_node.logical_id,
            destination_node_logical_id=junction_node.logical_id,
        ),
        DirectEdgeConfig(
            source_node_logical_id=apologise_node.logical_id,
            destination_node_logical_id=junction_node.logical_id,
        ),
        DirectEdgeConfig(
            source_node_logical_id=escalate_node.logical_id,
            destination_node_logical_id=junction_node.logical_id,
        ),
        DirectEdgeConfig(
            source_node_logical_id=junction_node.logical_id,
            destination_node_logical_id=farewell_node.logical_id,
        ),
    ]

    return WorkflowConfigFullyHydrated(
        workflow_config=workflow_config,
        node_configs=[
            greeting_node,
            check_node,
            approved_node,
            apologise_node,
            escalate_node,
            junction_node,
            farewell_node,
        ],
        edge_configs=edges,
    )


# ─── DRIVING IT ───────────────────────────────────────────────────────────────


async def run_once(client: AsyncWorkflowClient, workflow_id: str, mode: str, label: str) -> None:
    """One run, with the flakiness dialled by a dynamic variable."""
    print("\n" + "=" * 70)
    print(f"  {label}  (mode={mode!r})")
    print("=" * 70)

    async with client.runs.stream(
        workflow_id=workflow_id,
        command=WorkflowCommand.START,
        dynamic_variables={"mode": mode},
    ) as stream:
        async for event in stream:
            if event.type == "assistant_response":
                print(f"🤖 {event.output}")

            elif event.type == "self_loop_delay":
                # Emitted just before the runtime waits `time_between_retries`.
                # NOTE: event-specific fields arrive as TOP-LEVEL attributes, not under
                # `event.data` (which the server never populates). `RunEvent` is
                # extra="allow", so read them straight off the event.
                print(f"   ⏱️  attempt {event.attempt_number}, waiting {event.delay_seconds}s")

            elif event.type == "self_loop_exhausted":
                print(f"   ⛔ stopped on '{event.outcome}' after {event.total_attempts} attempts")

            elif event.type == "node_expired":
                print("   ⌛ an in-flight execution was terminated by expiry_time")

            if event.is_terminal():
                print(f"→ {event.type} {getattr(event, 'message', None) or event.error or ''}")
                break


async def main() -> None:
    client = get_async_client()

    config = build_assistant_workflow()
    workflow = await client.workflows.create_from_config(config, name=config.workflow_config.name)
    print(f"Created workflow {workflow.id}")

    try:
        # The check answers on its second attempt — the loop exits through the happy edge.
        await run_once(client, workflow.id, mode="normal", label="Run 1 — the check answers")

        # It never answers. The loop exhausts, `self_loop_outcome` becomes 'max_retries',
        # and the second conditional edge is what stops this looking like a stall.
        await run_once(client, workflow.id, mode="always_pending", label="Run 2 — the check never answers")
    finally:
        await client.workflows.delete(workflow.id)
        print(f"\nDeleted workflow {workflow.id}")
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
