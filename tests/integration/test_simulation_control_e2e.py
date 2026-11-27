"""A simulation group is paused, held, resumed and stopped, and the simulations list filters as asked.

Both workflows answer through an LLM gateway whose host can never resolve (the ``.invalid`` domain is reserved for
exactly that), so each simulation fails at once without reaching any provider, and the group works through forty of
them one at a time: long enough to pause it. No LLM is billed; the workflows and the simulation are deleted.

    pytest tests/integration/test_simulation_control_e2e.py -m integration
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator, Tuple

import pytest

from interactly import ConflictError, SimulationStatus, WorkflowClient
from interactly.configs import (
    CustomLLMConfig,
    SayLLMNodeConfig,
    SimulationConfig,
    SimulationWorkflowDetails,
    WorkflowConfig,
    WorkflowConfigFullyHydrated,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("INTERACTLY_API_KEY"), reason="requires live INTERACTLY_* credentials"),
]

#: What a group's pause or resume can answer for one workflow run of a simulation in flight.
_RUN_OUTCOMES = {"applied", "already_requested", "not_paused", "not_durable", "run_ended", "not_found", "conflict"}


def _unreachable_llm() -> CustomLLMConfig:
    return CustomLLMConfig(
        base_url="https://llm.unreachable.invalid/v1",
        model="none",
        api_key="unused",
        max_retries=0,
        request_timeout_ms=2000,
        streaming=False,
    )


def _workflow(role: str) -> WorkflowConfigFullyHydrated:
    node = SayLLMNodeConfig(name="Ask", is_start=True, llms_config=_unreachable_llm(), wait_for_user_message=True)
    return WorkflowConfigFullyHydrated(
        workflow_config=WorkflowConfig(
            name=f"SDK_E2E simulation {role} {uuid.uuid4().hex[:8]}", llms_config=_unreachable_llm()
        ),
        node_configs=[node],
        edge_configs=[],
    )


@pytest.fixture
def simulation() -> Iterator[Tuple[WorkflowClient, str, str, str]]:
    """A client, and a simulation of two throwaway workflows, as (client, simulation id, selected id, counter id)."""
    client = WorkflowClient()
    workflow_ids = []
    simulation_id = None
    try:
        workflow_ids = [client.workflows.create_from_config(_workflow(role)).id for role in ("selected", "counter")]
        config = SimulationConfig(
            name=f"SDK_E2E simulation control {uuid.uuid4().hex[:8]}",
            description="SDK_E2E pause, resume and stop",
            selected_workflow=SimulationWorkflowDetails(workflow_id=workflow_ids[0]),
            counter_workflow=SimulationWorkflowDetails(workflow_id=workflow_ids[1]),
            number_of_simulations=40,
            max_concurrent_runs=1,
            timeout_seconds=20,
            max_events=50,
        )
        simulation_id = client.simulations.create(config=config.model_dump(exclude_none=True)).id
        yield client, simulation_id, workflow_ids[0], workflow_ids[1]
    finally:
        if simulation_id:
            client.simulations.delete(simulation_id)
        for workflow_id in workflow_ids:
            client.workflows.delete(workflow_id)
        client.close()


def test_a_paused_group_starts_no_simulation_until_resumed_and_a_stopped_one_cannot_be_paused(simulation):
    client, simulation_id, _, _ = simulation
    group_id = client.simulations.run(simulation_id).id

    paused = client.simulations.pause_run(group_id, reason="SDK_E2E pause")
    time.sleep(1)
    held_at = client.simulations.list_executions(group_id, size=1).total
    time.sleep(4)
    held_after = client.simulations.list_executions(group_id, size=1).total
    status_while_paused = client.simulations.get_run(group_id).status
    resumed = client.simulations.resume_run(group_id)
    stopped = client.simulations.stop_run(group_id)

    assert paused.simulation_group.status == SimulationStatus.PAUSED
    assert all(r.role in {"selected", "counter"} and r.outcome in _RUN_OUTCOMES for r in paused.runs + resumed.runs)
    assert (status_while_paused, held_after) == (SimulationStatus.PAUSED, held_at)
    assert resumed.simulation_group.status == SimulationStatus.RUNNING
    assert stopped.status == SimulationStatus.CANCELLED
    with pytest.raises(ConflictError, match="already ended"):
        client.simulations.pause_run(group_id)
    assert client.simulations.stop_run(group_id).status == SimulationStatus.CANCELLED


def test_the_simulations_list_filters_as_asked(simulation):
    client, simulation_id, selected_id, counter_id = simulation
    logical_id = (client.simulations.get(simulation_id).simulation_config or {}).get("logical_id")
    now = datetime.now(timezone.utc)

    def ids(**filters) -> list:
        return [s.id for s in client.simulations.list(size=50, **filters)]

    assert ids(selected_workflow_id=selected_id) == [simulation_id]
    assert ids(counter_workflow_id=counter_id, counter_version_number=0) == [simulation_id]
    assert ids(logical_id=logical_id) == [simulation_id]
    assert ids(selected_workflow_id=selected_id, selected_version_number=7) == []
    assert ids(selected_workflow_id=selected_id, status=SimulationStatus.PENDING) == [simulation_id]
    assert ids(selected_workflow_id=selected_id, status=SimulationStatus.COMPLETED) == []
    assert ids(selected_workflow_id=selected_id, start=now - timedelta(hours=1), end=now + timedelta(minutes=5)) == [
        simulation_id
    ]
    assert ids(selected_workflow_id=selected_id, start=now - timedelta(days=400), end=now - timedelta(days=380)) == []
    assert client.simulations.get(simulation_id).status == SimulationStatus.PENDING
