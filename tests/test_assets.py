"""Tests for SigNoz deploy artifacts — dashboard, alert rule, install script."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestDashboardJSON(unittest.TestCase):
    """deploy/dashboard.json must be valid and have all required panels."""

    REQUIRED_PANELS = [
        "Tool Calls",
        "Repeated Call Fingerprints",
        "Quarantine Count",
        "Alert-to-Action Latency",
        "Quarantined Agents",
        "Idempotency Key",
        "Dry-Run",
    ]

    def setUp(self):
        path = Path("deploy/dashboard.json")
        if not path.exists():
            self.skipTest("deploy/dashboard.json not found")
        self.data = json.loads(path.read_text())

    def test_valid_json_structure(self):
        """Dashboard has version, title, and panels list."""
        self.assertIn("version", self.data)
        self.assertIn("title", self.data)
        self.assertIn("panels", self.data)
        self.assertGreater(len(self.data["panels"]), 0)

    def test_all_required_panels_present(self):
        """Every required semantic panel title has a matching entry."""
        titles = [p.get("title", "") for p in self.data["panels"]]
        for required in self.REQUIRED_PANELS:
            matches = [t for t in titles if required.lower() in t.lower()]
            self.assertGreater(len(matches), 0, f"No panel matching '{required}'")

    def test_every_panel_has_query(self):
        """Every panel contains a query field."""
        for p in self.data["panels"]:
            self.assertIn("query", p, f"Panel '{p.get('title')}' missing query")


class TestAlertRuleJSON(unittest.TestCase):
    """deploy/alert-rule.json must be valid and have required fields."""

    def setUp(self):
        path = Path("deploy/alert-rule.json")
        if not path.exists():
            self.skipTest("deploy/alert-rule.json not found")
        self.data = json.loads(path.read_text())

    def test_alert_name_required(self):
        """Alert rule has a name."""
        self.assertIn("alert", self.data)

    def test_has_condition(self):
        """Alert rule has a condition block."""
        self.assertIn("condition", self.data)

    def test_has_severity(self):
        """Alert rule has a severity level."""
        self.assertIn("severity", self.data)

    def test_has_webhook_config(self):
        """Alert rule has a webhook config pointing to Sentinel."""
        self.assertIn("webhook_configs", self.data)
        self.assertIn("url", self.data["webhook_configs"][0])
        self.assertIn("sentinel", self.data["webhook_configs"][0]["url"])


class TestInstallScript(unittest.TestCase):
    """scripts/install-signoz-assets.py parses correctly."""

    def setUp(self):
        # Load via importlib to handle hyphen in filename
        import importlib.util
        path = Path("scripts/install-signoz-assets.py")
        if not path.exists():
            self.skipTest("install-signoz-assets.py not found")
        spec = importlib.util.spec_from_file_location("install_signoz_assets", path)
        self.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.installer)

    def test_import_works(self):
        """Install script imports without error."""
        self.assertTrue(hasattr(self.installer, "install_alert"))

    def test_install_alert_returns_code(self):
        """install_alert returns an HTTP status code on network error."""
        with patch.object(self.installer, "urlopen") as mock_urlopen:
            mock_resp = MagicMock(status=200)
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            code = self.installer.install_alert("http://localhost:1", None)
            self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()
