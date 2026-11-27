"""
WebSocket streaming helpers.

The Interactly Workflow Service exposes a WebSocket endpoint at:
    ws://host/v1/workflow-runs/ws

Protocol:
    1. Client opens WebSocket connection with auth headers.
    2. Client sends a JSON message conforming to WorkflowRunInput:
           {"workflow_id": "...", "command": "start", "run_by": "api"}
       A ``rerun_token`` may be included on the first ``start`` frame to resume a projected re-run
       (see ``client.reruns``).
    3. Server streams JSON event messages until the run completes.
    4. Connection closes (server-initiated) when run finishes or errors.

Two things the server may do that are easy to misread:

* **Background events arrive mid-wait.** While the workflow waits for the next user message, fork
  companions keep running and their events keep arriving. ``end_workflow_iteration`` therefore does
  not mean "your turn" — ``workflow_ready_for_input`` does.
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

import json
from typing import Any, Awaitable, Callable, Generic, Iterator, Optional, Type, TypeVar, cast

from interactly._exceptions import InteractlyError
from interactly._utils._logs import logger


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
    Async iterator over WebSocket event messages.

    Usage::

        async with client.runs.stream(workflow_id="abc", command="start") as stream:
            async for event in stream:
                print(event.type, event.output)
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
        # Send the initial command payload.
        try:
            await self._ws.send(json.dumps(self._payload))
        except websockets.exceptions.ConnectionClosed:
            # A caller refused outright (a viewer, on the run socket) is accepted and closed at once, often before
            # the start frame goes out. Iteration reports that close, as it does one that follows the start frame,
            # so the same refusal raises the same exception whichever side was first.
            logger.debug("WebSocket closed before the start frame was sent")
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    def __aiter__(self) -> "AsyncStream[ItemT]":
        return self

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
            raise StopAsyncIteration
        except websockets.exceptions.ConnectionClosed as exc:
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

        if isinstance(data, dict) and data.get("type") == "workflow_error" and isinstance(data.get("message"), str):
            self._last_error_message = data["message"]
        return self._parse(data)

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
    Synchronous iterator over WebSocket event messages.

    Internally runs the async stream inside a dedicated event loop managed by
    ``anyio``, so it works in any thread including the main thread (unlike
    ``asyncio.get_event_loop().run_until_complete``).

    Usage::

        with client.runs.stream(workflow_id="abc", command="start") as stream:
            for event in stream:
                print(event.type, event.output)
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
