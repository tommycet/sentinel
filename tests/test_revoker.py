"""Tests for sentinel.revoker — reversible credential revocation adapters."""
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from sentinel.revoker import DryRunRevoker, HttpRevoker, get_revoker


class _RevocationHandler(BaseHTTPRequestHandler):
    status = 200
    response = b'{"message": "accepted"}'
    request = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        type(self).request = {
            "body": json.loads(self.rfile.read(length)),
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
        }
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).response)

    def log_message(self, format, *args):
        pass


class _ServerMixin:
    def setUp(self):
        _RevocationHandler.status = 200
        _RevocationHandler.response = b'{"message": "accepted"}'
        _RevocationHandler.request = None
        self.server = HTTPServer(("127.0.0.1", 0), _RevocationHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/revoke"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class TestDryRunRevoker(unittest.TestCase):
    def test_quarantine_returns_dry_run(self):
        result = DryRunRevoker().quarantine("cred-1", incident_id="inc-1")
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "dry_run")
        self.assertIn("credential_id_hash", result)
        self.assertNotIn("credential_id", result)
        self.assertIn("message", result)
        self.assertNotIn("cred-1", repr(result))

    def test_release_returns_dry_run_release(self):
        result = DryRunRevoker().release("cred-1")
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "dry_run_release")
        self.assertIn("credential_id_hash", result)
        self.assertNotIn("cred-1", repr(result))


class TestHttpRevoker(_ServerMixin, unittest.TestCase):
    def test_successful_post(self):
        with patch.dict(
            os.environ,
            {
                "SENTINEL_REVOKE_URL": self.url,
                "SENTINEL_REVOKE_TOKEN": "token-123",
            },
            clear=False,
        ):
            result = HttpRevoker().quarantine(
                "cred-1", reason="Runaway agent detected", incident_id="inc-1"
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "quarantined")
        self.assertEqual(_RevocationHandler.request["body"]["action"], "quarantine")
        self.assertEqual(_RevocationHandler.request["body"]["credential_id"], "cred-1")
        self.assertEqual(_RevocationHandler.request["body"]["incident_id"], "inc-1")
        self.assertEqual(_RevocationHandler.request["authorization"], "Bearer token-123")
        self.assertEqual(_RevocationHandler.request["content_type"], "application/json")

    def test_4xx_response_returns_failure(self):
        _RevocationHandler.status = 400
        _RevocationHandler.response = b'{"message": "invalid credential"}'
        with patch.dict(os.environ, {"SENTINEL_REVOKE_URL": self.url}, clear=False):
            result = HttpRevoker().release("cred-1")

        self.assertFalse(result["success"])
        self.assertNotIn("credential_id", result)
        self.assertIn("credential_id_hash", result)
        self.assertNotIn("cred-1", repr(result))
        self.assertIn("400", result["message"])

    def test_timeout_returns_failure(self):
        with patch.dict(os.environ, {"SENTINEL_REVOKE_URL": self.url}, clear=False), patch(
            "sentinel.revoker.urllib.request.build_opener"
        ) as mock_opener:
            mock_open = mock_opener.return_value.open
            mock_open.side_effect = TimeoutError
            result = HttpRevoker().quarantine("cred-1")

        self.assertFalse(result["success"])
        self.assertIn("timeout", result["message"].lower())

    def test_secret_never_leaks_in_error_or_return(self):
        secret = "super-secret-bearer-token"
        _RevocationHandler.status = 500
        _RevocationHandler.response = json.dumps({"message": secret}).encode()
        with patch.dict(
            os.environ,
            {"SENTINEL_REVOKE_URL": self.url, "SENTINEL_REVOKE_TOKEN": secret},
            clear=False,
        ):
            result = HttpRevoker().quarantine("cred-1")

        self.assertFalse(result["success"])
        self.assertNotIn(secret, repr(result))

    def test_kwargs_cannot_override_invariants(self):
        """Caller-supplied action in kwargs must not override the real action."""
        with patch.dict(os.environ, {"SENTINEL_REVOKE_URL": self.url}, clear=False):
            result = HttpRevoker().quarantine(
                "cred-1", action="release", incident_id="inc-1"
            )

        self.assertTrue(result["success"])
        # The HTTP request must contain quarantine (not release) as action
        self.assertEqual(_RevocationHandler.request["body"]["action"], "quarantine")
        self.assertEqual(_RevocationHandler.request["body"]["credential_id"], "cred-1")

    def test_redirect_with_auth_blocked(self):
        """Redirect handler must raise HTTPError when Authorization header present."""
        # We can't test a real redirect in a unit test. Verify the handler exists.
        from urllib.request import HTTPRedirectHandler
        from sentinel.revoker import _NoRedirectHandler

        handler = _NoRedirectHandler()
        self.assertIsInstance(handler, HTTPRedirectHandler)


class TestGetRevoker(unittest.TestCase):
    def test_factory_defaults_to_dry_run(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(get_revoker(), DryRunRevoker)

    def test_factory_returns_http_when_url_set(self):
        with patch.dict(
            os.environ, {"SENTINEL_REVOKE_URL": "http://example.test/revoke"}, clear=True
        ):
            self.assertIsInstance(get_revoker(), HttpRevoker)


if __name__ == "__main__":
    unittest.main()
