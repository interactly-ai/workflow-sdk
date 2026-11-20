import _shared_sdk  # noqa: F401 - bootstraps sys.path (see wf_examples/_shared_sdk.py)

"""Example 19 — Interactly Workflow SDK.

Approvals: a run that pauses for a person. The workflow stops at a Pause Workflow node until a manager approves the
refill it asks about. The script starts it as a durable background run, waits for it to pause, finds the step waiting
for a person, approves it with data, and follows the run to completion.
See ``wf_example_progression_19.md`` for an illustrated walkthrough.

The Pause Workflow node is enabled per server (``CONTROL_WAIT_NODES_ENABLED``). Where it is off, the server refuses the
workflow and the script says so instead of running.

Run it::

    INTERACTLY_API_KEY=... python wf_examples/wf_example_progression_19.py
"""

import asyncio
import time
from typing import Optional

from interactly import AsyncWorkflowClient, BadRequestError, Run
from interactly.configs import (
    DirectEdgeConfig,
    NoOpNodeConfig,
    PauseWorkflowNodeConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
)
from _shared_sdk import get_async_client

#: The run's dynamic variables: the Pause Workflow node's reason names them.
DYNAMIC_VARIABLES = {"patient_name": "Ada Lovelace", "medication": "lisinopril 10 mg"}

#: Statuses a run ends in.
FINISHED = {"completed", "failed", "cancelled"}


def build_assistant_workflow() -> WorkflowConfigFullyHydrated:
    """
    Build a workflow that waits for a manager's approval before it carries on.

    Key concepts introduced in this example:

    1. PauseWorkflowNodeConfig — a step that holds the run until a person approves it. Its ``reason`` (which may use
       dynamic variables) is what the approver sees; ``timeout_seconds`` bounds the wait, after which the run carries
       on as timed out. Once approved, the node writes the approver's note and data to its output variables
       (``pause_result``, ``pause_result_note``, ``pause_result_resumed_by``, ...).

    2. Background runs — ``client.workflows.start_background_run()`` starts a durable run with no user and no socket.
       Only a durable run can wait like this: its state is stored while it waits, for minutes or days.

    3. Approving — ``client.runs.list_pauses()`` lists what the run waits on; ``client.runs.resume(pause_ids=...)``
       approves the steps waiting for a person, with a note and data for them.
    """
    start = NoOpNodeConfig(name="Refill requested", is_start=True)
    approval = PauseWorkflowNodeConfig(
        name="Manager approval",
        description="Holds the run until a manager approves the refill",
        reason="Approve a refill of {{medication}} for {{patient_name}}",
        timeout_seconds=3600,
    )
    done = NoOpNodeConfig(name="Refill sent")

    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(
            category="System Examples",
            name="Example 19: Approvals with a Pause Workflow node",
            description=(
                "A refill request that waits for a manager's approval at a Pause Workflow node, started as a "
                "background run and approved through the run-control API."
            ),
            miscellaneous={"default_dynamic_variables": DYNAMIC_VARIABLES},
        ),
        node_configs=[start, approval, done],
        edge_configs=[
            DirectEdgeConfig(
                name="Requested → Approval",
                source_node_logical_id=start.logical_id,
                destination_node_logical_id=approval.logical_id,
            ),
            DirectEdgeConfig(
                name="Approval → Sent",
                source_node_logical_id=approval.logical_id,
                destination_node_logical_id=done.logical_id,
            ),
        ],
    )


def control_nodes_refused(error: Exception) -> bool:
    """Whether the server refused the workflow because its Pause Workflow node is not enabled there."""
    return isinstance(error, BadRequestError) and "CONTROL_WAIT_NODES_ENABLED" in str(error)


async def wait_for_status(client: AsyncWorkflowClient, run_id: str, statuses: set, timeout: float = 60) -> Run:
    """Poll the run until its status is one of ``statuses``, or the timeout passes. Returns the run as last read."""
    deadline = time.monotonic() + timeout
    while True:
        run = await client.runs.get(run_id)
        if run.status in statuses or time.monotonic() > deadline:
            return run
        await asyncio.sleep(1)


async def run_approval_flow(client: AsyncWorkflowClient) -> Optional[Run]:
    """
    Upload the workflow, run it in the background, approve its step, and follow it to the end. Returns the finished
    run, or None when the server does not enable the Pause Workflow node. The workflow is deleted afterwards.
    """
    config = build_assistant_workflow()
    try:
        workflow = await client.workflows.create_from_config(config)
    except BadRequestError as error:
        if control_nodes_refused(error):
            print(f"Skipped: this server does not enable the Pause Workflow node.\n  {error}")
            return None
        raise
    print(f"Uploaded workflow id={workflow.id}")

    try:
        # 1. Start it as a durable background run.
        started = await client.workflows.start_background_run(
            workflow.id, dynamic_variables=DYNAMIC_VARIABLES, run_by="Example 19"
        )
        run_id = started.workflow_run_id
        print(f"Started background run {run_id} ({started.status})")

        # 2. It runs its first turn in the background and stops at the approval step.
        run = await wait_for_status(client, run_id, {"paused"} | FINISHED)
        print(f"Run is {run.status}; waiting on: {run.pause_summary}")
        if run.status != "paused":
            return run

        # 3. Find the step waiting for a person, and what it asks.
        pauses = await (await client.runs.list_pauses(run_id, open_only=True)).list_all()
        approval = next(pause for pause in pauses if pause.waits_for_person)
        print(f"Waiting for a person: {approval.wake.get('reason')!r} (pause {approval.pause_id})")

        # 4. Approve it, with a note and data for the node.
        result = await client.runs.resume(
            run_id,
            pause_ids=[approval.pause_id],
            note="Approved for 30 days",
            data={"approved": True, "days": 30},
        )
        print(f"Approved: {result.outcome}; made ready: {result.made_ready}")

        # 5. The server resumes the run and it carries on to the end.
        run = await wait_for_status(client, run_id, FINISHED)
        print(f"Run finished: {run.status}")
        return run
    finally:
        await client.workflows.delete(workflow.id)
        print(f"Workflow {workflow.id} deleted.")


async def run():
    client = get_async_client()
    try:
        await run_approval_flow(client)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run())
