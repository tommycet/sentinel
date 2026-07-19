"""Best-effort OTLP/HTTP JSON span export for Sentinel."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
import urllib.request
from typing import Any

_LOG = logging.getLogger(__name__)
_DEFAULT_ENDPOINT = "http://localhost:4317"
_DEFAULT_TIMEOUT = 5.0


def _attribute_value(value: Any) -> dict[str, Any]:
    """Convert a supported Python scalar to an OTLP JSON AnyValue."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, int):
        return {"intValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    raise TypeError(f"unsupported OTLP attribute type: {type(value).__name__}")


def _build_payload(
    name: str,
    attributes: dict[str, Any],
    start_time: float,
    end_time: float,
    status_code: int,
) -> dict[str, Any]:
    """Build one OTLP trace export request without retaining raw credentials."""
    safe_attributes = dict(attributes)
    credential_id = safe_attributes.pop("credential.id", None)
    if credential_id is not None:
        safe_attributes["credential.id_hash"] = hashlib.sha256(
            str(credential_id).encode()
        ).hexdigest()

    span_attributes = [
        {"key": key, "value": _attribute_value(value)}
        for key, value in safe_attributes.items()
        if value is not None
    ]
    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                {"key": "service.name", "value": {"stringValue": "sentinel"}},
                {"key": "service.version", "value": {"stringValue": "0.1.0"}},
            ]},
            "scopeSpans": [{"spans": [{
                "traceId": secrets.token_hex(16),
                "spanId": secrets.token_hex(8),
                "parentSpanId": "",
                "name": name,
                "startTimeUnixNano": int(start_time * 1_000_000_000),
                "endTimeUnixNano": int(end_time * 1_000_000_000),
                "attributes": span_attributes,
                "status": {"code": status_code},
            }]}],
        }]
    }


def _send(payload: bytes) -> bool:
    """POST a serialized trace request to the configured OTLP endpoint."""
    endpoint = os.getenv("SENTINEL_OTEL_ENDPOINT", _DEFAULT_ENDPOINT).rstrip("/")
    if not endpoint.endswith("/v1/traces"):
        endpoint += "/v1/traces"
    timeout = float(os.getenv("SENTINEL_OTEL_TIMEOUT", str(_DEFAULT_TIMEOUT)))
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return 200 <= response.status < 300


def export_span(
    name: str,
    attributes: dict[str, Any],
    start_time: float,
    end_time: float | None = None,
    status_code: int = 1,
) -> bool:
    """Export one span; return False instead of disrupting Sentinel on failure."""
    try:
        payload = _build_payload(
            name, attributes, start_time,
            time.time() if end_time is None else end_time,
            status_code,
        )
        return _send(json.dumps(payload).encode())
    except Exception as exc:
        _LOG.warning("OTLP span export failed: %s", exc)
        return False
