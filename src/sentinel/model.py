"""Alert validation and incident modeling for Sentinel."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# SigNoz alert status constants
ALERT_STATUS_FIRING = "firing"
ALERT_STATUS_RESOLVED = "resolved"

# Required label keys
REQUIRED_LABELS = frozenset({"agent_id", "credential_id"})


@dataclass(frozen=True, slots=True)
class Incident:
    """Validated SigNoz alert turned into an actionable incident.

    `id` and `store_status` are set by the IncidentStore when hydrating from DB;
    freshly parsed incidents have id=0 and store_status="".
    """

    alertname: str
    status: str
    starts_at: datetime
    agent_id: str
    credential_id: str
    severity: str = ""
    idempotency_key: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    id: int = 0
    store_status: str = ""

    def needs_quarantine(self) -> bool:
        """Return True if this incident should trigger quarantine."""
        return self.status == ALERT_STATUS_FIRING


def _normalize_timestamp(ts: str) -> datetime:
    """Parse ISO-8601 timestamp and return a timezone-aware datetime."""
    # Handle Z suffix
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        raise ValueError(f"Invalid startsAt timestamp: {ts!r}") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _compute_idempotency_key(payload: dict[str, Any]) -> str:
    """Derive a deterministic idempotency key from alert payload."""
    labels = payload.get("labels", {}) or {}
    agent_id = labels.get("agent_id", "")
    credential_id = labels.get("credential_id", "")
    # Prefer explicit fingerprint, but combine with agent_id+credential_id
    # so two alerts with the same fingerprint but different agents are NOT
    # collapsed (F12).
    if "fingerprint" in payload:
        raw = f"{payload['fingerprint']}|{agent_id}|{credential_id}"
        return hashlib.sha256(raw.encode()).hexdigest()
    # Fallback: stable subset of fields
    stable = {
        "status": payload.get("status"),
        "alertname": payload.get("alertname"),
        "startsAt": payload.get("startsAt"),
        "labels": labels,
    }
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def parse_alert(body: bytes) -> Incident:
    """Parse and validate a SigNoz alert webhook body into an Incident.

    Args:
        body: Raw JSON bytes from the webhook POST body.

    Returns:
        Validated Incident.

    Raises:
        ValueError: If required fields are missing or malformed.
        json.JSONDecodeError: If body is not valid JSON.
    """
    payload = json.loads(body)

    # Required top-level fields
    status = payload.get("status")
    if not status:
        raise ValueError("Missing required field: status")

    alertname = payload.get("alertname")
    if not alertname:
        raise ValueError("Missing required field: alertname")

    starts_at_str = payload.get("startsAt")
    if not starts_at_str:
        raise ValueError("Missing required field: startsAt")
    starts_at = _normalize_timestamp(starts_at_str)

    # Required labels
    labels = payload.get("labels", {})
    if not isinstance(labels, dict):
        raise ValueError("labels must be a JSON object")

    for label_key in REQUIRED_LABELS:
        if label_key not in labels:
            raise ValueError(f"Missing required label: {label_key}")

    agent_id = str(labels["agent_id"])
    credential_id = str(labels["credential_id"])
    severity = str(labels.get("severity", ""))

    idempotency_key = _compute_idempotency_key(payload)

    return Incident(
        alertname=alertname,
        status=status,
        starts_at=starts_at,
        agent_id=agent_id,
        credential_id=credential_id,
        severity=severity,
        idempotency_key=idempotency_key,
        raw=payload,
    )
