"""
WebSocket streaming helpers.

The Interactly Workflow Service exposes a WebSocket endpoint at:
    ws://host/v1/workflow-runs/ws

Protocol:
    1. Client opens WebSocket connection with auth headers.
    2. Client sends a JSON message conforming to WorkflowRunInput:
           {"workflow_id": "...", "command": "start", "run_by": "api"}
       A ``rerun_token`` may be included on the first ``start`` frame to resume a projected re-run
       (see ``client.reruns``). A ``workflow_run_id`` instead takes back a run a socket handed off
       (see ``client.runs.stream``).
    3. Server streams JSON event messages until the run waits for the user's next message
       (``workflow_ready_for_input``) or ends.
    4. Client sends each later turn as a ``resume`` frame (``send()``), or ``stop`` to end the run
       (``stop()``). The socket has no ``data`` command; that is REST execute's.
    5. Connection closes (server-initiated) when run finishes or errors.

Things the server does that are easy to misread:

* **"Your turn" has no one event.** The server sends ``workflow_ready_for_input`` only while fork
  companions run on in the background, and their events keep arriving after it. Without companions
  it sends nothing of the kind: the turn's ``end_workflow_iteration`` closes a turn that left the run
  waiting, and also one that ends it. A stream follows each turn the way the server settles one and
  marks the event that hands over to the user, so ``event.is_ready_for_input()`` answers either way.
* **A frame sent mid-turn waits.** The server reads the socket only between turns, so a ``send()`` or
  ``stop()`` made while a turn runs takes effect when that turn ends. Between turns, it interrupts the
  companions' background work at its next safe point.
* **Some closures are rejections, not endings.** The server closes the socket with one code per
  refusal, and each code raises its own ``StreamError`` subclass carrying ``code``, ``reason`` and,
  when the server sent one first, the ``workflow_error`` frame's full ``server_message`` (a close
  reason holds only 123 bytes). Close code 1000 is the run ending and stops iteration.
* **Leaving the stream ends the run.** Closing the socket on a run that has not finished cancels
  it (``status`` ``cancelled``, ``termination_source`` ``websocket_disconnect``), companion threads
  included, even mid-turn. A durable socket run waiting on a pause is the exception: the server
  hands it on rather than cancelling it.

SDK design:
    - ``AsyncStream[T]``  — async-native iterator.  Use with ``async for``.
    - ``Stream[T]``       — synchronous iterator that runs the async stream
                            inside a dedicated event loop via anyio.

Both are generic over *T*, the Pydantic model the events are validated into.
Pass ``cast_to=RunEvent`` to get typed events back.
"""

from __future__ import annotations

import functools
import json
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Generic, Iterator, Optional, Type, TypeVar, cast

from interactly._exceptions import InteractlyError
from interactly._utils._logs import logger
from interactly._utils._serialise import serialise_config
from interactly._utils._transform import deep_merge

if TYPE_CHECKING:  # pragma: no cover - imports for type hints only
    from interactly_configs.workflow_run import WorkflowRunInput


