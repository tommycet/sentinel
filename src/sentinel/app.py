"""Sentinel HTTP service — signed webhook receiver for SigNoz alerts.

Stdlib only: http.server, json, urllib, argparse.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .auth import verify_webhook
from .model import Incident, parse_alert
from .revoker import get_revoker
from .store import IncidentStore
from .telemetry import export_span

# Maximum request body size: 64 KiB
MAX_BODY_BYTES = 64 * 1024

# The TTL for replay-protection signature cache (app-wide constant)
_REPLAY_TTL = 301

# Default port
DEFAULT_PORT = 8090

log = logging.getLogger("sentinel.app")


class SentinelRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Sentinel webhook endpoints.

    Uses server-level attributes:
    - server.store: IncidentStore instance
    - server.revoker: Revoker instance
    - server.webhook_secret: str for HMAC verification
    - server.dry_run: bool for dry-run mode
    """

    # Disable default date/logging from BaseHTTPRequestHandler
    def log_message(self, format, *args):
        pass  # We use our own logging

    def _send_json(self, status: int, data: dict) -> None:
        """Send a JSON response."""
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        """Read request body with size limit.

        Raises ValueError on:
        - missing Content-Length (F1 — reject 411)
        - body exceeding MAX_BODY_BYTES (413)
        - malformed Content-Length
        """
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ValueError("Missing Content-Length header")  # → 411

        try:
            cl = int(content_length)
        except ValueError:
            raise ValueError("Invalid Content-Length header")

        if cl > MAX_BODY_BYTES:
            raise ValueError(f"Body too large: {cl} > {MAX_BODY_BYTES}")
        if cl == 0:
            return b""

        body = self.rfile.read(cl)
        if len(body) != cl:
            # F4: drain any leftover bytes from the socket so they don't
            # pollute the next keep-alive request.
            self.rfile.read(65536)

        if len(body) > MAX_BODY_BYTES:
            raise ValueError(f"Body too large: {len(body)} > {MAX_BODY_BYTES}")
        return body

    def _get_headers(self) -> dict[str, str]:
        """Extract headers as a dict."""
        return {k: v for k, v in self.headers.items()}

    def _replay_key(self, timestamp: str, signature: str, body: bytes) -> str:
        """Stable key for replay-protection dedup."""
        return hashlib.sha256(
            f"{timestamp}|{signature}|".encode() + body
        ).hexdigest()

    def do_GET(self) -> None:
        """Handle GET requests (health check only)."""
        if self.path == "/livez":
            self._send_json(200, {"status": "ok", "version": "0.1.0"})
        else:
            self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self) -> None:
        """Handle POST requests (/alerts, /incidents/<id>/release)."""
        try:
            body = self._read_body()
        except ValueError as e:
            msg = str(e)
            if "Content-Length" in msg:
                self._send_json(411, {"status": "error", "message": msg})
            else:
                self._send_json(413, {"status": "error", "message": msg})
            return

        headers = self._get_headers()

        # Extract webhook secret from server
        webhook_secret = getattr(self.server, "webhook_secret", "")
        store = getattr(self.server, "store", None)
        revoker = getattr(self.server, "revoker", None)

        if not webhook_secret:
            self._send_json(500, {"status": "error", "message": "Server not configured"})
            return

        if not store or not revoker:
            self._send_json(500, {"status": "error", "message": "Store/revoker not configured"})
            return

        # Route: /alerts
        if self.path == "/alerts":
            self._handle_alerts(body, headers, webhook_secret, store, revoker)
            return

        # Route: /incidents/<id>/release  (F3: use urlparse for query-string resilience)
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/incidents/") and path.endswith("/release"):
            parts = path.split("/")
            if len(parts) >= 3:
                try:
                    incident_id = int(parts[2])
                except ValueError:
                    self._send_json(400, {"status": "error", "message": "Invalid incident ID"})
                    return
                self._handle_release(incident_id, body, headers, webhook_secret, store, revoker)
                return

        self._send_json(404, {"status": "error", "message": "Not found"})

    def _verify_and_record(
        self, body: bytes, headers: dict[str, str], secret: str, store: IncidentStore
    ) -> bool:
        """Verify HMAC + replay guard.  Returns True if authorized."""
        timestamp = headers.get("X-Sentinel-Timestamp", "")
        signature = headers.get("X-Sentinel-Signature", "")

        try:
            if not verify_webhook(timestamp, signature, body, secret):
                return False
        except ValueError:
            return False

        # F2: replay protection — any captured (ts, sig, body) is single-use.
        rkey = self._replay_key(timestamp, signature, body)
        if not store.record_signature(rkey):
            return False

        return True

    def _handle_alerts(
        self,
        body: bytes,
        headers: dict[str, str],
        secret: str,
        store: IncidentStore,
        revoker: Any,
    ) -> None:
        """Handle POST /alerts — verify, parse, claim, quarantine."""
        # Verify webhook signature + replay guard
        if not self._verify_and_record(body, headers, secret, store):
            self._send_json(401, {"status": "error", "message": "Invalid or expired signature"})
            return

        t_start = time.time()
        # Parse alert
        try:
            incident = parse_alert(body)
        except (ValueError, json.JSONDecodeError) as e:
            self._send_json(400, {"status": "error", "message": str(e)})
            return

        # Check if needs quarantine
        if not incident.needs_quarantine():
            claimed_incident, _ = store.claim(incident)
            self._send_json(
                200,
                {
                    "status": "ignored",
                    "incident_id": claimed_incident.id,
                    "action": "ignored",
                    "message": f"Alert status '{incident.status}' does not require quarantine",
                    "error": None,
                },
            )
            return

        # Claim incident (idempotent)
        claimed_incident, is_new = store.claim(incident)

        if not is_new:
            self._send_json(
                200,
                {
                    "status": "duplicate",
                    "incident_id": claimed_incident.id,
                    "action": None,
                    "message": "Duplicate alert — already processed",
                    "error": None,
                },
            )
            return

        # Quarantine via revoker
        result = revoker.quarantine(
            claimed_incident.credential_id,
            incident_id=claimed_incident.id,
            alertname=claimed_incident.alertname,
        )

        action = result.get("action", "unknown")
        success = result.get("success", False)

        if success:
            # Transition incident to quarantined state
            store.mark_quarantined(claimed_incident.id)
            export_span(  # F6: emit telemetry (best-effort)
                "sentinel.agent.quarantined",
                {
                    "agent.id": claimed_incident.agent_id,
                    "credential.id": claimed_incident.credential_id,
                    "alert.name": claimed_incident.alertname,
                    "sentinel.action": action,
                    "sentinel.dry_run": getattr(self.server, "dry_run", True),
                    "sentinel.incident.id": claimed_incident.id,
                    "sentinel.latency_ms": int((time.time() - t_start) * 1000),
                },
                start_time=t_start,
            )
            self._send_json(
                200,
                {
                    "status": "success",
                    "incident_id": claimed_incident.id,
                    "action": action,
                    "message": result.get("message", ""),
                    "error": None,
                },
            )
        else:
            # F16: revoker failure → 502, not 200
            export_span(  # F6: emit telemetry (best-effort)
                "sentinel.agent.quarantined",
                {
                    "agent.id": claimed_incident.agent_id,
                    "credential.id": claimed_incident.credential_id,
                    "alert.name": claimed_incident.alertname,
                    "sentinel.action": action,
                    "sentinel.failure": True,
                    "sentinel.incident.id": claimed_incident.id,
                    "sentinel.latency_ms": int((time.time() - t_start) * 1000),
                },
                start_time=t_start,
                status_code=2,
            )
            self._send_json(
                502,
                {
                    "status": "error",
                    "incident_id": claimed_incident.id,
                    "action": action,
                    "message": result.get("message", "Quarantine failed"),
                    "error": result.get("message", ""),
                },
            )

    def _handle_release(
        self,
        incident_id: int,
        body: bytes,
        headers: dict[str, str],
        secret: str,
        store: IncidentStore,
        revoker: Any,
    ) -> None:
        """Handle POST /incidents/<id>/release — verify, get, release."""
        # Verify webhook signature + replay guard
        if not self._verify_and_record(body, headers, secret, store):
            self._send_json(401, {"status": "error", "message": "Invalid or expired signature"})
            return

        # F5: atomically claim the release so only one caller wins.
        incident = store.claim_for_release(incident_id)
        if incident is None:
            # Either not found or not quarantined — check which.
            existing = store.get(incident_id)
            if existing is None:
                self._send_json(404, {"status": "error", "message": "Incident not found"})
            else:
                self._send_json(
                    400,
                    {
                        "status": "error",
                        "message": f"Incident {incident_id} is not quarantined (status: {existing.store_status})",
                    },
                )
            return

        # Release via revoker
        result = revoker.release(
            incident.credential_id,
            incident_id=incident.id,
            alertname=incident.alertname,
        )

        if result.get("success", False):
            # F5: commit the release
            store.release_ok(incident_id)
            export_span(  # F6: emit telemetry (best-effort)
                "sentinel.agent.released",
                {
                    "agent.id": incident.agent_id,
                    "credential.id": incident.credential_id,
                    "alert.name": incident.alertname,
                    "sentinel.action": "released",
                    "sentinel.incident.id": incident_id,
                },
                start_time=time.time(),
            )
            self._send_json(
                200,
                {
                    "status": "success",
                    "action": "released",
                    "message": result.get("message", ""),
                    "error": None,
                },
            )
        else:
            # F5b: revert store state, record failure
            store.release_failed(
                incident_id, result.get("message", "Release failed")
            )
            export_span(  # F6: emit telemetry (best-effort)
                "sentinel.agent.released",
                {
                    "agent.id": incident.agent_id,
                    "credential.id": incident.credential_id,
                    "alert.name": incident.alertname,
                    "sentinel.action": "release_failed",
                    "sentinel.failure": True,
                    "sentinel.incident.id": incident_id,
                },
                start_time=time.time(),
                status_code=2,
            )
            self._send_json(
                502,
                {
                    "status": "error",
                    "action": result.get("action", "unknown"),
                    "message": result.get("message", "Release failed"),
                    "error": result.get("message", ""),
                },
            )


