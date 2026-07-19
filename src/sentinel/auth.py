"""HMAC webhook authentication and replay protection for Sentinel."""
from __future__ import annotations

import hashlib
import hmac
import time

# Replay window: ±300 seconds around current server time.
MAX_TIMESTAMP_SKEW = 300


def verify_webhook(
    timestamp: str,
    signature: str,
    body: bytes,
    secret: str,
) -> bool:
    """Verify webhook request authenticity and freshness.

    Args:
        timestamp: Value from X-Sentinel-Timestamp header (Unix seconds string).
        signature: Value from X-Sentinel-Signature header (hex HMAC-SHA256).
        body: Raw request body bytes (exact, not parsed).
        secret: SENTINEL_WEBHOOK_SECRET value.

    Returns:
        True if the signature is valid and the timestamp is fresh.

    Raises:
        ValueError: If timestamp is missing, malformed, expired, or the
            signature is invalid/missing. Error messages never leak the secret.
    """
    # 1. Presence + parse timestamp BEFORE expensive HMAC (spec §Security).
    if not timestamp:
        raise ValueError("Missing X-Sentinel-Timestamp header")
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        # Use repr'd timestamp — never the secret.
        raise ValueError(f"Invalid timestamp: {timestamp!r}") from None

    # 2. Replay window check.
    if abs(time.time() - ts_int) > MAX_TIMESTAMP_SKEW:
        raise ValueError("Timestamp too old or too far in future")

    # 3. Signature presence.
    if not signature:
        raise ValueError("Missing X-Sentinel-Signature header")

    # 4. Compute expected signature: f"{timestamp}.{body}" w/ exact body bytes.
    #    timestamp used as provided (spec: exact string from header), encoded utf-8.
    signed_bytes = f"{timestamp}.".encode() + body
    expected = hmac.new(
        secret.encode(),
        signed_bytes,
        hashlib.sha256,
    ).hexdigest()

    # 5. Constant-time comparison.
    if not hmac.compare_digest(expected, signature):
        # Message deliberately generic — never log secret or signature values.
        raise ValueError("Invalid signature")

    return True
