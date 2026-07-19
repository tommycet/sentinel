"""Tests for sentinel.store — idempotent SQLite quarantine store.

TDD tests written first; implementation must satisfy all below.
"""
import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone

from sentinel.model import Incident, ALERT_STATUS_FIRING
from sentinel.store import (
    IncidentStore,
    STATUS_RECEIVED,
    STATUS_QUARANTINED,
    STATUS_FAILED,
    STATUS_RELEASED,
)


def _make_incident(
    alertname="RunawayToolLoop",
    key="key-1",
    agent_id="agent-123",
    credential_id="cred-abc",
    severity="critical",
):
    return Incident(
        alertname=alertname,
        status=ALERT_STATUS_FIRING,
        starts_at=datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc),
        agent_id=agent_id,
        credential_id=credential_id,
        severity=severity,
        idempotency_key=key,
    )


class _TmpStore:
    """Per-test temp-dir IncidentStore."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="sentinel-store-")
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.store = IncidentStore(self.db_path)

    def tearDown(self):
        self.store.close()
        for f in os.listdir(self.tmpdir):
            os.unlink(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)


class TestClaimFirst(_TmpStore, unittest.TestCase):
    """1. First claim succeeds."""

    def test_first_claim_returns_new_incident_with_id(self):
        inc = _make_incident(key="k-first")
        stored, is_new = self.store.claim(inc)

        self.assertTrue(is_new)
        self.assertIsInstance(stored, Incident)
        self.assertGreaterEqual(stored.id, 1)
        self.assertEqual(stored.idempotency_key, "k-first")

        # Idempotent: querying by key returns same id
        again = self.store.get_by_key("k-first")
        self.assertEqual(again.id, stored.id)

        # Incident status recorded as 'received'
        self.assertEqual(self.store.get(stored.id).store_status, STATUS_RECEIVED)


class TestClaimDuplicate(_TmpStore, unittest.TestCase):
    """2. Duplicate claim returns (existing_incident, is_new=False)."""

    def test_duplicate_claim_returns_existing_with_is_new_false(self):
        inc = _make_incident(key="k-dup")
        first, is_new_first = self.store.claim(inc)
        second, is_new_second = self.store.claim(inc)

        self.assertTrue(is_new_first)
        self.assertFalse(is_new_second)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.idempotency_key, second.idempotency_key)

    def test_duplicate_claim_does_not_create_extra_action(self):
        inc = _make_incident(key="k-dup2")
        self.store.claim(inc)
        self.store.claim(inc)
        row_id = self.store.get_by_key("k-dup2").id
        n = self.store._conn.execute(
            "SELECT COUNT(*) FROM actions WHERE incident_id=?", (row_id,)
        ).fetchone()[0]
        self.assertEqual(n, 1)


class TestStatusTransitions(_TmpStore, unittest.TestCase):
    """3. Status transitions persist across restarts."""

    def test_release_transitions_status_and_persists(self):
        inc = _make_incident(key="k-rel")
        self.store.claim(inc)
        stored = self.store.get_by_key("k-rel")
        self.assertEqual(stored.store_status, STATUS_RECEIVED)

        # Quarantine it
        self.store._set_status(stored.id, STATUS_QUARANTINED)
        self.assertEqual(self.store.get(stored.id).store_status, STATUS_QUARANTINED)

        ok = self.store.release(stored.id)
        self.assertTrue(ok)
        self.assertEqual(self.store.get(stored.id).store_status, STATUS_RELEASED)

        # Reopen store from same DB file: status persists
        self.store.close()
        self.store = IncidentStore(self.db_path)
        self.assertEqual(self.store.get(stored.id).store_status, STATUS_RELEASED)

        # Release audit row recorded
        rows = self.store._conn.execute(
            "SELECT action_type, status FROM actions WHERE incident_id=? ORDER BY id",
            (stored.id,),
        ).fetchall()
        self.assertIn(("release", "success"), rows)


class TestConcurrentClaims(unittest.TestCase):
    """4. Concurrent duplicate claims yield one winner."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="sentinel-conc-")
        self.db_path = os.path.join(self.tmpdir, "test.db")

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.unlink(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_only_one_winner_under_concurrency(self):
        # Single shared store instance; spec's threading.Lock serializes writes.
        store = IncidentStore(self.db_path)
        inc = _make_incident(key="k-concurrent")

        results = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            _, is_new = store.claim(inc)
            with results_lock:
                results.append(is_new)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        store.close()

        self.assertEqual(len(results), 8)
        self.assertEqual(sum(1 for r in results if r), 1)
        self.assertEqual(sum(1 for r in results if not r), 7)


class TestAuditImmutable(_TmpStore, unittest.TestCase):
    """5. Audit rows are immutable (no UPDATE against actions)."""

    def test_release_appends_does_not_modify_existing_action_row(self):
        inc = _make_incident(key="k-audit")
        self.store.claim(inc)
        stored = self.store.get_by_key("k-audit")

        before = self.store._conn.execute(
            "SELECT id, action_type, status, created_at FROM actions WHERE incident_id=?",
            (stored.id,),
        ).fetchall()

        self.store._set_status(stored.id, STATUS_QUARANTINED)
        self.store.release(stored.id)

        after = self.store._conn.execute(
            "SELECT id, action_type, status, created_at FROM actions WHERE incident_id=? ORDER BY id",
            (stored.id,),
        ).fetchall()

        # Original row preserved unchanged
        self.assertIn(before[0], after)
        # New row appended
        self.assertEqual(len(after), 2)
        self.assertEqual(after[1][1], "release")

    def test_no_action_mutation_api(self):
        """Store must not expose any action-mutation method."""
        for name in ("update_action", "edit_action", "patch_action", "delete_action"):
            self.assertFalse(
                hasattr(self.store, name),
                f"Store must not expose action mutation method: {name}",
            )


class TestForeignKeyConstraint(_TmpStore, unittest.TestCase):
    """6. Foreign key constraints work."""

    def test_action_with_nonexistent_incident_id_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._conn.execute(
                "INSERT INTO actions (incident_id, action_type, status) VALUES (?, ?, ?)",
                (999999, "quarantine", "pending"),
            )
            self.store._conn.commit()

    def test_delete_incident_blocked_when_actions_exist(self):
        inc = _make_incident(key="k-fk")
        self.store.claim(inc)
        stored = self.store.get_by_key("k-fk")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._conn.execute("DELETE FROM incidents WHERE id=?", (stored.id,))
            self.store._conn.commit()


class TestReleaseGuard(_TmpStore, unittest.TestCase):
    """release() returns False when incident is not 'quarantined'."""

    def test_release_non_quarantined_returns_false(self):
        inc = _make_incident(key="k-guard")
        self.store.claim(inc)
        stored = self.store.get_by_key("k-guard")
        # status is 'received', not 'quarantined'
        self.assertFalse(self.store.release(stored.id))

    def test_release_unknown_id_returns_false(self):
        self.assertFalse(self.store.release(999999))


class TestListQuarantined(_TmpStore, unittest.TestCase):
    """list_quarantined() returns only quarantined incidents."""

    def test_filters_to_quarantined(self):
        a = _make_incident(key="k-q1")
        b = _make_incident(key="k-q2")
        self.store.claim(a)
        self.store.claim(b)
        sa = self.store.get_by_key("k-q1")
        sb = self.store.get_by_key("k-q2")
        self.store._set_status(sa.id, STATUS_QUARANTINED)

        result = self.store.list_quarantined()
        self.assertEqual([i.id for i in result], [sa.id])

        # b not included
        self.assertNotIn(sb.id, [i.id for i in result])


class TestPragmas(_TmpStore, unittest.TestCase):
    """WAL mode + foreign keys enabled."""

    def test_wal_mode_enabled(self):
        mode = self.store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        # :memory: may use 'memory'; on-disk path should be 'wal'
        if self.db_path != ":memory:":
            self.assertEqual(mode.lower(), "wal")

    def test_foreign_keys_enabled(self):
        fk = self.store._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(fk, 1)


if __name__ == "__main__":
    unittest.main()
