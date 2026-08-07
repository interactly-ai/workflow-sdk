"""
Coverage for the Phase 3 HTTP surface: re-runs, run feedback, background-work pumping, the
streaming close codes, and the error-body handling.

The assertions lean on *what goes on the wire* rather than on the SDK's own plumbing. That is
deliberate: every bug this phase fixed was a mismatch between what the SDK sent or expected and what
the server actually does, and only a wire-level assertion can catch that class of error. The two
`get_fully_hydrated` bugs both survived a green test suite because the mocks encoded a shape the
server never produces.
"""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest
import respx

from interactly import AsyncWorkflowClient, BadRequestError, WorkflowClient
from interactly._exceptions import _make_status_error
from interactly._streaming import (
    _CLOSE_CODE_ERRORS,
    InvalidStreamInputError,
    RerunTokenError,
    StreamError,
)
from interactly.types.reruns.rerun import (
    RerunMode,
    RerunnableTurnsResponse,
    RerunPreflightResponse,
    RerunStartedResponse,
    RerunTokenPreviewResponse,
    RerunTokenResponse,
)
from interactly.types.runs.interactive_run import InteractiveRunResponse
from interactly.types.runs.run import RunFeedbackResponse

TEST_BASE_URL = "http://localhost:8611"
_RUN_ID = "run-1"
_WF_ID = "wf-1"


@pytest.fixture
def client() -> WorkflowClient:
    return WorkflowClient(
        api_key="test-api-key",
        team_id="test-team-id",
        user_id="test-user-id",
        base_url=TEST_BASE_URL,
        max_retries=0,
    )


def _captured(store: Dict[str, Any], payload: Dict[str, Any], status: int = 200):
    """respx side_effect that records the outgoing request and answers with ``payload``."""

    def _handler(request: httpx.Request) -> httpx.Response:
        store["url"] = str(request.url)
        store["method"] = request.method
        store["content"] = request.content.decode() or ""
        return httpx.Response(status, json=payload)

    return _handler


# =========================================================================== #
# Re-runs                                                                     #
# =========================================================================== #


class TestRerunnableTurns:
    @respx.mock
    def test_lists_turns_with_their_verdicts(self, client: WorkflowClient):
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/rerunnable-turns").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflow_run_id": _RUN_ID,
                    "turns": [
                        {"turn_index": 0, "rerunnable": True, "rerun_count": 2},
                        {"turn_index": 1, "rerunnable": False, "reason": "no stored config"},
                    ],
                },
            )
        )

        result = client.reruns.rerunnable_turns(_RUN_ID)

        assert isinstance(result, RerunnableTurnsResponse)
        assert [t.turn_index for t in result.turns] == [0, 1]
        assert result.turns[0].rerun_count == 2
        assert result.turns[1].reason == "no stored config"


class TestRerunPreconditions:
    """Server-enforced preconditions that are easy to misread. Both were hit live on dev."""

    @respx.mock
    def test_rest_driven_runs_report_why_they_cannot_be_rerun(self, client: WorkflowClient):
        # Re-run reconstructs state against the config the run used, and that snapshot is written
        # ONLY by the WebSocket driver. A run driven through the REST execute() path carries none,
        # so every turn comes back not-rerunnable with a message that reads like the run is old.
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/rerunnable-turns").mock(
            return_value=httpx.Response(
                200,
                json={
                    "workflow_run_id": _RUN_ID,
                    "turns": [
                        {
                            "turn_index": 0,
                            "rerunnable": False,
                            "reason": "This run predates workflow config snapshots, so its state "
                            "cannot be reconstructed.",
                        }
                    ],
                },
            )
        )

        turns = client.reruns.rerunnable_turns(_RUN_ID)

        assert turns.turns[0].rerunnable is False
        assert "cannot be reconstructed" in turns.turns[0].reason

    @respx.mock
    def test_feedback_on_an_unfinished_run_surfaces_the_servers_reason(self, client: WorkflowClient):
        from interactly import ConflictError

        respx.put(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/0/rating").mock(
            return_value=httpx.Response(
                409,
                json={
                    "detail": "Feedback cannot be left while the run is still in progress. "
                    "Wait for the run to finish and try again."
                },
            )
        )

        with pytest.raises(ConflictError) as excinfo:
            client.runs.set_turn_rating(_RUN_ID, 0, "up")

        assert "still in progress" in str(excinfo.value)