class StreamError(InteractlyError):
    """Raised when a streaming connection drops abnormally or a frame is malformed.

    When the server closed the socket, ``code`` and ``reason`` are the close code and reason. When it sent a
    ``workflow_error`` frame just before closing, ``server_message`` is that frame's message: the whole reason, where
    a close reason is cut at 123 bytes.
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[int] = None,
        reason: Optional[str] = None,
        server_message: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.server_message = server_message


class StreamRejectedError(StreamError):
    """The server refused to start or continue the run (close code **4000**).

    The reason says which: the start frame was malformed, the requested version does not exist, the workflow's
    configuration or runtime could not be loaded, or a take-back start frame was misused.
    """


class UnrunnableWorkflowError(StreamError):
    """The workflow's stored configuration cannot be run.

    Close code **4001**: its nodes belong to a different version than the one requested. **4002**: it has no nodes.
    **4005**: a super node in it could not be expanded. Fix the workflow; retrying the same start frame will not help.
    """


class ConcurrencyLimitError(StreamError):
    """The team or workflow is already running as many runs as it may (close code **4003**). Retry later."""


class InvalidStreamInputError(StreamError):
    """The server rejected the start frame because it carried state a client may not supply.

    Close code **4006**. The workflow service enforces one invariant absolutely: *a client is never
    the source of run state*. Sending ``initial_state`` — even a correct-looking one — is refused
    rather than merged, because a run whose state came from the wire cannot be audited. To resume or
    branch a run, mint a re-run token (``client.reruns.create_token``) and pass ``rerun_token``
    instead; the server rebuilds the state itself from the stored run.
    """


class RerunTokenError(StreamError):
    """The ``rerun_token`` in the start frame was not usable.

    Close code **4007**. Raised when the token has expired, was minted for a different workflow or
    version, or the workflow changed after the token was created. Mint a fresh one with
    ``client.reruns.create_token``; the reason is included in the message.
    """


class RunChangedElsewhereError(StreamError):
    """The run was changed elsewhere while this socket held it (close code **4009**).

    A person paused, resumed or cancelled it through the run-control API, or another session carried it on, so this
    session's next turn could not be stored. ``server_message`` gives the run's status as it now stands.
    """


class TakeBackRefusedError(StreamError):
    """The run could not be taken back on this socket (close code **4010**).

    It has ended, is being cancelled, is open in another session, or the server is carrying it on right now.
    ``server_message`` says which; the last of these is worth retrying in a moment.
    """


class TakeBackForbiddenError(StreamError):
    """The caller's role may not take back a run (close code **4030**): it needs developer access or above."""


class StreamNotFoundError(StreamError):
    """The workflow or the run named in the start frame does not exist for this team (close code **4040**)."""


class ResumeInputRejectedError(StreamError):
    """The frame carried a resume input (close code **4400**).

    Resuming a paused node is the server's to do, from the pause it recorded; approve a pause with
    ``client.runs.resume`` instead.
    """


class StreamPermissionError(StreamError):
    """The caller's role may not run workflows (close code **1008**): a viewer, or a role the server does not know.

    Running a workflow needs developer access or above.
    """


class StreamServerError(StreamError):
    """The server failed while handling the run (close code **1011**). The reason carries the error."""


#: WebSocket close codes the workflow service closes the run socket with, mapped to the exception that explains what
#: happened. 1000 is the run ending, not an error. Any other code stays a plain ``StreamError``.
_CLOSE_CODE_ERRORS: dict[int, type[StreamError]] = {
    1008: StreamPermissionError,
    1011: StreamServerError,
    4000: StreamRejectedError,
    4001: UnrunnableWorkflowError,
    4002: UnrunnableWorkflowError,
    4003: ConcurrencyLimitError,
    4005: UnrunnableWorkflowError,
    4006: InvalidStreamInputError,
    4007: RerunTokenError,
    4009: RunChangedElsewhereError,
    4010: TakeBackRefusedError,
    4030: TakeBackForbiddenError,
    4040: StreamNotFoundError,
    4400: ResumeInputRejectedError,
}

ItemT = TypeVar("ItemT")

__all__ = [
    "AsyncStream",
    "ConcurrencyLimitError",
    "InvalidStreamInputError",
    "RerunTokenError",
    "ResumeInputRejectedError",
    "RunChangedElsewhereError",
    "Stream",
    "StreamError",
    "StreamNotFoundError",
    "StreamPermissionError",
    "StreamRejectedError",
    "StreamServerError",
    "TakeBackForbiddenError",
    "TakeBackRefusedError",
    "UnrunnableWorkflowError",
]


