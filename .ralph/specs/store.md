# Store Spec — Idempotent Quarantine State

## Purpose
Guarantee at-most-once quarantine action per incident, with full audit trail.

## Database
- **Engine:** SQLite (stdlib `sqlite3`)
- **Path:** `SENTINEL_DB_PATH` (default: `sentinel.db`)
- **WAL Mode:** Enabled for concurrent access (`PRAGMA journal_mode=WAL`)
- **Foreign Keys:** Enabled (`PRAGMA foreign_keys=ON`)

## Schema

### Table: incidents
```sql
CREATE TABLE incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE NOT NULL,
    alertname TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'firing' or 'resolved'
    agent_id TEXT NOT NULL,
    credential_id TEXT NOT NULL,
    severity TEXT DEFAULT '',
    starts_at TEXT NOT NULL,  -- ISO-8601
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_incidents_key ON incidents(idempotency_key);
CREATE INDEX idx_incidents_credential ON incidents(credential_id);
CREATE INDEX idx_incidents_status ON incidents(status);
```

### Table: actions
```sql
CREATE TABLE actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,  -- 'quarantine' or 'release'
    status TEXT NOT NULL,        -- 'pending', 'success', 'failed'
    error_message TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',  -- JSON object
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

CREATE INDEX idx_actions_incident ON actions(incident_id);
CREATE INDEX idx_actions_status ON actions(status);
```

## Incident Statuses
| Status | Meaning |
|--------|---------|
| `received` | Alert received, not yet processed |
| `quarantined` | Quarantine action succeeded |
| `failed` | Quarantine action failed |
| `released` | Manually released |

## Action Statuses
| Status | Meaning |
|--------|---------|
| `pending` | Action not yet attempted |
| `success` | Action completed successfully |
| `failed` | Action failed |

## Class Contract
```python
class IncidentStore:
    """Thread-safe SQLite store for incident and action tracking."""
    
    def __init__(self, db_path: str = "sentinel.db"):
        """Initialize store with database path."""
        
    def claim(self, incident: Incident) -> tuple[Incident, bool]:
        """Claim an incident for processing.
        
        Args:
            incident: Validated Incident object
            
        Returns:
            (incident, is_new) where is_new=True if this is the first claim
            
        Raises:
            sqlite3.IntegrityError: If idempotency_key already exists (should never happen due to UNIQUE)
        """
        
    def get(self, incident_id: int) -> Incident | None:
        """Get incident by database ID."""
        
    def get_by_key(self, idempotency_key: str) -> Incident | None:
        """Get incident by idempotency key."""
        
    def release(self, incident_id: int) -> bool:
        """Release a quarantined incident.
        
        Returns:
            True if incident was quarantined and now released
            False if incident was not in quarantined state
        """
        
    def list_quarantined(self) -> list[Incident]:
        """List all currently quarantined incidents."""
        
    def close(self):
        """Close database connection."""
```

## Transaction Semantics
- `claim()`: BEGIN → INSERT incidents → INSERT actions (pending) → COMMIT
- `release()`: BEGIN → UPDATE incidents.status → INSERT actions (success) → COMMIT
- All writes use transactions to ensure atomicity

## Thread Safety
- Use `threading.Lock` for connection management
- SQLite WAL mode supports concurrent reads + single writer
- No connection sharing across threads

## Idempotency Guarantee
```python
# In the control loop:
incident, is_new = store.claim(incident)
if not is_new:
    # Duplicate alert - skip quarantine
    return {"status": "duplicate", "incident_id": incident.id}
```

## Files
- `src/sentinel/store.py` — Implementation
- `tests/test_store.py` — Unit tests

## Test Coverage Target
- First claim succeeds
- Duplicate claim fails (returns existing incident, is_new=False)
- Status transitions persist across restarts
- Concurrent duplicate claims yield one winner
- Audit rows are immutable (no updates to actions after creation)
- Foreign key constraints work
