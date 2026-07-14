"""
Retry logic for transient HTTP errors.

The SDK uses a simple exponential-backoff strategy with jitter:
    wait = min(base * 2**attempt, cap) + jitter

Retries are method-aware:
  - Idempotent methods (GET, HEAD, OPTIONS, DELETE, PUT) retry on any status
    in RETRY_STATUS_CODES.
  - Non-idempotent methods (POST, PATCH) must NOT be auto-replayed on a 5xx
    once the request was sent (the server may have committed it). They are only
    retried on 429 (rate limit — the request was rejected, not processed).
    Pre-send connection errors / timeouts are retried for every method by the
    caller (they raise before a response exists).

Only status codes in RETRY_STATUS_CODES are ever retried; client errors (4xx
other than 429) are never retried.
"""

from __future__ import annotations

import email.utils
import random
import time
from datetime import datetime, timezone
from typing import Callable, Optional

import httpx

from interactly._constants import RETRY_STATUS_CODES
from interactly._utils._logs import logger

__all__ = ["should_retry", "backoff_delay", "retry_after_seconds", "with_retry", "with_retry_async"]

_BACKOFF_BASE: float = 0.5  # seconds
_BACKOFF_CAP: float = 8.0   # seconds

# Methods that are safe to auto-replay: the server contract guarantees that
# repeating them has the same effect as issuing them once.
IDEMPOTENT_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "DELETE", "PUT"})

# For non-idempotent methods we only retry on statuses that mean the request
# was rejected before being processed.
_NON_IDEMPOTENT_RETRY_STATUS_CODES: frozenset[int] = frozenset({429})


def should_retry(method: str, response: httpx.Response) -> bool:
    """
    Return True if the response indicates a safe retry for the given method.

    Idempotent methods retry on the full RETRY_STATUS_CODES set. Non-idempotent
    methods (POST/PATCH) only retry on 429 — a 5xx may mean the write already
    committed, so auto-replaying it risks duplicate side effects.
    """
    status = response.status_code
    if method.upper() in IDEMPOTENT_METHODS:
        return status in RETRY_STATUS_CODES
    return status in _NON_IDEMPOTENT_RETRY_STATUS_CODES


def retry_after_seconds(response: httpx.Response) -> Optional[float]:
    """
    Parse the ``Retry-After`` header (delta-seconds or an HTTP-date) into a
    non-negative number of seconds, or ``None`` if absent/unparseable.
    """
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    raw = raw.strip()
    # Delta-seconds form.
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    # HTTP-date form.
    try:
        dt = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = (dt - datetime.now(timezone.utc)).total_seconds()
    return max(0.0, delta)


def backoff_delay(attempt: int) -> float:
    """
    Compute an exponential backoff with full jitter (AWS-style).

    Args:
        attempt: 0-based attempt index (first retry → 0).

    Returns:
        Seconds to sleep before the next attempt.
    """
    cap = _BACKOFF_CAP
    base = _BACKOFF_BASE
    delay = min(cap, base * (2**attempt))
    return random.uniform(0, delay)


def _retry_delay(attempt: int, response: httpx.Response) -> float:
    """Combine computed backoff with any server-supplied Retry-After hint."""
    delay = backoff_delay(attempt)
    ra = retry_after_seconds(response)
    if ra is not None:
        return max(ra, delay)
    return delay


def with_retry(
    send: Callable[[], httpx.Response],
    max_retries: int,
    method: str,
) -> httpx.Response:
    """
    Wrap a synchronous send callable with retry logic.

    Args:
        send:        A zero-argument callable that returns an httpx.Response.
        max_retries: Maximum number of additional attempts (0 = no retry).
        method:      The HTTP method, used to decide whether a 5xx is retryable.

    Returns:
        The final httpx.Response after all retry attempts.
    """
    for attempt in range(max_retries + 1):
        response = send()
        if attempt == max_retries or not should_retry(method, response):
            return response
        delay = _retry_delay(attempt, response)
        logger.debug(
            "Retryable response — sleeping before retry",
            extra={"status": response.status_code, "attempt": attempt + 1, "delay_s": round(delay, 3)},
        )
        time.sleep(delay)

    # Unreachable, but satisfies the type checker.
    return response  # type: ignore[return-value]


async def with_retry_async(
    send: Callable[[], "asyncio.Coroutine[None, None, httpx.Response]"],
    max_retries: int,
    method: str,
) -> httpx.Response:
    """
    Async variant of `with_retry`.
    """
    import asyncio

    for attempt in range(max_retries + 1):
        response = await send()
        if attempt == max_retries or not should_retry(method, response):
            return response
        delay = _retry_delay(attempt, response)
        logger.debug(
            "Retryable response — sleeping before retry",
            extra={"status": response.status_code, "attempt": attempt + 1, "delay_s": round(delay, 3)},
        )
        await asyncio.sleep(delay)

    return response  # type: ignore[return-value]
