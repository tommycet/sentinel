"""Tests for sentinel.telemetry — OTLP/HTTP span export."""
from __future__ import annotations

import json
import time
import unittest
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from unittest.mock import patch, MagicMock
import urllib.error

from sentinel.telemetry import export_span


class TestExportSpan(unittest.TestCase):
    """OTLP/HTTP span export via export_span()."""

    def test_valid_span_returns_true(self):
        """Successful export posts JSON to /v1/traces and returns True."""
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                received["content_type"] = self.headers["Content-Type"]
                received["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.handle_request)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_port}"
            with patch.dict("os.environ", {"SENTINEL_OTEL_ENDPOINT": endpoint}):
                result = export_span(
                    name="sentinel.alert.received",
                    attributes={"agent.id": "agent-1", "sentinel.alert.name": "Test"},
                    start_time=time.time() - 1.0,
                )
        finally:
            thread.join(timeout=1)
            server.server_close()

        self.assertTrue(result)
        self.assertEqual(received["path"], "/v1/traces")
        self.assertEqual(received["content_type"], "application/json")
        self.assertEqual(
            json.loads(received["body"])["resourceSpans"][0]["scopeSpans"][0]
            ["spans"][0]["name"],
            "sentinel.alert.received",
        )

    def test_export_payload_structure(self):
        """Payload matches OTLP/HTTP resourceSpans structure."""
        captured = {}
        original_send = None

        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            start = 1700000000.0
            end = start + 1.5
            export_span(
                name="sentinel.alert.received",
                attributes={"agent.id": "agent-123"},
                start_time=start,
                end_time=end,
            )

        data = captured["data"]
        # resourceSpans wrapper
        self.assertIn("resourceSpans", data)
        rs = data["resourceSpans"][0]

        # resource attributes: service.name + service.version
        resource_attrs = {a["key"]: a["value"] for a in rs["resource"]["attributes"]}
        self.assertEqual(resource_attrs["service.name"]["stringValue"], "sentinel")
        self.assertEqual(resource_attrs["service.version"]["stringValue"], "0.1.0")

        # scopeSpans → spans
        span = rs["scopeSpans"][0]["spans"][0]
        self.assertEqual(span["name"], "sentinel.alert.received")
        self.assertEqual(len(span["traceId"]), 32)  # 128-bit hex
        self.assertEqual(len(span["spanId"]), 16)   # 64-bit hex
        self.assertEqual(span["parentSpanId"], "")
        # Times in nanoseconds
        self.assertEqual(span["startTimeUnixNano"], int(start * 1e9))
        self.assertEqual(span["endTimeUnixNano"], int(end * 1e9))
        self.assertEqual(span["status"]["code"], 1)  # OK

    def test_attribute_string_value(self):
        """String attributes become stringValue."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span("test.span", {"key": "str_val"}, start_time=0.0)

        attrs = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
        attr = next(a for a in attrs if a["key"] == "key")
        self.assertEqual(attr["value"], {"stringValue": "str_val"})

    def test_attribute_int_value(self):
        """Int attributes become intValue."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span("test.span", {"count": 42}, start_time=0.0)

        attrs = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
        attr = next(a for a in attrs if a["key"] == "count")
        self.assertEqual(attr["value"], {"intValue": 42})

    def test_attribute_float_value(self):
        """Float attributes become doubleValue."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span("test.span", {"latency_ms": 123.5}, start_time=0.0)

        attrs = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
        attr = next(a for a in attrs if a["key"] == "latency_ms")
        self.assertEqual(attr["value"], {"doubleValue": 123.5})

    def test_attribute_bool_value(self):
        """Bool attributes become boolValue."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span("test.span", {"dry_run": True}, start_time=0.0)

        attrs = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
        attr = next(a for a in attrs if a["key"] == "dry_run")
        self.assertEqual(attr["value"], {"boolValue": True})

    def test_attribute_none_omitted(self):
        """None-valued attributes are omitted from payload."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span("test.span", {"present": "yes", "missing": None}, start_time=0.0)

        attrs = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
        keys = [a["key"] for a in attrs]
        self.assertIn("present", keys)
        self.assertNotIn("missing", keys)

    def test_end_time_defaults_to_now(self):
        """When end_time is None, it defaults to current time."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        fixed_now = 1700000005.0
        with patch("sentinel.telemetry._send", side_effect=capture_send):
            with patch("sentinel.telemetry.time.time", return_value=fixed_now):
                export_span("test.span", {}, start_time=1700000000.0)

        span = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        self.assertEqual(span["endTimeUnixNano"], int(fixed_now * 1e9))

    def test_status_code_error(self):
        """status_code=2 produces ERROR status in payload."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span("test.span", {}, start_time=0.0, status_code=2)

        span = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        self.assertEqual(span["status"]["code"], 2)

    def test_credential_id_hashed(self):
        """credential.id attribute is SHA-256 hashed, never raw."""
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span(
                "test.span",
                {"credential.id": "raw-credential-secret"},
                start_time=0.0,
            )

        attrs = captured["data"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
        hash_attr = next(a for a in attrs if a["key"] == "credential.id_hash")
        # Must be hex digest, not the raw value
        import hashlib
        expected = hashlib.sha256("raw-credential-secret".encode()).hexdigest()
        self.assertEqual(hash_attr["value"]["stringValue"], expected)
        self.assertNotIn("raw-credential-secret", json.dumps(attrs))

    def test_network_error_returns_false(self):
        """Network failure returns False, never raises."""
        with patch("sentinel.telemetry._send", side_effect=OSError("connection refused")):
            result = export_span("test.span", {"k": "v"}, start_time=0.0)
        self.assertFalse(result)

    def test_http_error_returns_false(self):
        """HTTP error returns False, never raises."""
        with patch("sentinel.telemetry._send", side_effect=urllib.error.HTTPError(
            "http://localhost:4317", 500, "Internal Server Error", {}, None
        )):
            result = export_span("test.span", {"k": "v"}, start_time=0.0)
        self.assertFalse(result)

    def test_json_error_returns_false(self):
        """JSON serialization error returns False, never raises."""
        with patch("sentinel.telemetry._build_payload", side_effect=TypeError("not serializable")):
            result = export_span("test.span", {"k": "v"}, start_time=0.0)
        self.assertFalse(result)

    def test_export_never_raises(self):
        """export_span must never raise, even on unexpected errors."""
        with patch("sentinel.telemetry._send", side_effect=RuntimeError("boom")):
            result = export_span("test.span", {}, start_time=0.0)
        self.assertFalse(result)

    def test_credential_id_not_leaked(self):
        """Raw credential ID never appears anywhere in the serialized payload."""
        raw_id = "super-secret-cred-12345"
        captured = {}
        def capture_send(payload):
            captured["data"] = json.loads(payload)
            return True

        with patch("sentinel.telemetry._send", side_effect=capture_send):
            export_span("test.span", {"credential.id": raw_id}, start_time=0.0)

        full_json = json.dumps(captured["data"])
        self.assertNotIn(raw_id, full_json)


if __name__ == "__main__":
    unittest.main()
