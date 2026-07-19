"""Tests for SigNoz deploy artifacts — dashboard, alert rule, install script.

Uses SigNoz v5 format conventions (widgets[] not panels[],
TRACES_BASED_ALERT not Prometheus alert format).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestDashboardJSON(unittest.TestCase):
    """deploy/dashboard.json must be valid SigNoz v5 format."""

    REQUIRED_WIDGETS = [
        "Alerts Received",
        "Quarantines",
        "Releases",
        "Quarantine Events",
    ]

    def setUp(self):
        path = Path("deploy/dashboard.json")
        if not path.exists():
            self.skipTest("deploy/dashboard.json not found")
        self.data = json.loads(path.read_text())

    def test_valid_json_structure(self):
        """Dashboard has version, title, widgets list, and layout."""
        self.assertIn("version", self.data)
        self.assertEqual(self.data["version"], "v5")
        self.assertIn("title", self.data)
        self.assertIn("widgets", self.data)
        self.assertGreater(len(self.data["widgets"]), 0)
        self.assertIn("layout", self.data)
        self.assertEqual(len(self.data["layout"]), len(self.data["widgets"]))

    def test_all_required_widgets_present(self):
        """Every required semantic widget title has a matching entry."""
        titles = [w.get("title", "") for w in self.data["widgets"]]
        for required in self.REQUIRED_WIDGETS:
            matches = [t for t in titles if required.lower() in t.lower()]
            self.assertGreater(len(matches), 0, f"No widget matching '{required}'")

    def test_every_widget_has_query(self):
        """Every widget contains a query block."""
        for w in self.data["widgets"]:
            self.assertIn("query", w, f"Widget '{w.get('title')}' missing query")

    def test_every_widget_has_panel_types(self):
        """Every widget declares panelTypes."""
        for w in self.data["widgets"]:
            self.assertIn("panelTypes", w, f"Widget '{w.get('title')}' missing panelTypes")

    def test_layout_ids_match_widget_ids(self):
        """Layout i fields must match widget id fields."""
        widget_ids = {w["id"] for w in self.data["widgets"]}
        layout_ids = {item["i"] for item in self.data["layout"]}
        self.assertEqual(widget_ids, layout_ids,
                         f"Layout ids {layout_ids} don't match widget ids {widget_ids}")

    def test_all_clickhouse_queries(self):
        """All widget queries use clickhouse_sql for portability."""
        for w in self.data["widgets"]:
            q = w.get("query", {})
            self.assertEqual(q.get("queryType"), "clickhouse_sql",
                             f"Widget '{w.get('title')}' doesn't use clickhouse_sql")


class TestAlertRuleJSON(unittest.TestCase):
    """deploy/alert-rule.json must be valid SigNoz v5 TRACES_BASED_ALERT format."""

    def setUp(self):
        path = Path("deploy/alert-rule.json")
        if not path.exists():
            self.skipTest("deploy/alert-rule.json not found")
        self.data = json.loads(path.read_text())

    def test_alert_name_required(self):
        """Alert rule has a name."""
        self.assertIn("alert", self.data)

    def test_has_alert_type(self):
        """Alert rule must declare alertType (SigNoz v5)."""
        self.assertIn("alertType", self.data)
        self.assertEqual(self.data["alertType"], "TRACES_BASED_ALERT")

    def test_has_condition(self):
        """Alert rule has a condition block."""
        self.assertIn("condition", self.data)
        cond = self.data["condition"]
        self.assertIn("compositeQuery", cond)
        self.assertIn("evalWindow", cond)
        self.assertIn("op", cond)

    def test_has_clickhouse_query(self):
        """Alert condition uses clickhouse_sql."""
        queries = self.data["condition"]["compositeQuery"]["queries"]
        self.assertGreater(len(queries), 0)
        for q in queries:
            self.assertEqual(q.get("type"), "clickhouse_sql")

    def test_without_prometheus_fields(self):
        """SigNoz v5 alerts don't use Prometheus-format severity or webhook_configs."""
        self.assertNotIn("severity", self.data)
        self.assertNotIn("webhook_configs", self.data)

    def test_annotations_present(self):
        """Alert rule has human-readable annotations."""
        self.assertIn("annotations", self.data)
        self.assertIn("summary", self.data["annotations"])
        self.assertIn("description", self.data["annotations"])


class TestInstallScript(unittest.TestCase):
    """scripts/install-signoz-assets.py parses correctly."""

    def setUp(self):
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
