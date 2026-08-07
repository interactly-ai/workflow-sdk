"""
Unit tests for the exception hierarchy and factory function.
"""

from __future__ import annotations

import httpx

from interactly._exceptions import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    _make_status_error,
)


def _fake_response(status_code: int, body: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "http://localhost:8611/v1/workflows")
    content = b""
    headers: dict[str, str] = {}
    if body is not None:
        import json
        content = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    response = httpx.Response(status_code=status_code, content=content, headers=headers, request=request)
    return response


class TestMakeStatusError:
    def test_401_returns_authentication_error(self):
        response = _fake_response(401, {"detail": "Unauthorized"})
        error = _make_status_error(response, {"detail": "Unauthorized"})
        assert isinstance(error, AuthenticationError)
        assert error.status_code == 401

    def test_403_returns_permission_denied(self):
        response = _fake_response(403)
        error = _make_status_error(response)
        assert isinstance(error, PermissionDeniedError)

    def test_404_returns_not_found(self):
        response = _fake_response(404, {"detail": "Not found"})
        error = _make_status_error(response, {"detail": "Not found"})
        assert isinstance(error, NotFoundError)
        assert "Not found" in error.message

    def test_409_returns_conflict(self):
        response = _fake_response(409)
        assert isinstance(_make_status_error(response), ConflictError)

    def test_422_returns_unprocessable(self):
        response = _fake_response(422, {"detail": "Validation error"})
        assert isinstance(_make_status_error(response, {"detail": "Validation error"}), UnprocessableEntityError)

    def test_429_returns_rate_limit(self):
        response = _fake_response(429)
        assert isinstance(_make_status_error(response), RateLimitError)

    def test_500_returns_internal_server_error(self):
        response = _fake_response(500)
        assert isinstance(_make_status_error(response), InternalServerError)

    def test_503_returns_internal_server_error(self):
        response = _fake_response(503)
        assert isinstance(_make_status_error(response), InternalServerError)

    def test_request_id_extracted_from_headers(self):
        request = httpx.Request("GET", "http://localhost:8611/v1/workflows")
        response = httpx.Response(
            404,
            content=b"{}",
            headers={"X-Request-Id": "req-abc-123"},
            request=request,
        )
        error = _make_status_error(response, {})
        assert error.request_id == "req-abc-123"


class TestAPIConnectionError:
    def test_stores_request(self):
        req = httpx.Request("GET", "http://localhost:8611")
        exc = APIConnectionError(message="Connection refused", request=req)
        assert exc.request is req
        assert "Connection refused" in str(exc)

    def test_timeout_is_subclass_of_connection_error(self):
        req = httpx.Request("GET", "http://localhost:8611")
        exc = APITimeoutError(message="Timed out", request=req)
        assert isinstance(exc, APIConnectionError)
