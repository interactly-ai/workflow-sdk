"""
Unit tests for the retry helpers.
"""

from __future__ import annotations

import pytest
import httpx

from interactly._utils._retry import backoff_delay, should_retry, with_retry


def _make_response(status: int) -> httpx.Response:
    req = httpx.Request("GET", "http://localhost:8611/v1/workflows")
    return httpx.Response(status, request=req)


class TestShouldRetry:
    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_idempotent_retryable_status_codes(self, status: int):
        # Idempotent methods retry on the full retryable-status set.
        assert should_retry("GET", _make_response(status)) is True

    @pytest.mark.parametrize("status", [200, 201, 400, 401, 403, 404, 422])
    def test_non_retryable_status_codes(self, status: int):
        assert should_retry("GET", _make_response(status)) is False

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_non_idempotent_not_retried_on_5xx(self, status: int):
        # POST/PATCH must NOT be auto-replayed on a 5xx — the write may have committed.
        assert should_retry("POST", _make_response(status)) is False
        assert should_retry("PATCH", _make_response(status)) is False

    def test_non_idempotent_retried_on_429(self):
        # 429 means rejected-before-processing, so it is safe to retry even for POST.
        assert should_retry("POST", _make_response(429)) is True


class TestBackoffDelay:
    def test_delay_is_non_negative(self):
        for attempt in range(5):
            assert backoff_delay(attempt) >= 0

    def test_delay_does_not_exceed_cap(self):
        # Cap is 8.0 seconds.
        for attempt in range(20):
            assert backoff_delay(attempt) <= 8.0

    def test_first_attempt_bounded(self):
        # With base=0.5 and attempt=0, max possible jitter is 0.5.
        for _ in range(50):
            assert backoff_delay(0) <= 0.5


class TestWithRetry:
    def test_no_retry_on_200(self):
        call_count = 0

        def send() -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _make_response(200)

        response = with_retry(send, max_retries=2, method="GET")
        assert response.status_code == 200
        assert call_count == 1  # Only one call; no retry needed.

    def test_retries_on_500_up_to_max(self):
        call_count = 0

        def send() -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _make_response(500)

        response = with_retry(send, max_retries=2, method="GET")
        assert response.status_code == 500
        # Initial attempt + 2 retries = 3 total calls.
        assert call_count == 3

    def test_non_idempotent_not_retried_on_500(self):
        call_count = 0

        def send() -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _make_response(500)

        # A POST that 500s must not be replayed (server may have committed it).
        response = with_retry(send, max_retries=2, method="POST")
        assert response.status_code == 500
        assert call_count == 1

    def test_stops_retrying_after_success(self):
        attempts = iter([500, 500, 200])

        def send() -> httpx.Response:
            return _make_response(next(attempts))

        response = with_retry(send, max_retries=3, method="GET")
        assert response.status_code == 200

    def test_zero_max_retries_sends_once(self):
        call_count = 0

        def send() -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _make_response(500)

        with_retry(send, max_retries=0, method="GET")
        assert call_count == 1
