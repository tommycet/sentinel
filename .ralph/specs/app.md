# App Spec — HTTP Service

## Purpose
Expose Sentinel's control loop as an HTTP service that receives SigNoz webhooks.

## Server
- **Module:** `http.server.ThreadingHTTPServer` (stdlib)
- **Port:** `SENTINEL_PORT` (default: 8090)
- **Concurrency:** Thread-per-request (ThreadingHTTPServer)
- **Timeout:** No server-level timeout (delegated to deployment layer)

## Endpoints

### GET /livez
**Purpose:** Health check

**Response:**
- Status: 200 OK
- Body: `{"status":"ok","version":"0.1.0"}`
- Headers: `Content-Type: application/json`

**No authentication required** (health checks should be public)

### POST /alerts
**Purpose:** Receive SigNoz alert webhooks

**Request:**
- Method: POST
- Headers:
  - `Content-Type: application/json` (required)
  - `X-Sentinel-Timestamp: <unix_seconds>` (required)
  - `X-Sentinel-Signature: <hex_hmac_sha256>` (required)
- Body: JSON alert payload (see model.md)
- Max Size: 64 KiB (reject with 413 if exceeded)

**Response:**
- Status: 200 OK (success), 400 Bad Request (validation error), 401 Unauthorized (auth failure), 413 Payload Too Large
- Body: JSON object with keys:
  - `status`: `"success"` | `"duplicate"` | `"error"`
  - `incident_id`: int | null (database ID)
  - `action`: `"quarantined"` | `"ignored"` | `"dry_run"` | null
  - `message`: str (human-readable result)
  - `error`: str | null (error details, no secrets)

**Processing Flow:**
```
1. Check Content-Length <= 65536 (64 KiB)
2. Read body
3. Verify webhook (auth.verify_webhook)
4. Parse alert (model.parse_alert)
5. Check allowlist (if SENTINEL_ALLOWED_CREDENTIALS is set)
6. Claim incident (store.claim)
7. If duplicate: return {"status": "duplicate", ...}
8. If resolved: return {"status": "ignored", ...}
9. Evaluate policy (future: from policies/*.yaml)
10. Quarantine (revoker.quarantine)
11. Export telemetry (telemetry.export_span)
12. Return result
```

### POST /incidents/<id>/release
**Purpose:** Manually release a quarantined agent

**Request:**
- Method: POST
- Headers:
  - `X-Sentinel-Timestamp: <unix_seconds>` (required)
  - `X-Sentinel-Signature: <hex_hmac_sha256>` (required)
- URL Param: `id` = incident database ID

**Response:**
- Status: 200 OK (success), 400 Bad Request, 401 Unauthorized, 404 Not Found
- Body: JSON object with keys:
  - `status`: `"success"` | `"error"`
  - `action`: `"released"` | null
  - `message`: str

**Processing Flow:**
```
1. Verify webhook
2. Get incident by ID (store.get)
3. If not found: 404
4. If not quarantined: 400 ("Incident not quarantined")
5. Release (revoker.release)
6. Update store (store.release)
7. Export telemetry
8. Return result
```

## Request Handler Structure
```python
class AlertHandler:
    """Handle POST /alerts requests."""
    
    def __init__(self, store: IncidentStore, revoker: Revoker, secret: str):
        self.store = store
        self.revoker = revoker
        self.secret = secret
        
    def handle(self, headers: dict, body: bytes) -> tuple[int, dict]:
        """Process request and return (status_code, response_dict)."""

class ReleaseHandler:
    """Handle POST /incidents/<id>/release requests."""
    
    def __init__(self, store: IncidentStore, revoker: Revoker, secret: str):
        ...
        
    def handle(self, incident_id: str, headers: dict) -> tuple[int, dict]:
        ...
```

## Main Function
```python
def main():
    """Start the Sentinel HTTP service."""
    import argparse
    import os
    from sentinel.store import IncidentStore
    from sentinel.revoker import get_revoker
    from sentinel.auth import verify_webhook
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("SENTINEL_PORT", 8090)))
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()
    
    # Initialize components
    store = IncidentStore(os.getenv("SENTINEL_DB_PATH", "sentinel.db"))
    revoker = get_revoker()
    secret = os.getenv("SENTINEL_WEBHOOK_SECRET")
    if not secret:
        raise ValueError("SENTINEL_WEBHOOK_SECRET is required")
    
    # Start server
    server = ThreadingHTTPServer(("0.0.0.0", args.port), RequestHandler)
    print(f"Sentinel listening on port {args.port}")
    server.serve_forever()
```

## Environment Variables
| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SENTINEL_PORT` | NO | 8090 | HTTP server port |
| `SENTINEL_WEBHOOK_SECRET` | YES | None | HMAC shared secret |
| `SENTINEL_DB_PATH` | NO | `sentinel.db` | SQLite database path |
| `SENTINEL_DRY_RUN` | NO | `true` | Dry-run mode (override with `--dry-run=false`) |
| `SENTINEL_ALLOWED_CREDENTIALS` | NO | `""` | Comma-separated allowlist |

## Logging
- Structured JSON logs to stderr
- Log level: INFO by default
- Never log: secrets, full credential IDs, request bodies (except in debug mode)
- Always log: incident ID, action type, success/failure

## Files
- `src/sentinel/app.py` — Implementation
- `tests/test_app.py` — Unit tests (use `http.client` or `urllib`)

## Test Coverage Target
- Health endpoint returns 200
- Valid alert → quarantine (dry-run)
- Forged alert → 401
- Malformed JSON → 400
- Oversized body → 413
- Missing headers → 401
- Duplicate alert → 200 with status="duplicate"
- Resolved alert → 200 with status="ignored"
- Release endpoint → 200 with status="success"
- Release non-existent → 404
- Release non-quarantined → 400