class AsyncStream(Generic[ItemT]):
    """
    Async iterator over WebSocket event messages, which also sends the run's later turns.

    Usage::

        async with client.runs.stream(workflow_id="abc") as stream:
            async for event in stream:
                print(event.type, event.output)

    A whole conversation in one block::

        replies = iter(["I'd like to book an appointment.", "Tuesday morning, please."])
        async with client.runs.stream(workflow_id="abc") as stream:
            async for event in stream:
                if event.is_ready_for_input():
                    reply = next(replies, None)
                    if reply is None:
                        await stream.stop()
                    else:
                        await stream.send(reply)
    """

    def __init__(
        self,
        *,
        ws_url: str,
        ws_headers: dict[str, str],
        payload: dict[str, Any],
        cast_to: Optional[Type[ItemT]],
        token_provider: Optional[Callable[[], Awaitable[Optional[str]]]] = None,
    ) -> None:
        self._ws_url = ws_url
        self._ws_headers = ws_headers
        self._payload = payload
        self._cast_to = cast_to
        self._token_provider = token_provider
        self._ws: Any = None
        # The message of the last `workflow_error` frame, which the server sends before some closes.
        self._last_error_message: Optional[str] = None
        # Known up front when taking a run back; otherwise from the first frame that names the run.
        self._run_id: Optional[str] = payload.get("workflow_run_id") or None
        # Set once iteration has reported the socket's close: nothing more can be sent after it.
        self._closed = False
        self._turn = _TurnTracker()

    async def __aenter__(self) -> "AsyncStream[ItemT]":
        try:
            import websockets
        except ImportError as exc:
            raise ImportError(
                "The 'websockets' package is required for streaming. "
                "Install it with: pip install 'interactly[stream]' or pip install websockets"
            ) from exc

        # The gateway authenticates WS upgrades via a single-use ``?token=``
        # session rather than the bearer header, so mint one when a provider is
        # supplied. A ``None`` token means no gateway session endpoint is
        # available; fall back to the header-based handshake.
        ws_url = self._ws_url
        if self._token_provider is not None:
            token = await self._token_provider()
            if token:
                sep = "&" if "?" in ws_url else "?"
                ws_url = f"{ws_url}{sep}token={token}"

        # Build additional_headers accepted by websockets ≥ 12.
        additional_headers = list(self._ws_headers.items())
        logger.debug("Opening WebSocket", extra={"url": ws_url})
        self._ws = await websockets.connect(
            ws_url,
            additional_headers=additional_headers,
        )
        # Send the initial command payload. A caller refused outright (a viewer, on the run socket) is accepted and
        # closed at once, often before this goes out; iteration reports that close (see `_send_frame`).
        await self._send_frame(self._payload)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    def __aiter__(self) -> "AsyncStream[ItemT]":
        return self

    @property
    def run_id(self) -> Optional[str]:
        """The run's id: from the first frame that names it, or the one taken back. ``None`` until then."""
        return self._run_id

    async def send(
        self,
        message: Optional[str] = None,
        *,
        dynamic_variables: Optional[dict[str, Any]] = None,
        runtime_variables: Optional[dict[str, Any]] = None,
        run_input: Optional["WorkflowRunInput"] = None,
    ) -> None:
        """Send the run's next turn: ``message`` as the user's next message, on the main thread.

        Call it once an event ``is_ready_for_input()``, then keep iterating the same stream for the turn's events, so
        one block holds a whole conversation. The server reads the socket only between turns: a turn sent while one
        is running waits for it to end.

        The variables the stream was opened with go with every turn, because edge conditions read them from each
        turn's input. ``dynamic_variables`` and ``runtime_variables`` given here are merged over them, for this turn
        only.

        While a person has paused the run, the server refuses the turn with a ``run_paused`` frame and drops the
        message; send it again after ``run_resumed``.

        Args:
            message: The user's next message, as text. Leave it out for a turn that carries none.
            dynamic_variables: ``{{...}}`` values for this turn, merged over the stream's.
            runtime_variables: ``[[...]]`` values for this turn, merged over the stream's.
            run_input: A typed ``WorkflowRunInput``, for a turn that needs more than one message (other threads,
                other node inputs). Its ``command`` is sent as ``resume`` whatever it holds.

        Raises:
            ValueError: Both ``message`` and ``run_input`` were given.
            StreamError: The stream is not open, or has already reported its end.
        """
        frame = _turn_frame(
            self._payload,
            self._run_id,
            message=message,
            dynamic_variables=dynamic_variables,
            runtime_variables=runtime_variables,
            run_input=run_input,
        )
        await self._send_frame(frame)

    async def stop(self) -> None:
        """Stop the run.

        The server stores it as ``cancelled`` (``termination_source`` ``client_stop``), sends a last frame and closes
        the socket normally, which ends iteration; keep iterating to see them. Like ``send()``, it takes effect
        between turns.

        Raises:
            StreamError: The stream is not open, or has already reported its end.
        """
        await self._send_frame(_stop_frame(self._payload, self._run_id))

    async def __anext__(self) -> ItemT:
        if self._ws is None:
            raise StopAsyncIteration

        try:
            import websockets
        except ImportError as exc:
            raise ImportError(
                "The 'websockets' package is required for streaming. "
                "Install it with: pip install 'interactly[stream]' or pip install websockets"
            ) from exc

        try:
            raw = await self._ws.recv()
        except websockets.exceptions.ConnectionClosedOK:
            # Normal closure (code 1000) → clean end of stream.
            logger.debug("WebSocket closed normally (1000)")
            self._closed = True
            raise StopAsyncIteration
        except websockets.exceptions.ConnectionClosed as exc:
            self._closed = True
            # Any non-1000 closure is an abnormal termination, not end-of-stream. Some of them are
            # the server rejecting the start frame for a specific, fixable reason — surface those as
            # their own exception rather than as an opaque "closed abnormally".
            close_frame = getattr(exc, "rcvd", None)
            code: Optional[int] = getattr(close_frame, "code", None)
            reason: str = getattr(close_frame, "reason", "") or ""
            logger.debug("WebSocket closed abnormally", extra={"code": code, "reason": reason})
            server_message = self._last_error_message
            error_cls = _CLOSE_CODE_ERRORS.get(code) if code is not None else None
            if error_cls is None:
                message = f"WebSocket connection closed abnormally: {exc}"
                error_cls = StreamError
            else:
                message = f"{server_message or reason or 'no reason given'} (close code {code})"
            raise error_cls(message, code=code, reason=reason or None, server_message=server_message) from exc

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise StreamError(f"Failed to decode stream frame as JSON: {exc}") from exc

        if not isinstance(data, dict):
            return self._parse(data)
        if data.get("type") == "workflow_error" and isinstance(data.get("message"), str):
            self._last_error_message = data["message"]
        if self._run_id is None and data.get("workflow_run_id"):
            self._run_id = str(data["workflow_run_id"])
        hands_over = self._turn.hands_over_to_user(data)
        item = self._parse(data)
        if hands_over and hasattr(item, "_ends_turn_awaiting_user"):
            # A RunEvent: its is_ready_for_input() reads this.
            item._ends_turn_awaiting_user = True
        return item

    async def _send_frame(self, frame: dict[str, Any]) -> None:
        if self._ws is None:
            raise StreamError("The stream is not open: send from inside its `with` block.")
        if self._closed:
            raise StreamError("The stream has ended: the server closed the run's socket, so nothing more can be sent.")
        import websockets

        try:
            await self._ws.send(json.dumps(frame))
        except websockets.exceptions.ConnectionClosedOK as exc:
            # The run ended on its own before this frame went out; nothing will take it.
            close_frame = getattr(exc, "rcvd", None)
            raise StreamError(
                "The run has ended, so nothing more can be sent; the stream still holds its last events.",
                code=getattr(close_frame, "code", None),
                reason=getattr(close_frame, "reason", None) or None,
            ) from exc
        except websockets.exceptions.ConnectionClosed:
            # A refusal or a failure, a frame the server sent before the close possibly still unread. Iteration
            # reports that close, as it does one met while receiving, so the same close raises the same exception
            # whichever side was first.
            logger.debug("WebSocket closed before a frame was sent")

    def _parse(self, data: dict[str, Any]) -> ItemT:
        if self._cast_to is None:
            return data  # type: ignore[return-value]
        # Same unbounded-`ItemT` situation as `_pagination._from_response`: the runtime contract is
        # the `hasattr` branch, but a checker only sees `type[object]`.
        if hasattr(self._cast_to, "model_validate"):
            return cast(ItemT, self._cast_to.model_validate(data))  # type: ignore[attr-defined]
        return self._cast_to(data)  # type: ignore[call-arg]


