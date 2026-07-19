"""Tests for sentinel.app — signed webhook HTTP service."""
import hashlib
import hmac
import http.client
import json
import os
import socket
import threading
import time
import unittest

from sentinel.app import SentinelRequestHandler, main, MAX_BODY_BYTES

SECRET = "test-secret-key-abc123"

TEST_DB = "/tmp/sentinel_test_app.db"


def _sign(timestamp: str, body: bytes, secret: str) -> str:
    msg = f"{timestamp}.".encode() + body
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _headers(body: bytes, secret: str = SECRET) -> dict:
    ts = str(int(time.time()))
    sig = _sign(ts, body, secret)
    return {
        "X-Sentinel-Timestamp": ts,
        "X-Sentinel-Signature": sig,
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }


class TestAppService(unittest.TestCase):
    """Integration tests against the HTTP server (via http.client)."""

    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        cls._server = None
        cls._thread = None
        cls.port = None

    @classmethod
    def tearDownClass(cls):
        cls._stop_server()
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    @classmethod
    def _start_server(cls, dry_run: bool = True):
        from http.server import ThreadingHTTPServer
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

        from sentinel.store import IncidentStore
        from sentinel.revoker import get_revoker

        store = IncidentStore(TEST_DB)
        revoker = get_revoker()

        server = ThreadingHTTPServer(("127.0.0.1", port), SentinelRequestHandler)
        server.store = store
        server.revoker = revoker
        server.webhook_secret = SECRET
        server.dry_run = dry_run

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        cls._server = server
        cls._thread = thread
        cls.port = port
        return port

    @classmethod
    def _stop_server(cls):
        if cls._server:
            cls._server.shutdown()
            cls._server.server_close()
            cls._server = None
            cls._thread = None

    def _request(self, method: str, path: str, body: bytes = b"",
                 headers: dict | None = None) -> tuple[int, dict, str]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body or None, headers=headers or {})
            resp = conn.getresponse()
            raw = resp.read().decode()
            conn.close()
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {}
            return resp.status, data, raw
        except Exception:
            conn.close()
            raise

    def test_livez_returns_200(self):
        self._start_server()
        try:
            status, data, _ = self._request("GET", "/livez")
            self.assertEqual(status, 200)
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("version"), "0.1.0")
        finally:
            self._stop_server()

    def test_alerts_valid_quarantine_dry_run(self):
        self._start_server(dry_run=True)
        try:
            body = json.dumps({
                "status": "firing",
                "alertname": "RunawayToolLoop",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-1", "credential_id": "cred-abc"},
            }).encode()
            hdrs = _headers(body)

            status, data, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status, 200)
            self.assertEqual(data.get("status"), "success")
            self.assertIsNotNone(data.get("incident_id"))
            self.assertEqual(data.get("action"), "dry_run")
        finally:
            self._stop_server()

    def test_alerts_forged_signature_returns_401(self):
        self._start_server()
        try:
            body = json.dumps({
                "status": "firing",
                "alertname": "Test",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "a", "credential_id": "c"},
            }).encode()
            hdrs = _headers(body, secret="wrong-secret")

            status, data, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status, 401)
            self.assertEqual(data.get("status"), "error")
        finally:
            self._stop_server()

    def test_alerts_malformed_json_returns_400(self):
        self._start_server()
        try:
            body = b"not valid json"
            hdrs = _headers(body)

            status, data, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status, 400)
            self.assertEqual(data.get("status"), "error")
        finally:
            self._stop_server()

    def test_alerts_oversized_body_returns_413(self):
        self._start_server()
        try:
            body = b"x" * (MAX_BODY_BYTES + 1)
            hdrs = _headers(body)

            status, data, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status, 413)
        finally:
            self._stop_server()

    def test_alerts_missing_headers_returns_401(self):
        self._start_server()
        try:
            body = json.dumps({
                "status": "firing",
                "alertname": "Test",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "a", "credential_id": "c"},
            }).encode()
            headers_no_auth = {"Content-Type": "application/json",
                               "Content-Length": str(len(body))}

            status, data, _ = self._request("POST", "/alerts", body, headers_no_auth)
            self.assertEqual(status, 401)
            self.assertEqual(data.get("status"), "error")
        finally:
            self._stop_server()

    def test_alerts_duplicate_returns_200_duplicate(self):
        self._start_server(dry_run=True)
        try:
            body = json.dumps({
                "status": "firing",
                "alertname": "DupAlert",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-dup", "credential_id": "cred-dup"},
            }).encode()
            hdrs1 = _headers(body)

            status1, data1, _ = self._request("POST", "/alerts", body, hdrs1)
            self.assertEqual(status1, 200)
            self.assertEqual(data1.get("status"), "success")

            # Ensure a fresh clock tick so the replay key differs.
            time.sleep(1)
            hdrs2 = _headers(body)
            status2, data2, _ = self._request("POST", "/alerts", body, hdrs2)
            self.assertEqual(status2, 200)
            self.assertEqual(data2.get("status"), "duplicate")
            self.assertEqual(data2.get("incident_id"), data1.get("incident_id"))
        finally:
            self._stop_server()

    def test_alerts_resolved_returns_ignored(self):
        self._start_server(dry_run=True)
        try:
            body = json.dumps({
                "status": "resolved",
                "alertname": "ResolvedAlert",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-res", "credential_id": "cred-res"},
            }).encode()
            hdrs = _headers(body)

            status, data, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status, 200)
            self.assertEqual(data.get("status"), "ignored")
            self.assertEqual(data.get("action"), "ignored")
            self.assertIsNotNone(data.get("incident_id"))
        finally:
            self._stop_server()

    def test_release_valid_returns_200(self):
        self._start_server(dry_run=True)
        try:
            body = json.dumps({
                "status": "firing",
                "alertname": "ReleaseMe",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-rel", "credential_id": "cred-rel"},
            }).encode()
            hdrs = _headers(body)
            _, create_data, _ = self._request("POST", "/alerts", body, hdrs)
            incident_id = create_data.get("incident_id")
            self.assertIsNotNone(incident_id)

            release_headers = _headers(b"")
            status, data, _ = self._request(
                "POST", f"/incidents/{incident_id}/release",
                headers=release_headers)
            self.assertEqual(status, 200)
            self.assertEqual(data.get("status"), "success")
            self.assertEqual(data.get("action"), "released")
        finally:
            self._stop_server()

    def test_release_nonexistent_returns_404(self):
        self._start_server()
        try:
            hdrs = _headers(b"")
            status, data, _ = self._request("POST", "/incidents/99999/release",
                                            headers=hdrs)
            self.assertEqual(status, 404)
        finally:
            self._stop_server()

    def test_release_non_quarantined_returns_400(self):
        self._start_server(dry_run=True)
        try:
            body = json.dumps({
                "status": "resolved",
                "alertname": "NonQAlert",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-nq", "credential_id": "cred-nq"},
            }).encode()
            hdrs = _headers(body)
            _, create_data, _ = self._request("POST", "/alerts", body, hdrs)
            incident_id = create_data.get("incident_id")
            self.assertIsNotNone(incident_id)

            release_hdrs = _headers(b"")
            status, data, _ = self._request(
                "POST", f"/incidents/{incident_id}/release",
                headers=release_hdrs)
            self.assertEqual(status, 400)
            self.assertEqual(data.get("status"), "error")
        finally:
            self._stop_server()

    # -- F2: replay protection — same (timestamp, signature, body) rejected ----

    def test_replay_same_signature_rejected(self):
        """F2: replaying the SAME headers (ts+sig) must 401, not 200 duplicate."""
        self._start_server(dry_run=True)
        try:
            body = json.dumps({
                "status": "firing",
                "alertname": "ReplayAlert",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-rep", "credential_id": "cred-rep"},
            }).encode()
            hdrs = _headers(body)  # same ts + sig on both calls

            status1, data1, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status1, 200)
            self.assertEqual(data1.get("status"), "success")

            # Same headers → same replay_key → record_signature returns False → 401.
            status2, data2, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status2, 401)
            self.assertEqual(data2.get("status"), "error")
        finally:
            self._stop_server()

    # -- F16: 502 on revoker failure ----------------------------------------

    def test_revoker_failure_returns_502(self):
        """F16: revoker.quarantine success:False → 502 (not 200), status=error."""
        self._start_server(dry_run=True)
        try:
            # Replace revoker.quarantine with a failing stub.
            self._server.revoker.quarantine = lambda cred_id, **kw: {
                "success": False,
                "action": "quarantine",
                "message": "upstream down",
            }
            body = json.dumps({
                "status": "firing",
                "alertname": "QuarantineFail",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-qf", "credential_id": "cred-qf"},
            }).encode()
            hdrs = _headers(body)
            status, data, _ = self._request("POST", "/alerts", body, hdrs)
            self.assertEqual(status, 502)
            self.assertEqual(data.get("status"), "error")
        finally:
            self._stop_server()

    # -- F1: 411 on missing Content-Length ----------------------------------

    def test_missing_content_length_returns_411(self):
        """F1: POST /alerts with no Content-Length → 411."""
        self._start_server()
        try:
            body = json.dumps({
                "status": "firing",
                "alertname": "NoCL",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "a", "credential_id": "c"},
            }).encode()
            ts = str(int(time.time()))
            sig = _sign(ts, body, SECRET)
            # Raw socket: omit Content-Length entirely. http.client would add it.
            req = (
                f"POST /alerts HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.port}\r\n"
                f"X-Sentinel-Timestamp: {ts}\r\n"
                f"X-Sentinel-Signature: {sig}\r\n"
                f"Content-Type: application/json\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            ).encode() + body
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as s:
                s.sendall(req)
                chunks = []
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                raw = b"".join(chunks).decode()
            status_line = raw.split("\r\n", 1)[0]
            self.assertIn(" 411", status_line)
            self.assertIn('"status": "error"', raw)
        finally:
            self._stop_server()

    # -- F5: concurrent release calls revoker once ---------------------------

    def test_concurrent_release_calls_revoker_once(self):
        """F5: two concurrent release calls → revoker.release invoked once,
        one 200, one 400 (not quarantined)."""
        self._start_server(dry_run=True)
        try:
            # Pre-seed a quarantined incident via /alerts.
            body = json.dumps({
                "status": "firing",
                "alertname": "ConcurrentRel",
                "startsAt": "2026-07-19T12:00:00Z",
                "labels": {"agent_id": "agent-cr", "credential_id": "cred-cr"},
            }).encode()
            hdrs = _headers(body)
            _, create_data, _ = self._request("POST", "/alerts", body, hdrs)
            incident_id = create_data.get("incident_id")
            self.assertIsNotNone(incident_id)
            self.assertEqual(
                self._server.store.get(incident_id).store_status, "quarantined"
            )

            # Wrap revoker.release with a counter. DryRunRevoker.release succeeds.
            release_calls = []
            real_release = self._server.revoker.release

            def counting_release(cred_id, **kw):
                release_calls.append(cred_id)
                return real_release(cred_id, **kw)

            self._server.revoker.release = counting_release

            barrier = threading.Barrier(2)
            results = []

            def caller(idx):
                body = str(idx).encode()
                rh = _headers(body)
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
                status, data, _ = self._request(
                    "POST", f"/incidents/{incident_id}/release",
                    body=body, headers=rh,
                )
                results.append((status, data.get("status")))

            t1 = threading.Thread(target=caller, args=(1,))
            t2 = threading.Thread(target=caller, args=(2,))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            # Exactly one revoker.release call.
            self.assertEqual(len(release_calls), 1,
                             f"expected 1 release call, got {len(release_calls)}")
            # One 200/success, one 400/error.
            statuses = sorted(r[0] for r in results)
            self.assertEqual(statuses, [200, 400],
                             f"expected [200, 400], got {statuses}")
            self.assertIn("success", [r[1] for r in results])
        finally:
            self._stop_server()


if __name__ == "__main__":
    unittest.main()
