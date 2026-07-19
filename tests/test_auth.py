"""Tests for sentinel.auth — HMAC webhook authentication and replay protection."""
import hmac
import hashlib
import time
import unittest
from unittest.mock import patch

from sentinel.auth import verify_webhook


SECRET = "test-secret-key-abc123"
BODY = b'{"status":"firing","alertname":"Test"}'


def _sign(timestamp: str, body: bytes, secret: str) -> str:
    """Helper: compute valid HMAC signature for test fixtures."""
    msg = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _ts(offset: int = 0) -> str:
    """Helper: return a timestamp string offset from current time."""
    return str(int(time.time() + offset))


class TestVerifyWebhook(unittest.TestCase):
    """Webhook signature verification and replay protection."""

    def test_valid_request(self):
        """A request with correct signature and fresh timestamp passes."""
        ts = _ts()
        sig = _sign(ts, BODY, SECRET)
        self.assertTrue(verify_webhook(ts, sig, BODY, SECRET))

    def test_altered_body_fails(self):
        """Tampered body produces signature mismatch."""
        ts = _ts()
        sig = _sign(ts, BODY, SECRET)
        tampered = b'{"status":"resolved","alertname":"Test"}'
        with self.assertRaises(ValueError) as ctx:
            verify_webhook(ts, sig, tampered, SECRET)
        self.assertIn("Invalid signature", str(ctx.exception))

    def test_wrong_secret_fails(self):
        """Signature made with a different secret is rejected."""
        ts = _ts()
        sig = _sign(ts, BODY, "wrong-secret")
        with self.assertRaises(ValueError) as ctx:
            verify_webhook(ts, sig, BODY, SECRET)
        self.assertIn("Invalid signature", str(ctx.exception))

    def test_stale_timestamp_rejected(self):
        """Timestamp 301 seconds in the past is rejected."""
        ts = _ts(-301)
        sig = _sign(ts, BODY, SECRET)
        with self.assertRaises(ValueError) as ctx:
            verify_webhook(ts, sig, BODY, SECRET)
        self.assertIn("Timestamp", str(ctx.exception))

    def test_future_timestamp_rejected(self):
        """Timestamp 301 seconds in the future is rejected."""
        ts = _ts(301)
        sig = _sign(ts, BODY, SECRET)
        with self.assertRaises(ValueError) as ctx:
            verify_webhook(ts, sig, BODY, SECRET)
        self.assertIn("Timestamp", str(ctx.exception))

    def test_boundary_timestamp_accepted(self):
        """Timestamp exactly at ±300 seconds boundary is accepted."""
        now = 1_700_000_000
        ts_minus = str(now - 300)
        sig_minus = _sign(ts_minus, BODY, SECRET)
        with patch("sentinel.auth.time.time", return_value=now):
            self.assertTrue(verify_webhook(ts_minus, sig_minus, BODY, SECRET))

        ts_plus = str(now + 300)
        sig_plus = _sign(ts_plus, BODY, SECRET)
        with patch("sentinel.auth.time.time", return_value=now):
            self.assertTrue(verify_webhook(ts_plus, sig_plus, BODY, SECRET))

    def test_malformed_timestamp_rejected(self):
        """Non-integer timestamp raises ValueError."""
        ts = "not-a-number"
        sig = _sign(ts, BODY, SECRET)
        with self.assertRaises(ValueError) as ctx:
            verify_webhook(ts, sig, BODY, SECRET)
        self.assertIn("Invalid timestamp", str(ctx.exception))

    def test_empty_timestamp_rejected(self):
        """Empty string timestamp raises ValueError."""
        sig = _sign("", BODY, SECRET)
        with self.assertRaises(ValueError):
            verify_webhook("", sig, BODY, SECRET)

    def test_empty_signature_rejected(self):
        """Empty string signature is rejected."""
        ts = _ts()
        with self.assertRaises(ValueError) as ctx:
            verify_webhook(ts, "", BODY, SECRET)
        self.assertIn("Missing X-Sentinel-Signature header", str(ctx.exception))

    def test_secret_not_in_error_messages(self):
        """Error messages must never leak the secret value."""
        ts = _ts()
        sig = _sign(ts, BODY, "wrong-secret")
        try:
            verify_webhook(ts, sig, BODY, SECRET)
        except ValueError as e:
            self.assertNotIn(SECRET, str(e))
            self.assertNotIn("wrong-secret", str(e))


if __name__ == "__main__":
    unittest.main()
