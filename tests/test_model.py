"""Tests for sentinel.model — alert validation and incident modeling."""
import json
import unittest
from datetime import datetime, timezone

from sentinel.model import (
    Incident,
    parse_alert,
    ALERT_STATUS_FIRING,
    ALERT_STATUS_RESOLVED,
)


class TestParseAlert(unittest.TestCase):
    """Validate alert parsing and incident creation."""

    def setUp(self):
        self.maxDiff = None

    def test_valid_firing_alert(self):
        """A well-formed firing alert with required labels parses correctly."""
        payload = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "RunawayToolLoop",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {
                "agent_id": "agent-123",
                "credential_id": "cred-abc",
                "severity": "critical",
            },
            "annotations": {"summary": "Agent tool loop detected"},
        }
        body = json.dumps(payload).encode()
        incident = parse_alert(body)

        self.assertIsInstance(incident, Incident)
        self.assertEqual(incident.alertname, "RunawayToolLoop")
        self.assertEqual(incident.status, ALERT_STATUS_FIRING)
        self.assertEqual(incident.agent_id, "agent-123")
        self.assertEqual(incident.credential_id, "cred-abc")
        self.assertEqual(incident.severity, "critical")
        self.assertEqual(
            incident.starts_at, datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
        )
        self.assertIsNotNone(incident.idempotency_key)
        self.assertTrue(len(incident.idempotency_key) > 0)

    def test_missing_required_label_agent_id(self):
        """Alert missing agent_id label raises ValueError."""
        payload = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "TestAlert",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {"credential_id": "cred-abc"},
        }
        body = json.dumps(payload).encode()
        with self.assertRaises(ValueError) as ctx:
            parse_alert(body)
        self.assertIn("agent_id", str(ctx.exception))

    def test_missing_required_label_credential_id(self):
        """Alert missing credential_id label raises ValueError."""
        payload = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "TestAlert",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {"agent_id": "agent-123"},
        }
        body = json.dumps(payload).encode()
        with self.assertRaises(ValueError) as ctx:
            parse_alert(body)
        self.assertIn("credential_id", str(ctx.exception))

    def test_malformed_timestamp(self):
        """Alert with invalid startsAt raises ValueError."""
        payload = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "TestAlert",
            "startsAt": "not-a-timestamp",
            "labels": {"agent_id": "a", "credential_id": "c"},
        }
        body = json.dumps(payload).encode()
        with self.assertRaises(ValueError) as ctx:
            parse_alert(body)
        self.assertIn("startsAt", str(ctx.exception))

    def test_resolved_alert_is_noop(self):
        """Resolved alerts are parsed but flagged as no-op for quarantine."""
        payload = {
            "status": ALERT_STATUS_RESOLVED,
            "alertname": "RunawayToolLoop",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {"agent_id": "agent-123", "credential_id": "cred-abc"},
        }
        body = json.dumps(payload).encode()
        incident = parse_alert(body)

        self.assertEqual(incident.status, ALERT_STATUS_RESOLVED)
        self.assertFalse(incident.needs_quarantine())

    def test_deterministic_idempotency_key(self):
        """Same alert payload produces the same idempotency key."""
        payload = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "RunawayToolLoop",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {"agent_id": "agent-123", "credential_id": "cred-abc"},
        }
        body = json.dumps(payload).encode()
        incident1 = parse_alert(body)
        incident2 = parse_alert(body)
        self.assertEqual(incident1.idempotency_key, incident2.idempotency_key)

    def test_idempotency_key_differs_on_content(self):
        """Different alert payloads produce different idempotency keys."""
        payload1 = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "RunawayToolLoop",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {"agent_id": "agent-123", "credential_id": "cred-abc"},
        }
        payload2 = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "RunawayToolLoop",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {"agent_id": "agent-123", "credential_id": "cred-xyz"},
        }
        key1 = parse_alert(json.dumps(payload1).encode()).idempotency_key
        key2 = parse_alert(json.dumps(payload2).encode()).idempotency_key
        self.assertNotEqual(key1, key2)

    def test_fingerprint_preferred_for_idempotency(self):
        """If fingerprint is present, it is used for idempotency."""
        payload = {
            "status": ALERT_STATUS_FIRING,
            "alertname": "RunawayToolLoop",
            "startsAt": "2026-07-19T12:00:00Z",
            "labels": {"agent_id": "agent-123", "credential_id": "cred-abc"},
            "fingerprint": "fp-unique-123",
        }
        body = json.dumps(payload).encode()
        incident = parse_alert(body)
        self.assertEqual(incident.idempotency_key, "fp-unique-123")


class TestIncident(unittest.TestCase):
    """Incident dataclass behavior."""

    def test_needs_quarantine_only_firing(self):
        """Only firing incidents need quarantine."""
        firing = Incident(
            alertname="Test",
            status=ALERT_STATUS_FIRING,
            starts_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            agent_id="a",
            credential_id="c",
            idempotency_key="k",
        )
        resolved = Incident(
            alertname="Test",
            status=ALERT_STATUS_RESOLVED,
            starts_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            agent_id="a",
            credential_id="c",
            idempotency_key="k",
        )
        self.assertTrue(firing.needs_quarantine())
        self.assertFalse(resolved.needs_quarantine())

    def test_immutable_after_freeze(self):
        """Incident is frozen; attributes cannot be changed after creation."""
        incident = Incident(
            alertname="Test",
            status=ALERT_STATUS_FIRING,
            starts_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
            agent_id="a",
            credential_id="c",
            idempotency_key="k",
        )
        with self.assertRaises(AttributeError):
            incident.alertname = "Modified"


if __name__ == "__main__":
    unittest.main()
