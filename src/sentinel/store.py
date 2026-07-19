"""Idempotent, thread-safe SQLite quarantine store for Sentinel."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime

from .model import Incident

STATUS_RECEIVED = "received"
STATUS_QUARANTINED = "quarantined"
STATUS_RELEASING = "releasing"
STATUS_FAILED = "failed"
STATUS_RELEASED = "released"
VALID_STATUSES = frozenset(
    {STATUS_RECEIVED, STATUS_QUARANTINED, STATUS_RELEASING, STATUS_FAILED, STATUS_RELEASED}
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT UNIQUE NOT NULL,
    alertname TEXT NOT NULL,
    status TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    credential_id TEXT NOT NULL,
    severity TEXT DEFAULT '',
    starts_at TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_incidents_key ON incidents(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_incidents_credential ON incidents(credential_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);
CREATE INDEX IF NOT EXISTS idx_actions_incident ON actions(incident_id);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);

CREATE TABLE IF NOT EXISTS seen_signatures (
    sig_key TEXT PRIMARY KEY,
    created_at REAL NOT NULL
);
"""


class IncidentStore:
    """Thread-safe SQLite store for incident and immutable action tracking."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get("SENTINEL_DB_PATH", "sentinel.db")
        self._lock = threading.Lock()
        # The lock serializes use of this connection across caller threads.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except BaseException:
            self._conn.close()
            raise

    @staticmethod
    def _from_row(row: sqlite3.Row | tuple | None) -> Incident | None:
        if row is None:
            return None
        return Incident(
            id=row[0],
            idempotency_key=row[1],
            alertname=row[2],
            store_status=row[3],
            agent_id=row[4],
            credential_id=row[5],
            severity=row[6],
            starts_at=datetime.fromisoformat(row[7]),
            # Preserve alert semantics independently of store lifecycle.
            status="firing",
        )

    def _get_locked(self, column: str, value: object) -> Incident | None:
        # column is selected exclusively by internal callers, never user input.
        row = self._conn.execute(
            f"SELECT id, idempotency_key, alertname, status, agent_id, "
            f"credential_id, severity, starts_at FROM incidents WHERE {column}=?",
            (value,),
        ).fetchone()
        return self._from_row(row)

    def claim(self, incident: Incident) -> tuple[Incident, bool]:
        """Atomically claim an incident; duplicate keys return the existing row."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                cursor = self._conn.execute(
                    """INSERT OR IGNORE INTO incidents
                       (idempotency_key, alertname, status, agent_id,
                        credential_id, severity, starts_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        incident.idempotency_key,
                        incident.alertname,
                        STATUS_RECEIVED,
                        incident.agent_id,
                        incident.credential_id,
                        incident.severity,
                        incident.starts_at.isoformat(),
                    ),
                )
                is_new = cursor.rowcount == 1
                if is_new:
                    self._conn.execute(
                        """INSERT INTO actions
                           (incident_id, action_type, status)
                           VALUES (?, 'quarantine', 'pending')""",
                        (cursor.lastrowid,),
                    )
                stored = self._get_locked("idempotency_key", incident.idempotency_key)
                self._conn.commit()
                return stored, is_new
            except BaseException:
                self._conn.rollback()
                raise

    def get(self, incident_id: int) -> Incident | None:
        """Get an incident by database ID."""
        with self._lock:
            return self._get_locked("id", incident_id)

    def get_by_key(self, idempotency_key: str) -> Incident | None:
        """Get an incident by idempotency key."""
        with self._lock:
            return self._get_locked("idempotency_key", idempotency_key)

    def _set_status(self, incident_id: int, status: str) -> bool:
        """Set incident lifecycle status (used by the quarantine control loop)."""
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid incident status: {status!r}")
        with self._lock:
            cursor = self._conn.execute(
                """UPDATE incidents SET status=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (status, incident_id),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    def mark_quarantined(self, incident_id: int) -> bool:
        """Transition an incident from received to quarantined, appending audit row."""
        return self._set_status_with_audit(incident_id, STATUS_QUARANTINED, "quarantine", "success")

    def _set_status_with_audit(
        self, incident_id: int, status: str, action_type: str, action_status: str
    ) -> bool:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                cursor = self._conn.execute(
                    """UPDATE incidents SET status=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (status, incident_id),
                )
                updated = cursor.rowcount == 1
                if updated:
                    self._conn.execute(
                        """INSERT INTO actions
                           (incident_id, action_type, status)
                           VALUES (?, ?, ?)""",
                        (incident_id, action_type, action_status),
                    )
                self._conn.commit()
                return updated
            except BaseException:
                self._conn.rollback()
                raise

    def release(self, incident_id: int) -> bool:
        """Release a quarantined incident, appending an immutable audit row."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                cursor = self._conn.execute(
                    """UPDATE incidents
                       SET status=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND status=?""",
                    (STATUS_RELEASED, incident_id, STATUS_QUARANTINED),
                )
                released = cursor.rowcount == 1
                if released:
                    self._conn.execute(
                        """INSERT INTO actions
                           (incident_id, action_type, status)
                           VALUES (?, 'release', 'success')""",
                        (incident_id,),
                    )
                self._conn.commit()
                return released
            except BaseException:
                self._conn.rollback()
                raise

    def list_quarantined(self) -> list[Incident]:
        """List currently quarantined incidents, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, idempotency_key, alertname, status, agent_id,
                          credential_id, severity, starts_at
                   FROM incidents WHERE status=? ORDER BY id""",
                (STATUS_QUARANTINED,),
            ).fetchall()
            return [self._from_row(row) for row in rows]

    # -- F2: Replay protection ------------------------------------------------

    _REPLAY_TTL = 301  # seconds

    def record_signature(self, sig_key: str) -> bool:
        """Record a seen signature.  Returns False if already seen (replay)."""
        now = time.time()
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                # Purge expired entries
                self._conn.execute(
                    "DELETE FROM seen_signatures WHERE created_at < ?",
                    (now - self._REPLAY_TTL,),
                )
                self._conn.execute(
                    "INSERT INTO seen_signatures (sig_key, created_at) VALUES (?, ?)",
                    (sig_key, now),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                self._conn.rollback()
                return False
            except BaseException:
                self._conn.rollback()
                raise

    # -- F5: Atomic release guard ---------------------------------------------

    def claim_for_release(self, incident_id: int) -> Incident | None:
        """Atomically transition quarantined→releasing; returns Incident or None."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                cursor = self._conn.execute(
                    """UPDATE incidents
                       SET status=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND status=?""",
                    (STATUS_RELEASING, incident_id, STATUS_QUARANTINED),
                )
                if cursor.rowcount != 1:
                    self._conn.rollback()
                    return None
                row = self._conn.execute(
                    "SELECT id, idempotency_key, alertname, status, agent_id, "
                    "credential_id, severity, starts_at FROM incidents WHERE id=?",
                    (incident_id,),
                ).fetchone()
                self._conn.commit()
                return self._from_row(row)
            except BaseException:
                self._conn.rollback()
                raise

    def release_ok(self, incident_id: int) -> bool:
        """Commit the release after successful revoker."""
        return self._set_status_with_audit(
            incident_id, STATUS_RELEASED, "release", "success"
        )

    def release_failed(self, incident_id: int, error: str) -> bool:
        """Record a failed release; transition back to quarantined."""
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    """UPDATE incidents SET status=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND status=?""",
                    (STATUS_QUARANTINED, incident_id, STATUS_RELEASING),
                )
                self._conn.execute(
                    """INSERT INTO actions
                       (incident_id, action_type, status, error_message)
                       VALUES (?, 'release', 'failed', ?)""",
                    (incident_id, error),
                )
                self._conn.commit()
                return True
            except BaseException:
                self._conn.rollback()
                raise

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._conn.close()