class TestRerunPreflight:
    @respx.mock
    def test_reports_what_would_be_dropped(self, client: WorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/2/rerun-preflight").mock(
            return_value=httpx.Response(
                200,
                json={
                    "rerunnable": True,
                    "resolved_mode": "REMAPPED",
                    "carries_over": {"message_count": 6, "variable_count": 3},
                    "dropped": {"node_ids": ["node_a"], "variable_keys": ["v1"], "state_keys": []},
                    "node_matches": [
                        {
                            "source_node_logical_id": "n1",
                            "target_node_logical_id": "n2",
                            "matched_by": "name",
                        }
                    ],
                    "warnings": ["one node could not be matched"],
                },
            )
        )

        result = client.reruns.preflight(_RUN_ID, 2)

        assert isinstance(result, RerunPreflightResponse)
        assert result.resolved_mode is RerunMode.REMAPPED
        assert result.carries_over.message_count == 6
        assert result.dropped.node_ids == ["node_a"]
        assert result.node_matches[0].matched_by.value == "name"

    @respx.mock
    def test_omits_target_fields_the_caller_did_not_supply(self, client: WorkflowClient):
        # Omission is not the same as null: the server derives the source run's own workflow, the
        # active version, and a history mode chosen from how far the configs diverged.
        captured: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/0/rerun-preflight").mock(
            side_effect=_captured(captured, {"rerunnable": True})
        )

        client.reruns.preflight(_RUN_ID, 0)

        assert captured["content"] in ("{}", "")

    @respx.mock
    def test_sends_only_the_supplied_target_fields(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/0/rerun-preflight").mock(
            side_effect=_captured(captured, {"rerunnable": True})
        )

        client.reruns.preflight(
            _RUN_ID, 0, target_workflow_id="wf-2", history_mode="NONE", requested_mode="EXACT"
        )

        body = json.loads(captured["content"])
        assert body["target_workflow_id"] == "wf-2"
        assert body["history_mode"] == "NONE"
        assert body["requested_mode"] == "EXACT"
        assert "target_version_number" not in body


class TestRerunToken:
    @respx.mock
    def test_create_token_returns_the_credential_and_its_origin(self, client: WorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/1/rerun-token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "rerun_token": "tok-abc",
                    "expires_in_seconds": 900,
                    "resolved_mode": "EXACT",
                    "source_workflow_run_id": _RUN_ID,
                    "turn_index": 1,
                    "restored_message_count": 4,
                },
            )
        )

        result = client.reruns.create_token(_RUN_ID, 1)

        assert isinstance(result, RerunTokenResponse)
        assert result.rerun_token == "tok-abc"
        assert result.resolved_mode is RerunMode.EXACT
        assert result.restored_message_count == 4

    @respx.mock
    def test_preview_does_not_echo_the_token_back(self, client: WorkflowClient):
        # The preview response deliberately omits the token: the caller already holds it, and
        # repeating a credential in a body invites it into logs the request line would not reach.
        respx.get(
            f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/1/rerun-token/tok-abc"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "source_workflow_run_id": _RUN_ID,
                    "turn_index": 1,
                    "resolved_mode": "EXACT",
                    "effective_mode": "EXACT",
                    "edited": False,
                    "resume_thread_id": "0",
                    "threads": [{"thread_id": "0", "messages": []}],
                },
            )
        )

        result = client.reruns.preview_token(_RUN_ID, 1, "tok-abc")

        assert isinstance(result, RerunTokenPreviewResponse)
        assert result.resume_thread_id == "0"
        assert not hasattr(result, "rerun_token") or getattr(result, "rerun_token", None) is None

    @respx.mock
    def test_amend_sends_only_the_verbs_used(self, client: WorkflowClient):
        # The server sets extra="forbid" on this body, so anything it does not recognise is a hard
        # error — sending keys the caller did not ask for would turn a valid edit into a 4xx.
        captured: Dict[str, Any] = {}
        respx.patch(
            f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/1/rerun-token/tok-abc"
        ).mock(side_effect=_captured(captured, {"edited": True, "effective_mode": "EDITED"}))

        result = client.reruns.amend_token(
            _RUN_ID,
            1,
            "tok-abc",
            message_edits=[{"thread_id": "0", "index": 2, "text": "changed"}],
        )

        body = json.loads(captured["content"])
        assert "message_edits" in body
        for absent in ("dynamic_variables", "runtime_variables", "message_appends", "message_deletes"):
            assert absent not in body
        assert result.edited is True
        assert result.effective_mode == "EDITED"


