# Model Spec — Alert Parsing and Incident Modeling

## Purpose
Convert untrusted SigNoz alert webhook JSON into a validated `Incident` object that the control loop can act on.

## Input Contract
SigNoz alert webhooks POST a JSON body with the following structure (based on SigNoz alert manager):

```json
{
  "status": "firing",
  "alertname": "RunawayToolLoop",
  "startsAt": "2026-07-19T12:00:00Z",
  "labels": {
    "agent_id": "agent-123",
    "credential_id": "cred-abc",
    "severity": "critical",
    "alert_id": "alert-456"
  },
  "annotations": {
    "summary": "Agent tool loop detected",
    "description": "Agent agent-123 called tool X 10 times in 60s"
  },
  "fingerprint": "fp-unique-123"
}
```

## Required Fields
| Field | Type | Purpose |
|-------|------|---------|
| `status` | string | Must be `"firing"` to trigger quarantine |
| `alertname` | string | Name of the alert rule |
| `startsAt` | ISO-8601 string | When the alert fired |
| `labels.agent_id` | string | Unique identifier for the agent |
| `labels.credential_id` | string | Credential to quarantine |

## Optional Fields
| Field | Type | Purpose |
|-------|------|---------|
| `labels.severity` | string | Alert severity level |
| `labels.alert_id` | string | SigNoz internal alert ID |
| `fingerprint` | string | SigNoz alert fingerprint (used for idempotency) |
| `annotations` | object | Additional context |

## Output Contract
`Incident` frozen dataclass with the following attributes:

```python
@dataclass(frozen=True, slots=True)
class Incident:
    alertname: str          # e.g., "RunawayToolLoop"
    status: str            # "firing" or "resolved"
    starts_at: datetime     # Timezone-aware UTC datetime
    agent_id: str          # e.g., "agent-123"
    credential_id: str     # e.g., "cred-abc"
    severity: str          # e.g., "critical" (default: "")
    idempotency_key: str   # Deterministic key for deduplication
    raw: dict              # Original payload (for audit)
```

## Idempotency Key Logic
1. If `fingerprint` is present in payload → use it directly
2. Otherwise → compute SHA-256 hash of stable fields:
   ```json
   {
     "status": "...",
     "alertname": "...",
     "startsAt": "...",
     "labels": {...}
   }
   ```
   (sorted keys, compact JSON)

## Validation Rules
1. `status` must be present and non-empty
2. `alertname` must be present and non-empty
3. `startsAt` must be valid ISO-8601 (with or without `Z` suffix)
4. `labels` must be a dict
5. `labels.agent_id` must be present and non-empty
6. `labels.credential_id` must be present and non-empty

## Methods
| Method | Returns | Purpose |
|--------|---------|---------|
| `needs_quarantine()` | `bool` | `True` if `status == "firing"` |

## Error Handling
- Raise `ValueError` with descriptive message for any validation failure
- Raise `json.JSONDecodeError` if body is not valid JSON
- Never silently ignore missing fields

## Example Usage
```python
from sentinel.model import parse_alert

body = b'{"status":"firing","alertname":"Test","startsAt":"2026-07-19T12:00:00Z","labels":{"agent_id":"a","credential_id":"c"}}'
incident = parse_alert(body)

assert incident.needs_quarantine() == True
assert incident.agent_id == "a"
assert incident.credential_id == "c"
```

## Files
- `src/sentinel/model.py` — Implementation
- `tests/test_model.py` — Unit tests

## Test Coverage Target
- 100% branch coverage for validation logic
- Test cases: valid firing, valid resolved, missing fields, malformed timestamp, fingerprint preference
