#!/usr/bin/env python3
"""Install SigNoz dashboard and alert rule from JSON artifacts.

Reads deploy/dashboard.json and deploy/alert-rule.json, then POSTs them
to the running SigNoz instance via its API. Uses stdlib urllib only.

Usage:
    python3 scripts/install-signoz-assets.py [--url URL] [--api-key KEY]

Defaults:
    --url  http://localhost:8080  (SigNoz frontend)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def load_json(path: str) -> dict:
    """Read and parse a JSON file from deploy/. Returns dict."""
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] {path} not found")
        sys.exit(1)
    return json.loads(p.read_text())


def install_alert(base_url: str, api_key: str | None) -> int:
    """POST alert-rule.json to SigNoz alert API. Returns status code."""
    rule = load_json("deploy/alert-rule.json")
    url = f"{base_url}/api/v1/rules"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(rule).encode()
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=10) as resp:
            print(f"[OK] Alert rule installed: {resp.status}")
            return resp.status
    except HTTPError as e:
        print(f"[WARN] Alert install returned {e.code}: {e.read().decode(errors='replace')[:200]}")
        return e.code


def install_dashboard(base_url: str, api_key: str | None) -> int:
    """POST dashboard.json to SigNoz dashboard API. Returns status code."""
    dash = load_json("deploy/dashboard.json")
    url = f"{base_url}/api/v1/dashboards"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = json.dumps(dash).encode()
    req = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=10) as resp:
            print(f"[OK] Dashboard installed: {resp.status}")
            return resp.status
    except HTTPError as e:
        print(f"[WARN] Dashboard install returned {e.code}: {e.read().decode(errors='replace')[:200]}")
        return e.code


def main() -> None:
    base_url = os.environ.get("SIGNOZ_URL", "http://localhost:8080")
    api_key = os.environ.get("SIGNOZ_API_KEY", None)

    # Allow CLI overrides
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--url" and i + 2 < len(sys.argv):
            base_url = sys.argv[i + 2]
        elif arg == "--api-key" and i + 2 < len(sys.argv):
            api_key = sys.argv[i + 2]

    print(f"[info] Installing assets to {base_url}")
    install_alert(base_url, api_key)
    install_dashboard(base_url, api_key)
    print("[done] Asset installation complete")


if __name__ == "__main__":
    main()