class TestRerunExecute:
    @respx.mock
    def test_defaults_to_async_and_omits_message(self, client: WorkflowClient):
        # Omitting `message` is the safe default: re-entering the restored node would repeat
        # whatever it already did (a tool node's API write, an outbound notification).
        captured: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/3/rerun").mock(
            side_effect=_captured(
                captured, {"workflow_run_id": "run-2", "status": "started", "resolved_mode": "EXACT"}
            )
        )

        result = client.reruns.execute(_RUN_ID, 3)

        assert isinstance(result, RerunStartedResponse)
        assert result.workflow_run_id == "run-2"
        assert "async=true" in captured["url"].lower()
        assert "message" not in captured["content"]

    @respx.mock
    def test_message_and_sync_mode_are_sent_when_asked(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/3/rerun").mock(
            side_effect=_captured(captured, {"workflow_run_id": "run-2"})
        )

        client.reruns.execute(_RUN_ID, 3, message="try again", run_async=False)

        assert json.loads(captured["content"])["message"] == "try again"
        assert "async=false" in captured["url"].lower()

    @respx.mock
    async def test_async_client_mirrors_the_sync_surface(self, async_client: AsyncWorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/0/rerun").mock(
            return_value=httpx.Response(200, json={"workflow_run_id": "run-2"})
        )

        result = await async_client.reruns.execute(_RUN_ID, 0)

        assert result.workflow_run_id == "run-2"


class TestCheckpointIsGone:
    def test_removed_from_both_clients(
        self, client: WorkflowClient, async_client: AsyncWorkflowClient
    ):
        # The endpoint was deleted server-side; keeping the method would be a guaranteed 404.
        assert not hasattr(client.runs, "checkpoint")
        assert not hasattr(async_client.runs, "checkpoint")


# =========================================================================== #
# Run feedback                                                                #
# =========================================================================== #


