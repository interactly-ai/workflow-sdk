"""A stream's later turns: send(), stop(), run_id, and taking a run back.

The run socket takes each later user turn as a ``resume`` frame and ends a run on ``stop``; it has no ``data``
command. The frames are pinned here exactly as the workflow editor sends them, since the editor is the client the
server is built and tested against.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest
import respx
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close

from interactly import AsyncWorkflowClient, StreamError, StreamPermissionError, StreamServerError, WorkflowClient
from interactly._streaming import AsyncStream, Stream
from interactly.types.runs.run_event import RunEvent

BASE = "http://localhost:8611"

_ACK = {"type": "run_ack", "workflow_run_id": "run-1", "message": "Workflow run started successfully"}
_READY = {"type": "workflow_ready_for_input", "workflow_run_id": "run-1"}
_START = {
    "command": "start",
    "workflow_id": "wf-1",
    "run_by": "api",
    "thread_to_node_inputs": {"0": {"node_run_inputs": []}},
    "dynamic_variables": {"patient": "Ada", "clinic": {"city": "Lyon"}},
    "runtime_variables": {"attempt": 1},
}


class _ScriptedSocket:
    """Plays back frames, then closes with the given code; records every frame sent.

    ``close_on_send`` is a server that has already closed when the next frame goes out.
    """

    def __init__(
        self,
        frames: List[Dict[str, Any]],
        close_code: int = 1000,
        close_reason: str = "",
        *,
        close_on_send: bool = False,
    ) -> None:
        self._frames = list(frames)
        self._close = Close(close_code, close_reason)
        self.close_on_send = close_on_send
        self.sent: List[Dict[str, Any]] = []

    async def send(self, message: str) -> None:
        if self.close_on_send:
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


def _connecting_to(socket: _ScriptedSocket, monkeypatch) -> None:
    async def connect(*args: Any, **kwargs: Any) -> _ScriptedSocket:
        return socket

    monkeypatch.setattr(websockets, "connect", connect)


def _async_stream(payload: Optional[Dict[str, Any]] = None) -> AsyncStream[RunEvent]:
    return AsyncStream(ws_url="ws://unused", ws_headers={}, payload=payload or dict(_START), cast_to=RunEvent)


# --------------------------------------------------------------------------------------------- #
# The frames                                                                                      #
# --------------------------------------------------------------------------------------------- #


class TestTurnFrames:
    async def test_send_sends_the_message_as_the_editors_resume_frame(self, monkeypatch):
        # Arrange
        socket = _ScriptedSocket([_ACK])
        _connecting_to(socket, monkeypatch)
        # Act
        async with _async_stream() as stream:
            await stream.__anext__()
            await stream.send("I'd like to book an appointment.")
        # Assert
        assert socket.sent[1] == {
            "command": "resume",
            "workflow_id": "wf-1",
            "workflow_run_id": "run-1",
            "thread_to_node_inputs": {
                "0": {
                    "node_run_inputs": [
                        {"type": "llm", "messages": [{"type": "human", "content": "I'd like to book an appointment."}]}
                    ]
                }
            },
            "dynamic_variables": {"patient": "Ada", "clinic": {"city": "Lyon"}},
            "runtime_variables": {"attempt": 1},
        }

    async def test_a_turns_variables_are_merged_over_the_streams_for_that_turn_only(self, monkeypatch):
        socket = _ScriptedSocket([_ACK])
        _connecting_to(socket, monkeypatch)
        async with _async_stream() as stream:
            await stream.__anext__()
            await stream.send("first", dynamic_variables={"clinic": {"room": 4}}, runtime_variables={"attempt": 2})
            await stream.send("second")
        assert socket.sent[1]["dynamic_variables"] == {"patient": "Ada", "clinic": {"city": "Lyon", "room": 4}}
        assert socket.sent[1]["runtime_variables"] == {"attempt": 2}
        assert socket.sent[2]["dynamic_variables"] == {"patient": "Ada", "clinic": {"city": "Lyon"}}
        assert socket.sent[2]["runtime_variables"] == {"attempt": 1}

    async def test_a_typed_run_input_goes_as_resume_whatever_its_command(self, monkeypatch):
        from interactly.configs import LLMNodeRunInput, NodesRunInputs, WorkflowCommand, WorkflowRunInput

        socket = _ScriptedSocket([_ACK])
        _connecting_to(socket, monkeypatch)
        run_input = WorkflowRunInput(
            command=WorkflowCommand.START,
            dynamic_variables={"patient": "Grace"},
            thread_to_node_inputs={
                "0": NodesRunInputs(node_run_inputs=[LLMNodeRunInput(messages=[{"type": "human", "content": "hi"}])])
            },
        )
        async with _async_stream() as stream:
            await stream.__anext__()
            await stream.send(run_input=run_input)
        frame = socket.sent[1]
        assert (frame["command"], frame["workflow_id"], frame["workflow_run_id"]) == ("resume", "wf-1", "run-1")
        assert frame["thread_to_node_inputs"]["0"]["node_run_inputs"][0]["messages"] == [
            {"type": "human", "content": "hi"}
        ]
        assert frame["dynamic_variables"] == {"patient": "Grace", "clinic": {"city": "Lyon"}}

    async def test_a_turn_without_a_message_carries_an_empty_main_thread(self, monkeypatch):
        socket = _ScriptedSocket([_ACK])
        _connecting_to(socket, monkeypatch)
        async with _async_stream() as stream:
            await stream.__anext__()
            await stream.send()
        assert socket.sent[1]["thread_to_node_inputs"] == {"0": {"node_run_inputs": []}}

    async def test_a_message_and_a_typed_run_input_together_are_refused(self, monkeypatch):
        from interactly.configs import WorkflowRunInput

        socket = _ScriptedSocket([_ACK])
        _connecting_to(socket, monkeypatch)
        async with _async_stream() as stream:
            with pytest.raises(ValueError, match="either a message or a typed run_input"):
                await stream.send("hi", run_input=WorkflowRunInput())
        assert len(socket.sent) == 1

    async def test_stop_sends_the_editors_stop_frame(self, monkeypatch):
        socket = _ScriptedSocket([_ACK])
        _connecting_to(socket, monkeypatch)
        async with _async_stream() as stream:
            await stream.__anext__()
            await stream.stop()
        assert socket.sent[1] == {"command": "stop", "workflow_id": "wf-1", "workflow_run_id": "run-1"}


class TestRunId:
    async def test_it_is_unknown_until_a_frame_names_the_run(self, monkeypatch):
        _connecting_to(_ScriptedSocket([_ACK, _READY]), monkeypatch)
        async with _async_stream() as stream:
            assert stream.run_id is None
            await stream.__anext__()
            assert stream.run_id == "run-1"

    async def test_a_turn_sent_before_it_is_known_still_goes_out(self, monkeypatch):
        # The server reads frames in order and applies a resume to the run the socket holds, so a turn queued before
        # the first one ends is taken after it.
        socket = _ScriptedSocket([_ACK])
        _connecting_to(socket, monkeypatch)
        async with _async_stream() as stream:
            await stream.send("queued")
        assert socket.sent[1]["command"] == "resume"
        assert socket.sent[1]["workflow_run_id"] is None


# --------------------------------------------------------------------------------------------- #
# Sending once the run or the stream has ended                                                    #
# --------------------------------------------------------------------------------------------- #


class TestSendingAfterTheEnd:
    async def test_a_send_after_iteration_reported_the_end_raises(self, monkeypatch):
        _connecting_to(_ScriptedSocket([_ACK]), monkeypatch)
        async with _async_stream() as stream:
            async for _ in stream:
                pass
            with pytest.raises(StreamError, match="has ended"):
                await stream.send("too late")

    async def test_a_send_after_the_block_was_left_raises(self, monkeypatch):
        _connecting_to(_ScriptedSocket([_ACK]), monkeypatch)
        async with _async_stream() as stream:
            pass
        with pytest.raises(StreamError, match="not open"):
            await stream.stop()

    async def test_a_send_that_finds_the_run_ended_raises_at_once(self, monkeypatch):
        socket = _ScriptedSocket([_ACK, {"type": "end_workflow"}], 1000, "completed")
        _connecting_to(socket, monkeypatch)
        async with _async_stream() as stream:
            await stream.__anext__()
            socket.close_on_send = True
            with pytest.raises(StreamError) as caught:
                await stream.send("too late")
            events = [event.type async for event in stream]
        assert caught.value.code == 1000
        assert events == ["end_workflow"]

    async def test_a_send_that_finds_a_refusal_leaves_it_to_iteration(self, monkeypatch):
        socket = _ScriptedSocket([_ACK], 1008, "Your role, Viewer, can't run workflows.")
        _connecting_to(socket, monkeypatch)
        with pytest.raises(StreamPermissionError):
            async with _async_stream() as stream:
                await stream.__anext__()
                socket.close_on_send = True
                await stream.send("refused")
                await stream.__anext__()


# --------------------------------------------------------------------------------------------- #
# Taking a run back                                                                               #
# --------------------------------------------------------------------------------------------- #


def _async_client() -> AsyncWorkflowClient:
    return AsyncWorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)


class TestTakeBack:
    def test_the_start_frame_names_the_run_and_nothing_else(self):
        stream = _async_client().runs.stream(workflow_id="wf-1", workflow_run_id="run-9")
        assert stream._payload == {
            "command": "start",
            "workflow_id": "wf-1",
            "workflow_run_id": "run-9",
            "thread_to_node_inputs": {"0": {"node_run_inputs": []}},
        }
        assert stream.run_id == "run-9"

    @pytest.mark.parametrize(
        "extra",
        [{"version_number": 2}, {"rerun_token": "tok"}, {"command": "resume"}],
        ids=["version_number", "rerun_token", "command"],
    )
    def test_an_argument_a_take_back_cannot_carry_is_refused(self, extra):
        with pytest.raises(ValueError, match=f"drop {next(iter(extra))}"):
            _async_client().runs.stream(workflow_id="wf-1", workflow_run_id="run-9", **extra)

    def test_a_typed_run_input_is_refused_too(self):
        from interactly.configs import WorkflowRunInput

        with pytest.raises(ValueError, match="drop run_input"):
            _async_client().runs.stream(workflow_id="wf-1", workflow_run_id="run-9", run_input=WorkflowRunInput())

    async def test_its_variables_go_with_each_later_turn(self, monkeypatch):
        socket = _ScriptedSocket(
            [{"type": "run_ack", "workflow_run_id": "run-9", "message": "Workflow run taken back"}]
        )
        _connecting_to(socket, monkeypatch)
        stream = _async_client().runs.stream(workflow_id="wf-1", workflow_run_id="run-9", dynamic_variables={"a": 1})
        stream._token_provider = None
        async with stream:
            await stream.__anext__()
            await stream.send("carry on")
        assert socket.sent[1]["dynamic_variables"] == {"a": 1}
        assert socket.sent[1]["workflow_run_id"] == "run-9"

    def test_the_sync_client_refuses_before_making_any_request(self):
        client = WorkflowClient(api_key="k", team_id="t", user_id="u", base_url=BASE, max_retries=0)
        with respx.mock(assert_all_mocked=True, assert_all_called=False):
            with pytest.raises(ValueError):
                client.runs.stream(workflow_id="wf-1", workflow_run_id="run-9", version_number=1)


# --------------------------------------------------------------------------------------------- #
# The synchronous stream                                                                          #
# --------------------------------------------------------------------------------------------- #


class TestSyncStream:
    def test_send_and_stop_go_out_through_the_sync_stream(self, monkeypatch):
        socket = _ScriptedSocket([_ACK, _READY, {"type": "run_ack", "message": "Workflow run stopped successfully"}])
        _connecting_to(socket, monkeypatch)
        stream: Stream[RunEvent] = Stream(ws_url="ws://unused", ws_headers={}, payload=dict(_START), cast_to=RunEvent)
        with stream:
            seen = []
            for event in stream:
                seen.append(event.type)
                if event.is_ready_for_input():
                    stream.send("hello")
                    stream.stop()
            run_id = stream.run_id
        assert [frame["command"] for frame in socket.sent] == ["start", "resume", "stop"]
        assert run_id == "run-1"
        assert seen == ["run_ack", "workflow_ready_for_input", "run_ack"]

    def test_a_send_outside_the_block_raises(self, monkeypatch):
        _connecting_to(_ScriptedSocket([_ACK]), monkeypatch)
        stream: Stream[RunEvent] = Stream(ws_url="ws://unused", ws_headers={}, payload=dict(_START), cast_to=RunEvent)
        with stream:
            pass
        with pytest.raises(StreamError, match="not open"):
            stream.send("too late")
        assert stream.run_id is None


# --------------------------------------------------------------------------------------------- #
# When the run hands over to the user                                                             #
# --------------------------------------------------------------------------------------------- #


def _busy_wait(thread: str = "0") -> Dict[str, Any]:
    return {"type": "busy_wait_for_user_message", "origin_thread_id": thread}


def _failed_turn() -> List[Dict[str, Any]]:
    """A turn whose LLM node failed, its frames as a workflow-service sends them (captured on dev, trimmed)."""
    return [
        {"type": "user_messages", "messages": [{"type": "human", "content": "hello"}]},
        {"type": "start_node_run"},
        {"type": "say_llm"},
        {"type": "assistant_response", "content": "I am sorry, there seems to be an issue. Could you please repeat?"},
        {"type": "workflow_error", "error_message": "Error Connection error.", "fatal": False},
    ]


def _closing_error(reason: str) -> Dict[str, Any]:
    """The error frame the server sends with the whole reason just before it closes the socket with 1011."""
    return {"type": "workflow_error", "message": reason}


async def _ready_marks(frames: List[Dict[str, Any]], monkeypatch) -> List[str]:
    """The types of the events a stream says hand over to the user, reading ``frames`` to the end."""
    _connecting_to(_ScriptedSocket(frames), monkeypatch)
    async with _async_stream() as stream:
        return [event.type async for event in stream if event.is_ready_for_input()]


class TestReadyForInput:
    async def test_a_turn_left_waiting_hands_over_once_at_its_end(self, monkeypatch):
        # Without fork companions the server sends no workflow_ready_for_input at all.
        frames = [_ACK, _busy_wait(), {"type": "end_node_run"}, {"type": "end_workflow_iteration"}]
        assert await _ready_marks(frames, monkeypatch) == ["end_workflow_iteration"]

    async def test_with_companions_the_servers_own_signal_hands_over_and_nothing_else(self, monkeypatch):
        frames = [
            _ACK,
            _busy_wait(),
            {"type": "workflow_ready_for_input", "active_companion_thread_ids": ["0_companion_bg"]},
            {"type": "end_workflow_iteration"},
            {"type": "companion_step_boundary", "origin_thread_id": "0_companion_bg"},
        ]
        assert await _ready_marks(frames, monkeypatch) == ["workflow_ready_for_input"]

    async def test_a_turn_that_ends_the_run_does_not_hand_over(self, monkeypatch):
        frames = [_ACK, {"type": "end_thread"}, {"type": "end_workflow_iteration"}, {"type": "end_workflow"}]
        assert await _ready_marks(frames, monkeypatch) == []

    async def test_a_companion_waiting_is_not_the_run_waiting(self, monkeypatch):
        frames = [_ACK, _busy_wait("0_companion_bg"), {"type": "end_workflow_iteration"}]
        assert await _ready_marks(frames, monkeypatch) == []

    async def test_a_pause_after_the_wait_keeps_the_turn_from_handing_over(self, monkeypatch):
        frames = [
            _ACK,
            _busy_wait(),
            {"type": "pause_event", "origin_thread_id": "0"},
            {"type": "end_workflow_iteration"},
        ]
        assert await _ready_marks(frames, monkeypatch) == []

    async def test_a_failed_turn_starts_the_next_afresh(self, monkeypatch):
        frames = [_ACK, _busy_wait(), {"type": "workflow_error"}, {"type": "end_workflow_iteration"}]
        assert await _ready_marks(frames, monkeypatch) == []

    async def test_a_failure_the_server_tolerated_hands_over_at_its_error(self, monkeypatch):
        # A turn whose LLM node failed, as a server with default error limits sends it: the error is its last frame,
        # and the socket stays open for the next message.
        frames = [_ACK, _busy_wait(), {"type": "end_workflow_iteration"}, *_failed_turn()]
        assert await _ready_marks(frames, monkeypatch) == ["end_workflow_iteration", "workflow_error"]

    async def test_when_error_limits_end_the_run_the_error_hands_over_once_and_the_close_raises(self, monkeypatch):
        # The server sends the tolerated error before it checks the workflow's error limits. When they end the run,
        # a second error and then one with the whole reason follow, and the socket closes with 1011.
        reason = "Error Error Connection error. when running node 'Ask'"
        frames = [_ACK, *_failed_turn(), {"type": "workflow_error", "fatal": False}, _closing_error(reason)]
        _connecting_to(_ScriptedSocket(frames, 1011, reason), monkeypatch)
        seen: List[RunEvent] = []

        with pytest.raises(StreamServerError) as caught:
            async with _async_stream() as stream:
                async for event in stream:
                    seen.append(event)

        errors = [(e.is_ready_for_input(), e.is_terminal()) for e in seen if e.type == "workflow_error"]
        assert errors == [(True, False), (False, False), (False, True)]
        assert caught.value.server_message == reason

    async def test_a_fatal_failure_hands_nothing_over(self, monkeypatch):
        frames = [_ACK, _busy_wait(), {"type": "workflow_error", "fatal": True}]
        assert await _ready_marks(frames, monkeypatch) == []

    async def test_a_companions_failure_is_not_the_run_waiting(self, monkeypatch):
        frames = [_ACK, {"type": "workflow_error", "fatal": False, "origin_thread_id": "0_companion_bg"}]
        assert await _ready_marks(frames, monkeypatch) == []

    async def test_a_take_back_hands_over_when_its_run_waits_for_its_user(self, monkeypatch):
        taken = {"workflow_run_id": "run-9", "message": "Workflow run taken back"}
        frames = [
            {**taken, "workflow_run_status": "waiting_for_user_input"},
            {**taken, "workflow_run_status": "waiting"},
        ]
        assert await _ready_marks(frames, monkeypatch) == ["run_ack"]

    def test_an_event_read_outside_a_stream_answers_by_its_type(self):
        assert RunEvent.model_validate({"type": "workflow_ready_for_input"}).is_ready_for_input()
        assert not RunEvent.model_validate({"type": "end_workflow_iteration"}).is_ready_for_input()

    def test_the_companion_thread_delimiter_is_the_servers(self):
        from interactly._streaming import _COMPANION_THREAD_DELIMITER
        from interactly.configs import COMPANION_THREAD_DELIMITER

        assert _COMPANION_THREAD_DELIMITER == COMPANION_THREAD_DELIMITER
