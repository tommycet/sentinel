#!/usr/bin/env python3
"""Patch the Foundry-generated Docker Compose to add Sentinel service.

Usage:
    python3 scripts/patch-compose.py                    # patches pours/deployment/compose.yaml
    python3 scripts/patch-compose.py --path <path>      # patches custom path

The Sentinel service is added as a new top-level service under the signoz-network,
with SENTINEL_OTEL_ENDPOINT pointing at the signoz-ingester alias.
"""
import json
import os
import sys
from pathlib import Path


DEFAULT_PATH = "pours/deployment/compose.yaml"

SENTINEL_SERVICE = {
    "container_name": "signoz-sentinel",
    "build": {
        "dockerfile": "deploy/sentinel.Dockerfile",
        "context": ".",
    },
    "networks": {
        "signoz-network": {
            "aliases": ["signoz-sentinel"],
        },
    },
    "ports": ["8090:8090"],
    "environment": [
        "SENTINEL_PORT=8090",
        "SENTINEL_DB_PATH=/data/sentinel.db",
        "SENTINEL_OTEL_ENDPOINT=http://signoz-ingester:4317",
        "SENTINEL_WEBHOOK_SECRET=${SENTINEL_WEBHOOK_SECRET:-dev-secret-change-me}",
        "SENTINEL_REVOKE_URL=${SENTINEL_REVOKE_URL:-}",
        "SENTINEL_REVOKE_TOKEN=${SENTINEL_REVOKE_TOKEN:-}",
        "PYTHONUNBUFFERED=1",
    ],
    "volumes": ["sentinel-data:/data"],
    "restart": "unless-stopped",
}


def patch_compose(path: str) -> None:
    """Read compose YAML, inject Sentinel service and data volume."""
    p = Path(path)
    if not p.exists():
        print(f"[patch] {path} not found — creating fresh compose stub")
        os.makedirs(p.parent, exist_ok=True)
        p.write_text("services: {}\nnetworks:\n  signoz-network:\n    name: signoz-network\n")

    raw = p.read_text()
    lines = raw.splitlines()

    # -- inject sentinel-data volume --
    vol_marker = "volumes:"
    vol_insert = '  sentinel-data:\n    name: sentinel-data'
    if vol_marker not in raw:
        lines.append("")
        lines.append(vol_marker)
        lines.append(vol_insert)
    elif "sentinel-data" not in raw:
        for i, line in enumerate(lines):
            if line.strip() == vol_marker:
                lines.insert(i + 1, vol_insert)
                break

    # -- inject sentinel service after last existing service --
    svc_marker = "services:"
    sentinel_block = f"\n  sentinel:\n"
    for key, val in sorted(SENTINEL_SERVICE.items()):
        if isinstance(val, dict):
            sentinel_block += f"    {key}:\n"
            for k2, v2 in val.items():
                if isinstance(v2, list):
                    sentinel_block += f"      {k2}:\n"
                    for item in v2:
                        sentinel_block += f"      - {json.dumps(item)}\n"
                elif isinstance(v2, dict):
                    sentinel_block += f"      {k2}:\n"
                    for k3, v3 in v2.items():
                        sentinel_block += f"        {k3}: {v3}\n"
        elif isinstance(val, list):
            sentinel_block += f"    {key}:\n"
            for item in val:
                sentinel_block += f"    - {json.dumps(item)}\n"
        elif isinstance(val, str):
            sentinel_block += f"    {key}: {val}\n"
        else:
            sentinel_block += f"    {key}: {val}\n"

    # Insert before the first non-service top-level key after services block
    inserted = False
    if "sentinel:" not in raw:
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == svc_marker:
                # find the blank line or next top-level key after services
                for j in range(i + 1, len(lines)):
                    if lines[j].strip() == "" or (not lines[j].startswith("  ") and lines[j].strip()):
                        lines.insert(j, sentinel_block.rstrip("\n"))
                        inserted = True
                        break
                break

    result = "\n".join(lines)
    p.write_text(result)
    print(f"[patch] Sentinel service patched into {path}")


def main() -> None:
    path = DEFAULT_PATH
    if len(sys.argv) > 1 and sys.argv[1] != "--path":
        path = sys.argv[1]
    elif "--path" in sys.argv:
        idx = sys.argv.index("--path")
        if idx + 1 < len(sys.argv):
            path = sys.argv[idx + 1]
    patch_compose(path)


if __name__ == "__main__":
    main()
