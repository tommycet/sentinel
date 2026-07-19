"""Sentinel HTTP service — signed webhook receiver for SigNoz alerts.

Stdlib only: http.server, json, urllib, argparse.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
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

# Maximum request body size: 64 KiB
MAX_BODY_BYTES = 64 * 1024

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
        """Read request body with size limit."""
        content_length = self.headers.get("Content-Length")
        if content_length:
            try:
                cl = int(content_length)
            except ValueError:
                cl = 0
            if cl > MAX_BODY_BYTES:
                raise ValueError(f"Body too large: {cl} > {MAX_BODY_BYTES}")
            if cl == 0:
                return b""
        else:
            cl = MAX_BODY_BYTES

        body = self.rfile.read(cl)
        if len(body) > MAX_BODY_BYTES:
            raise ValueError(f"Body too large: {len(body)} > {MAX_BODY_BYTES}")
        return body

    def _get_headers(self) -> dict[str, str]:
        """Extract headers as a dict."""
        return {k: v for k, v in self.headers.items()}

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
            self._send_json(413, {"status": "error", "message": str(e)})
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

        # Route: /incidents/<id>/release
        if self.path.startswith("/incidents/") and self.path.endswith("/release"):
            parts = self.path.split("/")
            if len(parts) >= 3:
                try:
                    incident_id = int(parts[2])
                except ValueError:
                    self._send_json(400, {"status": "error", "message": "Invalid incident ID"})
                    return
                self._handle_release(incident_id, body, headers, webhook_secret, store, revoker)
                return

        self._send_json(404, {"status": "error", "message": "Not found"})

    def _handle_alerts(
        self,
        body: bytes,
        headers: dict[str, str],
        secret: str,
        store: IncidentStore,
        revoker: Any,
    ) -> None:
        """Handle POST /alerts — verify, parse, claim, quarantine."""
        # Verify webhook signature
        timestamp = headers.get("X-Sentinel-Timestamp", "")
        signature = headers.get("X-Sentinel-Signature", "")

        try:
            if not verify_webhook(timestamp, signature, body, secret):
                self._send_json(401, {"status": "error", "message": "Invalid or expired signature"})
                return
        except ValueError as e:
            self._send_json(401, {"status": "error", "message": str(e)})
            return

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
            self._send_json(
                200,
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
        # Verify webhook signature (empty body is fine for release)
        timestamp = headers.get("X-Sentinel-Timestamp", "")
        signature = headers.get("X-Sentinel-Signature", "")

        try:
            if not verify_webhook(timestamp, signature, body, secret):
                self._send_json(401, {"status": "error", "message": "Invalid or expired signature"})
                return
        except ValueError as e:
            self._send_json(401, {"status": "error", "message": str(e)})
            return

        # Get incident
        incident = store.get(incident_id)
        if incident is None:
            self._send_json(404, {"status": "error", "message": "Incident not found"})
            return

        # Only release if quarantined
        if incident.store_status != "quarantined":
            self._send_json(
                400,
                {
                    "status": "error",
                    "message": f"Incident {incident_id} is not quarantined (status: {incident.store_status})",
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
            # Update store
            store.release(incident_id)
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
            self._send_json(
                200,
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
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry-run mode: log actions without revoking credentials (default: True)",
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

    # Configure server
    server = ThreadingHTTPServer(("0.0.0.0", args.port), SentinelRequestHandler)
    server.store = store
    server.revoker = revoker
    server.webhook_secret = args.webhook_secret
    server.dry_run = args.dry_run

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    log.info("Sentinel listening on port %d (dry_run=%s)", args.port, args.dry_run)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down...")
        server.shutdown()
        server.server_close()
        store.close()
