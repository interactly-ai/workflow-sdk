"""Pausing, the control nodes and the other node types mirrored from upstream in this sync.

Each group checks the behaviour a client depends on: a workflow holding these nodes parses into their real classes
(not the forward-compatible fallback) and keeps its ``type`` when sent back, pause events carry what ends the pause,
and the validators upstream enforces at save time refuse the same configurations here.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

import interactly_configs as ic
from interactly_configs.events import Event, PauseEvent
from interactly_configs.llm import resolve_reasoning_effort
from interactly_configs.simulation import SimulationConfig
from interactly_configs.workflow import UnknownNodeConfig

NEW_NODE_TYPES = {
    "pause_workflow": ic.PauseWorkflowNodeConfig,
    "wait": ic.WaitNodeConfig,
    "wait_for_signal": ic.WaitForSignalNodeConfig,
    "terminate_workflow": ic.TerminateWorkflowNodeConfig,
    "aws_ecs_run_task": ic.RunEcsTaskNodeConfig,
    "aws_ecs_start_task": ic.StartEcsTaskNodeConfig,
    "aws_ecs_get_task_status": ic.GetEcsTaskStatusNodeConfig,
    "aws_ecs_stop_task": ic.StopEcsTaskNodeConfig,
    "aws_ecs_wait_for_tasks": ic.WaitForEcsTasksNodeConfig,
    "aws_ecs_get_task_logs": ic.GetEcsTaskLogsNodeConfig,
    "conversation_fetch": ic.ConversationFetchNodeConfig,
    "analysis_llm": ic.AnalysisLLMNodeConfig,
    "store_analysis": ic.StoreAnalysisNodeConfig,
    "decisions": ic.DecisionsNodeConfig,
}


class TestNewNodeTypesInAWorkflow:
    @pytest.mark.parametrize("node_type, cls", sorted(NEW_NODE_TYPES.items()))
    def test_a_stored_node_parses_into_its_class_and_keeps_its_type(self, node_type, cls):
        # Arrange
        stored = {"workflow_config": {"name": "w"}, "node_configs": [{"type": node_type, "logical_id": "n1"}]}

        # Act
        hydrated = ic.WorkflowConfigFullyHydrated.model_validate(stored)

        # Assert
        [node] = hydrated.node_configs
        assert type(node) is cls
        assert not isinstance(node, UnknownNodeConfig)
        assert hydrated.model_dump(mode="json")["node_configs"][0]["type"] == node_type

    def test_a_pause_workflow_node_built_in_code_round_trips(self):
        # Arrange
        node = ic.PauseWorkflowNodeConfig(logical_id="approve", name="Approve", reason="Check the dose", notify=False)
        hydrated = ic.WorkflowConfigFullyHydrated(workflow_config=ic.WorkflowConfig(name="w"), node_configs=[node])

        # Act
        again = ic.WorkflowConfigFullyHydrated.model_validate(hydrated.model_dump(mode="json"))

        # Assert
        [parsed] = again.node_configs
        assert (type(parsed), parsed.reason, parsed.notify) == (ic.PauseWorkflowNodeConfig, "Check the dose", False)

    def test_a_wait_longer_than_the_waiting_limit_is_refused(self):
        # Act / Assert
        with pytest.raises(ValidationError):
            ic.WaitNodeConfig(duration_seconds=ic.MAX_WAITING_SECONDS + 1)


class TestOnFailure:
    def test_every_node_routes_its_failures_unless_told_otherwise(self):
        # Act
        node = ic.NoOpNodeConfig(name="n")

        # Assert
        assert node.on_failure is ic.NodeFailurePolicy.ROUTE

    def test_aborting_the_run_cannot_be_combined_with_an_enabled_self_loop(self):
        # Act / Assert
        with pytest.raises(ValidationError, match="abort_workflow"):
            ic.NoOpNodeConfig(
                name="n",
                on_failure=ic.NodeFailurePolicy.ABORT_WORKFLOW,
                self_loop_config=ic.SelfLoopConfig(enabled=True, max_retries=3),
            )

    def test_aborting_the_run_alone_is_accepted(self):
        # Act
        node = ic.NoOpNodeConfig(name="n", on_failure="abort_workflow")

        # Assert
        assert node.on_failure is ic.NodeFailurePolicy.ABORT_WORKFLOW


class TestPausesAndTheirEvents:
    def test_a_run_can_be_waiting(self):
        # Act / Assert
        assert ic.WorkflowStatus("waiting") is ic.WorkflowStatus.WAITING

    @pytest.mark.parametrize(
        "wake, cls",
        [
            ({"kind": "manual", "reason": "Approve"}, ic.ManualWake),
            ({"kind": "timer", "wake_at": "2026-11-20T10:00:00Z"}, ic.TimerWake),
            ({"kind": "signal", "signal_key": "approval.done"}, ic.SignalWake),
            ({"kind": "run_pause"}, ic.RunPauseWake),
        ],
    )
    def test_a_pause_event_carries_what_ends_the_pause(self, wake, cls):
        # Arrange
        stored = {"type": "pause_event", "pause_id": "p1", "wake": wake}

        # Act
        event = TypeAdapter(Event).validate_python(stored)

        # Assert
        assert type(event) is PauseEvent
        assert isinstance(event.wake, cls)
        assert event.pause_id == "p1"

    def test_a_manual_pause_is_announced_unless_its_node_opted_out(self):
        # Act
        wake = TypeAdapter(ic.WakeCondition).validate_python({"kind": "manual"})

        # Assert
        assert wake.notify is True

    def test_a_pause_event_without_a_wake_is_a_manual_pause_as_before(self):
        # Act
        event = TypeAdapter(Event).validate_python({"type": "pause_event"})

        # Assert
        assert event.wake is None

    def test_a_terminate_event_parses_with_its_outcome_and_cause(self):
        # Act
        event = TypeAdapter(Event).validate_python(
            {"type": "terminate_workflow", "outcome": "failed", "reason": "no consent", "cause": "terminate_node"}
        )

        # Assert
        assert (type(event).__name__, event.outcome, event.cause) == (
            "TerminateWorkflowEvent",
            "failed",
            "terminate_node",
        )

    def test_a_thread_paused_durably_names_its_pause_and_wake(self):
        # Act
        event = TypeAdapter(Event).validate_python({"type": "pause_thread", "pause_id": "p1", "wake_kind": "timer"})

        # Assert
        assert (event.pause_id, event.wake_kind) == ("p1", ic.WakeKind.TIMER)


class TestOtherUpstreamChanges:
    def test_a_simulation_takes_one_outcome_per_waiting_node(self):
        # Arrange
        outcome = {"node_logical_id": "w", "outcome": "succeeded"}

        # Act / Assert
        with pytest.raises(ValidationError):
            SimulationConfig(simulated_node_outcomes=[outcome, outcome])

    def test_a_decisions_api_needs_the_gateway_base_url(self):
        # Act / Assert
        with pytest.raises(ValidationError, match="Gateway Base URL"):
            ic.CustomLLMConfig(model_name="m", decisions_api="openai")

    @pytest.mark.parametrize(
        "model, asked, used",
        [
            ("gpt-6.1-sol", "none", "low"),
            ("gpt-6.1-sol", "minimal", "low"),
            ("gpt-6-luna", "minimal", "none"),
            ("gpt-6.1-terra", "minimal", "none"),
            ("gpt-6-luna", "high", "high"),
        ],
    )
    def test_reasoning_effort_is_raised_to_what_a_gpt_6_model_accepts(self, model, asked, used):
        # Act / Assert
        assert resolve_reasoning_effort(model, asked) == used

    def test_credential_fields_publish_no_dashboard_marker(self):
        # Act
        headers = ic.ExternalAPIToolConfig.model_json_schema()["properties"]["api_headers"]

        # Assert: the mirror drops upstream's annotation, as it drops every dashboard annotation
        assert "sensitive_map" not in headers

    def test_a_workflow_is_standard_unless_made_an_evaluation(self):
        # Act / Assert
        assert ic.WorkflowConfig(name="w").workflow_type is ic.WorkflowType.STANDARD
