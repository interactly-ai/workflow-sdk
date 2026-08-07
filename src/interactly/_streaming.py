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
* **Some closures are rejections, not endings.** Close code 4006 means the start frame carried
  ``initial_state`` (never allowed from a client); 4007 means the ``rerun_token`` was expired or
  did not match. Both raise a specific exception rather than a generic StreamError.

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
    """Raised when a streaming connection drops abnormally or a frame is malformed."""


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


#: WebSocket close codes the workflow service uses to reject a start frame, mapped to the exception
#: that explains what to do about it. Anything else stays a generic ``StreamError``.
_CLOSE_CODE_ERRORS: dict[int, type[StreamError]] = {
    4006: InvalidStreamInputError,
    4007: RerunTokenError,
}

ItemT = TypeVar("ItemT")

__all__ = ["AsyncStream", "InvalidStreamInputError", "RerunTokenError", "Stream", "StreamError"]


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
        await self._ws.send(json.dumps(self._payload))
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
            reason: str = getattr(close_frame, "reason", "") or str(exc)
            logger.debug("WebSocket closed abnormally", extra={"code": code, "reason": reason})
            error_cls = _CLOSE_CODE_ERRORS.get(code) if code is not None else None
            if error_cls is None:
                raise StreamError(f"WebSocket connection closed abnormally: {exc}") from exc
            raise error_cls(f"{reason} (close code {code})") from exc

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise StreamError(f"Failed to decode stream frame as JSON: {exc}") from exc

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
