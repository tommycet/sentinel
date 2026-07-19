"""Sentinel HTTP service: signed webhook intake for SigNoz alerts.

Stdlib only. Receives SigNoz alerts, verifies HMAC, claims incident, and
quarantines the credential (or dry-runs). Also exposes /livez and a manual
release endpoint.
"""
from __future__ import annotations

import argparse
import hmac
import hashlib
import json
import logging
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from sentinel import auth, model, store, revoker

log = logging.getLogger("sentinel.app")

VERSION = "0.1.0"
MAX_BODY_BYTES = 64 * 1024  # 64 KiB cap per spec
_TS_RE = re.compile(r"^\d+$")

# Match /incidents/<id>/release (positive int id)
_RELEASE_RE = re.compile(r"^/incidents/(\d+)/release/?$")


def _now_iso() -> str:
    # Compact ISO timestamp for log lines; never contains secrets.
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log(level: int, event: str, **fields: Any) -> None:
    """Structured single-line stderr log. Never logs secrets or bodies."""
    safe = {k: v for k, v in fields.items()
            if k not in {"secret", "signature", "body", "raw"}}
    line = json.dumps(
        {"ts": _now_iso(), "event": event, **safe},
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    log.log(level, line)


class SentinelRequestHandler(BaseHTTPRequestHandler):
    """Dispatch GET /livez, POST /alerts, POST /incidents/<id>/release."""

    # Quiet base class logging; we emit our own structured logs.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, N803
        return

    # --- shared helpers ---

    @property
    def _cfg(self) -> dict:
        """Read component handles from the server instance."""
        return {
            "store": getattr(self.server, "store", None),
            "revoker": getattr(self.server, "revoker", None),
            "secret": getattr(self.server, "webhook_secret", ""),
            "dry_run": getattr(self.server, "dry_run", True),
        }

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_body(self) -> tuple[bytes | None, int | None]:
        """Read request body up to MAX_BODY_BYTES.

        Returns (body, error_status). On error, body is None and error_status
        is set (e.g., 413 for oversized).
        """
        try:
            clen = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            clen = 0
        if clen > MAX_BODY_BYTES:
            return None, 413
        if clen == 0:
            return b"", None
        # Defensive double-cap: never trust Content-Length alone.
        data = self.rfile.read(clen)
        if len(data) > MAX_BODY_BYTES:
            return None, 413
        return data, None

    def _verify(self, body: bytes) -> tuple[bool, str]:
        """Verify HMAC webhook. Returns (ok, error_message)."""
        ts = self.headers.get("X-Sentinel-Timestamp", "")
        sig = self.headers.get("X-Sentinel-Signature", "")
        secret = self._cfg["secret"]
        if not secret:
            _log(logging.ERROR, "auth_misconfigured",
                 path=self.path, reason="missing_secret")
            return False, "Server not configured for webhook auth"
        try:
            auth.verify_webhook(ts, sig, body, secret)
            return True, ""
        except ValueError as e:
            # Generic, never echoes secret or signature value.
            _log(logging.WARNING, "auth_failed",
                 path=self.path, reason=str(e))
            return False, str(e)

    # --- routes ---

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path == "/livez":
            self._send_json(200, {"status": "ok", "version": VERSION})
            return
        self._send_json(404, {"status": "error", "message": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if self.path == "/alerts":
            self._handle_alerts()
            return
        m = _RELEASE_RE.match(self.path)
        if m:
            self._handle_release(int(m.group(1)))
            return
        self._send_json(404, {"status": "error", "message": "not found"})

    # --- POST /alerts ---

    def _handle_alerts(self) -> None:
        body, err = self._read_body()
        if err == 413:
            _log(logging.WARNING, "body_oversized", path="/alerts")
            self._send_json(413, {"status": "error",
                                  "message": "payload too large",
                                  "incident_id": None, "action": None,
                                  "error": "body exceeds 64 KiB"})
            return

        ok, err_msg = self._verify(body or b"")
        if not ok:
            self._send_json(401, {"status": "error", "message": "unauthorized",
                                  "incident_id": None, "action": None,
                                  "error": err_msg})
            return

        # Parse alert (JSON + validation)
        try:
            incident = model.parse_alert(body or b"")
        except (ValueError, json.JSONDecodeError) as e:
            _log(logging.WARNING, "parse_failed", path="/alerts",
                 error=str(e))
            self._send_json(400, {"status": "error",
                                  "message": "invalid alert payload",
                                  "incident_id": None, "action": None,
                                  "error": str(e)})
            return

        st = self._cfg["store"]
        if st is None:
            self._send_json(500, {"status": "error",
                                  "message": "store not configured",
                                  "incident_id": None, "action": None,
                                  "error": "no store"})
            return

        stored_incident, is_new = st.claim(incident)
        incident_id = stored_incident.id if stored_incident else None

        if not is_new:
            _log(logging.INFO, "duplicate",
                 incident_id=incident_id,
                 alertname=incident.alertname)
            self._send_json(200, {
                "status": "duplicate",
                "incident_id": incident_id,
                "action": None,
                "message": "duplicate alert ignored",
                "error": None,
            })
            return

        # Resolved alerts: do not quarantine.
        if not incident.needs_quarantine():
            _log(logging.INFO, "ignored_resolved",
                 incident_id=incident_id,
                 alertname=incident.alertname)
            self._send_json(200, {
                "status": "ignored",
                "incident_id": incident_id,
                "action": "ignored",
                "message": "alert resolved; no action taken",
                "error": None,
            })
            return

        # Quarantine via revoker.
        rv = self._cfg["revoker"]
        if rv is None:
            self._send_json(500, {"status": "error",
                                  "message": "revoker not configured",
                                  "incident_id": incident_id,
                                  "action": None, "error": "no revoker"})
            return

        result = rv.quarantine(incident.credential_id,
                               alertname=incident.alertname,
                               incident_id=incident_id,
                               dry_run=self._cfg["dry_run"])

        action = result.get("action", "quarantined")
        if self._cfg["dry_run"] and action != "quarantined":
            action = "dry_run"
        # Mark store status as quarantined when revoker succeeds.
        # Always track lifecycle in store; dry_run only controls external calls.
        if result.get("success"):
            try:
                st._set_status(incident_id, store.STATUS_QUARANTINED)
            except Exception as e:  # noqa: BLE001
                _log(logging.ERROR, "store_status_update_failed",
                     incident_id=incident_id, error=type(e).__name__)

        _log(logging.INFO, "quarantined",
             incident_id=incident_id,
             alertname=incident.alertname,
             action=action,
             dry_run=self._cfg["dry_run"],
             success=bool(result.get("success")))

        self._send_json(200, {
            "status": "success",
            "incident_id": incident_id,
            "action": action,
            "message": result.get("message", "quarantined"),
            "error": None,
        })

    # --- POST /incidents/<id>/release ---

    def _handle_release(self, incident_id: int) -> None:
        # body unused but should still verify signature (may be empty).
        body, err = self._read_body()
        if err == 413:
            self._send_json(413, {"status": "error",
                                  "message": "payload too large",
                                  "action": None})
            return

        ok, err_msg = self._verify(body or b"")
        if not ok:
            self._send_json(401, {"status": "error", "message": "unauthorized",
                                  "action": None, "error": err_msg})
            return

        st = self._cfg["store"]
        if st is None:
            self._send_json(500, {"status": "error",
                                  "message": "store not configured",
                                  "action": None, "error": "no store"})
            return

        incident = st.get(incident_id)
        if not incident:
            _log(logging.INFO, "release_not_found",
                 incident_id=incident_id)
            self._send_json(404, {"status": "error",
                                  "message": "incident not found",
                                  "action": None,
                                  "error": f"no incident with id={incident_id}"})
            return

        if incident.store_status != store.STATUS_QUARANTINED:
            _log(logging.INFO, "release_not_quarantined",
                 incident_id=incident_id,
                 status=incident.store_status)
            self._send_json(400, {
                "status": "error",
                "action": None,
                "message": "Incident not quarantined",
                "error": f"current status: {incident.store_status!r}",
            })
            return

        rv = self._cfg["revoker"]
        if rv is None:
            self._send_json(500, {"status": "error",
                                  "message": "revoker not configured",
                                  "action": None, "error": "no revoker"})
            return

        result = rv.release(incident.credential_id,
                             incident_id=incident_id,
                             dry_run=self._cfg["dry_run"])

        # Update store on real release.
        if result.get("success") and not self._cfg["dry_run"]:
            st.release(incident_id)
        else:
            # In dry-run we don't change DB status; just log.
            pass

        _log(logging.INFO, "released",
             incident_id=incident_id,
             dry_run=self._cfg["dry_run"],
             success=bool(result.get("success")))

        self._send_json(200, {
            "status": "success",
            "action": "released",
            "message": result.get("message", "released"),
            "error": None,
        })


def make_server(host: str, port: int, store_obj: "store.IncidentStore",
                revoker_obj: "revoker.Revoker", secret: str,
                dry_run: bool = True) -> ThreadingHTTPServer:
    """Build a ThreadingHTTPServer with components attached as attributes."""
    srv = ThreadingHTTPServer((host, port), SentinelRequestHandler)
    srv.store = store_obj  # type: ignore[attr-defined]
    srv.revoker = revoker_obj  # type: ignore[attr-defined]
    srv.webhook_secret = secret  # type: ignore[attr-defined]
    srv.dry_run = dry_run  # type: ignore[attr-defined]
    return srv


def main() -> None:
    """Entry point: parse args, wire components, serve."""
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="sentinel",
        description="Sentinel signed webhook HTTP service",
    )
    parser.add_argument("--port", type=int,
                        default=int(os.getenv("SENTINEL_PORT", "8090")),
                        help="HTTP port (default: 8090 or $SENTINEL_PORT)")
    parser.add_argument("--dry-run", action="store_true",
                        default=os.getenv("SENTINEL_DRY_RUN", "true").lower()
                        not in ("0", "false", "no"),
                        help="Dry-run mode: don't actually revoke")
    parser.add_argument("--webhook-secret", default=None,
                        help="HMAC shared secret "
                             "(default: $SENTINEL_WEBHOOK_SECRET)")
    parser.add_argument("--db-path", default=None,
                        help="SQLite path "
                             "(default: $SENTINEL_DB_PATH or sentinel.db)")
    args = parser.parse_args()

    secret = args.webhook_secret or os.getenv("SENTINEL_WEBHOOK_SECRET")
    if not secret:
        print("SENTINEL_WEBHOOK_SECRET is required "
              "(--webhook-secret or env var)", file=sys.stderr)
        raise SystemExit(2)

    db_path = args.db_path or os.getenv("SENTINEL_DB_PATH", "sentinel.db")
    store_obj = store.IncidentStore(db_path)
    revoker_obj = revoker.get_revoker()

    srv = make_server("0.0.0.0", args.port, store_obj, revoker_obj,
                      secret, dry_run=args.dry_run)

    _log(logging.INFO, "listening",
         port=args.port, dry_run=args.dry_run,
         db_path=db_path)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        _log(logging.INFO, "shutdown")
    finally:
        srv.shutdown()
        srv.server_close()
        store_obj.close()


if __name__ == "__main__":
    main()
