"""What a ``RunEvent`` guarantees to a caller reading the stream.

Every assertion here pins something a Phase 5 notebook or guide relied on, and three of them pin
corrections to claims the Phase 4 docs made that turned out to be false when run against a server.
The distinction that matters: ``interactly_configs`` models the *typed* event hierarchy (tested in
``configs/tests``), while ``RunEvent`` is the loose, forward-compatible view the WebSocket stream
yields. They fail differently, so they are tested separately.
"""

from __future__ import annotations

import pytest

from interactly.types.runs.run_event import RunEvent


class TestBackgroundEventTypes:
    """The event types Phase 2 added must survive the loose model intact."""

    @pytest.mark.parametrize(
        "event_type",
        [
            "companion_step_boundary",
            "waiting_evaluation_boundary",
            "waiting_condition_matched",
            "workflow_ready_for_input",
            "self_loop_delay",
            "self_loop_exhausted",
            "node_expired",
            "guardrail_escalation_edge",
        ],
    )
    def test_type_round_trips(self, event_type: str):
        event = RunEvent.model_validate({"type": event_type})
        assert event.type == event_type
        # None of these end the run; only end_workflow / workflow_error do.
        assert event.is_terminal() is False


class TestReadinessVsTermination:
    """The three events that used to coincide and now diverge.

    Breaking a stream loop on the wrong one is the most common streaming bug once companion threads
    are in play: ``end_workflow_iteration`` means one turn's accounting is done, NOT "your turn".
    """

    def test_ready_for_input_is_not_terminal(self):
        event = RunEvent.model_validate({"type": "workflow_ready_for_input"})
        assert event.is_ready_for_input() is True
        assert event.is_terminal() is False

    def test_iteration_end_is_neither(self):
        event = RunEvent.model_validate({"type": "end_workflow_iteration"})
        assert event.is_ready_for_input() is False
        assert event.is_terminal() is False

    @pytest.mark.parametrize("event_type", ["end_workflow", "workflow_error"])
    def test_only_these_two_are_terminal(self, event_type: str):
        event = RunEvent.model_validate({"type": event_type})
        assert event.is_terminal() is True
        assert event.is_ready_for_input() is False


class TestEventExtrasAreTopLevel:
    """Event-specific fields arrive as attributes, NOT under ``data``.

    The Phase 4 docs described ``data`` as "additional server payload", and an example was written
    printing ``event.data`` for a ``self_loop_exhausted``. Against a real server it printed ``None``
    every time: the server populates these fields at the top level and never fills ``data`` in.
    """

    def test_self_loop_exhausted_carries_outcome_at_top_level(self):
        # Shape copied from a real dev response.
        event = RunEvent.model_validate(
            {
                "type": "self_loop_exhausted",
                "outcome": "max_retries",
                "total_attempts": 4,
                "reason": "Bounded self-loop for node node_x stopped after 4 attempt(s): max_retries",
                "source_node_name": "Check Eligibility",
            }
        )
        assert event.outcome == "max_retries"
        assert event.total_attempts == 4
        assert event.data is None, "the server does not populate `data`; extras are top-level"

    def test_self_loop_delay_carries_attempt_number(self):
        event = RunEvent.model_validate(
            {"type": "self_loop_delay", "delay_seconds": 2.0, "attempt_number": 4}
        )
        assert event.attempt_number == 4
        assert event.delay_seconds == 2.0

    def test_waiting_condition_matched_carries_the_hydrated_expression(self):
        # The hydrated form is the field to read when a condition is not firing as expected: it shows
        # what the variables actually resolved to.
        event = RunEvent.model_validate(
            {
                "type": "waiting_condition_matched",
                "condition_expression": "[[thread_bg.attempts]] >= 3",
                "hydrated_condition_expression": "3 >= 3",
                "trigger_mode": "on_node_completion",
                "transitions_this_wait": 1,
            }
        )
        assert event.hydrated_condition_expression == "3 >= 3"
        assert event.condition_expression == "[[thread_bg.attempts]] >= 3"

    def test_extras_are_reachable_through_model_extra_too(self):
        event = RunEvent.model_validate({"type": "self_loop_exhausted", "outcome": "expiry_time"})
        assert (event.model_extra or {}).get("outcome") == "expiry_time"


class TestActiveCompanionThreadIds:
    """``workflow_ready_for_input`` reports INTERNAL thread ids, not the configured ``thread_id``.

    A companion authored as ``thread_id="labpoll"`` comes back as ``"0_companion_labpoll"``. Code that
    compares for equality against the configured id silently never matches.
    """

    def test_ids_are_internal_not_configured(self):
        event = RunEvent.model_validate(
            {"type": "workflow_ready_for_input", "active_companion_thread_ids": ["0_companion_labpoll"]}
        )
        active = event.active_companion_thread_ids
        assert active == ["0_companion_labpoll"]
        assert "labpoll" not in active, "equality against the configured thread_id must not match"
        assert any(tid.endswith("labpoll") for tid in active), "suffix matching is the workable check"


class TestThreadReferenceId:
    """``thread_reference_id`` distinguishes the main thread from a companion on every event."""

    def test_main_thread_is_zero(self):
        event = RunEvent.model_validate({"type": "assistant_response", "thread_reference_id": "0"})
        assert event.thread_reference_id == "0"

    def test_companion_carries_its_configured_id(self):
        event = RunEvent.model_validate({"type": "start_node_run", "thread_reference_id": "labpoll"})
        assert event.thread_reference_id == "labpoll"

    def test_absent_is_none_rather_than_an_error(self):
        # Events emitted outside any thread (run_ack, end_workflow) carry no reference id.
        event = RunEvent.model_validate({"type": "run_ack"})
        assert event.thread_reference_id is None


class TestForwardCompatibility:
    """A server ahead of the SDK must never break an older client."""

    def test_unknown_type_with_unknown_fields_is_preserved(self):
        event = RunEvent.model_validate(
            {"type": "some_event_added_next_quarter", "brand_new_field": {"nested": 1}}
        )
        assert event.type == "some_event_added_next_quarter"
        assert event.brand_new_field == {"nested": 1}
        assert event.is_terminal() is False

    def test_content_is_mapped_onto_output(self):
        # The server names the field `content`; the SDK surfaces it as `output`.
        event = RunEvent.model_validate({"type": "assistant_response", "content": "Hello."})
        assert event.output == "Hello."

    def test_origin_node_logical_id_is_mapped_onto_node_id(self):
        event = RunEvent.model_validate({"type": "start_node_run", "origin_node_logical_id": "node_a"})
        assert event.node_id == "node_a"