class TestRunFeedback:
    @respx.mock
    def test_set_turn_rating_sends_the_value_and_returns_the_list(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}
        respx.put(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/2/rating").mock(
            side_effect=_captured(
                captured,
                {
                    "ratings": [{"logical_id": "r1", "value": "up", "createdBy": "u1"}],
                    "feedback_users": {"u1": {"id": "u1", "firstName": "Ada", "email": "a@x.com"}},
                },
            )
        )

        result = client.runs.set_turn_rating(_RUN_ID, 2, "up")

        assert isinstance(result, RunFeedbackResponse)
        assert json.loads(captured["content"])["value"] == "up"
        # The full list comes back, not just the caller's record, so a client can render aggregate
        # counts without a refetch.
        assert result.ratings[0]["value"] == "up"
        assert result.feedback_users["u1"].firstName == "Ada"

    @respx.mock
    def test_accepts_a_rating_enum_as_well_as_a_string(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}
        respx.put(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/events/e1/rating").mock(
            side_effect=_captured(captured, {"ratings": []})
        )
        from interactly_configs import RatingValue

        client.runs.set_event_rating(_RUN_ID, "e1", RatingValue.STRONG_UP)

        assert json.loads(captured["content"])["value"] == "strong_up"

    @respx.mock
    def test_add_turn_comment(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/0/comments").mock(
            side_effect=_captured(captured, {"comments": [{"logical_id": "c1", "content": "note"}]})
        )

        result = client.runs.add_turn_comment(_RUN_ID, 0, "note")

        assert json.loads(captured["content"])["content"] == "note"
        assert result.comments[0]["content"] == "note"

    @respx.mock
    def test_delete_endpoints_hit_the_right_paths(self, client: WorkflowClient):
        for route, call in (
            (
                respx.delete(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/1/rating"),
                lambda: client.runs.delete_turn_rating(_RUN_ID, 1),
            ),
            (
                respx.delete(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/events/e1/rating"),
                lambda: client.runs.delete_event_rating(_RUN_ID, "e1"),
            ),
            (
                respx.delete(f"{TEST_BASE_URL}/v1/workflow-runs/{_RUN_ID}/turns/1/comments/c1"),
                lambda: client.runs.delete_turn_comment(_RUN_ID, 1, "c1"),
            ),
        ):
            route.mock(return_value=httpx.Response(200, json={"ratings": [], "comments": []}))
            assert isinstance(call(), RunFeedbackResponse)


class TestRerunListFilters:
    @respx.mock
    def test_source_filters_are_sent_as_query_params(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}
        respx.get(f"{TEST_BASE_URL}/v1/workflow-runs").mock(
            side_effect=_captured(captured, {"workflow_runs": [], "total": 0, "page": 1, "size": 20})
        )

        client.runs.list(source_workflow_run_id=_RUN_ID, source_turn_index=3)

        assert f"source_workflow_run_id={_RUN_ID}" in captured["url"]
        assert "source_turn_index=3" in captured["url"]


# =========================================================================== #
# Background work                                                             #
# =========================================================================== #


class TestBackgroundWork:
    @respx.mock
    def test_pump_posts_to_the_pump_endpoint(self, client: WorkflowClient):
        captured: Dict[str, Any] = {}
        respx.post(f"{TEST_BASE_URL}/v1/workflows/{_WF_ID}/runs/{_RUN_ID}/pump-companions").mock(
            side_effect=_captured(
                captured,
                {
                    "run_id": _RUN_ID,
                    "status": "waiting_for_user_input",
                    "turn_number": 1,
                    "events": [],
                    "is_waiting_for_input": True,
                    "is_completed": False,
                    "has_background_work": False,
                },
            )
        )

        result = client.runs.pump_companions(_WF_ID, _RUN_ID)

        assert isinstance(result, InteractiveRunResponse)
        assert result.has_background_work is False
        assert captured["method"] == "POST"

    @respx.mock
    def test_drive_polls_until_no_work_remains(self, client: WorkflowClient):
        # Two pumps report work outstanding, the third does not — the loop must stop there.
        responses = [
            httpx.Response(200, json={**_pump_body(), "has_background_work": True}),
            httpx.Response(200, json={**_pump_body(), "has_background_work": True}),
            httpx.Response(200, json={**_pump_body(), "has_background_work": False}),
        ]
        respx.post(
            f"{TEST_BASE_URL}/v1/workflows/{_WF_ID}/runs/{_RUN_ID}/pump-companions"
        ).mock(side_effect=responses)

        collected = client.runs.drive_background_work(
            _WF_ID, _RUN_ID, interval_seconds=0, max_iterations=10
        )

        assert len(collected) == 3
        assert collected[-1].has_background_work is False

    @respx.mock
    def test_drive_is_bounded_when_work_never_finishes(self, client: WorkflowClient):
        # A companion can legitimately run for a long time; blocking forever is not an option.
        respx.post(f"{TEST_BASE_URL}/v1/workflows/{_WF_ID}/runs/{_RUN_ID}/pump-companions").mock(
            return_value=httpx.Response(200, json={**_pump_body(), "has_background_work": True})
        )

        collected = client.runs.drive_background_work(
            _WF_ID, _RUN_ID, interval_seconds=0, max_iterations=4
        )

        assert len(collected) == 4
        # Still outstanding — the caller can tell it ran out of iterations rather than finishing.
        assert collected[-1].has_background_work is True

    @respx.mock
    def test_drive_returns_every_response_so_no_events_are_lost(self, client: WorkflowClient):
        respx.post(f"{TEST_BASE_URL}/v1/workflows/{_WF_ID}/runs/{_RUN_ID}/pump-companions").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={
                        **_pump_body(),
                        "has_background_work": True,
                        "events": [{"type": "companion_step_boundary"}],
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        **_pump_body(),
                        "has_background_work": False,
                        "events": [{"type": "say_llm", "content": "lab result is in"}],
                    },
                ),
            ]
        )

        collected = client.runs.drive_background_work(
            _WF_ID, _RUN_ID, interval_seconds=0, max_iterations=5
        )

        all_events = [e for r in collected for e in r.events]
        assert len(all_events) == 2


