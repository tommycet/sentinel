# Auth Spec — Webhook Authentication and Replay Protection

## Purpose
Prevent arbitrary callers and replayed payloads from triggering quarantine actions.

## Protocol
Webhook requests to `/alerts` and `/incidents/*/release` MUST include two headers:

| Header | Format | Purpose |
|--------|--------|---------|
| `X-Sentinel-Timestamp` | Unix seconds (integer string) | Prevent replay attacks |
| `X-Sentinel-Signature` | Hex HMAC-SHA256 | Verify request integrity |

## Signed Payload
```
signed_bytes = f"{timestamp}.{body}"
```

Where:
- `timestamp` = value of `X-Sentinel-Timestamp` header (exact string)
- `body` = raw request body bytes (exact, not parsed)

## Signature Verification
```python
import hmac
import hashlib

expected = hmac.new(
    secret.encode(),
    signed_bytes.encode(),
    hashlib.sha256
).hexdigest()

if not hmac.compare_digest(expected, signature):
    raise ValueError("Invalid signature")
```

## Replay Protection
- Accept timestamps within ±300 seconds of current Unix time
- Reject timestamps outside this window
- Use `time.time()` for current time (stdlib only)

## Environment
| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `SENTINEL_WEBHOOK_SECRET` | YES | None | Shared secret for HMAC |

## Function Contract
```python
def verify_webhook(
    timestamp: str,
    signature: str,
    body: bytes,
    secret: str
) -> bool:
    """Verify webhook request authenticity and freshness.
    
    Args:
        timestamp: Value from X-Sentinel-Timestamp header
        signature: Value from X-Sentinel-Signature header (hex)
        body: Raw request body bytes
        secret: SENTINEL_WEBHOOK_SECRET value
        
    Returns:
        True if valid and fresh
        
    Raises:
        ValueError: If timestamp is malformed, expired, or signature invalid
    """
```

## Validation Steps
1. Parse `timestamp` as integer (raise if fails)
2. Check `abs(current_time - timestamp) <= 300` (raise if fails)
3. Compute expected signature from `timestamp` + `.` + `body`
4. Compare with `hmac.compare_digest(expected, signature)` (raise if fails)
5. Return `True`

## Error Messages
| Condition | Message |
|-----------|---------|
| Missing timestamp header | "Missing X-Sentinel-Timestamp header" |
| Malformed timestamp | "Invalid timestamp: {timestamp}" |
| Expired timestamp | "Timestamp too old or too far in future" |
| Missing signature header | "Missing X-Sentinel-Signature header" |
| Invalid signature | "Invalid signature" |

## Security Considerations
- Use `hmac.compare_digest` to prevent timing attacks
- Never log the secret or signature
- Redact secrets from error messages
- Validate timestamp BEFORE signature to avoid unnecessary HMAC computation

## Files
- `src/sentinel/auth.py` — Implementation
- `tests/test_auth.py` — Unit tests

## Test Coverage Target
- Valid request
- Altered body (signature mismatch)
- Wrong secret
- Stale timestamp (-301 seconds)
- Future timestamp (+301 seconds)
- Missing headers
- Malformed timestamp (non-integer)
