# Revoker Spec — Reversible Credential Revocation

## Purpose
Separate the control loop from the actual credential revocation mechanism, allowing:
- Dry-run mode (default for hackathon safety)
- Pluggable revocation backends (HTTP API, local broker, etc.)
- Easy testing with mock implementations

## Interface
```python
from abc import ABC, abstractmethod
from typing import Any

class Revoker(ABC):
    """Abstract base class for credential revocation adapters."""
    
    @abstractmethod
    def quarantine(self, credential_id: str, **kwargs: Any) -> dict:
        """Quarantine a credential.
        
        Args:
            credential_id: The credential to quarantine
            **kwargs: Additional context (e.g., incident_id, reason)
            
        Returns:
            dict with keys:
            - 'success': bool
            - 'action': str (e.g., 'quarantined', 'dry_run')
            - 'credential_id': str
            - 'message': str (human-readable result)
            - 'details': dict (implementation-specific)
        """
        
    @abstractmethod
    def release(self, credential_id: str, **kwargs: Any) -> dict:
        """Release a quarantined credential.
        
        Returns:
            dict with same structure as quarantine()
        """
```

## Implementations

### DryRunRevoker
**Purpose:** Safe default that logs but never actually revokes.

**Configuration:** None (always available)

**Behavior:**
- `quarantine()`: Logs intended action, returns `{'success': True, 'action': 'dry_run', ...}`
- `release()`: Logs intended action, returns `{'success': True, 'action': 'dry_run_release', ...}`

**Use Case:** Hackathon default, development, testing

### HttpRevoker
**Purpose:** Call an external HTTP API to revoke credentials.

**Configuration:**
| Environment Variable | Required | Default | Purpose |
|---------------------|----------|---------|---------|
| `SENTINEL_REVOKE_URL` | YES | None | API endpoint URL |
| `SENTINEL_REVOKE_TOKEN` | NO | None | Bearer token for auth |
| `SENTINEL_REVOKE_TIMEOUT` | NO | 10 | Request timeout in seconds |

**Request Format:**
```
POST {SENTINEL_REVOKE_URL}
Authorization: Bearer {SENTINEL_REVOKE_TOKEN}
Content-Type: application/json

{
  "action": "quarantine",
  "credential_id": "{credential_id}",
  "reason": "Runaway agent detected",
  "incident_id": "{incident_id}"
}
```

**Response Handling:**
- 2xx status → success
- 4xx/5xx status → failure with error message from response
- Timeout → failure with timeout message
- Connection error → failure with connection error message

**Behavior:**
- `quarantine()`: POST to revoke URL with action="quarantine"
- `release()`: POST to revoke URL with action="release"

**Use Case:** Production when SigNoz supports key revocation API

## Factory Function
```python
def get_revoker() -> Revoker:
    """Get the appropriate revoker based on configuration.
    
    Priority:
    1. If SENTINEL_REVOKE_URL is set → HttpRevoker
    2. Otherwise → DryRunRevoker
    
    This ensures dry-run is always the safe default.
    """
```

## Error Handling
- Never raise exceptions from `quarantine()` or `release()`
- Always return a dict with `success=False` and `message` on failure
- Never include secrets in error messages or return values
- Log errors internally but don't expose sensitive details

## Files
- `src/sentinel/revoker.py` — Implementation
- `tests/test_revoker.py` — Unit tests

## Test Coverage Target
- DryRunRevoker: quarantine, release
- HttpRevoker: successful HTTP call, 4xx response, 5xx response, timeout, connection error
- Factory: returns DryRunRevoker when no URL, returns HttpRevoker when URL set
- No secret leakage in any error message or return value