def _pump_body() -> Dict[str, Any]:
    return {
        "run_id": _RUN_ID,
        "status": "waiting_for_user_input",
        "turn_number": 1,
        "events": [],
        "is_waiting_for_input": True,
        "is_completed": False,
    }


# =========================================================================== #
# Streaming close codes                                                       #
# =========================================================================== #


class TestStreamCloseCodes:
    @pytest.mark.parametrize(
        "code, expected",
        [(4006, InvalidStreamInputError), (4007, RerunTokenError)],
    )
    def test_rejection_codes_map_to_actionable_exceptions(self, code, expected):
        # A generic "closed abnormally" tells the caller nothing about what to change.
        assert _CLOSE_CODE_ERRORS[code] is expected
        assert issubclass(expected, StreamError)

    def test_other_codes_stay_generic(self):
        assert 1006 not in _CLOSE_CODE_ERRORS

    def test_stream_accepts_a_rerun_token(self, client: WorkflowClient):
        import inspect

        assert "rerun_token" in inspect.signature(client.runs.stream).parameters


# =========================================================================== #
# Error bodies                                                                #
# =========================================================================== #


class TestErrorBodies:
    def _error(self, body: Any, status: int = 400):
        request = httpx.Request("POST", f"{TEST_BASE_URL}/v1/edges")
        return _make_status_error(httpx.Response(status, request=request, json=body), body)

    def test_400_maps_to_bad_request(self):
        assert isinstance(self._error({"detail": "nope"}), BadRequestError)

    def test_validation_bodies_keep_both_the_category_and_the_rule(self):
        # The server sends `message` (category) AND `error` (which rule failed). Picking whichever
        # came first in an `or` chain threw away the actionable half.
        exc = self._error(
            {
                "message": "Invalid 'evaluate while waiting for user input' edge configuration",
                "error": "Edge 'e1' has evaluate_while_waiting_config enabled but its source node "
                "also has outgoing direct edges",
            }
        )
        text = str(exc)
        assert "Invalid 'evaluate while waiting for user input' edge configuration" in text
        assert "outgoing direct edges" in text

    def test_identical_strings_are_not_repeated(self):
        assert str(self._error({"message": "same", "error": "same"})) == "same"

    def test_fastapi_detail_only_bodies_are_unchanged(self):
        assert str(self._error({"detail": "Field required"}, 422)) == "Field required"

    def test_non_dict_body_falls_back_to_the_reason_phrase(self):
        assert str(self._error("plain text")) == "Bad Request"

    def test_raw_body_stays_available_for_inspection(self):
        body = {"message": "cat", "error": "detail"}
        assert self._error(body).body == body