class Stream(Generic[ItemT]):
    """
    Synchronous iterator over WebSocket event messages, which also sends the run's later turns.

    Internally runs the async stream inside a dedicated event loop managed by
    ``anyio``, so it works in any thread including the main thread (unlike
    ``asyncio.get_event_loop().run_until_complete``).

    Usage::

        with client.runs.stream(workflow_id="abc") as stream:
            for event in stream:
                print(event.type, event.output)
                if event.is_ready_for_input():
                    stream.send(input("You: "))

    ``send()``, ``stop()`` and ``run_id`` behave as :class:`AsyncStream`'s do.
    """

    def __init__(
        self,
        *,
        ws_url: str,
        ws_headers: dict[str, str],
        payload: dict[str, Any],
        cast_to: Optional[Type[ItemT]],
    ) -> None:
        self._ws_url = ws_url
        self._ws_headers = ws_headers
        self._payload = payload
        self._cast_to = cast_to
        self._portal: Any = None
        self._portal_cm: Any = None
        self._async_stream: Optional[AsyncStream[ItemT]] = None
        self._aenter_cm: Any = None

    def __enter__(self) -> "Stream[ItemT]":
        try:
            from anyio.from_thread import start_blocking_portal
        except ImportError as exc:
            raise ImportError(
                "The 'anyio' package is required for synchronous streaming. "
                "Install it with: pip install 'interactly[stream]' or pip install anyio"
            ) from exc

        self._portal_cm = start_blocking_portal()
        self._portal = self._portal_cm.__enter__()

        try:
            self._async_stream = AsyncStream(
                ws_url=self._ws_url,
                ws_headers=self._ws_headers,
                payload=self._payload,
                cast_to=self._cast_to,
            )
            self._portal.call(self._async_stream.__aenter__)
        except BaseException:
            # WS handshake (or portal.call) failed after the portal thread
            # started — tear the portal down so its thread/event loop don't leak.
            self._async_stream = None
            try:
                self._portal_cm.__exit__(None, None, None)
            except Exception:
                pass
            self._portal = None
            self._portal_cm = None
            raise
        return self

    def __exit__(self, *args: object) -> None:
        if self._async_stream is not None and self._portal is not None:
            try:
                self._portal.call(self._async_stream.__aexit__, None, None, None)
            except Exception:
                pass
        if self._portal_cm is not None:
            try:
                self._portal_cm.__exit__(None, None, None)
            except Exception:
                pass
        # The portal's event loop is gone: anything called on the stream from here would hang or fail obscurely.
        self._async_stream = None
        self._portal = None
        self._portal_cm = None

    def __iter__(self) -> Iterator[ItemT]:
        return self

    def __next__(self) -> ItemT:
        if self._async_stream is None or self._portal is None:
            raise StopIteration
        try:
            return cast(ItemT, self._portal.call(self._async_stream.__anext__))
        except StopAsyncIteration:
            raise StopIteration
        except StopIteration:
            raise

    @property
    def run_id(self) -> Optional[str]:
        """The run's id: from the first frame that names it, or the one taken back. ``None`` until then."""
        return self._async_stream.run_id if self._async_stream is not None else None

    def send(
        self,
        message: Optional[str] = None,
        *,
        dynamic_variables: Optional[dict[str, Any]] = None,
        runtime_variables: Optional[dict[str, Any]] = None,
        run_input: Optional["WorkflowRunInput"] = None,
    ) -> None:
        """Send the run's next turn. See :meth:`AsyncStream.send`."""
        stream, portal = self._open()
        portal.call(
            functools.partial(
                stream.send,
                message,
                dynamic_variables=dynamic_variables,
                runtime_variables=runtime_variables,
                run_input=run_input,
            )
        )

    def stop(self) -> None:
        """Stop the run. See :meth:`AsyncStream.stop`."""
        stream, portal = self._open()
        portal.call(stream.stop)

    def _open(self) -> tuple[AsyncStream[ItemT], Any]:
        if self._async_stream is None or self._portal is None:
            raise StreamError("The stream is not open: send from inside its `with` block.")
        return self._async_stream, self._portal


