"""Run control on the wire: pausing, resuming, cancelling and signalling a durable run, and listing its pauses, signals
and external jobs.

Every answer replayed here was captured from a workflow-service (``fixtures/run_control.json``), with its ids
replaced: a mock encoding a shape the server never produces keeps a broken method green. The one exception is the
409 carrying ``Retry-After``, which the server sends only when a run changes under a request and cannot be provoked on
demand; its body here is the real 409 body, with the header added.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import respx

from interactly import (
    AsyncWorkflowClient,
    BadRequestError,
    ConflictError,
    InternalServerError,
    UnprocessableEntityError,
    WorkflowClient,
)
from interactly._exceptions import NoMorePagesError
from interactly._utils import _retry
from interactly.types.runs.run_control import RunControlResult, RunPause, SignalResult

BASE = "http://localhost:8611"
RUN = "665f1c0a2b3c4d5e6f700000"
ANSWERS: Dict[str, Dict[str, Any]] = json.loads((Path(__file__).parent / "fixtures" / "run_control.json").read_text())


def _client(max_retries: int = 0) -> WorkflowClient:
    return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=max_retries)


def _aclient(max_retries: int = 0) -> AsyncWorkflowClient:
    return AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=max_retries)


def _replay(calls: List[httpx.Request], *names: str, headers: Dict[str, str] | None = None):
    """Answer each request with the next captured answer, recording the requests."""
    queue = list(names)

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        answer = ANSWERS[queue.pop(0) if len(queue) > 1 else queue[0]]
        return httpx.Response(answer["status"], json=answer["body"], headers=headers or {})

    return _handler


def _body(request: httpx.Request) -> Any:
    return json.loads(request.content) if request.content else None


@pytest.fixture
def no_sleep(monkeypatch):
    slept: List[float] = []
    monkeypatch.setattr(_retry.time, "sleep", slept.append)

    async def _asleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr(_retry.asyncio, "sleep", _asleep)
    return slept


class TestPauseResumeCancel:
    @respx.mock
    def test_pause_sends_the_reason_and_says_the_run_is_paused(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/pause").mock(side_effect=_replay(calls, "pause"))

        # Act
        result = _client().runs.pause(RUN, reason="Checking the dose")

        # Assert
        assert _body(calls[0]) == {"reason": "Checking the dose"}
        assert isinstance(result, RunControlResult)
        assert (result.outcome, result.status) == ("applied", "paused")

    @respx.mock
    def test_a_pause_without_a_reason_sends_no_body_and_a_repeat_is_already_requested(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/pause").mock(side_effect=_replay(calls, "pause_again"))

        # Act
        result = _client().runs.pause(RUN)

        # Assert
        assert _body(calls[0]) is None
        assert result.outcome == "already_requested"

    @respx.mock
    def test_resuming_the_run_sends_only_the_note(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/resume").mock(side_effect=_replay(calls, "resume_run"))

        # Act
        result = _client().runs.resume(RUN, note="all clear")

        # Assert
        assert _body(calls[0]) == {"note": "all clear"}
        assert (result.status, result.made_ready) == ("waiting", [])

    @respx.mock
    def test_approving_pauses_sends_their_ids_and_data_and_lists_those_made_ready(self):
        # Arrange
        calls: List[httpx.Request] = []
        approval = "665f1c0a2b3c4d5e6f700002"
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/resume").mock(side_effect=_replay(calls, "resume_pauses"))

        # Act
        result = _client().runs.resume(RUN, pause_ids=[approval], note="ok", data={"approved": True})

        # Assert
        assert _body(calls[0]) == {"note": "ok", "pause_ids": [approval], "data": {"approved": True}}
        assert result.made_ready == [approval]

    @respx.mock
    def test_approve_all_is_sent_only_when_asked_for(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/resume").mock(side_effect=_replay(calls, "resume_pauses"))

        # Act
        _client().runs.resume(RUN, all_waiting_for_person=True)
        _client().runs.resume(RUN)

        # Assert
        assert [_body(c) for c in calls] == [{"all_waiting_for_person": True}, None]

    @pytest.mark.parametrize(
        "method, answer, error, message",
        [
            ("resume", "resume_nothing", ConflictError, "Nothing in this run is paused"),
            ("pause", "pause_ended", ConflictError, "The run has ended"),
            ("resume", "resume_unknown_pause", BadRequestError, "Not an open pause of this run"),
        ],
    )
    @respx.mock
    def test_a_refusal_raises_with_the_servers_message(self, method, answer, error, message):
        # Arrange
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/{method}").mock(side_effect=_replay([], answer))

        # Act / Assert
        with pytest.raises(error, match=message):
            getattr(_client().runs, method)(RUN)

    @respx.mock
    def test_cancel_sends_the_reason_and_says_the_run_is_cancelled(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/cancel").mock(side_effect=_replay(calls, "cancel"))

        # Act
        result = _client().runs.cancel(RUN, reason="No longer needed")

        # Assert
        assert _body(calls[0]) == {"reason": "No longer needed"}
        assert result.status == "cancelled"


class TestSignals:
    @respx.mock
    def test_a_signal_sends_its_body_as_it_is_with_an_idempotency_key(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/signals/approval.done").mock(
            side_effect=_replay(calls, "signal_stored")
        )

        # Act
        result = _client().runs.send_signal(RUN, "approval.done", ["ok"])

        # Assert
        assert _body(calls[0]) == ["ok"]
        key = calls[0].headers["Idempotency-Key"]
        assert len(key) == 32 and all(c in "0123456789abcdef" for c in key)
        assert isinstance(result, SignalResult)
        assert (result.outcome, result.replayed) == ("stored", False)

    @respx.mock
    def test_each_call_makes_its_own_key_unless_one_is_given(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/signals/approval.done").mock(
            side_effect=_replay(calls, "signal_stored", "signal_replayed")
        )

        # Act
        _client().runs.send_signal(RUN, "approval.done", ["ok"])
        result = _client().runs.send_signal(RUN, "approval.done", ["ok"], idempotency_key="order-42")

        # Assert
        assert calls[1].headers["Idempotency-Key"] == "order-42"
        assert calls[0].headers["Idempotency-Key"] != "order-42"
        assert result.replayed is True

    @pytest.mark.parametrize("body, sent", [(None, b""), (0, b"0"), ("ready", b'"ready"'), ({"value": 7.2}, None)])
    @respx.mock
    def test_any_json_value_is_a_body_and_none_sends_none(self, body, sent):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/signals/lab.result").mock(
            side_effect=_replay(calls, "signal_delivered")
        )

        # Act
        result = _client().runs.send_signal(RUN, "lab.result", body)

        # Assert
        assert result.outcome == "delivered"
        if sent is None:
            assert _body(calls[0]) == body
        else:
            assert calls[0].content == sent

    @pytest.mark.parametrize(
        "answer, error, message",
        [
            ("signal_other_body", ConflictError, "A different signal already waits under this key"),
            ("signal_fails_schema", UnprocessableEntityError, "fails its wait's schema"),
            ("signal_bad_key", BadRequestError, "A signal key is 1 to 128"),
        ],
    )
    @respx.mock
    def test_a_refused_signal_raises_with_the_servers_message(self, answer, error, message):
        # Arrange
        respx.post(url__regex=rf"{BASE}/v1/workflow-runs/{RUN}/signals/.*").mock(side_effect=_replay([], answer))

        # Act / Assert
        with pytest.raises(error, match=message):
            _client().runs.send_signal(RUN, "form.submitted", {"age": 3})

    @respx.mock
    def test_the_key_is_sent_as_one_path_segment(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(url__regex=rf"{BASE}/v1/workflow-runs/{RUN}/signals/.*").mock(
            side_effect=_replay(calls, "signal_bad_key")
        )

        # Act
        with pytest.raises(BadRequestError):
            _client().runs.send_signal(RUN, "bad key/../x", 1)

        # Assert
        assert calls[0].url.raw_path.decode().endswith("/signals/bad%20key%2F..%2Fx")


class TestLists:
    @respx.mock
    def test_pauses_are_listed_with_what_waits_for_a_person(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.get(f"{BASE}/v1/workflow-runs/{RUN}/pauses").mock(side_effect=_replay(calls, "list_pauses"))

        # Act
        page = _client().runs.list_pauses(RUN, open_only=True)

        # Assert
        assert dict(calls[0].url.params) == {"limit": "100", "open_only": "true"}
        assert [p.node_id for p in page] == ["approve", "wait_lab"]
        assert all(isinstance(p, RunPause) for p in page)
        assert [p.waits_for_person for p in page] == [True, False]
        assert page.items[1].wake == {"kind": "signal", "signal_key": "lab.result"}
        assert page.has_next_page is False

    @respx.mock
    def test_a_full_page_is_followed_by_the_one_after_its_last_pause(self):
        # Arrange: two captured pauses, served one per page
        rows = ANSWERS["list_pauses"]["body"]["pauses"]
        calls: List[httpx.Request] = []

        def _paged(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            after = request.url.params.get("after")
            start = 0 if after is None else [r["pause_id"] for r in rows].index(after) + 1
            return httpx.Response(200, json={"workflow_run_id": RUN, "pauses": rows[start : start + 1]})

        respx.get(f"{BASE}/v1/workflow-runs/{RUN}/pauses").mock(side_effect=_paged)

        # Act
        everything = _client().runs.list_pauses(RUN, limit=1).list_all()

        # Assert: the third page is empty, and ends the walk
        assert [p.pause_id for p in everything] == [r["pause_id"] for r in rows]
        assert [c.url.params.get("after") for c in calls] == [None, rows[0]["pause_id"], rows[1]["pause_id"]]

    @respx.mock
    def test_the_last_page_has_no_next(self):
        # Arrange
        respx.get(f"{BASE}/v1/workflow-runs/{RUN}/external-jobs").mock(side_effect=_replay([], "list_external_jobs"))

        # Act
        page = _client().runs.list_external_jobs(RUN)

        # Assert
        assert (len(page), page.next_after, page.has_next_page) == (0, None, False)
        with pytest.raises(NoMorePagesError):
            page.next_page()

    @respx.mock
    def test_signals_are_listed_with_what_took_them_and_without_their_bodies(self):
        # Arrange
        respx.get(f"{BASE}/v1/workflow-runs/{RUN}/signals").mock(side_effect=_replay([], "list_signals"))

        # Act
        stored, delivered = _client().runs.list_signals(RUN)

        # Assert: one still waiting for a wait, one taken by the wait it was posted for
        assert (stored.signal_key, stored.consumed, stored.idempotency_key) == ("approval.done", False, "c8-stored")
        assert (delivered.signal_key, delivered.consumed) == ("lab.result", True)
        assert delivered.consumed_by_pause_key.endswith(":wait_lab:1:1")
        assert all("body" not in s.model_dump() for s in (stored, delivered))


class TestRetries:
    @respx.mock
    def test_a_409_saying_retry_after_is_retried(self, no_sleep):
        # Arrange
        calls: List[httpx.Request] = []
        answers = iter(
            [
                httpx.Response(409, json=ANSWERS["pause_ended"]["body"], headers={"Retry-After": "1"}),
                httpx.Response(200, json=ANSWERS["pause"]["body"]),
            ]
        )
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/pause").mock(side_effect=lambda r: calls.append(r) or next(answers))

        # Act
        result = _client(max_retries=2).runs.pause(RUN)

        # Assert
        assert (len(calls), result.outcome) == (2, "applied")
        assert no_sleep and no_sleep[0] >= 1

    @respx.mock
    def test_a_409_without_retry_after_is_raised_at_once(self, no_sleep):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/resume").mock(side_effect=_replay(calls, "resume_nothing"))

        # Act / Assert
        with pytest.raises(ConflictError):
            _client(max_retries=2).runs.resume(RUN)
        assert len(calls) == 1

    @respx.mock
    def test_a_503_is_raised_at_once_with_its_retry_after(self, no_sleep):
        # Arrange
        calls: List[httpx.Request] = []
        unavailable = {"message": "Durable runs are unavailable on this server right now"}
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/cancel").mock(
            side_effect=lambda r: calls.append(r) or httpx.Response(503, json=unavailable, headers={"Retry-After": "30"})
        )

        # Act / Assert
        with pytest.raises(InternalServerError) as raised:
            _client(max_retries=2).runs.cancel(RUN)
        assert len(calls) == 1
        assert raised.value.response.headers["Retry-After"] == "30"

    @respx.mock
    def test_other_posts_keep_their_own_rule(self, no_sleep):
        # Arrange: a 409 with Retry-After from a route that is not run control
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/comments").mock(
            side_effect=lambda r: calls.append(r)
            or httpx.Response(409, json={"message": "conflict"}, headers={"Retry-After": "1"})
        )

        # Act / Assert
        with pytest.raises(ConflictError):
            _client(max_retries=2).runs.add_comment(RUN, content="hi")
        assert len(calls) == 1


class TestAsync:
    @respx.mock
    async def test_pause_and_approve(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/pause").mock(side_effect=_replay(calls, "pause"))
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/resume").mock(side_effect=_replay(calls, "resume_pauses"))

        # Act
        async with _aclient() as client:
            paused = await client.runs.pause(RUN, reason="r")
            approved = await client.runs.resume(RUN, all_waiting_for_person=True)

        # Assert
        assert (paused.status, approved.made_ready) == ("paused", ["665f1c0a2b3c4d5e6f700002"])
        assert _body(calls[1]) == {"all_waiting_for_person": True}

    @respx.mock
    async def test_a_signal_carries_an_idempotency_key(self):
        # Arrange
        calls: List[httpx.Request] = []
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/signals/lab.result").mock(
            side_effect=_replay(calls, "signal_delivered")
        )

        # Act
        async with _aclient() as client:
            result = await client.runs.send_signal(RUN, "lab.result", {"value": 7.2}, idempotency_key="k1")

        # Assert
        assert (calls[0].headers["Idempotency-Key"], result.outcome) == ("k1", "delivered")

    @respx.mock
    async def test_every_page_of_pauses(self):
        # Arrange
        rows = ANSWERS["list_pauses"]["body"]["pauses"]

        def _paged(request: httpx.Request) -> httpx.Response:
            after = request.url.params.get("after")
            start = 0 if after is None else [r["pause_id"] for r in rows].index(after) + 1
            return httpx.Response(200, json={"workflow_run_id": RUN, "pauses": rows[start : start + 1]})

        respx.get(f"{BASE}/v1/workflow-runs/{RUN}/pauses").mock(side_effect=_paged)

        # Act
        async with _aclient() as client:
            page = await client.runs.list_pauses(RUN, limit=1)
            first = [p.pause_id async for p in page]
            everything = await page.list_all()

        # Assert
        assert first == [rows[0]["pause_id"]]
        assert [p.pause_id for p in everything] == [r["pause_id"] for r in rows]

    @respx.mock
    async def test_a_409_saying_retry_after_is_retried(self, no_sleep):
        # Arrange
        answers = iter(
            [
                httpx.Response(409, json=ANSWERS["pause_ended"]["body"], headers={"Retry-After": "1"}),
                httpx.Response(202, json=ANSWERS["signal_stored"]["body"]),
            ]
        )
        respx.post(f"{BASE}/v1/workflow-runs/{RUN}/signals/approval.done").mock(side_effect=lambda r: next(answers))

        # Act
        async with _aclient(max_retries=1) as client:
            result = await client.runs.send_signal(RUN, "approval.done", ["ok"])

        # Assert
        assert result.outcome == "stored"
        assert no_sleep and no_sleep[0] >= 1
