"""Run control against a live server: background runs, approvals, pauses, signals and cancels.

The unit suite replays captured answers; this checks the server still gives them. Both tests need a Pause Workflow
node, which a server enables per deployment (``CONTROL_WAIT_NODES_ENABLED``), so each skips where the server refuses
it. Run it against dev when a release is cut::

    pytest tests/integration/test_run_control_e2e.py -m integration

No LLM calls. Each test deletes the workflow it uploads.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

from interactly import AsyncWorkflowClient, BadRequestError

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("INTERACTLY_API_KEY"),
        reason="requires live INTERACTLY_* credentials",
    ),
]

_EXAMPLES = Path(__file__).resolve().parents[2] / "wf_examples"
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))

import wf_example_progression_19 as example_19  # noqa: E402


async def test_example_19_approves_its_step_and_the_run_completes():
    """The curriculum's approval flow, exactly as its documented command runs it."""
    client = AsyncWorkflowClient()
    try:
        run = await example_19.run_approval_flow(client)
    finally:
        await client.close()

    if run is None:
        pytest.skip("this server does not enable the Pause Workflow node")
    assert run.status == "completed"


async def test_a_background_run_is_paused_signalled_and_cancelled():
    client = AsyncWorkflowClient()
    config = example_19.build_assistant_workflow()
    config.workflow_config.name = f"SDK_E2E run control {uuid.uuid4().hex[:8]}"
    workflow_id = None
    try:
        try:
            workflow_id = (await client.workflows.create_from_config(config)).id
        except BadRequestError as error:
            if example_19.control_nodes_refused(error):
                pytest.skip("this server does not enable the Pause Workflow node")
            raise

        started = await client.workflows.start_background_run(
            workflow_id, dynamic_variables=example_19.DYNAMIC_VARIABLES, run_by="SDK_E2E"
        )
        run_id = started.workflow_run_id
        run = await example_19.wait_for_status(client, run_id, {"paused"} | example_19.FINISHED)
        assert run.status == "paused" and run.durable is True

        # A person's pause on top of the node's: recorded, and shown on the run.
        held = await client.runs.pause(run_id, reason="SDK_E2E hold")
        assert held.outcome == "applied"
        run = await client.runs.get(run_id)
        assert (run.pause_requested, run.pause_reason) == (True, "SDK_E2E hold")

        # A signal no wait is listening for yet is stored, and listed without its body.
        signal = await client.runs.send_signal(run_id, "sdk_e2e.note", {"n": 1})
        assert signal.outcome == "stored"
        listed = await (await client.runs.list_signals(run_id)).list_all()
        assert [(s.signal_key, s.consumed) for s in listed] == [("sdk_e2e.note", False)]

        cancelled = await client.runs.cancel(run_id, reason="SDK_E2E done")
        assert cancelled.outcome == "applied"
        run = await example_19.wait_for_status(client, run_id, example_19.FINISHED, timeout=30)
        assert run.status == "cancelled"
        assert await (await client.runs.list_pauses(run_id, open_only=True)).list_all() == []
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()