#: How the server names a fork companion's thread: ``"<parent>_companion_<id>"``. A companion waiting is background
#: work, not the run waiting for its user.
_COMPANION_THREAD_DELIMITER = "_companion_"


class _TurnTracker:
    """Follows a run socket's turns, as the server settles one, to find the event that hands over to the user.

    A turn leaves the run waiting for the user when a main thread busy-waits for a message and no pause came after
    it; the last of the two wins, as it does on the server. ``end_workflow_iteration`` ends the turn. When fork
    companions run on, the server says the same with ``workflow_ready_for_input``, and that event hands over instead,
    so the user is told once. A take-back's acknowledgement hands over when the run it took back waits for its user.
    """

    def __init__(self) -> None:
        self._waiting = False
        self._announced = False

    def hands_over_to_user(self, frame: dict[str, Any]) -> bool:
        kind = frame.get("type")
        main_thread = _COMPANION_THREAD_DELIMITER not in str(frame.get("origin_thread_id") or "")
        if kind == "busy_wait_for_user_message" and main_thread:
            self._waiting = True
        elif kind in ("pause_event", "pause_thread") and main_thread:
            self._waiting = False
        elif kind == "workflow_ready_for_input":
            self._announced = True
        elif kind == "end_workflow_iteration":
            hands_over = self._waiting and not self._announced
            self._waiting = self._announced = False
            return hands_over
        elif kind in ("end_workflow", "workflow_error"):
            # A turn that fails ends with its error instead of an iteration end, the socket open when the server
            # tolerated the failure.
            self._waiting = self._announced = False
        elif not kind and frame.get("workflow_run_status") == "waiting_for_user_input":
            return True
        return False


