"""Runs and the run socket: close codes, pause frames, the run list's filters, the execute version, and run fields.

Each of these was a wire mismatch, so each test pins the wire rather than the plumbing:

* the run socket closes with one code per refusal, and only two had an exception of their own;
* ``runs.execute(version_number=N)`` sent the version in the body, which the server overwrites, so every turn ran
  the active version;
* the run GET and list rows carried keys the SDK dropped, so a key the server added could never be read.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import pytest
import respx
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close

from interactly import (
    AsyncWorkflowClient,
    RunChangedElsewhereError,
    StreamError,
    StreamPermissionError,
    TakeBackRefusedError,
    WorkflowClient,
)
from interactly._streaming import _CLOSE_CODE_ERRORS, AsyncStream
from interactly.types.runs.interactive_run import InteractiveRunResponse
from interactly.types.runs.run import Run
from interactly.types.runs.run_event import RunEvent
from interactly.types.schedules.schedule import Schedule
from interactly.types.shared import RunStatus

BASE = "http://localhost:8611"

# --------------------------------------------------------------------------------------------- #
# The run socket                                                                                  #
# --------------------------------------------------------------------------------------------- #


class _FakeSocket:
    """Plays back frames, then closes with the given code, the way `websockets` reports a close.

    ``closed_before_start`` is a server that closes the socket as soon as it accepts it, so the start frame finds
    it closed already.
    """

    def __init__(
        self,
        frames: List[Dict[str, Any]],
        close_code: int,
        close_reason: str = "",
        *,
        closed_before_start: bool = False,
    ) -> None:
        self._frames = list(frames)
        self._close = Close(close_code, close_reason)
        self._closed_before_start = closed_before_start
        self.sent: List[Dict[str, Any]] = []

    async def send(self, message: str) -> None:
        if self._closed_before_start:
            raise self._closed()
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        if self._frames:
            return json.dumps(self._frames.pop(0))
        raise self._closed()

    async def close(self) -> None:
        return None

    def _closed(self) -> Exception:
        if self._close.code == 1000:
            return ConnectionClosedOK(self._close, None)
        return ConnectionClosedError(self._close, None)


def _stream_over(socket: _FakeSocket) -> AsyncStream[RunEvent]:
    stream: AsyncStream[RunEvent] = AsyncStream(ws_url="ws://unused", ws_headers={}, payload={}, cast_to=RunEvent)
    stream._ws = socket
    return stream


async def _read_until_closed(stream: AsyncStream[RunEvent], events: List[RunEvent]) -> None:
    async for event in stream:
        events.append(event)


class TestCloseCodes:
    @pytest.mark.parametrize("code, error_cls", sorted(_CLOSE_CODE_ERRORS.items()))
    async def test_each_code_raises_its_own_error_with_the_code_and_reason(self, code, error_cls):
        # Arrange
        stream = _stream_over(_FakeSocket([], code, "the server's reason"))
        # Act
        with pytest.raises(error_cls) as caught:
            await _read_until_closed(stream, [])
        # Assert
        assert caught.value.code == code
        assert caught.value.reason == "the server's reason"
        assert f"close code {code}" in str(caught.value)

    async def test_the_workflow_error_frame_sent_before_a_close_supplies_the_whole_reason(self):
        # The close reason is cut at 123 bytes; the frame the server sends first carries all of it.
        message = "This run was changed elsewhere and is now paused; this session can't go on with it."
        frames = [{"type": "workflow_error", "message": message, "workflow_run_status": "paused"}]
        stream = _stream_over(_FakeSocket(frames, 4009, "Workflow run is now paused"))
        events: List[RunEvent] = []

        with pytest.raises(RunChangedElsewhereError) as caught:
            await _read_until_closed(stream, events)

        assert [e.type for e in events] == ["workflow_error"]
        assert caught.value.server_message == message
        assert message in str(caught.value)

    async def test_a_take_back_refusal_names_why(self):
        reason = "This run is open in another editor. A closed tab lets go of it within a minute or two."
        stream = _stream_over(_FakeSocket([{"type": "workflow_error", "message": reason}], 4010, reason[:123]))
        with pytest.raises(TakeBackRefusedError) as caught:
            await _read_until_closed(stream, [])
        assert caught.value.server_message == reason

    async def test_a_normal_close_ends_the_stream(self):
        stream = _stream_over(_FakeSocket([{"type": "end_workflow"}], 1000, "completed"))
        events: List[RunEvent] = []
        await _read_until_closed(stream, events)
        assert [e.type for e in events] == ["end_workflow"]

    async def test_an_unknown_code_stays_a_plain_stream_error_carrying_the_code(self):
        stream = _stream_over(_FakeSocket([], 4999, "something new"))
        with pytest.raises(StreamError) as caught:
            await _read_until_closed(stream, [])
        assert type(caught.value) is StreamError
        assert caught.value.code == 4999


class TestCloseBeforeTheStartFrame:
    """A caller refused outright is accepted and closed at once, so the start frame can find the socket closed."""

    _REASON = "Your role, Viewer, can't run workflows. It needs Developer access or above."

    @staticmethod
    def _stream_connecting_to(socket: _FakeSocket, monkeypatch) -> AsyncStream[RunEvent]:
        async def connect(*args: Any, **kwargs: Any) -> _FakeSocket:
            return socket

        monkeypatch.setattr(websockets, "connect", connect)
        return AsyncStream(ws_url="ws://unused", ws_headers={}, payload={"command": "start"}, cast_to=RunEvent)

    async def test_a_refusal_before_the_start_frame_raises_its_typed_error(self, monkeypatch):
        # Arrange
        stream = self._stream_connecting_to(_FakeSocket([], 1008, self._REASON, closed_before_start=True), monkeypatch)
        # Act
        with pytest.raises(StreamPermissionError) as caught:
            async with stream:
                await _read_until_closed(stream, [])
        # Assert
        assert caught.value.code == 1008
        assert caught.value.reason == self._REASON

    async def test_the_same_refusal_after_the_start_frame_raises_the_same_error(self, monkeypatch):
        socket = _FakeSocket([], 1008, self._REASON)
        stream = self._stream_connecting_to(socket, monkeypatch)
        with pytest.raises(StreamPermissionError):
            async with stream:
                await _read_until_closed(stream, [])
        assert socket.sent == [{"command": "start"}]

    async def test_a_normal_close_before_the_start_frame_says_the_run_has_ended(self, monkeypatch):
        # Only a refusal or a failure is left for iteration, which carries its typed exception. A normal close means
        # nothing will take the frame, so it is said at once.
        stream = self._stream_connecting_to(_FakeSocket([], 1000, closed_before_start=True), monkeypatch)
        with pytest.raises(StreamError) as caught:
            async with stream:
                pass
        assert type(caught.value) is StreamError
        assert caught.value.code == 1000


class TestPauseFrames:
    _PAUSED = {
        "type": "run_paused",
        "message": "This run was paused by u1: checking the dose. Resume it to carry on.",
        "workflow_run_id": "run-1",
        "workflow_run_status": "paused",
        "paused_by": "u1",
        "pause_reason": "checking the dose",
    }

    def test_a_run_paused_frame_is_recognised_and_keeps_its_fields(self):
        event = RunEvent.model_validate(self._PAUSED)
        assert event.is_run_paused()
        assert not event.is_terminal()
        assert event.model_extra["paused_by"] == "u1"

    def test_a_run_resumed_frame_is_recognised(self):
        event = RunEvent.model_validate({"type": "run_resumed", "resumed_by": "u1", "workflow_run_status": "running"})
        assert event.is_run_resumed()
        assert not event.is_run_paused()


# --------------------------------------------------------------------------------------------- #
# The run list's filters                                                                          #
# --------------------------------------------------------------------------------------------- #

_EMPTY_PAGE = {"items": [], "total": 0, "page": 1, "size": 20, "pages": 0}


def _captured(calls: List[httpx.Request], body: Dict[str, Any]):
    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=body)

    return _handler


class TestRunListFilters:
    def test_needs_attention_logical_id_and_version_are_sent_as_query_keys(self):
        calls: List[httpx.Request] = []
        client = WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)
        with respx.mock(assert_all_mocked=True) as router:
            router.get(f"{BASE}/v1/workflow-runs").mock(side_effect=_captured(calls, _EMPTY_PAGE))
            client.runs.list(needs_attention=True, logical_id="workflow_abc", version_number=2)
        params = calls[0].url.params
        assert params["needs_attention"] == "true"
        assert params["logical_id"] == "workflow_abc"
        assert params["version_number"] == "2"

    def test_unset_filters_are_not_sent(self):
        calls: List[httpx.Request] = []
        client = WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)
        with respx.mock(assert_all_mocked=True) as router:
            router.get(f"{BASE}/v1/workflow-runs").mock(side_effect=_captured(calls, _EMPTY_PAGE))
            client.runs.list()
        assert set(calls[0].url.params) == {"page", "size"}

    async def test_the_async_client_sends_the_same_query(self):
        calls: List[httpx.Request] = []
        client = AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)
        with respx.mock(assert_all_mocked=True) as router:
            router.get(f"{BASE}/v1/workflow-runs").mock(side_effect=_captured(calls, _EMPTY_PAGE))
            await client.runs.list(needs_attention=True)
        assert calls[0].url.params["needs_attention"] == "true"


# --------------------------------------------------------------------------------------------- #
# REST execute                                                                                    #
# --------------------------------------------------------------------------------------------- #

_TURN = {
    "run_id": "run-1",
    "status": "waiting_for_user_input",
    "turn_number": 1,
    "events": [],
    "is_waiting_for_input": True,
    "is_completed": False,
}


def _execute(call, response: Optional[Dict[str, Any]] = None) -> httpx.Request:
    calls: List[httpx.Request] = []
    with respx.mock(assert_all_mocked=True) as router:
        router.post(f"{BASE}/v1/workflows/wf-1/execute").mock(side_effect=_captured(calls, response or _TURN))
        call()
    return calls[0]


class TestExecuteVersion:
    """The server reads a REST turn's version only from `?version=`, and overwrites the body's."""

    def _client(self) -> WorkflowClient:
        return WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)

    def test_version_number_is_sent_as_the_version_query_key(self):
        request = _execute(lambda: self._client().runs.execute("wf-1", version_number=3))
        assert request.url.params["version"] == "3"

    def test_a_typed_run_inputs_version_is_sent_too(self):
        from interactly.configs import WorkflowRunInput

        run_input = WorkflowRunInput(command="start", version_number=2)
        request = _execute(lambda: self._client().runs.execute_with_input("wf-1", run_input=run_input))
        assert request.url.params["version"] == "2"

    def test_no_version_means_no_query_key(self):
        request = _execute(lambda: self._client().runs.execute("wf-1"))
        assert "version" not in request.url.params

    def test_a_paused_durable_turn_carries_its_pause_summary(self):
        summary = {"manual": 1, "manual_pauses": [{"pause_id": "p1", "node_id": "approve"}]}
        response: Dict[str, Any] = {}
        body = {**_TURN, "status": "paused", "is_waiting_for_input": False, "pause_summary": summary}

        def call() -> None:
            response["value"] = self._client().runs.execute("wf-1")

        _execute(call, body)
        assert isinstance(response["value"], InteractiveRunResponse)
        assert response["value"].pause_summary == summary


# --------------------------------------------------------------------------------------------- #
# Run fields                                                                                      #
# --------------------------------------------------------------------------------------------- #


def _run_get(**envelope: Any) -> Dict[str, Any]:
    return {
        "workflow_run": {
            "_id": "run-1",
            "team_id": "t",
            "created_at": "2026-11-20T10:00:00Z",
            "updated_at": "2026-11-20T10:05:00Z",
            "workflow_name": "Refills",
            "is_background_run": False,
            "schedule_id": None,
            "workflow_run": {
                "workflow_run_id": "run-1",
                "workflow_id": "wf-1",
                "status": "cancelled",
                "termination_source": "client_stop",
            },
        },
        **envelope,
    }


class TestRunFields:
    def test_known_envelope_and_record_keys_are_read(self):
        run = Run.model_validate(_run_get(can_continue_in_editor=True, workflow_deleted=False))
        assert run.can_continue_in_editor is True
        assert run.workflow_deleted is False
        assert run.workflow_name == "Refills"
        assert run.is_background_run is False

    def test_why_the_run_ended_is_read_even_when_it_did_not_fail(self):
        run = Run.model_validate(_run_get())
        assert run.status == "cancelled"
        assert run.termination_source == "client_stop"
        assert run.error is None

    def test_a_key_the_server_adds_is_kept_rather_than_dropped(self):
        run = Run.model_validate(_run_get(a_key_from_the_future={"x": 1}))
        assert run.model_extra["a_key_from_the_future"] == {"x": 1}


class TestStatusEnums:
    def test_a_schedule_running_now_parses(self):
        schedule = Schedule.model_validate(
            {
                "id": "s1",
                "workflow_id": "wf-1",
                "team_id": "t",
                "status": "in_progress",
                "scheduled_time": "2026-11-20T10:00:00Z",
            }
        )
        assert schedule.status.value == "in_progress"

    def test_run_status_offers_only_what_a_server_sends(self):
        assert "pending" not in {member.value for member in RunStatus}
