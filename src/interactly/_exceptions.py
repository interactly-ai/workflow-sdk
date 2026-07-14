"""
Full exception hierarchy for the Interactly SDK.

Usage:
    from interactly import NotFoundError, RateLimitError

    try:
        workflow = client.workflows.get("id")
    except NotFoundError:
        ...
    except RateLimitError as e:
        retry_after = e.response.headers.get("Retry-After")
        ...
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

__all__ = [
    "InteractlyError",
    "APIError",
    "APIConnectionError",
    "APITimeoutError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "UnprocessableEntityError",
    "RateLimitError",
    "InternalServerError",
    "NoMorePagesError",
]


class InteractlyError(Exception):
    """Base class for all errors raised by the Interactly SDK."""


class NoMorePagesError(InteractlyError):
    """
    Raised when ``next_page()`` / ``anext_page()`` is called on the last page.

    A domain-specific exception is used instead of ``StopIteration`` /
    ``StopAsyncIteration`` so that raising it from a public method does not
    trip PEP-479 semantics inside a caller's generator.
    """


class APIConnectionError(InteractlyError):
    """
    Raised when an HTTP request fails at the network layer — before any
    response is received (DNS failure, connection refused, etc.).

    ``request`` may be ``None`` for failures where httpx never built a request
    object (e.g. pool timeouts — ``httpx.PoolTimeout.request`` is ``None``).
    """

    def __init__(self, *, message: str, request: Optional[httpx.Request] = None) -> None:
        super().__init__(message)
        self.request = request


class APITimeoutError(APIConnectionError):
    """
    Raised when the server does not respond within the configured timeout.
    Inherits from APIConnectionError because no HTTP response is available.
    """


class APIError(InteractlyError):
    """
    Raised for any HTTP response with a 4xx or 5xx status code.

    Attributes:
        status_code: The HTTP status code.
        message:     Human-readable error description from the response body.
        body:        The parsed JSON response body (if available).
        request:     The original httpx.Request that triggered this error.
        response:    The raw httpx.Response.
        request_id:  The value of the X-Request-Id header, if present.
    """

    status_code: int
    message: str
    body: Optional[Any]
    request: httpx.Request
    response: httpx.Response
    request_id: Optional[str]

    def __init__(
        self,
        *,
        message: str,
        status_code: int,
        body: Optional[Any],
        request: httpx.Request,
        response: httpx.Response,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.body = body
        self.request = request
        self.response = response
        self.request_id = response.headers.get("X-Request-Id")

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"status_code={self.status_code}, "
            f"message={self.message!r}, "
            f"request_id={self.request_id!r})"
        )


class AuthenticationError(APIError):
    """HTTP 401 — API key missing, invalid, or expired."""


class PermissionDeniedError(APIError):
    """HTTP 403 — Valid credentials but insufficient permissions."""


class NotFoundError(APIError):
    """HTTP 404 — The requested resource does not exist."""


class ConflictError(APIError):
    """HTTP 409 — The request conflicts with existing server state."""


class UnprocessableEntityError(APIError):
    """HTTP 422 — Request body failed schema validation."""


class RateLimitError(APIError):
    """HTTP 429 — Too many requests. Check `response.headers['Retry-After']`."""


class InternalServerError(APIError):
    """HTTP 5xx — An unexpected error occurred on the server."""


# --------------------------------------------------------------------------- #
# Factory                                                                      #
# --------------------------------------------------------------------------- #

def _make_status_error(
    response: httpx.Response,
    body: Optional[Any] = None,
) -> APIError:
    """
    Map an HTTP error response to the most specific APIError subclass.
    Called by _base_client after receiving a non-2xx response.
    """
    status = response.status_code
    # Extract a readable message from the response body.
    if isinstance(body, dict):
        message = str(body.get("detail") or body.get("message") or body.get("error") or response.reason_phrase)
    else:
        message = response.reason_phrase or f"HTTP {status}"

    kwargs: dict[str, Any] = {
        "message": message,
        "status_code": status,
        "body": body,
        "request": response.request,
        "response": response,
    }

    if status == 401:
        return AuthenticationError(**kwargs)
    if status == 403:
        return PermissionDeniedError(**kwargs)
    if status == 404:
        return NotFoundError(**kwargs)
    if status == 409:
        return ConflictError(**kwargs)
    if status == 422:
        return UnprocessableEntityError(**kwargs)
    if status == 429:
        return RateLimitError(**kwargs)
    if status >= 500:
        return InternalServerError(**kwargs)
    return APIError(**kwargs)
