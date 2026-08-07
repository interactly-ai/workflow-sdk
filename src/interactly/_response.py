"""
APIResponse — wraps a raw httpx.Response and provides typed parsing.

Keeps raw response metadata (headers, request_id, status_code) accessible
while making `.parse()` the idiomatic way to get a typed model instance.
"""

from __future__ import annotations

from typing import Generic, Optional, Type, TypeVar, cast

import httpx
from pydantic import BaseModel

from interactly._exceptions import APIError, _make_status_error
from interactly._utils._logs import logger

ModelT = TypeVar("ModelT")

__all__ = ["APIResponse"]


class APIResponse(Generic[ModelT]):
    """
    Thin wrapper around httpx.Response that adds typed parsing.

    Attributes:
        http_response: The raw httpx.Response for escape-hatch access.
        request_id:    The server-assigned request identifier (X-Request-Id).
        status_code:   The HTTP status code.
    """

    def __init__(self, *, http_response: httpx.Response, cast_to: Type[ModelT] | None) -> None:
        self._http_response = http_response
        self._cast_to = cast_to

    # ---------------------------------------------------------------------- #
    # Metadata                                                                 #
    # ---------------------------------------------------------------------- #

    @property
    def http_response(self) -> httpx.Response:
        return self._http_response

    @property
    def headers(self) -> httpx.Headers:
        return self._http_response.headers

    @property
    def status_code(self) -> int:
        return self._http_response.status_code

    @property
    def request_id(self) -> str | None:
        # httpx's Headers.get is untyped, so the value arrives as Any.
        return cast(Optional[str], self._http_response.headers.get("X-Request-Id"))

    # ---------------------------------------------------------------------- #
    # Parsing                                                                  #
    # ---------------------------------------------------------------------- #

    def parse(self) -> ModelT:
        """
        Parse the response body and return a typed model instance.

        Raises:
            APIError subclass on non-2xx responses.
        """
        if self._http_response.is_error:
            body = self._try_parse_json()
            raise _make_status_error(self._http_response, body)

        body = self._try_parse_json()
        logger.debug(
            "Response received",
            extra={"status": self.status_code, "request_id": self.request_id},
        )

        if self._cast_to is None or self._cast_to is type(None):
            return None  # type: ignore[return-value]

        if isinstance(body, self._cast_to):
            return body

        # Pydantic model validation.
        if isinstance(self._cast_to, type) and issubclass(self._cast_to, BaseModel):
            return self._cast_to.model_validate(body)

        # Explicit dict/list casts: validate the body shape rather than falling
        # through to ``self._cast_to(body)`` (which would silently do e.g.
        # ``dict(list)`` and raise an opaque error on a shape mismatch).
        if self._cast_to is dict:
            if not isinstance(body, dict):
                raise APIError(
                    message=f"Expected a JSON object but the server returned {type(body).__name__}",
                    status_code=self.status_code,
                    body=body,
                    request=self._http_response.request,
                    response=self._http_response,
                )
            return body  # type: ignore[return-value]

        if self._cast_to is list:
            if not isinstance(body, list):
                raise APIError(
                    message=f"Expected a JSON array but the server returned {type(body).__name__}",
                    status_code=self.status_code,
                    body=body,
                    request=self._http_response.request,
                    response=self._http_response,
                )
            return body  # type: ignore[return-value]

        # Primitive types (str, int, bool). `ResponseT` is unbounded, so a checker sees `object()`
        # and objects to the argument; at runtime this branch only ever holds a real primitive type.
        return self._cast_to(body)  # type: ignore[call-arg]

    def _try_parse_json(self) -> object:
        try:
            return self._http_response.json()
        except Exception:
            return self._http_response.text