def _turn_frame(
    start: dict[str, Any],
    run_id: Optional[str],
    *,
    message: Optional[str],
    dynamic_variables: Optional[dict[str, Any]],
    runtime_variables: Optional[dict[str, Any]],
    run_input: Optional["WorkflowRunInput"],
) -> dict[str, Any]:
    """The ``resume`` frame of a run's next turn, shaped as the workflow editor sends it.

    The server runs a ``resume`` on the run the socket holds; ``workflow_run_id`` names it as the editor does. Each
    variable map is the stream's (from its ``start`` frame), then the typed input's, then this turn's, each merged
    over the one before.
    """
    if message is not None and run_input is not None:
        raise ValueError("Pass either a message or a typed run_input, not both.")
    if run_input is not None:
        frame: dict[str, Any] = dict(serialise_config(run_input))
    else:
        node_run_inputs = [] if message is None else [_user_message_input(message)]
        frame = {"thread_to_node_inputs": {"0": {"node_run_inputs": node_run_inputs}}}
    frame["command"] = "resume"
    frame["workflow_id"] = start.get("workflow_id")
    frame["workflow_run_id"] = run_id
    for name, given in (("dynamic_variables", dynamic_variables), ("runtime_variables", runtime_variables)):
        frame[name] = deep_merge(deep_merge(start.get(name) or {}, frame.get(name) or {}), given or {})
    return frame


def _stop_frame(start: dict[str, Any], run_id: Optional[str]) -> dict[str, Any]:
    """The ``stop`` frame, as the workflow editor sends it."""
    return {"command": "stop", "workflow_id": start.get("workflow_id"), "workflow_run_id": run_id}


def _user_message_input(text: str) -> dict[str, Any]:
    """An LLM node input holding one user message: how a user's turn reaches the workflow."""
    return {"type": "llm", "messages": [{"type": "human", "content": text}]}
