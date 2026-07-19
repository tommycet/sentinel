# Telemetry Spec — OTLP/HTTP Export

## Purpose
Make Sentinel's control loop observable by exporting telemetry back to SigNoz via OTLP/HTTP.

## Protocol
- **Format:** OTLP/HTTP JSON
- **Endpoint:** `SENTINEL_OTEL_ENDPOINT` (default: `http://localhost:4317`)
- **Transport:** stdlib `urllib.request` with JSON payload
- **Timeout:** 5 seconds (non-blocking; failure doesn't block quarantine)

## Span Definitions

### sentinel.alert.received
**Purpose:** Track when an alert webhook is received

**Attributes:**
```python
{
    "sentinel.alert.name": incident.alertname,
    "sentinel.alert.status": incident.status,
    "sentinel.incident.id": incident.idempotency_key,
    "agent.id": incident.agent_id,
    "credential.id_hash": hashlib.sha256(incident.credential_id.encode()).hexdigest(),
    "sentinel.dry_run": str(dry_run_mode).lower(),
}
```

### sentinel.policy.evaluated
**Purpose:** Track policy evaluation result

**Attributes:**
```python
{
    "sentinel.incident.id": incident.idempotency_key,
    "sentinel.policy.name": "runaway-tool-loop",  # From policy file
    "sentinel.policy.result": "quarantine" | "ignore",
    "sentinel.policy.threshold": 8,  # From policy config
    "sentinel.policy.window_seconds": 60,
}
```

### sentinel.agent.quarantined
**Purpose:** Track successful quarantine action

**Attributes:**
```python
{
    "sentinel.incident.id": incident.idempotency_key,
    "agent.id": incident.agent_id,
    "credential.id_hash": hashlib.sha256(incident.credential_id.encode()).hexdigest(),
    "sentinel.action": "quarantine",
    "sentinel.dry_run": str(dry_run_mode).lower(),
    "sentinel.latency_ms": int((time.time() - start_time) * 1000),
}
```

### sentinel.agent.released
**Purpose:** Track successful release action

**Attributes:**
```python
{
    "sentinel.incident.id": incident.idempotency_key,
    "agent.id": incident.agent_id,
    "credential.id_hash": hashlib.sha256(incident.credential_id.encode()).hexdigest(),
    "sentinel.action": "release",
    "sentinel.latency_ms": int((time.time() - start_time) * 1000),
}
```

## Payload Structure (OTLP/HTTP JSON)

### Trace Export Request
```json
{
  "resourceSpans": [
    {
      "resource": {
        "attributes": [
          {"key": "service.name", "value": {"stringValue": "sentinel"}},
          {"key": "service.version", "value": {"stringValue": "0.1.0"}}
        ]
      },
      "scopeSpans": [
        {
          "spans": [
            {
              "traceId": "<random_hex_32>",
              "spanId": "<random_hex_16>",
              "parentSpanId": "",
              "name": "sentinel.alert.received",
              "startTimeUnixNano": <start_time_ns>,
              "endTimeUnixNano": <end_time_ns>,
              "attributes": [
                {"key": "sentinel.alert.name", "value": {"stringValue": "RunawayToolLoop"}},
                {"key": "agent.id", "value": {"stringValue": "agent-123"}}
              ],
              "status": {"code": 1}  // OK
            }
          ]
        }
      ]
    }
  ]
}
```

## Function Contract
```python
def export_span(
    name: str,
    attributes: dict[str, Any],
    start_time: float,
    end_time: float | None = None,
    status_code: int = 1,  # 1=OK, 2=ERROR
) -> bool:
    """Export a single span to OTLP/HTTP endpoint.
    
    Args:
        name: Span name (e.g., 'sentinel.alert.received')
        attributes: Dict of attribute key->value (values will be converted)
        start_time: Unix timestamp in seconds (float)
        end_time: Unix timestamp in seconds, or None for now
        status_code: OTLP status code (1=OK, 2=ERROR)
        
    Returns:
        True if export succeeded, False otherwise
        
    Note:
        Failure to export does NOT raise exceptions and does NOT block
        the control loop. Errors are logged but not propagated.
    """
```

## Attribute Value Conversion
| Python Type | OTLP Value |
|-------------|------------|
| `str` | `{"stringValue": value}` |
| `int` | `{"intValue": value}` |
| `float` | `{"doubleValue": value}` |
| `bool` | `{"boolValue": value}` |
| `None` | Omitted |

## Environment
| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SENTINEL_OTEL_ENDPOINT` | NO | `http://localhost:4317` | OTLP/HTTP endpoint |
| `SENTINEL_OTEL_TIMEOUT` | NO | 5 | Export timeout in seconds |

## Failure Handling
- Network errors → log warning, return `False`
- HTTP errors → log warning with status, return `False`
- JSON serialization errors → log error, return `False`
- **Never** block the control loop
- **Never** raise exceptions

## Files
- `src/sentinel/telemetry.py` — Implementation
- `tests/test_telemetry.py` — Unit tests

## Test Coverage Target
- Valid span export (mock HTTP server)
- Attribute value conversion for all types
- Credential ID hashing (never raw in attributes)
- Export failure doesn't raise exceptions
- Export failure doesn't block control loop