def main() -> None:
    """Start the Sentinel HTTP service."""
    parser = argparse.ArgumentParser(
        description="Sentinel — Closed-loop SigNoz-native agent runaway detection"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SENTINEL_PORT", DEFAULT_PORT)),
        help="Port to listen on (default: 8090)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.getenv("SENTINEL_HOST", "127.0.0.1"),
        help="Host to bind to (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry-run mode: log actions without revoking credentials (default: True)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        dest="no_dry_run",
        default=False,
        help="Disable dry-run: actually revoke credentials",
    )
    parser.add_argument(
        "--webhook-secret",
        type=str,
        default=os.getenv("SENTINEL_WEBHOOK_SECRET", ""),
        required=not os.getenv("SENTINEL_WEBHOOK_SECRET"),
        help="Shared secret for HMAC webhook authentication",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=os.getenv("SENTINEL_DB_PATH", "sentinel.db"),
        help="Path to SQLite database (default: sentinel.db)",
    )

    args = parser.parse_args()

    if not args.webhook_secret:
        print("Error: --webhook-secret is required", file=sys.stderr)
        sys.exit(1)

    # Initialize components
    store = IncidentStore(args.db_path)
    revoker = get_revoker()

    # Resolve dry-run: --no-dry-run wins if set
    dry_run = not args.no_dry_run if args.no_dry_run else args.dry_run

    # Configure server — bind to configurable host (F17: default 127.0.0.1)
    server = ThreadingHTTPServer((args.host, args.port), SentinelRequestHandler)
    server.store = store
    server.revoker = revoker
    server.webhook_secret = args.webhook_secret
    server.dry_run = dry_run

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    log.info(
        "Sentinel listening on %s:%d (dry_run=%s, revoker=%s)",
        args.host,
        args.port,
        dry_run,
        type(revoker).__name__,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()
        server.server_close()
        store.close()
