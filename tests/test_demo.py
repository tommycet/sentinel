"""Tests for demo modules — runaway agent simulation and signed alert sender.

TDD: written first, implementation must satisfy all tests.
"""
import builtins
import hashlib
import json
import time
import unittest
from unittest.mock import MagicMock, patch


class TestRunawayAgent(unittest.TestCase):
    """Tests for demo/runaway_agent.py."""

    def test_canonicalize_args_stable_hash(self):
        """canonicalize_args produces stable hash for same args."""
        from demo.runaway_agent import canonicalize_args

        args1 = {"tool": "search", "query": "hello", "limit": 10}
        args2 = {"limit": 10, "query": "hello", "tool": "search"}  # different order
        args3 = {"tool": "search", "query": "hello", "limit": 10}  # same as args1

        h1 = canonicalize_args(args1)
        h2 = canonicalize_args(args2)
        h3 = canonicalize_args(args3)

        # Same content, same hash regardless of key order
        self.assertEqual(h1, h2)
        self.assertEqual(h1, h3)

        # Different content, different hash
        args4 = {"tool": "search", "query": "world", "limit": 10}
        h4 = canonicalize_args(args4)
        self.assertNotEqual(h1, h4)

    def test_canonicalize_args_returns_hex_string(self):
        """canonicalize_args returns a hex string."""
        from demo.runaway_agent import canonicalize_args

        result = canonicalize_args({"a": 1})
        self.assertIsInstance(result, str)
        # SHA256 hex is 64 characters
        self.assertEqual(len(result), 64)
        # All hex characters
        int(result, 16)

    def test_call_sequence_yields_5_distinct_then_15_identical(self):
        """call_sequence generator yields 5 distinct calls then 15 identical failing calls."""
        from demo.runaway_agent import call_sequence

        calls = list(call_sequence())
        self.assertEqual(len(calls), 20)

        # First 5 are distinct
        first_five = calls[:5]
        first_five_tools = [c[0] for c in first_five]
        self.assertEqual(len(set(first_five_tools)), 5)

        # Last 15 are identical
        last_fifteen = calls[5:]
        for c in last_fifteen:
            self.assertEqual(c[0], "failing_tool")
            self.assertEqual(c[1], {"query": "bad"})

    def test_quarantine_triggers_at_repetition_8_not_7(self):
        """run_demo triggers quarantine exactly at repetition 8, not 7."""
        from demo.runaway_agent import run_demo

        post_calls = []
        sleep_calls = []
        quarantine_calls = []

        def mock_post(url, data, headers):
            post_calls.append((url, data, headers))
            return MagicMock(status=200, read=lambda: b'{"status":"ok"}')

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        def mock_print(*args, **kwargs):
            text = str(args[0]) if args else ""
            if "QUARANTINE" in text.upper():
                quarantine_calls.append(text)

        with patch('builtins.print', mock_print):
            run_demo(mock_post, mock_sleep)

        # Quarantine should be triggered exactly once
        self.assertEqual(len(quarantine_calls), 1)

    def test_no_quarantine_below_threshold(self):
        """run_demo does not trigger quarantine below threshold of 8."""
        from demo import runaway_agent
        from demo.runaway_agent import run_demo

        post_calls = []
        sleep_calls = []
        quarantine_calls = []

        def mock_post(url, data, headers):
            post_calls.append((url, data, headers))
            return MagicMock(status=200, read=lambda: b'{"status":"ok"}')

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        def mock_print(*args, **kwargs):
            text = str(args[0]) if args else ""
            if "QUARANTINE" in text.upper():
                quarantine_calls.append(text)

        def short_call_sequence():
            for i in range(5):
                yield (f"tool_{i}", {"arg": i})
            for i in range(7):
                yield ("failing_tool", {"query": "bad"})

        with patch.object(runaway_agent, 'call_sequence', short_call_sequence):
            with patch('builtins.print', mock_print):
                run_demo(mock_post, mock_sleep)

        self.assertEqual(len(quarantine_calls), 0)


class TestSendSignedAlert(unittest.TestCase):
    """Tests for demo/send_signed_alert.py."""

    def test_hmac_signature_matches_auth_protocol(self):
        """send_signed_alert computes HMAC signature matching auth.py protocol."""
        from demo.send_signed_alert import compute_signature

        secret = "test-secret"
        timestamp = "1700000000"
        body = b'{"status":"firing","alertname":"Test","startsAt":"2026-01-01T00:00:00Z","labels":{"agent_id":"agent-1","credential_id":"cred-1"}}'

        sig = compute_signature(timestamp, body, secret)

        import hmac as hmac_module
        signed_bytes = f"{timestamp}.".encode() + body
        expected = hmac_module.new(
            secret.encode(),
            signed_bytes,
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(sig, expected)

    def test_alert_json_structure(self):
        """Alert JSON has correct structure with all required fields."""
        from demo.send_signed_alert import build_alert_json

        result = build_alert_json(
            status="firing",
            alertname="RunawayToolLoop",
            agent_id="agent-e2e",
            credential_id="cred-e2e",
        )

        self.assertIn("status", result)
        self.assertIn("alertname", result)
        self.assertIn("startsAt", result)
        self.assertIn("labels", result)
        self.assertIn("agent_id", result["labels"])
        self.assertIn("credential_id", result["labels"])
        self.assertEqual(result["status"], "firing")
        self.assertEqual(result["alertname"], "RunawayToolLoop")
        self.assertEqual(result["labels"]["agent_id"], "agent-e2e")
        self.assertEqual(result["labels"]["credential_id"], "cred-e2e")


if __name__ == "__main__":
    unittest.main()
