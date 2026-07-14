"""
Unit tests for webhook signature verification.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from interactly.webhooks import WebhookVerificationError, verify_signature


def _sign(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


class TestVerifySignature:
    def test_valid_signature_passes(self):
        # Arrange
        payload = b'{"event": "workflow.completed"}'
        secret = "my-webhook-secret"
        signature = _sign(payload, secret)

        # Act / Assert — should not raise
        verify_signature(payload, secret, signature)

    def test_invalid_signature_raises(self):
        payload = b'{"event": "workflow.completed"}'
        with pytest.raises(WebhookVerificationError, match="Signature mismatch"):
            verify_signature(payload, "my-secret", "bad-signature")

    def test_missing_signature_raises(self):
        with pytest.raises(WebhookVerificationError, match="Missing"):
            verify_signature(b"payload", "secret", None)

    def test_empty_signature_raises(self):
        with pytest.raises(WebhookVerificationError):
            verify_signature(b"payload", "secret", "")

    def test_tampered_payload_fails(self):
        # Arrange — sign original, but verify against tampered payload.
        original = b'{"event": "workflow.completed"}'
        tampered = b'{"event": "workflow.failed"}'
        secret = "my-secret"
        signature = _sign(original, secret)

        with pytest.raises(WebhookVerificationError):
            verify_signature(tampered, secret, signature)

    def test_timestamp_too_old_raises(self):
        payload = b'{"event": "test"}'
        secret = "my-secret"
        signature = _sign(payload, secret)
        old_ts = str(int(time.time()) - 400)  # 400 seconds ago.

        with pytest.raises(WebhookVerificationError, match="too old"):
            verify_signature(payload, secret, signature, max_age_seconds=300, timestamp_header=old_ts)

    def test_fresh_timestamp_passes(self):
        payload = b'{"event": "test"}'
        secret = "my-secret"
        signature = _sign(payload, secret)
        ts = str(int(time.time()))

        # Should not raise.
        verify_signature(payload, secret, signature, max_age_seconds=300, timestamp_header=ts)

    def test_invalid_timestamp_header_raises(self):
        payload = b'{"event": "test"}'
        secret = "my-secret"
        signature = _sign(payload, secret)

        with pytest.raises(WebhookVerificationError, match="Invalid timestamp"):
            verify_signature(payload, secret, signature, timestamp_header="not-a-number")
