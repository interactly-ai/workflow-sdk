"""A run's pause state, the WAITING status, and webhook actions this SDK does not know yet.

The run fixtures are real answers from a workflow-service, captured for a durable run a person paused while a timer
and a Pause Workflow node held it, with every id, name and address replaced:

* ``run_get_paused.json``: ``GET /v1/workflow-runs/{id}``. The pause state and the feedback authors sit on the
  envelope, beside the stored record.
* ``run_list_paused.json``: the run list. A row carries ``pause_requested`` and ``pause_summary`` itself.
"""

from __future__ import annotations

import copy
import json
from datetime import timezone
from pathlib import Path

import pytest

from interactly.types.runs.run import Run
from interactly.types.shared import RunStatus
from interactly.types.webhooks.webhook import (
    WebhookAction,
    WebhookDeliveryAttempt,
    WebhookEvent,
    WebhookSubscription,
)

FIXTURES = Path(__file__).parent / "fixtures"
PAUSER = "665f1c0a2b3c4d5e6f708192"
APPROVAL = "665f1c0a2b3c4d5e6f708400"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class TestARunsPauseState:
    def test_the_get_answer_fills_every_pause_field(self):
        # Act
        run = Run.model_validate(_fixture("run_get_paused.json"))

        # Assert
        assert (run.status, run.durable, run.pause_requested) == (RunStatus.PAUSED, True, True)
        assert (run.paused_by, run.pause_reason) == (PAUSER, "Checking the dose")
        assert run.paused_since is not None and run.paused_since.tzinfo is not None
        assert run.paused_since.utcoffset() == timezone.utc.utcoffset(None)
        assert run.paused_seconds_total == pytest.approx(0.015993)
        assert [p["pause_id"] for p in run.pause_summary["manual_pauses"]] == [APPROVAL]

    def test_the_get_answer_names_whoever_paused_the_run(self):
        # Act
        run = Run.model_validate(_fixture("run_get_paused.json"))

        # Assert: feedback_users sits on the envelope too, and used to be dropped with it
        pauser = run.feedback_users[run.paused_by]
        assert (pauser.firstName, pauser.lastName) == ("Ada", "Lovelace")

    def test_a_run_waiting_on_a_timer_reads_as_waiting(self):
        # Arrange: the same run once the person's pause is lifted, still waiting on its timer
        answer = copy.deepcopy(_fixture("run_get_paused.json"))
        answer["workflow_run"]["workflow_run"]["status"] = "waiting"
        answer.update(pause_requested=False, paused_by=None, pause_reason=None, paused_since=None)

        # Act
        run = Run.model_validate(answer)

        # Assert
        assert run.status == RunStatus.WAITING
        assert (run.pause_requested, run.paused_by, run.paused_since) == (False, None, None)
        assert run.pause_summary["by_wake_kind"] == {"timer": 1, "manual": 1}

    def test_a_list_row_carries_what_the_list_sends_and_leaves_the_rest_unknown(self):
        # Arrange
        [row] = _fixture("run_list_paused.json")["workflow_runs"]

        # Act
        run = Run.model_validate(row)

        # Assert
        assert run.pause_requested is True
        assert [p["pause_id"] for p in run.pause_summary["manual_pauses"]] == [APPROVAL]
        assert (run.durable, run.paused_by, run.paused_since, run.paused_seconds_total) == (None, None, None, None)

    def test_an_answer_without_pause_state_leaves_every_field_unknown(self):
        # Arrange: a server older than the pause fields sends the envelope with the record alone
        answer = {"workflow_run": _fixture("run_get_paused.json")["workflow_run"]}

        # Act
        run = Run.model_validate(answer)

        # Assert
        assert (run.durable, run.pause_requested, run.pause_summary, run.paused_by) == (None, None, None, None)
        assert run.feedback_users == {}

    def test_an_already_flat_run_keeps_its_pause_fields(self):
        # Act
        run = Run.model_validate({"id": "r1", "workflow_id": "w1", "status": "waiting", "durable": True})

        # Assert
        assert (run.status, run.durable) == ("waiting", True)


class TestWebhookActions:
    def test_the_pause_actions_are_known(self):
        # Act / Assert
        assert WebhookAction("workflow_run_paused") is WebhookAction.WORKFLOW_RUN_PAUSED
        assert WebhookAction("workflow_run_resumed") is WebhookAction.WORKFLOW_RUN_RESUMED

    def test_a_known_action_parses_as_its_member(self):
        # Act
        event = WebhookEvent(event_id="e1", subscription_id="s1", action="workflow_run_resumed", status="delivered")

        # Assert
        assert event.action is WebhookAction.WORKFLOW_RUN_RESUMED

    def test_an_event_with_an_action_this_sdk_does_not_know_still_parses(self):
        # Act
        event = WebhookEvent(event_id="e1", subscription_id="s1", action="workflow_run_split", status="pending")

        # Assert
        assert event.action == "workflow_run_split"
        assert not isinstance(event.action, WebhookAction)

    def test_a_subscription_to_known_and_unknown_actions_parses_and_keeps_each(self):
        # Act
        subscription = WebhookSubscription(
            id="s1",
            name="ops",
            url="https://example.com/hook",
            actions=["workflow_run_paused", "workflow_run_split"],
            enabled=True,
            has_bearer_token=False,
            timeout_seconds=10,
            max_retries=3,
            retry_backoff_seconds=10,
        )

        # Assert
        assert subscription.actions == [WebhookAction.WORKFLOW_RUN_PAUSED, "workflow_run_split"]
        assert subscription.actions[0] is WebhookAction.WORKFLOW_RUN_PAUSED

    def test_a_delivery_attempt_for_an_unknown_action_parses(self):
        # Act
        attempt = WebhookDeliveryAttempt(
            event_id="e1",
            subscription_id="s1",
            attempt_number=1,
            action="workflow_run_split",
            request_url="https://example.com/hook",
            success=True,
        )

        # Assert
        assert attempt.action == "workflow_run_split"
