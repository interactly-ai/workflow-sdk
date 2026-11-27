"""REST execute against a live server: the version a turn runs is the one asked for.

The server reads a turn's version only from ``?version=`` and overwrites the body's; the SDK used to send it in the
body, so every turn ran the active version. This runs version 0 of a workflow whose active version is 1, and reads the
run back. No LLM calls; the workflow it uploads is deleted.

    pytest tests/integration/test_runs_e2e.py -m integration
"""

from __future__ import annotations

import os
import uuid

import pytest

from interactly import AsyncWorkflowClient
from interactly.configs import (
    DirectEdgeConfig,
    SayStaticMessageNodeConfig,
    StaticMessagesConfig,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]


def _static_workflow() -> WorkflowConfigFullyHydrated:
    greet = SayStaticMessageNodeConfig(
        name="Greet", is_start=True, static_messages_config=StaticMessagesConfig(static_messages=["hi"])
    )
    bye = SayStaticMessageNodeConfig(name="Bye", static_messages_config=StaticMessagesConfig(static_messages=["bye"]))
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(name=f"SDK_E2E execute version {uuid.uuid4().hex[:8]}"),
        node_configs=[greet, bye],
        edge_configs=[
            DirectEdgeConfig(
                source_node_logical_id=greet.logical_id, destination_node_logical_id=bye.logical_id, name="greet->bye"
            )
        ],
    )


async def test_execute_runs_the_version_asked_for_not_the_active_one():
    client = AsyncWorkflowClient()
    workflow_id = None
    try:
        workflow_id = (await client.workflows.create_from_config(_static_workflow())).id
        await client.workflows.versions.create(
            workflow_id, version_name="v1", source_version_number=0, mark_as_active=True
        )

        turn = await client.runs.execute(workflow_id, version_number=0)
        run = await client.runs.get(turn.run_id)

        assert run.version_number == 0
    finally:
        if workflow_id:
            await client.workflows.delete(workflow_id)
        await client.close()
