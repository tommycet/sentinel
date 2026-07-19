"""Signed alert sender helper — POST HMAC-signed alerts to Sentinel.

Used by demo scripts and E2E tests to send realistic SigNoz alert webhooks
to the Sentinel webhook endpoint at /alerts.

Usage:
    python3 -c "from demo.send_signed_alert import build_alert_json, compute_signature; print(build_alert_json('firing', 'Test', 'agent-1', 'cred-1'))"
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time


def compute_signature(timestamp: str, body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 hex digest matching the Sentinel auth protocol.

    The signed payload is: <timestamp>. + <raw request body>.
    """
    signed_bytes = f"{timestamp}.".encode() + body
    return hmac.new(
        secret.encode(),
        signed_bytes,
        hashlib.sha256,
    ).hexdigest()


def build_alert_json(
    status: str = "firing",
    alertname: str = "RunawayToolLoop",
    agent_id: str = "agent-1",
    credential_id: str = "cred-1",
) -> dict:
    """Build a SigNoz-style alert webhook payload dict.

    Fields match the subset parsed by sentinel.model.parse_alert:
        - status
        - alertname / labels.alertname
        - labels.agent_id
        - labels.credential_id
        - startsAt (ISO-8601 UTC)
    """
    return {
        "status": status,
        "alertname": alertname,
        "startsAt": "2026-01-01T00:00:00Z",
        "labels": {
            "alertname": alertname,
            "agent_id": agent_id,
            "credential_id": credential_id,
        },
    }


def send_alert(
    url: str,
    secret: str,
    *,
    status: str = "firing",
    alertname: str = "RunawayToolLoop",
    agent_id: str = "agent-1",
    credential_id: str = "cred-1",
) -> tuple[int, dict]:
    """POST a signed alert to a Sentinel webhook endpoint.

    Returns (status_code, response_json_dict).
    """
    import http.client
    from urllib.parse import urlsplit

    body_dict = build_alert_json(
        status=status,
        alertname=alertname,
        agent_id=agent_id,
        credential_id=credential_id,
    )
    body = json.dumps(body_dict).encode()
    timestamp = str(int(time.time()))
    signature = compute_signature(timestamp, body, secret)

    parsed = urlsplit(url)
    if parsed.scheme == "https":
        conn_cls = http.client.HTTPSConnection
    else:
        conn_cls = http.client.HTTPConnection
    conn = conn_cls(parsed.hostname or "localhost", parsed.port or 80)
    path = parsed.path or "/"
    conn.request(
        "POST",
        path,
        body=body,
        headers={
            "Content-Type": "application/json",
            "X-Sentinel-Timestamp": timestamp,
            "X-Sentinel-Signature": signature,
        },
    )
    resp = conn.getresponse()
    resp_body = resp.read()
    conn.close()
    return resp.status, json.loads(resp_body)


if __name__ == "__main__":
    import sys

    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090/alerts"
    secret = sys.argv[2] if len(sys.argv) > 2 else "dev-secret"
    code, body = send_alert(url, secret)
    print(f"Status: {code}")
    print(json.dumps(body, indent=2))
