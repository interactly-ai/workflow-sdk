"""
Webhook signature verification helper.

When you configure a webhook endpoint in the Interactly dashboard, the server
signs every outgoing request with HMAC-SHA256 using your webhook secret.  Use
``verify_signature()`` to confirm that a received payload came from Interactly.

Usage::

    from interactly.webhooks import verify_signature, WebhookVerificationError

    @app.post("/webhook")
    async def handle_webhook(request: Request):
        payload = await request.body()
        try:
            verify_signature(
                payload=payload,
                secret=settings.INTERACTLY_WEBHOOK_SECRET,
                signature_header=request.headers.get("X-Interactly-Signature"),
            )
        except WebhookVerificationError:
            raise HTTPException(status_code=400, detail="Invalid signature")

        event = json.loads(payload)
        ...
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

__all__ = ["WebhookVerificationError", "verify_signature"]


class WebhookVerificationError(Exception):
    """Raised when a webhook payload signature cannot be verified."""


def verify_signature(
    payload: bytes,
    secret: str,
    signature_header: Optional[str],
    *,
    max_age_seconds: int = 300,
    timestamp_header: Optional[str] = None,
) -> None:
    """
    Verify a webhook payload using HMAC-SHA256.

    The server computes ``HMAC-SHA256(secret, payload)`` and sends the hex
    digest in the ``X-Interactly-Signature`` header.

    Args:
        payload:           The raw request body bytes.
        secret:            Your webhook signing secret from the dashboard.
        signature_header:  Value of the ``X-Interactly-Signature`` header.
        max_age_seconds:   Reject payloads older than this (replay protection).
                           Only applied when ``timestamp_header`` is also provided.
        timestamp_header:  Value of the ``X-Interactly-Timestamp`` header (Unix seconds).

    Raises:
        WebhookVerificationError: If the signature is absent, malformed, or does
                                  not match, or if the payload is too old.
    """
    if not signature_header:
        raise WebhookVerificationError("Missing X-Interactly-Signature header")

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Use a constant-time comparison to prevent timing attacks.
    if not hmac.compare_digest(expected, signature_header.strip()):
        raise WebhookVerificationError("Signature mismatch — payload may be tampered with")

    # Optional replay-protection check.
    if timestamp_header is not None:
        try:
            ts = int(timestamp_header)
        except ValueError:
            raise WebhookVerificationError(f"Invalid timestamp header value: {timestamp_header!r}")
        age = int(time.time()) - ts
        if age > max_age_seconds:
            raise WebhookVerificationError(
                f"Webhook payload is too old ({age}s > {max_age_seconds}s limit)"
            )
