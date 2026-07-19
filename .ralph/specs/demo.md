# Demo Spec — Deterministic Runaway Agent

## Purpose
Provide a repeatable demonstration that shows:
1. Normal agent operation (5 successful tool calls)
2. Runaway behavior (10+ identical failing tool calls)
3. Detection → Alert → Quarantine → Recovery

## Components

### runaway_agent.py
**Purpose:** Simulate an agent that eventually enters a runaway loop.

**Behavior:**
```python
import time
import random
from some_mcp_client import MCPClient  # Placeholder - use actual MCP client

# Phase 1: Normal operation (5 calls)
for i in range(5):
    result = client.call_tool("safe_tool", {"param": i})
    print(f"Normal call {i}: {result}")
    time.sleep(0.5)

# Phase 2: Runaway loop (10+ calls with same args)
for i in range(15):
    # Same tool, same arguments every time
    result = client.call_tool("failing_tool", {"param": "stuck"})
    print(f"Runaway call {i}: {result}")
    time.sleep(0.3)  # Fast loop
```

**MCP Client:** Use the official `mcp` CLI or a Python MCP client library.

**Tool Definitions:**
- `safe_tool`: Always succeeds, returns `{"status": "ok"}`
- `failing_tool`: Always fails after 3 calls with same args, returns `{"error": "rate limited"}`

### send_signed_alert.py
**Purpose:** Helper script to send test alerts to Sentinel (for development).

**Usage:**
```bash
python demo/send_signed_alert.py \
  --url http://localhost:8090/alerts \
  --secret my-secret \
  --alertname RunawayToolLoop \
  --agent-id agent-123 \
  --credential-id cred-abc
```

**Implementation:**
- Builds alert JSON payload
- Computes HMAC-SHA256 signature
- Sends POST request with headers
- Prints response

## Policy Definition (runaway-tool-loop.yaml)

**Purpose:** Define when to quarantine based on telemetry patterns.

**Format:**
```yaml
# policies/runaway-tool-loop.yaml
name: runaway-tool-loop
description: Quarantine agents that repeat the same tool call too many times
enabled: true

# Detection criteria
conditions:
  - type: repeated_tool_call
    tool_name: any  # or specific tool name
    threshold: 8    # Minimum repetitions
    window_seconds: 60  # Time window
    
  - type: token_budget_exceeded
    budget_tokens: 10000  # Optional: also quarantine on token spend
    
# Action to take
actions:
  - type: quarantine
    dry_run: true  # Override via SENTINEL_DRY_RUN
    
# Notification
notification:
  slack_webhook: null  # Optional: not required for hackathon
```

**Note:** For hackathon MVP, hardcode the policy logic in the control loop. The YAML file is for future extensibility and documentation.

## Deterministic Incident

**Requirements:**
1. Same agent ID always produces same idempotency key for same alert
2. Alert fingerprint (if provided by SigNoz) is used for idempotency
3. Canonicalized tool call arguments (sorted keys, consistent serialization)

**Canonicalization:**
```python
import json

def canonicalize_args(args: dict) -> str:
    """Create a stable hash of tool arguments."""
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
```

## Demo Script (demo.sh)

**Purpose:** One-command demo for judges.

**Usage:**
```bash
bash demo.sh
```

**Contents:**
```bash
#!/bin/bash
set -e

echo "=== Starting Sentinel Demo ==="

# Start Sentinel in background
python -m sentinel --port 8090 --dry-run &
SENTINEL_PID=$!
sleep 2

# Start SigNoz (if not already running)
# ... (assume Foundry deployment is already up)

# Run the runaway agent
echo "=== Phase 1: Normal operation ==="
python demo/runaway_agent.py

# Wait for alert to fire
echo "=== Waiting for alert... ==="
sleep 10

# Check Sentinel logs
echo "=== Sentinel Actions ==="
curl -s http://localhost:8090/incidents | python -m json.tool

# Release the agent
echo "=== Releasing agent ==="
INCIDENT_ID=$(curl -s http://localhost:8090/incidents | python -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
curl -X POST http://localhost:8090/incidents/$INCIDENT_ID/release \
  -H "X-Sentinel-Timestamp: $(date +%s)" \
  -H "X-Sentinel-Signature: $(echo -n "$(date +%s)." | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)"

# Cleanup
kill $SENTINEL_PID

echo "=== Demo Complete ==="
```

## Files
- `demo/runaway_agent.py` — Runaway agent simulator
- `demo/send_signed_alert.py` — Test alert sender
- `policies/runaway-tool-loop.yaml` — Policy definition
- `demo.sh` — One-command demo script

## Test Coverage Target
- Normal calls don't trigger quarantine
- Runaway calls trigger exactly one quarantine
- Duplicate alerts are ignored
- Release restores normal operation
