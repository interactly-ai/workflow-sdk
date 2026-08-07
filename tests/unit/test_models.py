"""Unit tests for Pydantic response models."""

from __future__ import annotations

from interactly.types.runs.run import Run
from interactly.types.runs.run_event import RunEvent
from interactly.types.workflows.workflow import Workflow


class TestWorkflowModel:
    def test_parses_minimal_response(self):
        data = {"id": "wf-1", "name": "Minimal"}
        wf = Workflow.model_validate(data)
        assert wf.id == "wf-1"
        assert wf.name == "Minimal"
        assert wf.description is None

    def test_extra_fields_are_stored(self):
        data = {"id": "wf-1", "name": "X", "future_field": "value"}
        wf = Workflow.model_validate(data)
        # Extra fields are preserved (extra="allow").
        assert wf.model_extra is not None
        assert wf.model_extra.get("future_field") == "value"

    def test_parses_datetime_strings(self):
        data = {"id": "wf-1", "name": "X", "created_at": "2024-01-01T00:00:00Z"}
        wf = Workflow.model_validate(data)
        assert wf.created_at is not None


class TestRunModel:
    def test_parses_complete_run(self):
        data = {
            "id": "run-1",
            "workflow_id": "wf-1",
            "status": "completed",
            "run_by": "api",
            "version_number": 2,
        }
        run = Run.model_validate(data)
        assert run.id == "run-1"
        # status is Optional[str] (finding RT-3) — compare against the raw value.
        assert run.status == "completed"

    def test_unknown_status_is_accepted(self):
        # Future status values must not break parsing (finding RT-3): status is a
        # plain str, so an unrecognized value is passed through unchanged.
        data = {"id": "run-1", "workflow_id": "wf-1", "status": "unknown_future_status"}
        run = Run.model_validate(data)
        assert run.status == "unknown_future_status"


class TestRunEvent:
    def test_parses_terminal_event(self):
        # Terminal event types are end_workflow / workflow_error (finding RT-2).
        event = RunEvent.model_validate({"type": "end_workflow", "status": "completed"})
        assert event.is_terminal() is True

    def test_parses_non_terminal_event(self):
        event = RunEvent.model_validate({"type": "node_started", "node_id": "node-1"})
        assert event.is_terminal() is False

    def test_unknown_event_type_is_preserved(self):
        event = RunEvent.model_validate({"type": "new_event_type_v2", "output": "hello"})
        assert event.type == "new_event_type_v2"
        assert event.is_terminal() is False

    def test_parses_reverse_conditional_edge_event(self):
        # Arrange — payload emitted by the server when a global node triggers reverse navigation.
        event = RunEvent.model_validate(
            {
                "type": "reverse_conditional_edge",
                "global_node_logical_id": "global-node-1",
                "node_id": "prev-node-2",
            }
        )

        # Assert — typed field is accessible directly (not via model_extra).
        assert event.type == "reverse_conditional_edge"
        assert event.global_node_logical_id == "global-node-1"
        assert event.node_id == "prev-node-2"

    def test_reverse_conditional_edge_is_not_terminal(self):
        # Arrange — navigation events must never be treated as run-ending.
        event = RunEvent.model_validate({"type": "reverse_conditional_edge"})

        # Assert
        assert event.is_terminal() is False

    def test_reverse_conditional_edge_global_node_id_defaults_to_none(self):
        # Arrange — server may omit global_node_logical_id in older payloads.
        event = RunEvent.model_validate({"type": "reverse_conditional_edge"})

        # Assert — field present but None, not in model_extra.
        assert event.global_node_logical_id is None
        assert "global_node_logical_id" not in (event.model_extra or {})
